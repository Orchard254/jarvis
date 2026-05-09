import hashlib
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional

from settings import (
    ENABLE_SKILLS,
    SKILL_CANDIDATE_CAP,
    SKILL_DEMOTE_FAILURES,
    SKILL_PROMOTION_RUNS,
    SKILL_RETIRE_FAILURES,
    SKILLS_DB,
)

from skills import skill_embedder
from skills.skill_embedder import add_skill as embed_skill
from skills.skill_embedder import delete_skill as delete_embedding

logger = logging.getLogger(__name__)


def init_db():
    if not ENABLE_SKILLS:
        return
    SKILLS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SKILLS_DB))
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
    conn.close()
    # Initialise the semantic embedder in a background thread so startup
    # is not blocked by the SentenceTransformer model load / HF cache check.
    # skill_search already falls back to SQL while the embedder is warming up.
    import threading

    def _bg_init():
        try:
            skill_embedder.init()
            logger.info("Skill embedder initialised (semantic search active)")
        except Exception as exc:
            logger.warning(
                f"Skill embedder init failed — falling back to SQL search: {exc}"
            )

    threading.Thread(target=_bg_init, daemon=True, name="skill-embedder-init").start()
    auto_retire_stale()
    logger.info("Skill store DB initialized")


def save_candidate(intent_label: str, code: str, language: str = "python") -> str:
    if not ENABLE_SKILLS:
        return ""
    code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
    conn = sqlite3.connect(str(SKILLS_DB))
    try:
        existing = conn.execute(
            """
            SELECT skill_id FROM skills
            WHERE intent_label = ?
            AND code = ?
        """,
            (intent_label, code),
        ).fetchone()
        if existing:
            logger.info(
                f"Skill candidate already exists: {existing[0]} — skipping duplicate save"
            )
            return existing[0]
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        conn.execute(
            """
            INSERT INTO skills (skill_id, intent_label, code, language, status)
            VALUES (?, ?, ?, ?, 'candidate')
        """,
            (skill_id, intent_label, code, language),
        )
        conn.commit()
        logger.info(f"Saved candidate skill {skill_id} for {intent_label}")
    except Exception as e:
        logger.error(f"Failed to save candidate: {e}")
        return ""
    finally:
        conn.close()

    # Enforce candidate cap now that connection is closed
    prune_candidates()
    return skill_id


def promote_skill(skill_id: str, conn=None):
    if not ENABLE_SKILLS:
        return
    should_close = False
    if conn is None:
        conn = sqlite3.connect(str(SKILLS_DB))
        should_close = True
    try:
        row = conn.execute(
            "SELECT intent_label, code FROM skills WHERE skill_id = ?", (skill_id,)
        ).fetchone()
        if not row:
            logger.warning(f"Skill {skill_id} not found for promotion")
            return
        intent_label, code = row
        conn.execute(
            "UPDATE skills SET status = 'active', embedding_generated = 1 WHERE skill_id = ?",
            (skill_id,),
        )
        conn.commit()
        embed_skill(skill_id, intent_label, code)
        logger.info(f"Promoted skill {skill_id} to active")
    except Exception as e:
        logger.error(f"Failed to promote skill {skill_id}: {e}")
    finally:
        if should_close:
            conn.close()


def record_run(skill_id: str, success: bool):
    if not ENABLE_SKILLS:
        return
    conn = sqlite3.connect(str(SKILLS_DB))
    try:
        row = conn.execute(
            """
            SELECT run_count, success_count, failure_count, status
            FROM skills WHERE skill_id = ?
        """,
            (skill_id,),
        ).fetchone()
        if not row:
            return
        run_count, success_count, failure_count, status = row
        run_count += 1
        if success:
            success_count += 1
        else:
            failure_count += 1
        success_rate = success_count / run_count if run_count > 0 else 0.0
        last_used = datetime.now().isoformat()
        conn.execute(
            """
            UPDATE skills
            SET run_count = ?, success_count = ?, failure_count = ?,
                success_rate = ?, last_used = ?
            WHERE skill_id = ?
        """,
            (
                run_count,
                success_count,
                failure_count,
                success_rate,
                last_used,
                skill_id,
            ),
        )
        if status == "candidate" and success_count >= SKILL_PROMOTION_RUNS:
            promote_skill(skill_id, conn=conn)
        elif status == "active" and failure_count >= SKILL_DEMOTE_FAILURES:
            conn.execute(
                "UPDATE skills SET status = 'candidate' WHERE skill_id = ?", (skill_id,)
            )
            logger.info(f"Demoted skill {skill_id} to candidate")
        if failure_count >= SKILL_RETIRE_FAILURES:
            conn.execute(
                "UPDATE skills SET status = 'retired' WHERE skill_id = ?", (skill_id,)
            )
            delete_embedding(skill_id)
            logger.info(f"Retired skill {skill_id}")
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record run for {skill_id}: {e}")
    finally:
        conn.close()


def get_skill(skill_id: str) -> Optional[dict]:
    if not ENABLE_SKILLS:
        return None
    conn = sqlite3.connect(str(SKILLS_DB))
    try:
        row = conn.execute(
            "SELECT * FROM skills WHERE skill_id = ?", (skill_id,)
        ).fetchone()
        if not row:
            return None
        columns = [
            col[1] for col in conn.execute("PRAGMA table_info(skills)").fetchall()
        ]
        return dict(zip(columns, row))
    except Exception as e:
        logger.error(f"Failed to get skill {skill_id}: {e}")
        return None
    finally:
        conn.close()


