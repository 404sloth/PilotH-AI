"""
Vendor Management dedicated API routes.
Provides typed, purpose-specific endpoints for vendor operations.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


# ── Request / Response models ────────────────────────────────────────────────


class FindBestVendorRequest(BaseModel):
    service_required: str
    budget_monthly: Optional[float] = None
    min_quality_score: float = 75.0
    min_on_time_rate: float = 0.85
    required_tier: Optional[str] = None
    country: Optional[str] = None
    top_n: int = 5
    client_project_id: Optional[str] = None


class AssessVendorRequest(BaseModel):
    vendor_name: Optional[str] = None
    vendor_id: Optional[str] = None
    action: str = "full_assessment"


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", summary="Search vendors")
def search_vendors(
    name: Optional[str] = Query(None, description="Partial vendor name"),
    service_tag: Optional[str] = Query(
        None, description="Filter by service capability"
    ),
    country: Optional[str] = Query(None, description="Filter by country ISO code"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search and filter vendors from the database."""
    from integrations.data_warehouse.vendor_db import search_vendors as dal_search

    results = dal_search(
        vendor_name=name, service_tag=service_tag, country=country, limit=limit
    )
    return {"count": len(results), "vendors": results}


@router.get("/{vendor_id}/scorecard", summary="Get vendor scorecard")
def get_scorecard(vendor_id: str):
    """Return a comprehensive scorecard for a single vendor."""
    from integrations.data_warehouse.vendor_db import get_vendor_scorecard

    data = get_vendor_scorecard(vendor_id)
    if not data or not data.get("vendor"):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found.")
    return data


@router.get("/{vendor_id}/contract", summary="Get vendor contract")
def get_contract(vendor_id: str):
    """Return the most recent contract for a vendor."""
    from integrations.data_warehouse.vendor_db import get_contract_details

    contract = get_contract_details(vendor_id=vendor_id)
    if not contract:
        raise HTTPException(
            status_code=404, detail=f"No contract found for vendor '{vendor_id}'."
        )
    return contract


@router.get("/{vendor_id}/sla", summary="Get SLA compliance")
def get_sla(vendor_id: str, period_days: int = Query(30, ge=1, le=365)):
    """Return SLA compliance metrics for a vendor."""
    from integrations.data_warehouse.vendor_db import get_sla_compliance

    sla = get_sla_compliance(vendor_id=vendor_id, period_days=period_days)
    if not sla:
        raise HTTPException(
            status_code=404, detail=f"No SLA data found for vendor '{vendor_id}'."
        )
    return sla


@router.get("/{vendor_id}/milestones", summary="Get milestones")
def get_milestones(vendor_id: str, project_id: Optional[str] = Query(None)):
    """Return project milestones for a vendor."""
    from integrations.data_warehouse.vendor_db import get_milestones as dal_ms

    return {
        "vendor_id": vendor_id,
        "milestones": dal_ms(vendor_id=vendor_id, project_id=project_id),
    }


@router.post("/find-best", summary="Find best vendors for a service")
def find_best_vendors(body: FindBestVendorRequest):
    """
    Core matching endpoint: compare all vendors capable of a service and return ranked shortlist.
    This is the primary endpoint for new project vendor selection.
    """
    from backend.services.agent_registry import get_agent

    agent = get_agent("vendor_management")
    if not agent:
        raise HTTPException(
            status_code=503, detail="Vendor Management Agent not initialised."
        )

    result = agent.execute(
        {
            "action": "find_best",
            "service_required": body.service_required,
            "budget_monthly": body.budget_monthly,
            "min_quality_score": body.min_quality_score,
            "min_on_time_rate": body.min_on_time_rate,
            "required_tier": body.required_tier,
            "country": body.country,
            "top_n": body.top_n,
            "client_project_id": body.client_project_id,
        }
    )
    return result


@router.post("/assess", summary="Assess a specific vendor")
def assess_vendor(body: AssessVendorRequest):
    """
    Full assessment pipeline for a known vendor: evaluation, SLA, milestones, risk, summary.
    """
    from backend.services.agent_registry import get_agent

    agent = get_agent("vendor_management")
    if not agent:
        raise HTTPException(
            status_code=503, detail="Vendor Management Agent not initialised."
        )

    if not body.vendor_name and not body.vendor_id:
        raise HTTPException(status_code=422, detail="Provide vendor_name or vendor_id.")

    result = agent.execute(
        {
            "action": body.action,
            "vendor_name": body.vendor_name,
            "vendor_id": body.vendor_id,
        }
    )
    return result


@router.get("/selections/{client_project_id}", summary="Get saved vendor selections")
def get_selections(client_project_id: str):
    """Return previously persisted vendor selection decisions for a client project."""
    from integrations.data_warehouse.vendor_db import get_saved_selections

    return {
        "client_project_id": client_project_id,
        "selections": get_saved_selections(client_project_id),
    }
