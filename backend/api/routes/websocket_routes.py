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
                if not isinstance(data, dict):
                    await websocket.send_json({"status": "ERROR", "message": "Invalid message payload"})
                    continue

                message_type = data.get("type")
                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if message_type == "query":
                    from backend.api.dependencies import get_settings
                    from orchestrator.controller import OrchestratorController
                    import asyncio

                    prompt = (data.get("message") or "").strip()
                    if not prompt:
                        await websocket.send_json({"status": "ERROR", "message": "Message is required"})
                        continue

                    thread_id = data.get("thread_id") or session_id
                    agent_hint = data.get("agent_hint")
                    controller = OrchestratorController(get_settings())
                    result = await asyncio.to_thread(
                        controller.handle,
                        message=prompt,
                        session_id=thread_id,
                        context={
                            "conversation_id": thread_id,
                            "user_message_metadata": (
                                {"agent_hint": agent_hint} if agent_hint else {}
                            ),
                        }
                        if thread_id
                        else {"user_message_metadata": {"agent_hint": agent_hint}}
                        if agent_hint
                        else {},
                        agent_hint=agent_hint,
                    )
                    await websocket.send_json(
                        {
                            "status": "SUCCESS",
                            "message": result.get("response", ""),
                            "thread_id": result.get("conversation_id") or thread_id,
                            "session_id": result.get("session_id"),
                            "agent": result.get("metadata", {}).get("agent"),
                            "action": result.get("metadata", {}).get("action"),
                            "data": result.get("data", {}),
                            "metadata": result.get("metadata", {}),
                        }
                    )
                    continue

                if message_type in {"approve", "deny"}:
                    task_id = data.get("task_id")
                    if not task_id:
                        await websocket.send_json(
                            {
                                "status": "ERROR",
                                "message": "task_id is required for approve/deny actions",
                            }
                        )
                        continue

                    from human_loop.manager import get_hitl_manager
                    import asyncio

                    manager = get_hitl_manager()
                    approved = message_type == "approve"
                    try:
                        await asyncio.to_thread(
                            manager.resume,
                            task_id=task_id,
                            approved=approved,
                            feedback=data.get("feedback", ""),
                        )
                        await websocket.send_json(
                            {
                                "status": "SUCCESS",
                                "message": "Approval accepted" if approved else "Approval denied",
                                "task_id": task_id,
                            }
                        )
                    except Exception as exc:
                        await websocket.send_json(
                            {"status": "ERROR", "message": str(exc), "task_id": task_id}
                        )
                    continue

                await websocket.send_json(
                    {"status": "ERROR", "message": f"Unsupported message type: {message_type}"}
                )
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
