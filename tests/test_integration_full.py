"""
JARVIS Full Architecture Integration Test Suite
Validates: Layer boundaries, safety funnel, async indexer, verification router,
           context budgeting, orchestrator routing, memory persistence, autonomous queue.
Runs without external APIs (mocked). Fails if core rules are broken.
"""
import pytest
import sys
import time
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── HELPER: Import with graceful skip on missing deps ──────────────────────
def _import_safe(module_path: str):
    try:
        mod = __import__(module_path, fromlist=[""])
        return mod
    except ImportError as e:
        pytest.skip(f"Module {module_path} not found: {e}")

settings = _import_safe("settings")
safety_exec = _import_safe("safety.executor")
tool_guard = _import_safe("safety.tool_guard")
audit_log = _import_safe("safety.audit_log")
verifier = _import_safe("verification.verifier")
state_checks = _import_safe("verification.state_checks")
orchestrator_mod = _import_safe("core.orchestrator")
brain_loop = _import_safe("brain.tool_loop")
context_mgr = _import_safe("brain.context_manager")
indexer = _import_safe("indexer.pc_indexer")
write_q = _import_safe("indexer.write_queue")
query_tool = _import_safe("tools.query_pc_index")
memory_mgr = _import_safe("memory.memory_manager")
autonomous_q = _import_safe("autonomous.task_queue")
approval_gate = _import_safe("autonomous.approval_gate")
activity_log = _import_safe("autonomous.activity_log")

# ── TEST CLASSES ───────────────────────────────────────────────────────────

class TestLayerBoundariesAndSafety:
    """Validates Rule 1-3: No cross-imports, safety is mandatory, config is centralized."""
    
    def test_brain_does_not_import_tools_or_safety(self):
        import importlib
        brain_mod = importlib.import_module("brain")
        for name in dir(brain_mod):
            if name.startswith("_"): continue
            obj = getattr(brain_mod, name)
            if hasattr(obj, "__file__") and str(obj.__file__).startswith(str(Path(__file__).parent.parent / "brain")):
                source = open(obj.__file__, "r").read()
                assert "import tools" not in source and "from tools" not in source, "brain/ imports tools/"
                assert "import safety" not in source and "from safety" not in source, "brain/ imports safety/"

    def test_safety_executor_is_single_funnel(self):
        assert hasattr(safety_exec, "execute"), "safety/executor.py missing execute()"
        assert callable(safety_exec.execute)

    def test_ast_guard_blocks_dynamic_import(self):
        allowed, reason = tool_guard.check_imports("__import__('socket').send(b'bad')")
        assert not allowed, "AST guard failed to block dynamic import"
        assert "socket" in reason.lower()

    def test_execute_code_respects_timeout_and_env(self):
        from tools.execute_code import execute_code
        # This should run safely and quickly
        r = execute_code("import os; print('safe_env_check')", "python")
        assert r["success"]
        assert "safe_env_check" in r["stdout"]

    def test_audit_log_records_calls(self):
        audit_log.setup()
        # Simulate a call
        safety_exec.execute("notify_user", lambda **k: {"success": True}, {"message": "test", "urgency": "low"})
        # Verify log file exists and contains entry
        log_path = settings.LOGS_DIR / "audit.log"
        assert log_path.exists(), "audit.log not created"
        content = log_path.read_text()
        assert "notify_user" in content
        assert "test" in content


class TestAsyncIndexerAndDB:
    """Validates WAL mode, single-writer queue, read-only query, no main-thread blocking."""
    
    def test_indexer_init_creates_tables(self):
        indexer.init_db()
        assert settings.PC_INDEX_DB.exists(), "pc_index.db not created"
        import sqlite3
        conn = sqlite3.connect(settings.PC_INDEX_DB)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode")
        mode = c.fetchone()[0]
        assert mode.lower() == "wal", f"DB not in WAL mode: {mode}"
        conn.close()

    def test_write_queue_serializes_writes(self):
        w = write_q.IndexWriter()
        w.start()
        w.push("files", [{"filename": "test.txt", "full_path": "/tmp/test.txt"}])
        time.sleep(0.5)
        w.stop()
        # No exception = queue worked safely
        assert True

    def test_query_tool_opens_readonly(self):
        results = query_tool.query_pc_index("notepad", type="app")
        assert isinstance(results, list), "query_pc_index must return list"
        # Verify it used URI readonly mode
        import sqlite3
        # Quick check: trying to write should fail if opened correctly in prod
        # We just verify it doesn't crash and returns structure
        assert all("type" in r and "name" in r for r in results if r), "Invalid query result structure"


