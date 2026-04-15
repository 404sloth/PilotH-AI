"""
WebSocket routes — handles real-time client connections for agents updates.

Endpoints:
  - GET /ws[?session_id=abc123]  — Subscribe to session updates
  - GET /ws/broadcast            — Subscribe to global broadcasts
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.websocket.manager import get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = None,
):
    """
    WebSocket endpoint for session-specific updates.

    Usage (client):
      const ws = new WebSocket("ws://localhost:8000/ws?session_id=abc123");
      ws.onmessage = (ev) => console.log(JSON.parse(ev.data));

    Broadcasts:
      - Task progress updates
      - HITL approval requests
      - Task completion results
      - Errors and escalations
    """
    ws_manager = get_websocket_manager()

    try:
        # Accept and register connection
        await ws_manager.connect(websocket, session_id)

        if session_id:
            logger.info("[WS] Client connected to session=%s", session_id)
        else:
            logger.info("[WS] Client connected to broadcast channel")

        # Keep connection alive
        while True:
            # Wait for client message (heartbeat or explicit message)
            try:
                data = await websocket.receive_json()
                # Handle ping / client messages if needed
                if isinstance(data, dict) and data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                # Client disconnected or sent invalid data
                break

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except Exception as e:
        logger.warning("[WS] WebSocket error: %s", e)
    finally:
        await ws_manager.disconnect(websocket, session_id)


@router.websocket("/ws/broadcast")
async def websocket_broadcast_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for global broadcast channel.
    Used for system-wide alerts, escalations, etc.

    Receives:
      - Escalation alerts (level: critical, high, medium, low)
      - System notifications
      - Global status updates
    """
    ws_manager = get_websocket_manager()

    try:
        await ws_manager.connect(websocket, session_id=None)  # None = broadcast channel
        logger.info("[WS] Client connected to broadcast channel")

        while True:
            try:
                data = await websocket.receive_json()
                if isinstance(data, dict) and data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                break

    except WebSocketDisconnect:
        logger.info("[WS] Broadcast client disconnected")
    except Exception as e:
        logger.warning("[WS] Broadcast WebSocket error: %s", e)
    finally:
        await ws_manager.disconnect(websocket, session_id=None)


@router.get("/ws/stats")
async def websocket_stats():
    """
    Get current WebSocket connection statistics.

    Returns:
      - total_connections: Total active WebSocket clients
      - broadcast_subscribers: Clients on broadcast channel
      - active_sessions: Number of sessions with connections
    """
    ws_manager = get_websocket_manager()
    return ws_manager.get_stats()
