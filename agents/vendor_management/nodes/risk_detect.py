"""
Node: risk_detect_node
Responsibility: derive risk items from evaluation scores and operational data.
Rule-based with LLM enrichment for mitigation advice.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from agents.vendor_management.schemas import VendorState

logger = logging.getLogger(__name__)


from langchain_core.runnables import RunnableConfig

def risk_detect_node(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Identify risks based on evaluation scores, SLA breaches, and milestone delays.
    Appends LLM-generated mitigation advice if an LLM is available.
    """
    if state.get("error"):
        return {}

    action = state.get("action", "full_assessment")
    # Risk detection is meaningful only for single-vendor actions
    if action == "find_best":
        return {}

    scores = state.get("evaluation_scores") or {}
    sla_data = state.get("sla_data") or {}
    milestones = state.get("milestone_data") or []
    vendor = state.get("vendor_details") or {}

    risks: List[Dict[str, str]] = []

    # ---- Quality / reliability risks ----
    if scores.get("quality", 100) < 70:
        risks.append(
            {
                "category": "quality",
                "description": f"Quality score is below threshold: {scores['quality']:.0f}/100",
                "severity": "high",
                "mitigation": "Initiate quality improvement plan with vendor",
            }
        )

    if scores.get("reliability", 100) < 75:
        risks.append(
            {
                "category": "operational",
                "description": f"Reliability score is {scores.get('reliability', 0):.0f}/100 — inconsistent delivery",
                "severity": "high",
                "mitigation": "Implement weekly delivery tracking and escalation process",
            }
        )

    # ---- SLA risks ----
    compliance = (sla_data or {}).get("overall_compliance", 100.0)
    if compliance < 90:
        risks.append(
            {
                "category": "compliance",
                "description": f"SLA compliance at {compliance:.1f}% — below 90% threshold",
                "severity": "high" if compliance < 80 else "medium",
                "mitigation": "Initiate formal SLA remediation plan",
            }
        )

    for breach in (sla_data or {}).get("breaches", []):
        risks.append(
            {
                "category": "sla_breach",
                "description": breach,
                "severity": "medium",
                "mitigation": "Review with vendor account manager within 5 business days",
            }
        )

    # ---- Milestone / project risks ----
    delayed = [m for m in milestones if m.get("status") == "delayed"]
    if delayed:
        risks.append(
            {
                "category": "project",
                "description": f"{len(delayed)} milestone(s) delayed, worst overdue by {max(m.get('days_overdue', 0) for m in delayed)}d",
                "severity": "high",
                "mitigation": "Hold emergency project review and revise timeline",
            }
        )

    at_risk = [m for m in milestones if m.get("status") == "at_risk"]
    if at_risk:
        risks.append(
            {
                "category": "project",
                "description": f"{len(at_risk)} milestone(s) flagged at-risk",
                "severity": "medium",
                "mitigation": "Allocate additional resources or adjust scope",
            }
        )

    # ---- Cost risk ----
    if scores.get("cost", 100) < 60:
        risks.append(
            {
                "category": "financial",
                "description": "Vendor costs significantly above market rate",
                "severity": "medium",
                "mitigation": "Renegotiate contract or initiate alternative vendor search",
            }
        )

    requires_review = any(r["severity"] == "high" for r in risks)

    return {
        "risk_items": risks,
        "requires_human_review": state.get("requires_human_review", False)
        or requires_review,
        "messages": [
            AIMessage(
                content=(
                    f"Risk assessment: {len(risks)} risk(s) found. "
                    f"{'⚠ Human review recommended.' if requires_review else '✓ No critical risks.'}"
                )
            )
        ],
    }
