"""
intent_learner.py — Learned intent→tool routing cache (Tier 3 of the intent pipeline).

After every command execution the orchestrator calls::

    record_route(intent, tools, success)

On the next ``lookup_route(intent)`` the module checks:

1. **Exact normalised match** in SQLite (O(1) key lookup).
2. **Embedding similarity** via the already-loaded ``skill_embedder`` model
   (sentence-transformers in-process, threshold 0.78).

The module writes to the shared ``MEMORY_DB`` SQLite file in the
``intent_routes`` table so no extra file is needed.

Layer boundary
--------------
This module is low-level infrastructure.  It MUST NOT import from
``brain/``, ``core/orchestrator``, or ``tools/``.
"""

import json
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path

from settings import MEMORY_DB

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_CONFIDENCE_INIT_SUCCESS: float = 0.65
_CONFIDENCE_INIT_FAILURE: float = 0.35
_CONFIDENCE_HIT_DELTA: float = 0.10
_CONFIDENCE_MISS_DELTA: float = 0.15
_CONFIDENCE_MIN_RETURN: float = 0.55  # routes below this are not returned
_CONFIDENCE_STALE_MAX: float = 0.40  # stale gate — combined with age check
_STALE_DAYS: float = 30.0
_EMBEDDING_THRESHOLD: float = 0.78
_EMBEDDING_SCAN_LIMIT: int = 500

# ── Module-level state ────────────────────────────────────────────────────────

_db_ready: bool = False  # lazy-init flag


# ── Helpers ───────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Lowercase, replace punctuation with space, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)  # replace punctuation with space
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _ensure_db() -> None:
    """Create the ``intent_routes`` table if it doesn't exist (lazy init)."""
    global _db_ready
    if _db_ready:
        return
    db_path: Path = Path(MEMORY_DB)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intent_routes (
                    route_id    TEXT PRIMARY KEY,
                    intent_text TEXT NOT NULL,
                    tools_json  TEXT NOT NULL,
                    hits        INTEGER DEFAULT 0,
                    misses      INTEGER DEFAULT 0,
                    confidence  REAL    DEFAULT 0.5,
                    source      TEXT    DEFAULT 'llm',
                    last_used   REAL    DEFAULT 0,
                    created_at  REAL    NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_intent_text "
                "ON intent_routes (intent_text)"
            )
            conn.commit()
            _db_ready = True
            logger.debug("intent_learner: DB table ensured")
        finally:
            conn.close()
    except Exception as exc:
        logger.error(f"intent_learner._ensure_db failed: {exc}")


