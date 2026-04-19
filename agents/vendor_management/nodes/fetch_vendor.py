"""
Node: fetch_vendor_node
Responsibility: resolve the vendor(s) needed for this workflow step.
For FIND_BEST: runs the VendorMatcherTool.
For others: runs the VendorSearchTool + VendorScorecardTool.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from langchain_core.messages import ToolMessage

from agents.vendor_management.schemas import VendorState

logger = logging.getLogger(__name__)


def fetch_vendor_node(state: VendorState) -> Dict[str, Any]:
    """
    Resolve vendor data based on the requested action.
    Populates vendor_records (FIND_BEST) or vendor_details (all other actions).
    """
    action = state.get("action", "full_assessment")

    if action == "search_vendors":
        return _run_vendor_discovery(state)
    if action == "find_best":
        return _run_matcher(state)
    else:
        return _run_search(state)


def _run_vendor_discovery(state: VendorState) -> Dict[str, Any]:
    from agents.vendor_management.tools.vendor_search import (
        VendorSearchInput,
        VendorSearchTool,
    )

    limit = state.get("top_n") or 50
    if limit < 10:
        limit = 10

    tool = VendorSearchTool()
    result = tool.execute(
        VendorSearchInput(
            vendor_name=state.get("vendor_name"),
            vendor_id=state.get("vendor_id"),
            service_tag=state.get("service_required"),
            industry=state.get("industry"),
            category=state.get("category"),
            country=state.get("country"),
            limit=min(limit, 50),
        )
    )

    if not result.found:
        scope_parts = []
        if state.get("service_required"): scope_parts.append(f"service '{state['service_required']}'")
        if state.get("industry"): scope_parts.append(f"industry '{state['industry']}'")
        if state.get("category"): scope_parts.append(f"category '{state['category']}'")
        scope = " and ".join(scope_parts) or "the requested criteria"
        
        return {
            "vendors": [],
            "requires_human_review": True,
            "messages": [
                ToolMessage(
                    content=f"No vendors found for {scope}.",
                    tool_call_id="fetch_vendor",
                )
            ],
        }

    vendors = [vendor.model_dump() for vendor in result.vendors]
    return {
        "vendors": vendors,
        "messages": [
            ToolMessage(
                content=f"Found {result.count} vendor(s) matching the requested filters.",
                tool_call_id="fetch_vendor",
            )
        ],
    }


def _run_matcher(state: VendorState) -> Dict[str, Any]:
    from agents.vendor_management.tools.vendor_matcher import (
        VendorMatcherTool,
        VendorMatcherInput,
    )

    service = state.get("service_required")
    if not service:
        return {
            "error": "service_required is mandatory for find_best action",
            "requires_human_review": True,
            "messages": [
                ToolMessage(
                    content="Missing service_required.", tool_call_id="fetch_vendor"
                )
            ],
        }

    tool = VendorMatcherTool()
    result = tool.execute(
        VendorMatcherInput(
            service_tag=service,
            budget_monthly=state.get("budget_monthly"),
            min_quality_score=state.get("min_quality_score", 75.0),
            min_on_time_rate=state.get("min_on_time_rate", 0.85),
            required_tier=state.get("required_tier"),
            country=state.get("country"),
            top_n=state.get("top_n", 5),
            client_project_id=state.get("client_project_id"),
        )
    )

    if result.candidates_found == 0:
        return {
            "ranked_vendors": [],
            "top_recommendation": None,
            "requires_human_review": True,
            "messages": [
                ToolMessage(
                    content=f"No vendors found for service '{service}' matching requirements.",
                    tool_call_id="fetch_vendor",
                )
            ],
        }

    ranked = [v.model_dump() for v in result.ranked_vendors]
    return {
        "ranked_vendors": ranked,
        "top_recommendation": result.top_recommendation,
        "vendor_id": result.top_recommendation,
        "messages": [
            ToolMessage(
                content=f"Found {result.candidates_found} vendor(s) for '{service}'. Top: {result.top_recommendation}",
                tool_call_id="fetch_vendor",
            )
        ],
    }


def _run_search(state: VendorState) -> Dict[str, Any]:
    from agents.vendor_management.tools.vendor_search import (
        VendorSearchTool,
        VendorSearchInput,
    )
    from agents.vendor_management.tools.vendor_scorecard import (
        VendorScorecardTool,
        VendorScorecardInput,
    )

    vendor_name = state.get("vendor_name")
    vendor_id = state.get("vendor_id")

    tool = VendorSearchTool()
    result = tool.execute(
        VendorSearchInput(
            vendor_name=vendor_name,
            vendor_id=vendor_id,
            limit=1,
        )
    )

    if not result.found:
        ident = vendor_name or vendor_id or "unspecified vendor"
        return {
            "error": f"Vendor '{ident}' not found",
            "requires_human_review": True,
            "messages": [
                ToolMessage(
                    content=f"Vendor '{ident}' not found in database.", tool_call_id="fetch_vendor"
                )
            ],
        }

    vendor = result.vendors[0]
    vendor_id = vendor.vendor_id

    # Fetch full scorecard
    sc_tool = VendorScorecardTool()
    scorecard = sc_tool.execute(VendorScorecardInput(vendor_id=vendor_id))

    # Use .get() or check attribute to be safe
    eval_breakdown = getattr(scorecard, "evaluation_breakdown", {})

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "vendor_details": vendor.model_dump(),
        "sla_compliance": scorecard.sla_compliance,
        "overall_score": scorecard.overall_score,
        "evaluation_scores": eval_breakdown,
        "strengths": getattr(scorecard, "strengths", []),
        "weaknesses": getattr(scorecard, "weaknesses", []),
        "messages": [
            ToolMessage(
                content=f"Fetched vendor: {vendor.name} (ID: {vendor_id}, score: {scorecard.overall_score:.1f}/100)",
                tool_call_id="fetch_vendor",
            )
        ],
    }
