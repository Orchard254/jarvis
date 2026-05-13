"""Test that skill backend functions work (importable via execute_code)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_save_candidate_works(monkeypatch):
    import tempfile, settings, os
    from skills.skill_store import init_db

    temp_dir = Path(tempfile.mkdtemp())
    monkeypatch.setattr(settings, "SKILLS_DB", temp_dir / "skills.db")
    monkeypatch.setattr(settings, "ENABLE_SKILLS", True)
    init_db()

    from tools.skill_store_tool import save_candidate
    r = save_candidate("test intent", "print('hello')", "python")
    assert r["success"]
    assert r["skill_id"].startswith("skill_")
    assert "test intent" in r["intent"]


def test_promote_skill_works(monkeypatch):
    import tempfile, settings
    from skills.skill_store import init_db

    temp_dir = Path(tempfile.mkdtemp())
    monkeypatch.setattr(settings, "SKILLS_DB", temp_dir / "skills.db")
    monkeypatch.setattr(settings, "ENABLE_SKILLS", True)
    init_db()

    from tools.skill_store_tool import save_candidate, promote_skill
    r = save_candidate("promote test", "print('hi')", "python")
    assert r["success"]
    r2 = promote_skill(r["skill_id"])
    assert r2["success"]
    assert r2["skill_id"] == r["skill_id"]


def test_run_skill_works(monkeypatch):
    import tempfile, settings
    from skills.skill_store import init_db

    temp_dir = Path(tempfile.mkdtemp())
    monkeypatch.setattr(settings, "SKILLS_DB", temp_dir / "skills.db")
    monkeypatch.setattr(settings, "ENABLE_SKILLS", True)
    init_db()

    from tools.skill_store_tool import save_candidate, promote_skill
    from tools.run_skill_tool import run_skill

    r = save_candidate("run test", "print('run ok')", "python")
    assert r["success"]
    promote_skill(r["skill_id"])
    r2 = run_skill(r["skill_id"])
    assert r2["success"]
