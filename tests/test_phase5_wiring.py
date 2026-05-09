
"""Phase 5 tests — Orchestrator wiring, callback injection, recovery escalation."""
import pytest, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator
from core.recovery import RecoveryManager

def test_orchestrator_instantiates_clean():
    orc = Orchestrator()
    assert orc._history == []
    assert isinstance(orc._recovery, RecoveryManager)
    assert orc._mode == "interactive_cloud"
    assert orc.running is True

def test_mode_switching_valid():
    orc = Orchestrator()
    orc.set_mode("interactive_local")
    assert orc._mode == "interactive_local"
    orc.set_mode("invalid_mode")
    assert orc._mode == "interactive_local"  # Falls back safely

def test_callback_wrappers_exist():
    orc = Orchestrator()
    assert callable(orc._execute_wrapper)
    assert callable(orc._verify_wrapper)

def test_unknown_tool_returns_error():
    orc = Orchestrator()
    res = orc._execute_wrapper("nonexistent_tool", {})
    assert res["success"] is False
    assert "Unknown tool" in res["error"]

def test_history_management_bounds_growth(monkeypatch):
    # Mock tool_loop to return immediate success without LLM calls
    def mock_run(user_input, history, execute_fn, verify_fn, mode):
        return {"response": f"Mocked: {user_input}", "success": True, "error": None}
    monkeypatch.setattr("core.orchestrator.tool_loop_run", mock_run)

    orc = Orchestrator()
    # Simulate 25 user turns
    for i in range(25):
        orc.handle(f"test command {i}")
    assert len(orc._history) == 40  # 25 turns * 2 = 50, capped at 40

def test_recovery_escalation_on_failure(monkeypatch):
    def mock_fail(user_input, history, execute_fn, verify_fn, mode):
        return {"response": "Failed.", "success": False, "error": "ITERATION_CAP_EXCEEDED"}
    monkeypatch.setattr("core.orchestrator.tool_loop_run", mock_fail)

    orc = Orchestrator()
    resp = orc.handle("break the system")
    assert isinstance(resp, str)
    assert "break the system" in resp or "escalate" in resp.lower()

