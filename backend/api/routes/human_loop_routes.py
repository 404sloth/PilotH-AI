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
    approval_id: str
    approved:    bool
    feedback:    Optional[str] = ""


@router.get("/pending", summary="List pending HITL approvals")
def list_pending():
    """Return all pending human-approval requests."""
    from backend.services.agent_registry import get_agent
    agent = get_agent("vendor_management")
    if not agent or not agent.hitl:
        return {"pending": []}
    return {"pending": list(agent.hitl.pending.keys())}


@router.post("/decide", summary="Submit HITL decision")
def submit_decision(body: HITLDecisionRequest):
    """
    Approve or reject a pending HITL interrupt.
    The resumed workflow will continue with the human decision injected into state.
    """
    from backend.services.agent_registry import get_agent
    agent = get_agent("vendor_management")
    if not agent or not agent.hitl:
        raise HTTPException(status_code=503, detail="HITL manager not available.")

    if body.approval_id not in agent.hitl.pending:
        raise HTTPException(status_code=404, detail=f"Approval '{body.approval_id}' not found.")

    updated_state = agent.hitl.resume(
        approval_id=body.approval_id,
        decision=body.approved,
        feedback=body.feedback or "",
    )
    return {
        "approval_id": body.approval_id,
        "approved":    body.approved,
        "resumed_state_keys": list(updated_state.keys()),
    }
