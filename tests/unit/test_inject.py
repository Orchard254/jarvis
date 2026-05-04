# test_inject.py — Direct STT injection test harness for JARVIS
# Bypasses: wake word, microphone, STT, TTS
# Tests:    intent classification, tool validation, tool execution
#
# Usage:
#   python test_inject.py                        # interactive REPL
#   python test_inject.py "open notepad"         # single command
#   python test_inject.py --file commands.txt    # batch from file

import argparse
import os
import sys
import time

# Stub out hardware-dependent modules BEFORE any jarvis imports
import types

# ── Minimal stubs so we can import jarvis modules without hardware ────────────


# Stub: tts — replace speak/queue with console print
tts_stub = types.ModuleType("tts")
tts_stub.speak = lambda text: print(f"[TTS] {text}")
tts_stub.play_chime = lambda: None
tts_stub.play_think_chime = lambda: None


class _FakeTTSQueue:
    def start(self):
        pass

    def stop(self):
        pass

    def put(self, text):
        print(f"[TTS] {text}")

    def join(self):
        pass


tts_stub.TTSQueue = _FakeTTSQueue
sys.modules["tts"] = tts_stub

# Stub: stt
stt_stub = types.ModuleType("stt")
stt_stub.listen = lambda: input("[STT INPUT] > ")
sys.modules["stt"] = stt_stub

# Stub: wake_word
ww_stub = types.ModuleType("wake_word")
ww_stub.listen_for_wake_word = lambda: True
ww_stub.start_abort_listener = lambda: (None, None)
ww_stub.stop_abort_listener = lambda e, t: None
ww_stub.extend_cooldown = lambda s=4.0: None
ww_stub.reset_cooldown = lambda: None
sys.modules["wake_word"] = ww_stub

# Stub: ambient (if it exists)
ambient_stub = types.ModuleType("ambient")


class _FakeMonitor:
    def __init__(self, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def ping(self):
        pass


ambient_stub.AmbientMonitor = _FakeMonitor
sys.modules["ambient"] = ambient_stub

# ── Now safe to import jarvis internals ───────────────────────────────────────
try:
    # Add parent directory to path for imports
    from pathlib import Path
    import sys
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / 'jarvis'))
    
    from jarvis.config.config import get_config as config
    from jarvis.profile.user_profile import get_current_profile as user_profile
    from jarvis.core.brain import Brain
    from jarvis.config.prompts.jarvis_prompt import get_system_prompt as build_jarvis_prompt
    from jarvis.tools.registry import ToolRegistry
except ImportError as e:
    print(f"[ERROR] Could not import JARVIS modules: {e}")
    print("Make sure you're running this from the project directory.")
    sys.exit(1)

# ── Helpers ───────────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"


