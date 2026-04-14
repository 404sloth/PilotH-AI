"""
Node: evaluate_node
Responsibility: use LLM to evaluate vendor performance and produce
structured scores, strengths, and weaknesses from real data.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, AIMessage

from agents.vendor_management.schemas import VendorState

logger = logging.getLogger(__name__)


def evaluate_node(state: VendorState) -> Dict[str, Any]:
    """
    Evaluate a single vendor using LLM reasoning over real scorecard data.
    Skipped for FIND_BEST action (evaluation is embedded in VendorMatcherTool).
    """
    action = state.get("action", "full_assessment")

    # FIND_BEST doesn't need a separate evaluate step
    if action == "find_best":
        return {}

    vendor_details = state.get("vendor_details") or {}
    sla_data       = state.get("sla_data") or {}
    milestone_data = state.get("milestone_data") or []
    if state.get("error"):
        return {}

    if not vendor_details:
        return {"evaluation_scores": {}, "strengths": [], "weaknesses": []}

    # Load SLA and milestone tools if not already in state
    if not sla_data and state.get("vendor_id"):
        from agents.vendor_management.tools.sla_monitor import SLAMonitorTool, SLAMonitorInput
        sla_result = SLAMonitorTool().execute(SLAMonitorInput(vendor_id=state["vendor_id"]))
        sla_data = sla_result.model_dump()

    if not milestone_data and state.get("vendor_id"):
        from agents.vendor_management.tools.milestone_tracker import MilestoneTrackerTool, MilestoneTrackerInput
        ms_result = MilestoneTrackerTool().execute(MilestoneTrackerInput(vendor_id=state["vendor_id"]))
        milestone_data = [m.model_dump() for m in ms_result.milestones]

    # Build a structured prompt for the LLM
    vendor_context = json.dumps({
        "name":                   vendor_details.get("name"),
        "tier":                   vendor_details.get("tier"),
        "category":               vendor_details.get("category"),
        "quality_score":          vendor_details.get("quality_score"),
        "on_time_rate":           vendor_details.get("on_time_rate"),
        "avg_client_rating":      vendor_details.get("avg_client_rating"),
        "cost_competitiveness":   vendor_details.get("cost_competitiveness"),
        "communication_score":    vendor_details.get("communication_score"),
        "innovation_score":       vendor_details.get("innovation_score"),
        "total_projects":         vendor_details.get("total_projects_completed"),
        "sla_compliance_pct":     sla_data.get("overall_compliance") if sla_data else None,
        "sla_breaches":           sla_data.get("breaches") if sla_data else [],
        "delayed_milestones":     sum(1 for m in milestone_data if m.get("status") == "delayed"),
        "at_risk_milestones":     sum(1 for m in milestone_data if m.get("status") == "at_risk"),
    }, indent=2)

    prompt = f"""You are a senior procurement analyst. Evaluate the following vendor profile and return ONLY valid JSON.

Vendor Data:
{vendor_context}

Return JSON with these exact keys:
{{
    "evaluation_scores": {{
        "quality": <float 0-100>,
        "reliability": <float 0-100>,
        "sla_compliance": <float 0-100>,
        "communication": <float 0-100>,
        "cost": <float 0-100>,
        "innovation": <float 0-100>
    }},
    "strengths": [<string>, ...],
    "weaknesses": [<string>, ...]
}}"""

    try:
        from llm.model_factory import get_llm
        llm = get_llm(temperature=0.0)
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        parsed = json.loads(content)
        scores      = parsed.get("evaluation_scores", {})
        strengths   = parsed.get("strengths", [])
        weaknesses  = parsed.get("weaknesses", [])
        overall     = round(sum(scores.values()) / len(scores), 1) if scores else 0.0

    except Exception as e:
        logger.warning("LLM evaluation failed (%s), using rule-based fallback.", e)
        scores, strengths, weaknesses, overall = _rule_based_evaluate(vendor_details, sla_data, milestone_data)

    return {
        "evaluation_scores": scores,
        "overall_score":     overall,
        "sla_data":          sla_data,
        "milestone_data":    milestone_data,
        "strengths":         strengths,
        "weaknesses":        weaknesses,
        "messages": [AIMessage(
            content=f"Evaluation complete for {vendor_details.get('name')}. Score: {overall:.1f}/100."
        )],
    }


def _rule_based_evaluate(
    vendor: Dict[str, Any],
    sla: Dict[str, Any],
    milestones: List[Dict[str, Any]],
) -> tuple:
    """Fallback scoring without LLM using raw numeric data."""
    q    = float(vendor.get("quality_score") or 50)
    ot   = (float(vendor.get("on_time_rate") or 0.5)) * 100
    comm = float(vendor.get("communication_score") or 50)
    cost = float(vendor.get("cost_competitiveness") or 50)
    inno = float(vendor.get("innovation_score") or 50)
    slap = float(sla.get("overall_compliance") or 100)

    delayed = sum(1 for m in milestones if m.get("status") == "delayed")
    penalty = min(delayed * 5, 20)

    scores = {
        "quality":        q,
        "reliability":    max(ot - penalty, 0),
        "sla_compliance": slap,
        "communication":  comm,
        "cost":           cost,
        "innovation":     inno,
    }
    overall = round(sum(scores.values()) / len(scores), 1)

    strengths  = [k for k, v in scores.items() if v >= 85]
    weaknesses = [k for k, v in scores.items() if v <  70]

    return scores, [f"Strong {s}" for s in strengths], [f"Needs improvement: {w}" for w in weaknesses], overall