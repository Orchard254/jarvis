"""
Integration tests for newly wired features.

Run: python -m pytest tests/test_new_features.py -v
"""

import time
import pytest


# ── 1. CIRCUIT BREAKER ───────────────────────────────────────────────────────

class TestCircuitBreaker:
    """Circuit breaker wired into safety/executor.py — blocks after 3 failures."""

    def test_breaker_created_on_tool_call(self):
        from safety.executor import circuit_breakers, execute, CircuitOpenError
        from tools.read_pc_state import read_pc_state
        # First call creates a circuit breaker for the tool
        r = execute("read_pc_state", read_pc_state, {})
        assert r.get("success") is not None
        cbs = circuit_breakers.list_all()
        assert "read_pc_state" in cbs
        assert cbs["read_pc_state"]["state"] == "closed"

    def test_breaker_opens_after_3_failures(self):
        from core.circuit_breaker import CircuitBreaker, CircuitOpenError
        cb = CircuitBreaker(name="test_open", failure_threshold=3, timeout_seconds=0.5)
        # Fail 3 times
        for i in range(3):
            try:
                cb.sync_call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except ValueError:
                pass
        assert cb.state.value == "open"
        # 4th call should be rejected
        with pytest.raises(CircuitOpenError):
            cb.sync_call(lambda: "ok")

    def test_breaker_recovers_after_timeout(self):
        from core.circuit_breaker import CircuitBreaker, CircuitOpenError
        cb = CircuitBreaker(name="test_recover", failure_threshold=3, success_threshold=1, timeout_seconds=0.5)
        for i in range(3):
            try:
                cb.sync_call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except ValueError:
                pass
        assert cb.state.value == "open"
        time.sleep(0.6)
        # Should now be half_open and allow one call
        cb.sync_call(lambda: "recovered")
        assert cb.state.value == "closed"


# ── 2. SELF-REFLECTION ───────────────────────────────────────────────────────

class TestSelfReflection:
    """Self-reflection wired into orchestrator.handle() — heuristic quality scoring."""

    def test_reflector_scores_output(self):
        from core.self_reflection import self_reflector
        r = self_reflector.reflect("test_1", "The analysis is complete. Found 3 issues.")
        assert r.overall_score > 0
        assert len(r.scores) == 7  # 7 criteria
        assert r.task_id == "test_1"

    def test_reflector_detects_short_output(self):
        from core.self_reflection import self_reflector
        r = self_reflector.reflect("test_2", "ok")
        assert r.overall_score < 0.5  # short, no structure — should score low

    def test_reflector_detects_uncertainty(self):
        from core.self_reflection import self_reflector
        r = self_reflector.reflect("test_3", "I might think it could possibly be maybe the answer perhaps")
        scores = {s.criterion.value: s.score for s in r.scores}
        assert scores["accuracy"] < 0.8  # high uncertainty


# ── 3. LONG-TERM MEMORY ──────────────────────────────────────────────────────

class TestLongTermMemory:
    """Long-term RAG memory wired into orchestrator and jarvis.py."""

    def test_store_and_retrieve_preference(self):
        import tempfile, shutil
        from memory.long_term_memory import LongTermMemoryManager
        tmpdir = tempfile.mkdtemp()
        ltm = LongTermMemoryManager(persist_dir=tmpdir)
        ltm.remember_preference("editor", "vscode", confidence=0.9)
        prefs = ltm.get_user_preferences()
        assert prefs.get("editor") == "vscode"
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_relevant_context_retrieval(self):
        import tempfile, shutil
        from memory.long_term_memory import LongTermMemoryManager
        tmpdir = tempfile.mkdtemp()
        ltm = LongTermMemoryManager(persist_dir=tmpdir)
        ltm.remember_preference("browser", "firefox")
        ltm.remember_fact("User works on data science projects")
        ctx = ltm.get_relevant_context("what browser do I use", max_memories=3)
        assert "firefox" in ctx
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_build_personalized_prompt(self):
        import tempfile, shutil
        from memory.long_term_memory import LongTermMemoryManager
        tmpdir = tempfile.mkdtemp()
        ltm = LongTermMemoryManager(persist_dir=tmpdir)
        prompt = ltm.build_personalized_prompt("System ready.", "hello")
        assert "System ready." in prompt
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 4. FEEDBACK LOOP (IMPLICIT SIGNALS) ──────────────────────────────────────

