"""
Memory Manager — orchestrator-level interface to both session and global memory.
Provides a single API for storing/retrieving conversation context across agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified interface over session store (short-term) and
    global context (long-term, cross-agent).
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        from memory.session_store   import get_session_store
        from memory.global_context  import get_global_context
        self._session   = get_session_store().get_or_create(session_id)
        self._global    = get_global_context()

    # ── Session (short-term) ──────────────────────────────────────────────────

    def add_message(self, role: str, content: str) -> None:
        """Append a user or assistant message to the session."""
        self._session.add_message(role, content)

    def get_messages(self, last_n: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent messages from the session."""
        return self._session.messages[-last_n:]

    def set_session_context(self, key: str, value: Any) -> None:
        self._session.set_context(key, value)

    def get_session_context(self, key: str, default: Any = None) -> Any:
        return self._session.get_context(key, default)

    # ── Global (long-term, cross-agent) ───────────────────────────────────────

    def set_global(
        self,
        key: str,
        value: Any,
        agent: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        self._global.set(key, value, agent=agent, session_id=self.session_id, ttl_seconds=ttl_seconds)

    def get_global(self, key: str, default: Any = None) -> Any:
        return self._global.get(key, default)

    def log_decision(self, decision: str, agent: str, metadata: Optional[Dict] = None) -> None:
        self._global.log_decision(decision, agent=agent, session_id=self.session_id, metadata=metadata)

    def get_recent_decisions(self, n: int = 5) -> List[Dict]:
        return self._global.get_recent_decisions(n)

    # ── Composite helpers ─────────────────────────────────────────────────────

    def build_agent_context(self) -> Dict[str, Any]:
        """
        Build a context dict suitable for passing to an agent:
        recent messages + relevant global facts.
        """
        return {
            "session_id":       self.session_id,
            "recent_messages":  self.get_messages(5),
            "recent_decisions": self.get_recent_decisions(3),
            **{k: v for k, v in self._session.context.items()},
        }

    def save_agent_result(self, agent_name: str, result: Any) -> None:
        """Persist an agent's result both in session and global memory."""
        self.set_session_context(f"last_{agent_name}_result", result)
        self.set_global(
            f"agent_result:{self.session_id}:{agent_name}",
            result,
            agent=agent_name,
            ttl_seconds=3600,   # 1 hour
        )
