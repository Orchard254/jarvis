import hashlib
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional

import settings
from core.thread_db import get_connection

from skills import skill_embedder
from skills.skill_embedder import add_skill as embed_skill
from skills.skill_embedder import delete_skill as delete_embedding

# Skill versioning — tracks multiple versions per intent_label for A/B testing
try:
    from core.skill_versioning import get_registry, DeploymentStatus
    _version_registry = get_registry()
    _VERSIONING_AVAILABLE = True
except Exception:
    _version_registry = None
    _VERSIONING_AVAILABLE = False

logger = logging.getLogger(__name__)


def _connect():
    return get_connection(settings.SKILLS_DB, timeout=5.0)


def init_db():
    if not settings.ENABLE_SKILLS:
        return
    settings.SKILLS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            skill_id TEXT PRIMARY KEY,
            intent_label TEXT NOT NULL,
            code TEXT NOT NULL,
            language TEXT DEFAULT 'python',
            status TEXT DEFAULT 'candidate',
            run_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            last_used TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            embedding_generated BOOLEAN DEFAULT 0
        )
    """)
    conn.commit()
    import threading

    def _bg_init():
        try:
            skill_embedder.init()
            logger.info("Skill embedder initialised (semantic search active)")
        except Exception as exc:
            logger.warning(f"Skill embedder init failed — falling back to SQL search: {exc}")

    threading.Thread(target=_bg_init, daemon=True, name="skill-embedder-init").start()
    logger.info("Skill store DB initialized")


def save_candidate(intent_label: str, code: str, language: str = "python") -> str:
    if not settings.ENABLE_SKILLS:
        return ""
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT skill_id FROM skills WHERE intent_label = ? AND code = ?",
            (intent_label, code),
        ).fetchone()
        if existing:
            return existing[0]
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO skills (skill_id, intent_label, code, language, status) VALUES (?, ?, ?, ?, 'candidate')",
            (skill_id, intent_label, code, language),
        )
        conn.commit()

        # Track version in version registry when available
        if _VERSIONING_AVAILABLE:
            version = _compute_next_version(intent_label)
            # Register in-memory — actual version selection is passive (via select_version)
            _version_registry.register_version(
                intent_label, version,
                lambda: None,  # dummy — actual impl is in DB
                status=DeploymentStatus.DRAFT,
                metadata={"skill_id": skill_id, "language": language}
            )

        logger.info(f"Saved candidate skill {skill_id} for {intent_label}")
    except Exception as e:
        logger.error(f"Failed to save candidate: {e}")
        return ""

    return skill_id


def _compute_next_version(intent_label: str) -> str:
    """Compute the next version string for a given intent label."""
    conn = _connect()
    existing = conn.execute(
        "SELECT COUNT(*) FROM skills WHERE intent_label = ?", (intent_label,)
    ).fetchone()[0]
    return f"v{existing + 1}.0.0"


def promote_skill(skill_id: str, conn=None):
    if not settings.ENABLE_SKILLS:
        return
    if conn is None:
        conn = _connect()
    try:
        row = conn.execute(
            "SELECT intent_label, code FROM skills WHERE skill_id = ?", (skill_id,)
        ).fetchone()
        if not row:
            logger.warning(f"Skill {skill_id} not found for promotion")
            return
        intent_label, code = row

        # Demote any existing active skill with the same intent to ACTIVE (multi-version support)
        # so we keep the old version available for A/B comparison
        old_active = conn.execute(
            "SELECT skill_id FROM skills WHERE intent_label = ? AND status = 'active' AND skill_id != ?",
            (intent_label, skill_id),
        ).fetchone()
        if old_active:
            # Keep it active — traffic routing in version_registry handles selection
            pass

        conn.execute(
            "UPDATE skills SET status = 'active', embedding_generated = 1 WHERE skill_id = ?",
            (skill_id,),
        )
        conn.commit()
        embed_skill(skill_id, intent_label, code)

        # Promote version in registry
        if _VERSIONING_AVAILABLE:
            version = _compute_next_version(intent_label)
            versions = _version_registry.versions.get(intent_label, [])
            for v in versions:
                if v.metadata.get("skill_id") == skill_id:
                    v.status = DeploymentStatus.ACTIVE
                    v.traffic_percentage = 100.0
                else:
                    # Older versions become DEPRECATED to phase out traffic
                    if v.status == DeploymentStatus.ACTIVE:
                        v.status = DeploymentStatus.DEPRECATED
                        v.traffic_percentage = 0.0

        logger.info(f"Promoted skill {skill_id} to active")
    except Exception as e:
        logger.error(f"Failed to promote skill {skill_id}: {e}")


def record_run(skill_id: str, success: bool):
    """Update run stats. Lifecycle promotion/demotion/retirement is handled by the LLM via prompt instructions."""
    if not settings.ENABLE_SKILLS:
        return
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT run_count, success_count, failure_count FROM skills WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
        if not row:
            return
        run_count, success_count, failure_count = row
        run_count += 1
        if success:
            success_count += 1
        else:
            failure_count += 1
        success_rate = success_count / run_count if run_count > 0 else 0.0
        conn.execute(
            "UPDATE skills SET run_count=?, success_count=?, failure_count=?, success_rate=?, last_used=? WHERE skill_id=?",
            (run_count, success_count, failure_count, success_rate, datetime.now().isoformat(), skill_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record run for {skill_id}: {e}")


def get_skill(skill_id: str) -> Optional[dict]:
    if not settings.ENABLE_SKILLS:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM skills WHERE skill_id = ?", (skill_id,)).fetchone()
        if not row:
            return None
        columns = [col[1] for col in conn.execute("PRAGMA table_info(skills)").fetchall()]
        return dict(zip(columns, row))
    except Exception as e:
        logger.error(f"Failed to get skill {skill_id}: {e}")
        return None


def get_candidate_by_intent(intent: str) -> Optional[dict]:
    if not settings.ENABLE_SKILLS:
        return None
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM skills WHERE status = 'candidate' AND lower(intent_label) = lower(?) ORDER BY run_count DESC LIMIT 1",
            (intent,),
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_candidate_by_intent error: {e}")
        return None


def search_by_intent(intent: str) -> Optional[dict]:
    """Return the best active skill matching intent. Semantic search first, then exact label match."""
    if not settings.ENABLE_SKILLS:
        return None

    from skills.skill_embedder import search_similar

    matches = search_similar(intent, limit=10)
    for match in matches:
        skill = get_skill(match["skill_id"])
        if skill and skill["status"] == "active":
            return skill

    conn = _connect()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM skills WHERE status = 'active' AND lower(intent_label) = lower(?) ORDER BY success_rate DESC LIMIT 1",
        (intent,),
    ).fetchone()
    return dict(row) if row else None


def get_active_skills(limit: int = 100) -> list[dict]:
    if not settings.ENABLE_SKILLS:
        return []
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM skills WHERE status = 'active' LIMIT ?", (limit,)).fetchall()
        columns = [col[1] for col in conn.execute("PRAGMA table_info(skills)").fetchall()]
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get active skills: {e}")
        return []


def delete_skill(skill_id: str) -> bool:
    if not settings.ENABLE_SKILLS:
        return False
    conn = _connect()
    try:
        conn.execute("DELETE FROM skills WHERE skill_id = ?", (skill_id,))
        conn.commit()
        delete_embedding(skill_id)
        logger.info(f"Deleted skill {skill_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete skill {skill_id}: {e}")
        return False


def prune_candidates():
    if not settings.ENABLE_SKILLS:
        return
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM skills WHERE status = 'candidate'").fetchone()[0]
        if count <= settings.SKILL_CANDIDATE_CAP:
            return
        conn.execute(
            "DELETE FROM skills WHERE skill_id IN ("
            "SELECT skill_id FROM skills WHERE status = 'candidate' ORDER BY created_at ASC LIMIT ?"
            ")", (count - settings.SKILL_CANDIDATE_CAP,))
        conn.commit()
        logger.info(f"Pruned {count - settings.SKILL_CANDIDATE_CAP} candidates")
    except Exception as e:
        logger.error(f"Failed to prune candidates: {e}")
