"""
HITLManager — Production-grade Human-in-the-Loop manager.

Responsibilities:
  - Accept NodeInterrupt signals from LangGraph nodes
  - Persist pending approval tasks to SQLite (survives restarts)
  - Resume a paused graph after a human decision
  - Broadcast approval requests to connected WebSocket clients
  - Auto-expire stale tasks after a configurable timeout
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from langgraph.errors import NodeInterrupt

logger = logging.getLogger(__name__)

# TTL for pending approvals (seconds). Tasks older than this are auto-rejected.
_DEFAULT_TTL_SECONDS = 3600   # 1 hour


class ApprovalTask:
    """Represents a single pending human approval."""

    def __init__(
        self,
        task_id:     str,
        agent_name:  str,
        action:      str,
        state:       Dict[str, Any],
        context:     str,
        risk_items:  List[str],
        risk_score:  float,
        session_id:  Optional[str] = None,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ):
        self.task_id     = task_id
        self.agent_name  = agent_name
        self.action      = action
        self.state       = state
        self.context     = context
        self.risk_items  = risk_items
        self.risk_score  = risk_score
        self.session_id  = session_id
        self.created_at  = time.time()
        self.expires_at  = self.created_at + ttl_seconds
        self.status      = "pending"     # pending | approved | rejected | expired

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id":     self.task_id,
            "agent_name":  self.agent_name,
            "action":      self.action,
            "context":     self.context,
            "risk_items":  self.risk_items,
            "risk_score":  self.risk_score,
            "session_id":  self.session_id,
            "status":      self.status,
            "created_at":  self.created_at,
            "expires_at":  self.expires_at,
        }


class HITLManager:
    """
    Manages human approval requests for high-risk agent actions.

    Usage inside a LangGraph node:
        manager = HITLManager(threshold=0.75)
        manager.request_approval(state, agent_name="meetings_communication",
                                 action="create_event", context="External attendees detected.")
        # ^ This raises NodeInterrupt, pausing the graph.

    Resume after human decision:
        new_state = manager.resume(task_id, approved=True, feedback="Looks good.")
    """

    def __init__(
        self,
        threshold:   float = 0.7,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ):
        self.threshold   = threshold
        self.ttl_seconds = ttl_seconds
        self._pending:  Dict[str, ApprovalTask] = {}
        self._callbacks: List[Callable[[ApprovalTask], None]] = []

        # Restore persisted tasks on startup
        self._restore_from_db()

    # ── Public API ────────────────────────────────────────────────────────────

    def request_approval(
        self,
        state:       Dict[str, Any],
        agent_name:  str,
        action:      str,
        context:     str,
        risk_items:  Optional[List[str]] = None,
        risk_score:  float = 0.8,
        session_id:  Optional[str] = None,
    ) -> None:
        """
        Create an approval task and raise NodeInterrupt to pause the graph.
        The graph resumes only after `resume()` is called with the task_id.
        """
        task_id = str(uuid.uuid4())
        task = ApprovalTask(
            task_id=task_id,
            agent_name=agent_name,
            action=action,
            state=state,
            context=context,
            risk_items=risk_items or [],
            risk_score=risk_score,
            session_id=session_id,
            ttl_seconds=self.ttl_seconds,
        )
        self._pending[task_id] = task
        self._persist_task(task)
        self._notify_callbacks(task)

        logger.info(
            "[HITL] Approval required task_id=%s agent=%s action=%s",
            task_id, agent_name, action,
        )
        raise NodeInterrupt(
            f"Human approval required.\n"
            f"task_id: {task_id}\n"
            f"agent: {agent_name} / action: {action}\n"
            f"context: {context}\n"
            f"risk_score: {risk_score:.2f}\n"
            f"Call POST /hitl/decision with task_id and approved=true/false."
        )

    def resume(
        self,
        task_id:  str,
        approved: bool,
        feedback: str = "",
    ) -> Dict[str, Any]:
        """
        Resume a paused graph with the human's decision.

        Returns: Updated state dict with human_decision + human_feedback injected.
        Raises: KeyError if task_id is unknown or expired.
        """
        task = self._pending.get(task_id)

        if not task:
            # Try loading from DB
            task = self._load_from_db(task_id)
            if not task:
                raise KeyError(f"Unknown HITL task: {task_id}")

        if task.is_expired():
            task.status = "expired"
            self._update_db_status(task_id, "expired")
            raise TimeoutError(f"HITL task {task_id} has expired.")

        task.status = "approved" if approved else "rejected"
        self._update_db_status(task_id, task.status, feedback=feedback)
        self._pending.pop(task_id, None)

        updated_state = dict(task.state)
        updated_state["human_decision"] = approved
        updated_state["human_feedback"] = feedback
        updated_state["approved"]        = approved
        updated_state["human_rejected"]  = not approved
        updated_state["requires_approval"] = False

        logger.info("[HITL] task_id=%s decision=%s", task_id, task.status)
        return updated_state

    def get_pending(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all active (non-expired) pending tasks, optionally filtered by session."""
        self._purge_expired()
        tasks = list(self._pending.values())
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        return [t.to_dict() for t in tasks]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._pending.get(task_id) or self._load_from_db(task_id)
        return task.to_dict() if task else None

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task (admin action)."""
        task = self._pending.pop(task_id, None)
        if task:
            task.status = "cancelled"
            self._update_db_status(task_id, "cancelled")
            return True
        return False

    def register_callback(self, fn: Callable[[ApprovalTask], None]) -> None:
        """Register a function to be called when a new approval task is created."""
        self._callbacks.append(fn)

    def should_interrupt(self, risk_score: float) -> bool:
        """Return True if the risk_score exceeds the configured threshold."""
        return risk_score >= self.threshold

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _notify_callbacks(self, task: ApprovalTask) -> None:
        for fn in self._callbacks:
            try:
                fn(task)
            except Exception as e:
                logger.warning("HITL callback failed: %s", e)

    def _purge_expired(self) -> None:
        expired = [tid for tid, t in self._pending.items() if t.is_expired()]
        for tid in expired:
            task = self._pending.pop(tid)
            task.status = "expired"
            self._update_db_status(tid, "expired")
            logger.warning("[HITL] task_id=%s auto-expired", tid)

    # ── Persistence (SQLite) ──────────────────────────────────────────────────

    def _persist_task(self, task: ApprovalTask) -> None:
        try:
            from human_loop.approval import persist_approval_task
            persist_approval_task(task)
        except Exception as e:
            logger.debug("HITL persist skipped: %s", e)

    def _load_from_db(self, task_id: str) -> Optional[ApprovalTask]:
        try:
            from human_loop.approval import load_approval_task
            return load_approval_task(task_id)
        except Exception:
            return None

    def _restore_from_db(self) -> None:
        try:
            from human_loop.approval import load_pending_approvals
            restored = load_pending_approvals()
            for task in restored:
                if not task.is_expired():
                    self._pending[task.task_id] = task
            if restored:
                logger.info("[HITL] Restored %d pending task(s) from DB.", len(restored))
        except Exception as e:
            logger.debug("HITL restore skipped: %s", e)

    def _update_db_status(
        self, task_id: str, status: str, feedback: str = ""
    ) -> None:
        try:
            from human_loop.approval import update_approval_status
            update_approval_status(task_id, status, feedback)
        except Exception as e:
            logger.debug("HITL status update skipped: %s", e)


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional[HITLManager] = None


def get_hitl_manager(threshold: float = 0.7) -> HITLManager:
    """Return the process-global HITLManager singleton."""
    global _manager
    if _manager is None:
        _manager = HITLManager(threshold=threshold)
    return _manager