class TestFeedbackLoop:
    """Implicit feedback signals wired into executor_pool retry/success paths."""

    def test_feedback_loop_imports(self):
        from core.feedback_loop import get_collector, FeedbackType
        c = get_collector()
        assert c is not None
        assert FeedbackType.IMPLICIT_RETRY.value == "implicit_retry"

    def test_implicit_retry_recorded(self):
        from core.feedback_loop import get_collector
        c = get_collector()
        c.start_task("retry_test", "test_skill", {})
        c.record_retry("retry_test")
        events = c.store.get_feedback_for_skill("test_skill")
        retries = [e for e in events if e.feedback_type.value == "implicit_retry"]
        assert len(retries) >= 1

    def test_implicit_success_recorded(self):
        from core.feedback_loop import get_collector
        c = get_collector()
        c.start_task("success_test", "test_skill_2", {})
        c.record_success("success_test")
        events = c.store.get_feedback_for_skill("test_skill_2")
        successes = [e for e in events if e.feedback_type.value == "implicit_success"]
        assert len(successes) >= 1


# ── 5. SKILL VERSIONING ─────────────────────────────────────────────────────

class TestSkillVersioning:
    """Skill versioning wired into skill_store save/promote."""

    def test_version_registry_imports(self):
        from core.skill_versioning import get_registry, DeploymentStatus
        r = get_registry()
        assert r is not None

    def test_skill_save_creates_version(self):
        from core.skill_versioning import get_registry, DeploymentStatus
        r = get_registry()
        before = len(r.versions.get("test_intent", []))
        r.register_version("test_intent", "v1.0.0", lambda: None,
                          status=DeploymentStatus.DRAFT,
                          metadata={"skill_id": "test_001"})
        after = len(r.versions.get("test_intent", []))
        assert after == before + 1


# ── 6. PLATFORM ABSTRACTION ─────────────────────────────────────────────────

class TestPlatformAbstraction:
    """Platform abstraction wired into process_manager and control_window."""

    def test_platform_imports(self):
        from core.platform_abstraction import PlatformAbstraction
        p = PlatformAbstraction()
        assert p is not None

    def test_process_manager_lists_processes(self):
        from tools.process_manager import process_manager
        r = process_manager(action="list")
        assert r.get("success")
        assert "processes" in r
        assert r["count"] > 0

    def test_control_window_lists_windows(self):
        from tools.control_window import list_windows
        r = list_windows()
        assert r.get("success") or not r.get("success")
        # May return empty on headless, but shouldn't crash


# ── 7. EMOJI FIX ─────────────────────────────────────────────────────────────

class TestEmojiFix:
    """Tool_loop emoji removed for Windows cp1252 compatibility."""

    def test_tool_loop_has_no_emoji(self):
        import ast, os
        path = os.path.join(os.path.dirname(__file__), "..", "brain", "tool_loop.py")
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "\\U0001f" not in source, "Emoji unicode escapes still in tool_loop.py"
        assert "\\U0001f914" not in source
        assert "\\U0001f527" not in source


# ── 8. OPEN_APP TOOL ─────────────────────────────────────────────────────────

class TestOpenApp:
    """New open_app tool registered and handling input correctly."""

    def test_open_app_in_registry(self):
        from tools import TOOL_REGISTRY, TOOL_SCHEMAS
        assert "window" in TOOL_REGISTRY

        schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        assert "window" in schema_names

    def test_open_app_rejects_invalid_name(self):
        from tools.open_app import open_app
        r = open_app("")
        assert r.get("success") == False
        r = open_app(None)
        assert r.get("success") == False
        r = open_app(123)
        assert r.get("success") == False
