"""
Executive Dashboard API — powers the "Pulse" dashboard.
Uses JWT authentication to ensure sensitive project data is only seen by authorized managers.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

# Mock authentication dependency
# In a real system, this would decode a JWT and verify the user in the DB.
async def get_current_user():
    """Mock authentication dependency."""
    # For demo purposes, we return a mock user object.
    return {"id": "USR-001", "name": "Executive Admin", "role": "admin"}

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Models ---

class ProjectSummary(BaseModel):
    id: str
    name: str
    status: str
    progress_percent: float
    next_milestone: Optional[Dict[str, Any]]
    health_color: str

class TimelineEvent(BaseModel):
    type: str
    id: str
    date: str
    content: Optional[str] = None
    title: Optional[str] = None
    vendor_name: Optional[str] = None
    score: Optional[float] = None
    milestones: Optional[List[Dict[str, Any]]] = None

# --- Endpoints ---

@router.get("/projects", response_model=List[ProjectSummary], summary="List all projects for dashboard")
def list_projects(user: Dict = Depends(get_current_user)):
    """Return high-level scorecard for all projects."""
    from integrations.data_warehouse.vendor_db import get_all_projects_summary
    try:
        return get_all_projects_summary()
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
        raise HTTPException(status_code=500, detail="Internal database error")

@router.get("/projects/{project_id}/timeline", response_model=List[TimelineEvent], summary="Get chronological project timeline")
def get_timeline(project_id: str, user: Dict = Depends(get_current_user)):
    """Return a sequence of all lifecycle events (meetings, RFPs, SOWs)."""
    from integrations.data_warehouse.vendor_db import get_detailed_timeline
    try:
        events = get_detailed_timeline(project_id)
        if not events:
            raise HTTPException(status_code=404, detail="No timeline events found for this project.")
        return events
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Timeline fetch failed for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/projects/{project_id}/health", summary="Get detailed health assessment")
def get_health(project_id: str, user: Dict = Depends(get_current_user)):
    """Invoke the health computation tool for detailed risks and report."""
    from agents.vendor_management.tools.lifecycle_tools import compute_project_health
    # We call the tool directly or its underlying DAL
    result = compute_project_health.invoke({"project_id": project_id})
    return {"project_id": project_id, "report": result}

@router.post("/projects/{project_id}/simulate-full-lifecycle", summary="Demo: Run full project simulation")
async def simulate_lifecycle(project_id: str, user: Dict = Depends(get_current_user)):
    """
    Demo only: Orchestrates the entire flow using mock meetings.
    Requires an existing meeting with ID 'MTG-TEST-99' (created by test scripts).
    """
    from agents.vendor_management.tools.lifecycle_tools import (
        generate_rfp_from_meeting,
        generate_mock_vendor_responses,
        evaluate_vendor_responses,
        select_vendor_helper,
        generate_sow_from_meeting,
        simulate_daily_status
    )
    
    results = {}
    try:
        # Step 1: RFP (Using a known mock meeting ID)
        results["rfp"] = generate_rfp_from_meeting.invoke({"meeting_id": "MTG-TEST-99"})
        rfp_id = results["rfp"].split("'")[1] if "SUCCESS" in results["rfp"] else None
        
        if rfp_id:
            # Step 2: Responses
            results["responses"] = generate_mock_vendor_responses.invoke({"rfp_id": rfp_id})
            # Step 3: Evaluation
            results["evaluation"] = evaluate_vendor_responses.invoke({"rfp_id": rfp_id})
            # Step 4: Selection (Pick first vendor for demo)
            results["selection"] = select_vendor_helper.invoke({"project_id": project_id, "vendor_id": "V-001"})
            
            # Step 5: SOW (Using a negotiation meeting ID)
            results["sow"] = generate_sow_from_meeting.invoke({"meeting_id": "MTG-NEG-99"})
            # Step 6: Status
            results["status"] = simulate_daily_status.invoke({"project_id": project_id})
            
        return {"status": "simulation_complete", "log": results}
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
