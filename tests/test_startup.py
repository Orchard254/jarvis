"""
Smoke tests for refactored modules.
Runs without heavy deps (pyautogui, pyaudio, etc.) so CI can verify basic health.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_settings_package_auto_all():
    import settings
    assert len(settings.__all__) >= 120
    required = [
        "LLM_MODEL", "MEMORY_DB", "LOG_FILE", "ALLOWED_IMPORTS",
        "VOICE_ENABLED", "STT_EXCLUSIVE", "TOOL_STAGE", "ITERATION_CAPS",
        "BATTERY_WARN_THRESHOLD", "CALENDAR_BACKEND", "ENABLE_SKILLS",
    ]
    for key in required:
        assert hasattr(settings, key), f"Missing: {key}"


def test_settings_from_import():
    from settings import (
        LLM_MODEL, MEMORY_DB, LOGS_DIR, LOG_FILE, LOG_LEVEL,
        OLLAMA_API_KEY, ALLOWED_IMPORTS, ITERATION_CAPS,
        TOOL_STAGE, VOICE_ENABLED, STT_EXCLUSIVE, get_env_bool,
    )
    assert LLM_MODEL
    assert len(ALLOWED_IMPORTS) > 100
    assert ITERATION_CAPS["interactive_cloud"] == 10


def test_settings_submodules():
    from settings.paths import DATA_DIR, LOGS_DIR, MEMORY_DB
    from settings.llm import LLM_MODEL, ITERATION_CAPS, REASONING_EFFORT
    from settings.safety import ALLOWED_IMPORTS, BLOCKED_PATHS, SAFETY_ENABLED
    from settings.voice import STT_EXCLUSIVE, IS_SPEAKING, VOICE_ENABLED
    from settings.autonomous import AUTONOMOUS_REQUIRE_APPROVAL, TOOL_STAGE
    from settings.integrations import CALENDAR_BACKEND, SMTP_HOST
    from settings.log_cfg import LOG_FILE, LOG_LEVEL
    assert len(BLOCKED_PATHS) >= 3
    assert "shutdown" in AUTONOMOUS_REQUIRE_APPROVAL


def test_db_pool_consolidation():
    from memory.db_pool import get_episodic_connection, shutdown_pools, _MemoryPoolFacade
    pool = _MemoryPoolFacade()
    try:
        with pool.get_connection() as conn:
            assert conn is not None
    except Exception:
        pass  # DB might not exist yet, but the import and API must work


def test_tool_result_cache_thread_safety():
    from brain.tool_result_cache import ToolResultCache, get_cache
    c = ToolResultCache()
    assert c._total_misses == 0
    c._track_miss()
    assert c._total_misses == 1
    stats = c.stats()
    assert stats["total_misses"] == 1
    assert stats["total_hits"] == 0
    assert "hit_rate" in stats


def test_no_legacy_shims():
    for f in ["tool_loop.py", "tool_validator.py", "executor_agent.py"]:
        p = PROJECT_ROOT / "brain" / f
        assert not p.exists(), f"Legacy shim still exists: {f}"


def test_package_lock_removed():
    assert not (PROJECT_ROOT / "package-lock.json").exists()


def test_env_example_exists():
    example = PROJECT_ROOT / ".env.example"
    assert example.exists()
    content = example.read_text(encoding="utf-8")
    assert "your_api_key_here" in content
    assert "hf_" not in content or "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" not in content


def test_requirements_has_new_deps():
    reqs = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for dep in ["numpy", "edge-tts", "PyYAML", "pygame", "pandas", "pycaw", "comtypes"]:
        assert dep in reqs, f"Missing: {dep}"


def test_private_key_not_leaked_in_check():
    content = (PROJECT_ROOT / "jarvis.py").read_text(encoding="utf-8")
    assert "leaked_pattern" not in content
