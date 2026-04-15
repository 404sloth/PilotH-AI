"""
WebSocket Manager — handles real-time client connections and broadcasts.

Responsibilities:
  - Accept WebSocket connections from frontend clients
  - Broadcast task progress updates
  - Push HITL approval requests
  - Send escalation notifications
  - Manage connection lifecycle (connect, disconnect, reconnect)
  - Group broadcasts by session_id
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        """Initialize connection registry."""
        # session_id → Set of WebSocket connections
        self._active_connections: Dict[str, Set[WebSocket]] = {}
        # global broadcast (session_id = None)
        self._broadcast_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Accept a WebSocket connection and register it.

        Args:
            websocket: FastAPI WebSocket instance
            session_id: Session context (None = broadcast channel)
        """
        await websocket.accept()

        async with self._lock:
            if session_id:
                if session_id not in self._active_connections:
                    self._active_connections[session_id] = set()
                self._active_connections[session_id].add(websocket)
                logger.info("[WebSocket] Connected session=%s total=%d", session_id, len(self._active_connections[session_id]))
            else:
                self._broadcast_connections.add(websocket)
                logger.info("[WebSocket] Connected to broadcast channel total=%d", len(self._broadcast_connections))

    async def disconnect(
        self,
        websocket: WebSocket,
        session_id: Optional[str] = None,
    ) -> None:
        """Remove a connection from the registry."""
        async with self._lock:
            if session_id and session_id in self._active_connections:
                self._active_connections[session_id].discard(websocket)
                if not self._active_connections[session_id]:
                    del self._active_connections[session_id]
                logger.info("[WebSocket] Disconnected session=%s", session_id)
            else:
                self._broadcast_connections.discard(websocket)
                logger.info("[WebSocket] Disconnected from broadcast")

    async def broadcast_to_session(
        self,
        session_id: str,
        message: Dict[str, Any],
    ) -> None:
        """
        Broadcast a message to all clients in a session.

        Args:
            session_id: Target session
            message: JSON-serializable dict to broadcast
        """
        if session_id not in self._active_connections:
            return

        connections = list(self._active_connections[session_id])
        disconnected = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.debug("[WebSocket] Send failed, marking for removal: %s", e)
                disconnected.append(connection)

        # Clean up dead connections
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    self._active_connections[session_id].discard(conn)

    async def broadcast_global(
        self,
        message: Dict[str, Any],
    ) -> None:
        """
        Broadcast a message to all subscribed clients (broadcast channel).
        Used for escalations, alerts, etc.

        Args:
            message: JSON-serializable dict to broadcast
        """
        connections = list(self._broadcast_connections)
        disconnected = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.debug("[WebSocket] Global send failed: %s", e)
                disconnected.append(connection)

        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    self._broadcast_connections.discard(conn)

    def get_session_connection_count(self, session_id: str) -> int:
        """Return number of active connections for a session."""
        return len(self._active_connections.get(session_id, set()))

    def get_broadcast_connection_count(self) -> int:
        """Return number of broadcast subscribers."""
        return len(self._broadcast_connections)

    def get_total_connections(self) -> int:
        """Return total active connections."""
        total = sum(len(conns) for conns in self._active_connections.values())
        return total + len(self._broadcast_connections)


