#!/usr/bin/env python3
"""
JARVIS — Autonomous Windows Desktop AI Agent
Production Entry Point. Wires Indexer, Memory, Orchestrator, and Voice I/O.
"""

import logging
import os
import signal
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

# ── Windows console encoding fix ─────────────────────────────────────────────
# The default Windows console (PowerShell / cmd) uses CP1252, which cannot
# encode Unicode characters like →, ─, ⚠ that appear in log messages.
# Reconfiguring stdout/stderr to UTF-8 (with 'replace' fallback so we never
# crash) fixes the recurring UnicodeEncodeError from background threads.
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # non-interactive / piped — ignore

import safety.audit_log as audit_log
import settings
from core.console import PromptAwareStreamHandler
from core.orchestrator import Orchestrator
from indexer import pc_indexer
from memory import memory_manager
from settings import LOG_FILE, LOG_LEVEL, LOGS_DIR

LOGS_DIR.mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)

_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_console_handler = PromptAwareStreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter(_fmt))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=_fmt,
    handlers=[
        # encoding='utf-8' is essential on Windows — the default locale
        # encoding (CP1252) cannot represent Unicode chars like →, ⚠,
        # that appear in LLM-generated log messages (reflection insights, etc.).
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        _console_handler,
    ],
)

# Silence chatty third-party libraries that spam INFO logs on every startup.
# These produce 30+ lines of noise from HuggingFace model cache checks.
for _noisy in (
    "httpx",
    "httpcore",
    "huggingface_hub",
    "huggingface_hub.utils._headers",
    "sentence_transformers",
    "sentence_transformers.base.model",
    "transformers",
    "chromadb",
    "chromadb.telemetry",
    "chromadb.segment",
    "urllib3",
    "filelock",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Suppress the "unauthenticated requests" HF warning that fires on every
# cold-start download until the user sets HF_TOKEN in .env.
# (Set HF_TOKEN in .env to get higher rate limits; the warning is then gone.)
logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)

import warnings as _warnings

_warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")

# ── tqdm 4.67.x bug-fix ──────────────────────────────────────────────────────
# tqdm_asyncio.__del__ → close() accesses self.last_print_t which is never
# assigned when __init__ aborts partway through (e.g. during async teardown).
# Patching close() with a hasattr guard silences the spurious AttributeError.
try:
    from tqdm.std import tqdm as _std_tqdm

    _orig_tqdm_close = _std_tqdm.close

    def _safe_tqdm_close(self):
        if not hasattr(self, "last_print_t"):
            return
        _orig_tqdm_close(self)

    _std_tqdm.close = _safe_tqdm_close
    del _std_tqdm
except Exception:
    pass  # logger not yet defined at this point in module init
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("jarvis")


def handle_exit(signum, frame):
    logger.info("Shutting down JARVIS...")
    pc_indexer.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def main():
    logger.info("JARVIS Starting...")

    # ── First-run setup ──────────────────────────────────────────────────
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        example_path = Path(__file__).parent / ".env.example"
        if example_path.exists():
            print("\n📋 First run detected — creating .env from .env.example ...")
            import shutil
            shutil.copy(example_path, env_path)
            print("    Created .env — please edit it with your settings.")
        else:
            print("\n❌ ERROR: .env file not found!")
            print("    Please copy .env.example to .env and configure it.")
            sys.exit(1)

    from settings import OLLAMA_API_KEY

    leaked_pattern = "b3ad7ee1e4614eee89cb85dcfe1451d1.4a-cPAqHQnD-OHBwj9qHbg8d"
    if not OLLAMA_API_KEY or OLLAMA_API_KEY == leaked_pattern:
        print("\n" + "=" * 60)
        print("  JARVIS — API Key Setup Required")
        print("=" * 60)
        if OLLAMA_API_KEY == leaked_pattern:
            print("  ⚠  You're using a leaked placeholder key.")
        else:
            print("  No OLLAMA_API_KEY configured.")
        print()
        print("  To get your API key:")
        print("    1. Go to https://ollama.com/settings/api-keys")
        print("    2. Create a new API key")
        print("    3. Add it to your .env file:")
        print("       OLLAMA_API_KEY=your_key_here")
        print()
        print("  For local-only mode (no cloud), set:")
        print("    OLLAMA_MODE=local")
        print("    OLLAMA_LOCAL_URL=http://localhost:11434/api/chat")
        print("=" * 60)
        print("  Continuing with limited functionality...\n")

    # ── Startup health check ───────────────────────────────────────────────
    from core.health_check import run_all as run_health_check

    run_health_check()

    audit_log.setup()
    pc_indexer.start()

    mem = memory_manager.MemoryManager(session_id=f"cli_{os.getpid()}")

    # Prune old episodic memory (>90 days) on startup so the DB stays lean.
    # This is fast when there's little old data and silent on failure.
    try:
        mem.prune_old_episodes(days=90)
    except Exception as _prune_exc:
        logger.debug(f"Episode prune skipped: {_prune_exc}")

    # Initialize long-term memory (RAG-based, cross-session) for
    # semantically relevant memory retrieval
    ltm = None
    try:
        from memory.long_term_memory import init_memory_manager
        ltm = init_memory_manager(persist_dir=str(settings.DATA_DIR / "long_term_memory"))
        logger.info("Long-term memory initialized with semantic search")
    except Exception as _ltm_exc:
        logger.warning(f"Long-term memory unavailable: {_ltm_exc}")

    orc = Orchestrator(memory=mem, long_term_memory=ltm)

    print("\n" + "=" * 50)
    print("JARVIS ONLINE. Type a command or 'quit' to exit.")
    print("=" * 50)

    # Wire Voice I/O if enabled
    output_cb = None
    if settings.VOICE_ENABLED:
        from perception.input_handler import InputHandler

        input_handler = InputHandler(orc)
        input_handler.start_listening()
        output_cb = input_handler._output
        # Ensure cleanup on exit
        import atexit

        atexit.register(input_handler.stop)

    orc.run_cli(output_callback=output_cb)

    logger.info("JARVIS Stopped.")


if __name__ == "__main__":
    main()
