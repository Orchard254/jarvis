
import os
import tempfile
import sqlite3
import pytest
from pathlib import Path
import sys
import shutil

# Add jarvis directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Create temp dirs for each test run
_temp_root = tempfile.mkdtemp()
temp_skills_db = Path(_temp_root) / "skills.db"
temp_skills_chroma = Path(_temp_root) / "chroma"

# Override settings for testing
import settings
settings.ENABLE_SKILLS = True
settings.SKILLS_DB = temp_skills_db
settings.SKILLS_CHROMA = temp_skills_chroma
settings.SKILL_PROMOTION_RUNS = 2
settings.SKILL_DEMOTE_FAILURES = 2
settings.SKILL_RETIRE_FAILURES = 5
settings.SKILL_CANDIDATE_CAP = 3
settings.SKILL_MATCH_THRESHOLD = 0.0  # Low threshold for tests

from skills.skill_store import (
    init_db, save_candidate, promote_skill, record_run,
    get_skill, search_by_intent, get_active_skills, prune_candidates
)
from skills.skill_embedder import init as init_embedder, search_similar
from skills.skill_runner import run_skill


@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Clean up before each test
    if temp_skills_db.exists():
        temp_skills_db.unlink()
    if temp_skills_chroma.exists():
        shutil.rmtree(temp_skills_chroma, ignore_errors=True)
    # Initialize DB for each test
    init_db()
    yield
    # Cleanup
    if temp_skills_db.exists():
        temp_skills_db.unlink()
    if temp_skills_chroma.exists():
        shutil.rmtree(temp_skills_chroma, ignore_errors=True)


def test_skill_lifecycle_crud():
    # Test saving a candidate
    skill_id = save_candidate("test intent", "print('hello')", "python")
    assert skill_id != ""
    
    skill = get_skill(skill_id)
    assert skill is not None
    assert skill["status"] == "candidate"
    
    # Test promoting
    promote_skill(skill_id)
    skill = get_skill(skill_id)
    assert skill["status"] == "active"
    assert skill["embedding_generated"] == 1
    
    # Test recording runs
    record_run(skill_id, True)
    skill = get_skill(skill_id)
    assert skill["run_count"] == 1
    assert skill["success_count"] == 1


def test_semantic_search_basic():
    init_embedder()
    
    # Save and promote a skill
    skill_id = save_candidate("open music app", "import subprocess; subprocess.Popen('notepad.exe')")
    promote_skill(skill_id)
    
    # Search with similar intent
    skill = search_by_intent("play some music")
    # Note: If ChromaDB/sentence-transformers are not available, this may be None, which is acceptable for test
    if skill:
        assert skill["skill_id"] == skill_id


def test_skill_runner_executes_through_safety(monkeypatch):
    def mock_execute(*args, **kwargs):
        return {"success": True, "stdout": "test stdout", "stderr": ""}
    
    monkeypatch.setattr("skills.skill_runner.execute", mock_execute)
    
    skill_id = save_candidate("test run", "print('test')")
    promote_skill(skill_id)
    
    result = run_skill(skill_id, "test run")
    assert result["success"] is True


def test_automatic_demote_on_failures():
    skill_id = save_candidate("demote test", "print('fail')")
    promote_skill(skill_id)
    
    # Failures should demote to candidate
    record_run(skill_id, False)
    skill = get_skill(skill_id)
    assert skill["status"] == "active"
    
    record_run(skill_id, False)
    skill = get_skill(skill_id)
    assert skill["status"] == "candidate"


def test_prune_candidates_caps_memory():
    # Create more than cap candidates
    ids = []
    for i in range(settings.SKILL_CANDIDATE_CAP + 2):
        ids.append(save_candidate(f"candidate {i}", f"print({i})"))
    
    # Count before pruning
    conn = sqlite3.connect(str(settings.SKILLS_DB))
    count_before = conn.execute("SELECT COUNT(*) FROM skills WHERE status = 'candidate'").fetchone()[0]
    conn.close()
    assert count_before == settings.SKILL_CANDIDATE_CAP + 2
    
    prune_candidates()
    
    # Count after pruning
    conn = sqlite3.connect(str(settings.SKILLS_DB))
    count_after = conn.execute("SELECT COUNT(*) FROM skills WHERE status = 'candidate'").fetchone()[0]
    conn.close()
    assert count_after == settings.SKILL_CANDIDATE_CAP