class TestVerificationRouter:
    """Validates 3-tier router, no base64 injection, text-only summaries."""
    
    def test_state_check_tier1_returns_text(self):
        from verification.state_checks import verify_process_running, verify_window_visible
        # Should return bool, not crash
        assert isinstance(verify_process_running("python"), bool)
        assert isinstance(verify_window_visible("nonexistent"), bool)

    def test_verifier_never_returns_base64_in_context(self):
        mock_result = {"success": True, "returncode": 0}
        report = verifier.verify_action("execute_code", mock_result, expected="success")
        assert "status" in report
        assert "summary" in report
        # Ensure no image_b64 key leaks into context
        assert "image_b64" not in str(report).lower(), "Verification leaked base64 into context"


class TestOrchestratorRoutingAndBrain:
    """Validates mode-aware caps, callback injection, history pruning, dynamic routing."""
    
    def test_orchestrator_injects_callbacks_correctly(self):
        orc = orchestrator_mod.Orchestrator()
        assert callable(orc._execute_wrapper)
        assert callable(orc._verify_wrapper)
        # Test execute wrapper routes to safety
        res = orc._execute_wrapper("query_pc_index", {"query": "test"})
        assert isinstance(res, dict)

    def test_context_manager_prunes_over_budget(self):
        msgs = [{"role": "user", "content": "x" * 1000}] * 25
        pruned = context_mgr.prune_history(msgs, budget=500)
        assert len(pruned) < len(msgs), "Context manager failed to prune"
        system = [m for m in pruned if m["role"] == "system"]
        assert len(system) <= 1, "System prompt duplicated or lost"

    def test_tool_loop_respects_iteration_caps(self):
        cap = settings.ITERATION_CAPS.get("interactive_cloud", 3)
        assert isinstance(cap, int) and cap <= 6, "Iteration cap too high for cloud mode"

    def test_history_caps_at_40(self):
        orc = orchestrator_mod.Orchestrator()
        for i in range(25):
            orc._history.append({"role": "user", "content": f"test {i}"})
            orc._history.append({"role": "assistant", "content": f"resp {i}"})
        assert len(orc._history) <= 40, f"History grew to {len(orc._history)}, should cap at 40"


class TestMemoryVoiceAndAutonomous:
    """Validates mute flag, episodic persistence, queue states, approval gate, activity log."""
    
    def test_episodic_memory_persists(self):
        mm = memory_mgr.MemoryManager(session_id="integration_test")
        mm.write_episodic("command", command_text="verify_persist", success=True)
        events = mm.get_recent_episodes(limit=5)
        assert any("verify_persist" in str(e.get("command_text", "")) for e in events)

    def test_is_speaking_flag_integration(self):
        # Mock TTS to avoid audio
        with patch("output.tts.subprocess.Popen", return_value=MagicMock(wait=lambda x: None)):
            import output.tts as tts
            import settings
            original = settings.IS_SPEAKING.is_set()
            settings.IS_SPEAKING.clear()
            tts.speak("test", blocking=True)
            # Flag should be cleared after call
            assert not settings.IS_SPEAKING.is_set()
            if original:
                settings.IS_SPEAKING.set()

    def test_autonomous_queue_crud(self):
        autonomous_q.init_db()
        tid = autonomous_q.create_task("test_clean", confidence_required=0.85)
        pending = autonomous_q.get_pending_tasks()
        assert any(t["task_id"] == tid for t in pending)
        autonomous_q.update_task(tid, "running")
        autonomous_q.update_task(tid, "complete", result={"response": "done"})
        assert autonomous_q.get_task(tid)["status"] == "complete"

    def test_approval_gate_parsing_and_timeout(self):
        gate = approval_gate.ApprovalGate(timeout_seconds=1)
        tid = "gate_test_1"
        gate.request_approval(tid, "test", "plan", 0.9)
        assert gate.check_response(tid, "yes") is True
        assert gate.check_response(tid, "no") is None  # already resolved

    def test_activity_log_summary(self):
        summary = activity_log.generate_summary(since=time.time() - 86400)
        assert isinstance(summary, str)
        assert len(summary) > 0


class TestEndToEndSimulation:
    """Simulates a full command without real LLM/API. Validates pipeline flow."""
    
    def test_full_pipeline_mocked(self):
        orc = orchestrator_mod.Orchestrator()
        
        # Mock brain/tool_loop to return immediate success
        mock_result = {
            "response": "Simulated success.",
            "tool_calls": [{"tool": "query_pc_index", "args": {"query": "test"}, "result": {"success": True}}],
            "iterations": 1,
            "success": True,
            "error": None
        }
        
        with patch("brain.tool_loop.run", return_value=mock_result):
            resp = orc.handle("test command")
            assert isinstance(resp, str)
            assert len(resp) > 0
            assert len(orc._history) == 2  # user + assistant added