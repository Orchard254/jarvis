import sqlite3
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import settings
from skills.skill_store import (
    init_db, save_candidate, promote_skill, record_run,
    get_skill, search_by_intent, get_active_skills, prune_candidates
)
from skills.skill_runner import run_skill
from core.thread_db import close_thread_connections


@pytest.fixture(autouse=True)
def _isolate_skills_db(monkeypatch, tmp_path):
    db_path = tmp_path / "skills.db"
    monkeypatch.setattr(settings, "SKILLS_DB", db_path)
    monkeypatch.setattr(settings, "ENABLE_SKILLS", True)
    monkeypatch.setattr(settings, "SKILL_CANDIDATE_CAP", 3)
    close_thread_connections()
    init_db()
    yield
    close_thread_connections()


def test_skill_lifecycle_crud():
    skill_id = save_candidate("test intent", "print('hello')", "python")
    assert skill_id != ""
    skill = get_skill(skill_id)
    assert skill is not None
    assert skill["status"] == "candidate"
    promote_skill(skill_id)
    skill = get_skill(skill_id)
    assert skill["status"] == "active"
    record_run(skill_id, True)
    skill = get_skill(skill_id)
    assert skill["run_count"] == 1
    assert skill["success_count"] == 1


def test_sql_search_basic():
    skill_id = save_candidate("music player", "import subprocess; subprocess.Popen('notepad.exe')")
    promote_skill(skill_id)
    skill = search_by_intent("play some music")
    assert skill is not None
    assert skill["skill_id"] == skill_id


def test_skill_runner_executes_through_safety(monkeypatch):
    def mock_execute(*args, **kwargs):
        return {"success": True, "stdout": "test stdout", "stderr": ""}
    monkeypatch.setattr("skills.skill_runner.execute", mock_execute)
    skill_id = save_candidate("test run", "print('test')")
    promote_skill(skill_id)
    result = run_skill(skill_id, "test run")
    assert result["success"] is True


def test_prune_candidates_caps_memory():
    cap = settings.SKILL_CANDIDATE_CAP
    ids = []
    for i in range(cap + 2):
        ids.append(save_candidate(f"candidate {i}", f"print({i})"))
    close_thread_connections()
    conn = sqlite3.connect(str(settings.SKILLS_DB))
    try:
        count_before = conn.execute("SELECT COUNT(*) FROM skills WHERE status = 'candidate'").fetchone()[0]
    finally:
        conn.close()
    assert count_before == cap + 2
    prune_candidates()
    close_thread_connections()
    conn = sqlite3.connect(str(settings.SKILLS_DB))
    try:
        count_after = conn.execute("SELECT COUNT(*) FROM skills WHERE status = 'candidate'").fetchone()[0]
    finally:
        conn.close()
    assert count_after == cap
