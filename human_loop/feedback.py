"""
Feedback Collector — captures structured human feedback on agent outputs.

Feedback is stored in the `agent_feedback` table and used to:
  1. Log approval/rejection reasoning from HITL decisions
  2. Capture free-form ratings on agent responses
  3. Feed future fine-tuning or prompt improvement pipelines
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── DDL ───────────────────────────────────────────────────────────────────────

_FEEDBACK_DDL = """
CREATE TABLE IF NOT EXISTS agent_feedback (
    feedback_id  TEXT PRIMARY KEY,
    session_id   TEXT,
    agent_name   TEXT NOT NULL,
    action       TEXT NOT NULL,
    task_id      TEXT,               -- linked HITL task_id if applicable
    rating       INTEGER,            -- 1-5 star scale (NULL = not rated)
    approved     INTEGER,            -- 1=approved, 0=rejected, NULL=neutral
    comment      TEXT,
    categories   TEXT,               -- JSON list: ["accuracy","speed","clarity"]
    metadata     TEXT,               -- JSON extra data
    created_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_agent   ON agent_feedback(agent_name);
CREATE INDEX IF NOT EXISTS idx_feedback_session ON agent_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating  ON agent_feedback(rating);
"""


def create_feedback_table() -> None:
    from integrations.data_warehouse.sqlite_client import get_db_connection
    with get_db_connection() as conn:
        for stmt in _FEEDBACK_DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        conn.commit()


# ── Record feedback ───────────────────────────────────────────────────────────

def record_feedback(
    agent_name: str,
    action:     str,
    rating:     Optional[int] = None,       # 1-5
    approved:   Optional[bool] = None,
    comment:    str = "",
    categories: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    task_id:    Optional[str] = None,
    metadata:   Optional[Dict[str, Any]] = None,
) -> str:
    """
    Save one feedback record. Returns the feedback_id.
    """
    import json
    feedback_id = str(uuid.uuid4())

    if rating is not None and not (1 <= rating <= 5):
        raise ValueError("Rating must be 1-5")

    from integrations.data_warehouse.sqlite_client import get_db_connection
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO agent_feedback
                   (feedback_id, session_id, agent_name, action, task_id,
                    rating, approved, comment, categories, metadata, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    feedback_id,
                    session_id,
                    agent_name,
                    action,
                    task_id,
                    rating,
                    (1 if approved else 0) if approved is not None else None,
                    comment,
                    json.dumps(categories or []),
                    json.dumps(metadata or {}),
                    time.time(),
                ),
            )
            conn.commit()
        logger.info("[Feedback] Recorded %s for agent=%s action=%s", feedback_id, agent_name, action)
    except Exception as e:
        logger.warning("[Feedback] Failed to record: %s", e)

    return feedback_id


# ── Query feedback ────────────────────────────────────────────────────────────

def get_feedback_stats(agent_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Return aggregate feedback stats: avg rating, approval rate, total count.
    """
    from integrations.data_warehouse.sqlite_client import get_db_connection
    try:
        where = "WHERE agent_name=?" if agent_name else ""
        params = [agent_name] if agent_name else []
        with get_db_connection() as conn:
            cur = conn.execute(
                f"SELECT COUNT(*), AVG(rating), AVG(CAST(approved AS REAL)) "
                f"FROM agent_feedback {where}",
                params,
            )
            row = cur.fetchone()
            return {
                "total_feedback":  row[0] or 0,
                "avg_rating":      round(row[1], 2) if row[1] else None,
                "approval_rate":   round(row[2], 3) if row[2] is not None else None,
            }
    except Exception:
        return {"total_feedback": 0, "avg_rating": None, "approval_rate": None}


def get_recent_feedback(
    agent_name: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Retrieve recent feedback records."""
    import json
    from integrations.data_warehouse.sqlite_client import get_db_connection
    try:
        where = "WHERE agent_name=?" if agent_name else ""
        params: List[Any] = [agent_name] if agent_name else []
        params.append(limit)
        with get_db_connection() as conn:
            cur = conn.execute(
                f"SELECT * FROM agent_feedback {where} ORDER BY created_at DESC LIMIT ?",
                params,
            )
            rows = []
            for row in cur.fetchall():
                r = dict(row)
                r["categories"] = json.loads(r.get("categories") or "[]")
                r["metadata"]   = json.loads(r.get("metadata") or "{}")
                rows.append(r)
            return rows
    except Exception as e:
        logger.warning("[Feedback] Query failed: %s", e)
        return []