def _touch_route(route_id: str) -> None:
    """Update ``last_used`` timestamp for *route_id* (fire-and-forget)."""
    try:
        conn = sqlite3.connect(str(MEMORY_DB))
        try:
            conn.execute(
                "UPDATE intent_routes SET last_used = ? WHERE route_id = ?",
                (time.time(), route_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.debug(f"intent_learner._touch_route failed (non-fatal): {exc}")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity — no extra dependencies."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _is_stale(last_used: float, confidence: float) -> bool:
    """Return True if a route is too old and too uncertain to trust."""
    if confidence >= _CONFIDENCE_STALE_MAX:
        return False  # high-confidence routes never go stale
    age_days = (time.time() - last_used) / 86_400.0
    return age_days >= _STALE_DAYS


# ── Public API ────────────────────────────────────────────────────────────────


def lookup_route(intent: str) -> list[str] | None:
    """Return a cached tool list if a confident match is found, else ``None``.

    Lookup order
    ------------
    1. Exact normalised match in SQLite.
    2. Embedding cosine similarity (threshold 0.78) over up to 500 active rows.
    """
    try:
        _ensure_db()
        if not _db_ready:
            return None

        norm = _normalize(intent)

        conn = sqlite3.connect(str(MEMORY_DB))
        try:
            # ── Tier 1: exact match ─────────────────────────────────────
            cur = conn.execute(
                "SELECT route_id, tools_json, confidence, last_used "
                "FROM intent_routes "
                "WHERE intent_text = ? AND confidence >= ?",
                (norm, _CONFIDENCE_MIN_RETURN),
            )
            row = cur.fetchone()
            if row:
                route_id, tools_json, confidence, last_used = row
                if _is_stale(last_used, confidence):
                    logger.debug(
                        f"intent_learner: exact match '{norm}' is stale — skipping"
                    )
                else:
                    tools = json.loads(tools_json)
                    logger.info(
                        f"intent_learner [EXACT] intent='{norm}' "
                        f"tools={tools} conf={confidence:.2f}"
                    )
                    _touch_route(route_id)
                    return tools

            # ── Tier 2: embedding similarity ────────────────────────────
            try:
                from skills import skill_embedder  # type: ignore[import]

                query_vec: list[float] = skill_embedder.embed_text(intent)
            except Exception as emb_exc:
                logger.debug(
                    f"intent_learner: embedder unavailable ({emb_exc}) — skipping"
                )
                return None

            if not query_vec:
                return None  # embedder not ready yet

            cur = conn.execute(
                "SELECT route_id, intent_text, tools_json, confidence, last_used "
                "FROM intent_routes "
                "WHERE confidence >= ? "
                "ORDER BY last_used DESC "
                "LIMIT ?",
                (_CONFIDENCE_MIN_RETURN, _EMBEDDING_SCAN_LIMIT),
            )
            rows = cur.fetchall()

        finally:
            conn.close()

        best_score: float = 0.0
        best_route_id: str | None = None
        best_tools: list[str] | None = None

        for route_id, intent_text, tools_json, confidence, last_used in rows:
            if _is_stale(last_used, confidence):
                continue
            try:
                row_vec = skill_embedder.embed_text(intent_text)
            except Exception:
                continue
            if not row_vec:
                continue
            sim = _cosine_similarity(query_vec, row_vec)
            if sim > best_score:
                best_score = sim
                best_route_id = route_id
                best_tools = json.loads(tools_json)

        if best_score >= _EMBEDDING_THRESHOLD and best_tools is not None:
            logger.info(
                f"intent_learner [EMBED] intent='{norm}' "
                f"tools={best_tools} sim={best_score:.3f}"
            )
            _touch_route(best_route_id)  # type: ignore[arg-type]
            return best_tools

        return None

    except Exception as exc:
        logger.error(f"intent_learner.lookup_route failed (non-fatal): {exc}")
        return None


def record_route(
    intent: str,
    tools: list[str],
    success: bool,
    source: str = "llm",
) -> str:
    """Record or update a route and return its ``route_id``.

    - If an exact normalised match already exists the row is updated
      (confidence adjusted, hit/miss counter incremented).
    - Otherwise a new row is inserted.
    """
    try:
        _ensure_db()
        if not _db_ready:
            return ""

        norm = _normalize(intent)
        tools_json = json.dumps(tools)
        now = time.time()

        conn = sqlite3.connect(str(MEMORY_DB))
        try:
            cur = conn.execute(
                "SELECT route_id, confidence, hits, misses "
                "FROM intent_routes WHERE intent_text = ?",
                (norm,),
            )
            existing = cur.fetchone()

            if existing:
                route_id, confidence, hits, misses = existing
                if success:
                    confidence = min(1.0, confidence + _CONFIDENCE_HIT_DELTA)
                    hits += 1
                else:
                    confidence = max(0.0, confidence - _CONFIDENCE_MISS_DELTA)
                    misses += 1
                conn.execute(
                    """
                    UPDATE intent_routes
                    SET tools_json  = ?,
                        confidence  = ?,
                        hits        = ?,
                        misses      = ?,
                        source      = ?,
                        last_used   = ?
                    WHERE route_id = ?
                    """,
                    (tools_json, confidence, hits, misses, source, now, route_id),
                )
                logger.debug(
                    f"intent_learner: updated route '{norm}' "
                    f"success={success} conf={confidence:.2f}"
                )
            else:
                route_id = str(uuid.uuid4())
                confidence = (
                    _CONFIDENCE_INIT_SUCCESS if success else _CONFIDENCE_INIT_FAILURE
                )
                conn.execute(
                    """
                    INSERT INTO intent_routes
                        (route_id, intent_text, tools_json,
                         hits, misses, confidence, source, last_used, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route_id,
                        norm,
                        tools_json,
                        1 if success else 0,
                        0 if success else 1,
                        confidence,
                        source,
                        now,
                        now,
                    ),
                )
                logger.debug(
                    f"intent_learner: new route '{norm}' "
                    f"success={success} conf={confidence:.2f} id={route_id}"
                )

            conn.commit()
        finally:
            conn.close()

        return route_id

    except Exception as exc:
        logger.error(f"intent_learner.record_route failed (non-fatal): {exc}")
        return ""


def get_stats() -> dict:
    """Return ``{'total': N, 'active': N}`` for display / debugging.

    *total*  — every row in ``intent_routes``.
    *active* — rows with ``confidence >= 0.55`` that are not stale.
    """
    try:
        _ensure_db()
        if not _db_ready:
            return {"total": 0, "active": 0}

        now = time.time()
        stale_cutoff = now - (_STALE_DAYS * 86_400.0)

        conn = sqlite3.connect(str(MEMORY_DB))
        try:
            total_row = conn.execute("SELECT COUNT(*) FROM intent_routes").fetchone()
            total: int = total_row[0] if total_row else 0

            # Active = confidence is high enough OR last_used is recent enough
            # (mirrors the stale logic in _is_stale exactly):
            #   NOT stale  ⟺  confidence >= 0.40  OR  last_used > stale_cutoff
            active_row = conn.execute(
                """
                SELECT COUNT(*) FROM intent_routes
                WHERE confidence >= ?
                  AND (confidence >= ? OR last_used > ?)
                """,
                (_CONFIDENCE_MIN_RETURN, _CONFIDENCE_STALE_MAX, stale_cutoff),
            ).fetchone()
            active: int = active_row[0] if active_row else 0
        finally:
            conn.close()

        return {"total": total, "active": active}

    except Exception as exc:
        logger.error(f"intent_learner.get_stats failed (non-fatal): {exc}")
        return {"total": 0, "active": 0}