def get_candidate_by_intent(intent: str) -> Optional[dict]:
    """Return the best CANDIDATE (not yet active) skill matching *intent*.

    Used by the tool loop to promote skills that have succeeded enough times
    via the LLM path.  Distinct from search_by_intent() which only returns
    active skills.
    """
    if not ENABLE_SKILLS:
        return None
    conn = sqlite3.connect(str(SKILLS_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT * FROM skills
            WHERE status = 'candidate'
              AND lower(intent_label) = lower(?)
            ORDER BY run_count DESC
            LIMIT 1
            """,
            (intent,),
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_candidate_by_intent error: {e}")
        return None
    finally:
        conn.close()


def search_by_intent(intent: str) -> Optional[dict]:
    if not ENABLE_SKILLS:
        return None

    candidates = []

    from skills.skill_embedder import search_similar

    matches = search_similar(intent, limit=10)
    for match in matches:
        skill = get_skill(match["skill_id"])
        if skill and skill["status"] == "active":
            candidates.append({**skill, "similarity": match["similarity"]})

    if not candidates:
        conn = sqlite3.connect(str(SKILLS_DB))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        exact = c.execute(
            """
            SELECT * FROM skills
            WHERE status = 'active'
            AND lower(intent_label) = lower(?)
            ORDER BY success_rate DESC, last_used DESC
        """,
            (intent,),
        ).fetchall()
        conn.close()

        if exact:
            for row in exact:
                candidates.append(dict(row))

    if not candidates:
        return None

    best_skill = None
    best_weight = -1.0
    for skill in candidates:
        success_rate = skill.get("success_rate", 0.0)
        last_used_str = skill.get("last_used")
        days_since_used = 0.0
        if last_used_str:
            try:
                last_used = datetime.fromisoformat(last_used_str)
                days_since_used = (datetime.now() - last_used).days
            except (ValueError, TypeError, OSError):
                pass
        weight = success_rate * max(0.1, 1 - (days_since_used / 30))
        if weight > best_weight:
            best_weight = weight
            best_skill = skill

    if best_skill:
        logger.info(
            f"Best match found: {best_skill['skill_id']} — '{best_skill['intent_label']}' (weight={best_weight:.2f})"
        )
        return best_skill
    return None


def get_active_skills(limit: int = 100) -> list[dict]:
    if not ENABLE_SKILLS:
        return []
    conn = sqlite3.connect(str(SKILLS_DB))
    try:
        rows = conn.execute(
            "SELECT * FROM skills WHERE status = 'active' LIMIT ?", (limit,)
        ).fetchall()
        columns = [
            col[1] for col in conn.execute("PRAGMA table_info(skills)").fetchall()
        ]
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get active skills: {e}")
        return []
    finally:
        conn.close()


def prune_candidates():
    if not ENABLE_SKILLS:
        return
    conn = sqlite3.connect(str(SKILLS_DB))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM skills WHERE status = 'candidate'"
        ).fetchone()[0]
        if count <= SKILL_CANDIDATE_CAP:
            return
        conn.execute(
            """
            DELETE FROM skills
            WHERE skill_id IN (
                SELECT skill_id FROM skills
                WHERE status = 'candidate'
                ORDER BY created_at ASC
                LIMIT ?
            )
        """,
            (count - SKILL_CANDIDATE_CAP,),
        )
        conn.commit()
        logger.info(f"Pruned {count - SKILL_CANDIDATE_CAP} candidates")
    except Exception as e:
        logger.error(f"Failed to prune candidates: {e}")
    finally:
        conn.close()


def auto_retire_stale(days_limit=30):
    if not ENABLE_SKILLS:
        return
    conn = sqlite3.connect(str(SKILLS_DB))
    try:
        cutoff_date = datetime.now() - timedelta(days=days_limit)
        rows = conn.execute("""
            SELECT skill_id, last_used, success_rate, run_count, status
            FROM skills
            WHERE status IN ('active', 'candidate')
        """).fetchall()

        to_retire = []
        for row in rows:
            skill_id, last_used_str, success_rate, run_count, status = row
            should_retire = False

            if last_used_str:
                try:
                    last_used = datetime.fromisoformat(last_used_str)
                    if last_used < cutoff_date:
                        should_retire = True
                except (ValueError, TypeError, OSError):
                    pass

            if not should_retire and success_rate < 0.4 and run_count >= 5:
                should_retire = True

            if should_retire:
                to_retire.append(skill_id)

        if to_retire:
            conn.execute(
                """
                UPDATE skills
                SET status = 'retired'
                WHERE skill_id IN ({})
            """.format(",".join("?" * len(to_retire))),
                to_retire,
            )

            for skill_id in to_retire:
                delete_embedding(skill_id)

            conn.commit()
            logger.info(f"Auto-retired {len(to_retire)} stale skills")
    except Exception as e:
        logger.error(f"Failed to auto-retire stale skills: {e}")
    finally:
        conn.close()
