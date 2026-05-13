
"""Phase 0 tests — verify project structure, config keys, and entry point."""
import pytest
from pathlib import Path
import sys

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

def test_settings_imports():
    import settings
    required_keys = [
        "LLM_MODEL", "MAX_CONTEXT_TOKENS", "ITERATION_CAPS", "VERIFICATION_MODE",
        "MAX_RAM_PERCENT", "DB_WAL_MODE", "DB_BUSY_TIMEOUT", "TOOL_RETRY_LIMITS",
        "EXECUTE_CODE_TIMEOUT", "SKILL_MATCH_THRESHOLD", "WAKE_WORD", "LOG_FILE"
    ]
    for key in required_keys:
        assert hasattr(settings, key), f"Missing settings key: {key}"

def test_required_directories_exist():
    dirs = [
        "core", "brain", "safety", "tools", "skills", "indexer", "memory",
        "verification", "perception", "output", "autonomous", "tests",
        "data", "logs", "skills/db", "indexer/db", "memory/db"
    ]
    for d in dirs:
        assert (BASE / d).exists(), f"Missing directory: {d}"

def test_required_init_files():
    packages = [
        "core", "brain", "safety", "tools", "skills", "indexer",
        "memory", "verification", "perception", "output", "autonomous", "tests"
    ]
    for d in packages:
        assert (BASE / d / "__init__.py").exists(), f"Missing __init__.py in {d}/"

def test_jarvis_entry_point():
    entry = BASE / "jarvis.py"
    assert entry.exists()
    import importlib.util
    spec = importlib.util.spec_from_file_location("jarvis", str(entry))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")

def test_env_file_exists():
    assert (BASE / ".env").exists()

def test_requirements_has_critical_deps():
    reqs = (BASE / "requirements.txt").read_text().lower()
    critical = ["ollama", "chromadb", "pywin32", "psutil", "pillow", "pytesseract", "pytest"]
    for dep in critical:
        assert dep in reqs, f"Missing critical dependency in requirements.txt: {dep}"
