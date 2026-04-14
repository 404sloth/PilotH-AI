"""
Session Store — short-term, in-process memory keyed by session_id.
Stores conversation history, current task context, and agent state.
Backed by an in-memory dict (upgrade to Redis for production).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600  # sessions expire after 1 hour of inactivity


class Session:
    def __init__(self, session_id: str) -> None:
        self.session_id   = session_id
        self.messages:    List[Dict[str, Any]] = []
        self.context:     Dict[str, Any]       = {}
        self.agent_state: Dict[str, Any]       = {}
        self.created_at   = time.time()
        self.last_active  = time.time()

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content, "ts": time.time()})
        self.last_active = time.time()

    def set_context(self, key: str, value: Any) -> None:
        self.context[key] = value
        self.last_active  = time.time()

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > _TTL_SECONDS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id":  self.session_id,
            "messages":    self.messages[-20:],   # last 20 only for brevity
            "context":     self.context,
            "created_at":  self.created_at,
            "last_active": self.last_active,
        }


class SessionStore:
    """
    Thread-safe, in-process session store with automatic TTL expiry.
    """

    def __init__(self) -> None:
        self._lock     = threading.Lock()
        self._sessions: Dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.is_expired():
                session = Session(session_id)
                self._sessions[session_id] = session
                logger.debug("Created new session: %s", session_id)
            return session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session and session.is_expired():
                del self._sessions[session_id]
                return None
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def purge_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
            for sid in expired:
                del self._sessions[sid]
            return len(expired)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._sessions.values() if not s.is_expired())


# Module-level singleton
_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