def _print_banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════╗
║   JARVIS  —  STT Injection Tester   ║
╚══════════════════════════════════════╝{RESET}
{DIM}Wake word / mic / TTS are all stubbed out.
Type your command and press Enter.
Commands: 'quit', 'history', 'clear', 'mode'{RESET}
""")


def _print_result(text: str, label="JARVIS"):
    print(f"\n{GREEN}{BOLD}[{label}]{RESET} {text}\n")


def _print_info(text: str):
    print(f"{YELLOW}[INFO]{RESET} {text}")


def _print_error(text: str):
    print(f"{RED}[ERROR]{RESET} {text}")


def _print_history(history: list):
    if not history:
        print(f"{DIM}  (no history yet){RESET}")
        return
    for msg in history:
        role = msg.get("role", "?")
        content = str(msg.get("content", ""))[:120]
        color = CYAN if role == "user" else GREEN
        print(f"  {color}{role:<12}{RESET} {content}")


# ── Core test runner ──────────────────────────────────────────────────────────


class JARVISTester:
    def __init__(self):
        self.history = []
        self.system_prompt = _make_system_prompt()
        self.tools = get_tools()
        self._speaker_log = []  # Captures spoken output

    class _MockSpeaker:
        """Captures TTS output instead of playing audio."""

        def __init__(self, log_list):
            self._log = log_list

        def say(self, text):
            if text and text.strip():
                print(f"{GREEN}[TTS]{RESET} {text}")
                self._log.append(text)

        def wait(self):
            pass

        def stop(self):
            pass

    def run_command(self, user_text: str) -> dict:
        """
        Inject a text command and return result dict:
            {
                "input": str,
                "needs_tools": bool,
                "final_text": str,
                "spoken": list[str],
                "elapsed_ms": int,
            }
        """
        user_text = user_text.strip()
        if not user_text:
            return {}

        needs_tools = _likely_needs_tools(user_text)
        speaker = self._MockSpeaker(self._speaker_log)
        self._speaker_log.clear()

        t0 = time.time()

        if needs_tools:
            _print_info(f'Mode: AGENTIC  |  Input: "{user_text}"')
            final_text, self.history = _run_agentic_loop(
                user_text=user_text,
                history=self.history,
                tools=self.tools,
                system=self.system_prompt,
                speaker=speaker,
                abort_event=None,
            )
        else:
            _print_info(f'Mode: CHAT  |  Input: "{user_text}"')
            self.history.append({"role": "user", "content": user_text})
            full_reply = ""
            for sentence in stream_reply(self.history, self.system_prompt):
                speaker.say(sentence)
                full_reply += sentence + " "
            full_reply = full_reply.strip()
            final_text = full_reply
            if full_reply:
                self.history.append({"role": "assistant", "content": full_reply})

        self.history = _trim_history(self.history)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "input": user_text,
            "needs_tools": needs_tools,
            "final_text": final_text or "",
            "spoken": list(self._speaker_log),
            "elapsed_ms": elapsed_ms,
        }


# ── Run modes ─────────────────────────────────────────────────────────────────


def run_interactive(tester: JARVISTester):
    """Interactive REPL loop."""
    _print_banner()

    while True:
        try:
            user_input = input(f"{CYAN}You >{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue

        # Meta commands
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break
        elif user_input.lower() == "history":
            print(f"\n{BOLD}Conversation history:{RESET}")
            _print_history(tester.history)
            print()
            continue
        elif user_input.lower() == "clear":
            tester.history = []
            _print_info("History cleared.")
            continue
        elif user_input.lower() == "mode":
            preview = _likely_needs_tools(input(f"  Test string for mode detection: ").strip())
            _print_info(f"Would use {'AGENTIC' if preview else 'CHAT'} mode.")
            continue

        result = tester.run_command(user_input)
        if result.get("final_text"):
            _print_result(result["final_text"])
        _print_info(f"Done in {result['elapsed_ms']}ms")


def run_single(tester: JARVISTester, command: str):
    """Run one command and print result."""
    print(f"\n{BOLD}Running:{RESET} {command}\n")
    result = tester.run_command(command)
    if result.get("final_text"):
        _print_result(result["final_text"])
    _print_info(
        f"Done in {result['elapsed_ms']}ms  |  mode={'agentic' if result['needs_tools'] else 'chat'}"
    )


def run_batch(tester: JARVISTester, filepath: str):
    """Run commands from a file (one per line, # = comment)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        _print_error(f"File not found: {filepath}")
        sys.exit(1)

    print(f"\n{BOLD}Batch mode:{RESET} {len(lines)} commands from {filepath}\n")
    for i, cmd in enumerate(lines, 1):
        print(f"{DIM}─── [{i}/{len(lines)}] ───────────────────────────{RESET}")
        result = tester.run_command(cmd)
        if result.get("final_text"):
            _print_result(result["final_text"])
        _print_info(f"Done in {result['elapsed_ms']}ms")
        time.sleep(0.5)  # Brief pause between commands


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="JARVIS STT injection tester — no hardware required"
    )
    parser.add_argument("command", nargs="?", help="Single command to run")
    parser.add_argument("--file", "-f", help="Batch file of commands (one per line)")
    args = parser.parse_args()

    tester = JARVISTester()

    if args.file:
        run_batch(tester, args.file)
    elif args.command:
        run_single(tester, args.command)
    else:
        run_interactive(tester)
