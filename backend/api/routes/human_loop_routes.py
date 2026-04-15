"""
Human-in-the-Loop (HITL) API routes.
Allows external systems to approve/reject pending AI decisions.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class HITLDecisionRequest(BaseModel):
    task_id: str
    approved: bool
    feedback: Optional[str] = ""


@router.get("/pending", summary="List pending HITL approvals")
def list_pending(session_id: Optional[str] = None):
    """Return all pending human-approval requests."""
    from human_loop.manager import get_hitl_manager

    manager = get_hitl_manager()
    pending_tasks = manager.get_pending(session_id=session_id)
    return {"pending": pending_tasks, "count": len(pending_tasks)}


@router.get("/{task_id}", summary="Get HITL task details")
def get_hitl_task(task_id: str):
    """Get details of a specific HITL task."""
    from human_loop.manager import get_hitl_manager

    manager = get_hitl_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return task


@router.post("/decision", summary="Submit HITL decision")
def submit_decision(body: HITLDecisionRequest):
    """
    Approve or reject a pending HITL interrupt.
    The resumed workflow will continue with the human decision injected into state.
    """
    from human_loop.manager import get_hitl_manager

    manager = get_hitl_manager()
    
    try:
        updated_state = manager.resume(
            task_id=body.task_id,
            approved=body.approved,
            feedback=body.feedback or "",
        )
        return {
            "task_id": body.task_id,
            "approved": body.approved,
            "status": "resumed",
            "resumed_state_keys": list(updated_state.keys()),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel", summary="Cancel a HITL task")
def cancel_task(task_id: str):
    """Cancel an existing HITL approval task."""
    from human_loop.manager import get_hitl_manager

    manager = get_hitl_manager()
    if manager.cancel(task_id):
        return {"task_id": task_id, "status": "cancelled"}
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
