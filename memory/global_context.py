"""
Global Context — shared cross-agent memory for decisions, summaries, and facts.
All agents read/write through this interface.

Storage: SQLite `global_context` table (persistent across restarts).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from integrations.data_warehouse.sqlite_client import get_db_connection

logger = logging.getLogger(__name__)

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS global_context (
    key         TEXT    PRIMARY KEY,
    value_json  TEXT    NOT NULL,
    agent       TEXT,
    session_id  TEXT,
    updated_at  REAL    NOT NULL,
    ttl_seconds REAL    DEFAULT NULL    -- NULL = no expiry
)
"""

_INDEX_DDL = "CREATE INDEX IF NOT EXISTS idx_gc_agent ON global_context(agent)"


def _ensure_table() -> None:
    with get_db_connection() as conn:
        conn.execute(_TABLE_DDL)
        conn.execute(_INDEX_DDL)
        conn.commit()


class GlobalContext:
    """
    Persistent key-value store shared across all agents and sessions.
    Values are JSON-serialised for flexibility.
    """

    def __init__(self) -> None:
        _ensure_table()

    # ------------------------------------------------------------------
    def set(
        self,
        key: str,
        value: Any,
        agent: Optional[str] = None,
        session_id: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO global_context(key, value_json, agent, session_id, updated_at, ttl_seconds)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json  = excluded.value_json,
                    agent       = excluded.agent,
                    session_id  = excluded.session_id,
                    updated_at  = excluded.updated_at,
                    ttl_seconds = excluded.ttl_seconds
                """,
                (key, json.dumps(value), agent, session_id, time.time(), ttl_seconds),
            )
            conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT value_json, updated_at, ttl_seconds FROM global_context WHERE key=?",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return default
            # Check TTL
            if row["ttl_seconds"] is not None:
                age = time.time() - row["updated_at"]
                if age > row["ttl_seconds"]:
                    self.delete(key)
                    return default
            return json.loads(row["value_json"])

    def delete(self, key: str) -> None:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM global_context WHERE key=?", (key,))
            conn.commit()

    def list_by_agent(self, agent: str) -> Dict[str, Any]:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT key, value_json FROM global_context WHERE agent=?", (agent,)
            )
            return {r["key"]: json.loads(r["value_json"]) for r in cur.fetchall()}

    def append_to_list(
        self, key: str, item: Any, max_items: int = 100, **kwargs
    ) -> None:
        """Append an item to a stored list (FIFO, bounded)."""
        existing = self.get(key, [])
        if not isinstance(existing, list):
            existing = []
        existing.append(item)
        if len(existing) > max_items:
            existing = existing[-max_items:]
        self.set(key, existing, **kwargs)

    def log_decision(
        self,
        decision: str,
        agent: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Convenience: append a decision to the shared decision log."""
        entry = {
            "decision": decision,
            "agent": agent,
            "session_id": session_id,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self.append_to_list(
            "decision_log",
            entry,
            max_items=500,
            agent=agent,
            session_id=session_id,
        )
        logger.info("Decision logged by '%s': %s", agent, decision[:80])

    def get_recent_decisions(self, n: int = 10) -> List[Dict]:
        entries = self.get("decision_log", [])
        return entries[-n:]


# Module-level singleton
_ctx: Optional[GlobalContext] = None


def get_global_context() -> GlobalContext:
    global _ctx
    if _ctx is None:
        _ctx = GlobalContext()
    return _ctx