class WebSocketManager:
    """
    High-level WebSocket manager that coordinates between
    agents, task queue, HITL manager, and WebSocket connections.
    """

    def __init__(self):
        """Initialize WebSocket manager."""
        self._connection_manager = ConnectionManager()

    # ── Connection Management ─────────────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        session_id: Optional[str] = None,
    ) -> None:
        """Accept and register a WebSocket connection."""
        await self._connection_manager.connect(websocket, session_id)

    async def disconnect(
        self,
        websocket: WebSocket,
        session_id: Optional[str] = None,
    ) -> None:
        """Unregister a WebSocket connection."""
        await self._connection_manager.disconnect(websocket, session_id)

    # ── Broadcast helpers (called by agents, task queue, HITL manager) ────────

    async def broadcast_task_progress(
        self,
        session_id: str,
        task_id: str,
        agent_name: str,
        action: str,
        step: str,
        total_steps: int,
        current_step: int,
        message: str,
        status: str = "running",
    ) -> None:
        """
        Broadcast a task progress update to a session.

        Args:
            session_id: Session to broadcast to
            task_id: Task identifier
            agent_name: Agent executing the task
            action: Agent action
            step: Current step name
            total_steps: Total workflow steps
            current_step: Current step index (1-based)
            message: Human-readable status message
            status: "running" | "completed" | "error"
        """
        from human_loop.ui_components import agent_progress_card

        card = agent_progress_card(
            session_id=session_id,
            agent_name=agent_name,
            action=action,
            step=step,
            total_steps=total_steps,
            current_step=current_step,
            message=message,
            status=status,
        )
        await self._connection_manager.broadcast_to_session(session_id, card)

    async def broadcast_approval_request(
        self,
        task_id: str,
        session_id: Optional[str] = None,
        agent_name: str = "",
        action: str = "",
        context: str = "",
        risk_score: float = 0.8,
        risk_items: Optional[List[str]] = None,
        expires_at: Optional[float] = None,
    ) -> None:
        """
        Broadcast an HITL approval request to all clients (or specific session).

        Args:
            task_id: HITL task identifier
            session_id: Optional session filter
            agent_name: Agent name
            action: Agent action
            context: Context for the approval
            risk_score: Risk score (0.0-1.0)
            risk_items: List of risk descriptions
            expires_at: Expiration timestamp
        """
        from human_loop.ui_components import approval_card
        import time

        if not expires_at:
            expires_at = time.time() + 3600  # 1 hour default

        card = approval_card(
            task_id=task_id,
            agent_name=agent_name,
            action=action,
            context=context,
            risk_score=risk_score,
            risk_items=risk_items or [],
            expires_at=expires_at,
            session_id=session_id,
        )

        if session_id:
            await self._connection_manager.broadcast_to_session(session_id, card)
        else:
            await self._connection_manager.broadcast_global(card)

    async def broadcast_approval_decision(
        self,
        task_id: str,
        status: str,
        feedback: str = "",
        session_id: Optional[str] = None,
    ) -> None:
        """
        Broadcast an approval decision result.

        Args:
            task_id: HITL task identifier
            status: "approved" | "rejected" | "expired" | "cancelled"
            feedback: Human feedback
            session_id: Optional session filter
        """
        from human_loop.ui_components import status_card

        message = {
            "approved": "✅ Approval accepted",
            "rejected": "❌ Approval rejected",
            "expired": "⏰ Approval expired",
            "cancelled": "🚫 Approval cancelled",
        }.get(status, "ℹ️ Decision updated")

        card = status_card(
            task_id=task_id,
            status=status,
            message=message,
            feedback=feedback,
        )

        if session_id:
            await self._connection_manager.broadcast_to_session(session_id, card)
        else:
            await self._connection_manager.broadcast_global(card)

    async def broadcast_escalation(
        self,
        task_id: str,
        level: str,
        agent_name: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Broadcast an escalation alert.

        Args:
            task_id: Task or context identifier
            level: "low" | "medium" | "high" | "critical"
            agent_name: Agent that escalated
            message: Escalation message
            session_id: Optional session filter
        """
        alert = {
            "component_type": "alert",
            "alert_type": "escalation",
            "level": level,
            "task_id": task_id,
            "agent_name": agent_name,
            "message": message,
        }

        if session_id:
            await self._connection_manager.broadcast_to_session(session_id, alert)
        else:
            await self._connection_manager.broadcast_global(alert)

    async def broadcast_error(
        self,
        error: str,
        agent_name: str,
        session_id: Optional[str] = None,
        recoverable: bool = False,
    ) -> None:
        """
        Broadcast an error notification.

        Args:
            error: Error message
            agent_name: Agent that errored
            session_id: Optional session filter
            recoverable: Whether the error can be retried
        """
        from human_loop.ui_components import error_card

        if not session_id:
            logger.error("[WebSocket] Error broadcast without session_id")
            return

        card = error_card(
            session_id=session_id,
            agent_name=agent_name,
            error=error,
            recoverable=recoverable,
        )
        await self._connection_manager.broadcast_to_session(session_id, card)

    async def broadcast_task_completed(
        self,
        session_id: str,
        task_id: str,
        agent_name: str,
        action: str,
        result: Dict[str, Any],
        summary: Optional[str] = None,
    ) -> None:
        """
        Broadcast task completion.

        Args:
            session_id: Session identifier
            task_id: Task identifier
            agent_name: Agent name
            action: Agent action
            result: Result data
            summary: Human-friendly summary (usually from LLM)
        """
        from observability.pii_sanitizer import sanitize_output

        # Sanitize result before broadcasting
        sanitized_result = sanitize_output(result)

        completion = {
            "component_type": "task_complete",
            "task_id": task_id,
            "agent_name": agent_name,
            "action": action,
            "result": sanitized_result,
            "summary": summary,
        }
        await self._connection_manager.broadcast_to_session(session_id, completion)

    # ── Connection stats ──────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return connection statistics."""
        return {
            "total_connections": self._connection_manager.get_total_connections(),
            "broadcast_subscribers": self._connection_manager.get_broadcast_connection_count(),
            "active_sessions": len(self._connection_manager._active_connections),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Return the process-global WebSocketManager singleton."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
