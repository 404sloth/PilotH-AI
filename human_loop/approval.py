"""
HITL Approval DAL — all SQL for the `hitl_approvals` table.

This is the ONLY place that touches the hitl_approvals table.
Called exclusively by human_loop/manager.py.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from human_loop.manager import ApprovalTask

logger = logging.getLogger(__name__)

# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS hitl_approvals (
    task_id     TEXT PRIMARY KEY,
    agent_name  TEXT NOT NULL,
    action      TEXT NOT NULL,
    context     TEXT,
    risk_items  TEXT,           -- JSON array
    risk_score  REAL DEFAULT 0,
    session_id  TEXT,
    state_json  TEXT,           -- serialised agent state
    status      TEXT DEFAULT 'pending',  -- pending|approved|rejected|expired|cancelled
    feedback    TEXT DEFAULT '',
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS idx_hitl_status     ON hitl_approvals(status);
CREATE INDEX IF NOT EXISTS idx_hitl_session    ON hitl_approvals(session_id);
CREATE INDEX IF NOT EXISTS idx_hitl_created_at ON hitl_approvals(created_at DESC);
"""


def create_hitl_table() -> None:
    """Create the hitl_approvals table if it doesn't already exist."""
    from integrations.data_warehouse.sqlite_client import get_db_connection
    with get_db_connection() as conn:
        for stmt in _DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        conn.commit()


# ── Write operations ──────────────────────────────────────────────────────────

def persist_approval_task(task: "ApprovalTask") -> None:
    """Insert a new HITL task into the database."""
    from integrations.data_warehouse.sqlite_client import get_db_connection
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO hitl_approvals
                   (task_id, agent_name, action, context, risk_items, risk_score,
                    session_id, state_json, status, created_at, expires_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task.task_id,
                    task.agent_name,
                    task.action,
                    task.context,
                    json.dumps(task.risk_items),
                    task.risk_score,
                    task.session_id,
                    json.dumps(task.state, default=str),
                    task.status,
                    task.created_at,
                    task.expires_at,
                ),
            )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to persist HITL task %s: %s", task.task_id, e)


def update_approval_status(task_id: str, status: str, feedback: str = "") -> None:
    """Update the status and optional feedback for a task."""
    from integrations.data_warehouse.sqlite_client import get_db_connection
    try:
        with get_db_connection() as conn:
            conn.execute(
                """UPDATE hitl_approvals
                   SET status=?, feedback=?, resolved_at=?
                   WHERE task_id=?""",
                (status, feedback, time.time(), task_id),
            )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to update HITL status %s → %s: %s", task_id, status, e)


# ── Read operations ───────────────────────────────────────────────────────────

def load_approval_task(task_id: str) -> Optional["ApprovalTask"]:
    """Load a single task from DB and reconstruct an ApprovalTask object."""
    from integrations.data_warehouse.sqlite_client import get_db_connection
    from human_loop.manager import ApprovalTask
    try:
        with get_db_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM hitl_approvals WHERE task_id=?", (task_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return _row_to_task(dict(row))
    except Exception:
        return None


def load_pending_approvals() -> List["ApprovalTask"]:
    """Load all pending (non-resolved) tasks from DB — called on startup restart."""
    from integrations.data_warehouse.sqlite_client import get_db_connection
    from human_loop.manager import ApprovalTask
    try:
        with get_db_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM hitl_approvals WHERE status='pending' ORDER BY created_at DESC"
            )
            return [_row_to_task(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.warning("Could not load pending approvals: %s", e)
        return []


def get_approval_history(
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Query approval history with optional filters."""
    from integrations.data_warehouse.sqlite_client import get_db_connection
    try:
        clauses = []
        params: List[Any] = []
        if session_id:
            clauses.append("session_id=?")
            params.append(session_id)
        if agent_name:
            clauses.append("agent_name=?")
            params.append(agent_name)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        with get_db_connection() as conn:
            cur = conn.execute(
                f"SELECT task_id, agent_name, action, context, risk_score, "
                f"status, feedback, created_at, resolved_at "
                f"FROM hitl_approvals {where} ORDER BY created_at DESC LIMIT ?",
                params,
            )
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        logger.warning("History query failed: %s", e)
        return []


# ── Helper ────────────────────────────────────────────────────────────────────

def _row_to_task(row: Dict[str, Any]) -> "ApprovalTask":
    from human_loop.manager import ApprovalTask
    t = ApprovalTask.__new__(ApprovalTask)
    t.task_id    = row["task_id"]
    t.agent_name = row["agent_name"]
    t.action     = row["action"]
    t.context    = row.get("context", "")
    t.risk_items = json.loads(row.get("risk_items") or "[]")
    t.risk_score = row.get("risk_score", 0.0)
    t.session_id = row.get("session_id")
    t.state      = json.loads(row.get("state_json") or "{}")
    t.status     = row.get("status", "pending")
    t.created_at = row.get("created_at", time.time())
    t.expires_at = row.get("expires_at", time.time() + 3600)
    return t
