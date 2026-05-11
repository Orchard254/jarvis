
"""Phase 3 tests — Orchestrator routing & hierarchical recovery."""
import pytest, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.recovery import RecoveryManager
from core.orchestrator import Orchestrator

def test_recovery_classification():
    rm = RecoveryManager()
    assert rm.classify_error("timeout expired") == "TIMEOUT"
    assert rm.classify_error("access denied") == "PERMISSION_DENIED"
    assert rm.classify_error("unknown tool: fake") == "TOOL_NOT_FOUND"

def test_recovery_retry_caps():
    rm = RecoveryManager()
    assert rm.should_retry("execute_code", "timeout") is True
    assert rm.should_retry("execute_code", "timeout") is True
    assert rm.should_retry("execute_code", "timeout") is False

def test_orchestrator_deterministic_flow():
    orc = Orchestrator()
    resp = orc.handle("notify me with a test")
    assert isinstance(resp, str) and len(resp) > 0

def test_orchestrator_cli_instantiates():
    orc = Orchestrator()
    assert orc.running is True
    assert orc._recovery is not None
    assert orc._history == []
