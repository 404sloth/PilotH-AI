"""
Node: summarize_node
Responsibility: generate a final executive LLM summary of the vendor workflow.
Handles both FIND_BEST and single-vendor assessment modes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, AIMessage
from agents.vendor_management.schemas import VendorState

logger = logging.getLogger(__name__)


def summarize_node(state: VendorState) -> Dict[str, Any]:
    """
    Generate LLM-powered executive summary and prioritised recommendations.
    Falls back to rule-based summary if LLM unavailable.
    """
    action = state.get("action", "full_assessment")

    if action == "search_vendors":
        return _summarize_vendor_search(state)
    if action == "find_best":
        return _summarize_find_best(state)
    else:
        return _summarize_assessment(state)


# ---------------------------------------------------------------------------
# SEARCH_VENDORS summary
# ---------------------------------------------------------------------------


def _summarize_vendor_search(state: VendorState) -> Dict[str, Any]:
    vendors = state.get("vendors") or []
    service_filter = state.get("service_required")
    country = state.get("country")

    if not vendors:
        scope = service_filter or "the requested filters"
        return {
            "llm_summary": f"No vendors found matching {scope}.",
            "recommendations": [
                "Try broadening the service or country filters",
                "Check whether additional vendors need to be onboarded",
            ],
            "messages": [AIMessage(content="No vendors found.")],
        }

    category_counts: Dict[str, int] = {}
    service_counts: Dict[str, int] = {}
    for vendor in vendors:
        category = vendor.get("category") or "Unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
        for service in vendor.get("services", []):
            service_counts[service] = service_counts.get(service, 0) + 1

    top_services = sorted(service_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    top_categories = sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    summary_bits = ", ".join(f"{name} ({count})" for name, count in top_services)
    category_bits = ", ".join(f"{name} ({count})" for name, count in top_categories)

    location_text = f" in {country}" if country else ""
    if service_filter:
        summary = (
            f"Found {len(vendors)} vendor(s){location_text} that provide '{service_filter}'. "
            f"Top matches include {', '.join(v.get('name', 'Unknown') for v in vendors[:5])}. "
            f"Related service coverage in this result set: {summary_bits or service_filter}."
        )
    else:
        summary = (
            f"Found {len(vendors)} vendor(s){location_text} across {len(category_counts)} categories. "
            f"Leading categories are {category_bits or 'not available'}. "
            f"Most represented services are {summary_bits or 'not available'}."
        )

    recommendations = [
        "Use the vendor list to narrow down by service, region, or tier",
        "Run a best-vendor search once you know the target service and budget",
    ]
    if not service_filter:
        recommendations.append("Add a service filter to get a tighter shortlist")

    return {
        "llm_summary": summary,
        "recommendations": recommendations,
        "messages": [AIMessage(content=summary)],
    }


# ---------------------------------------------------------------------------
# FIND_BEST summary
# ---------------------------------------------------------------------------


def _summarize_find_best(state: VendorState) -> Dict[str, Any]:
    ranked = state.get("ranked_vendors") or []
    service = state.get("service_required", "requested service")

    if not ranked:
        return {
            "llm_summary": f"No vendors found offering '{service}' matching the project requirements.",
            "recommendations": [
                "Relax budget or quality constraints and retry",
                "Consider onboarding a new vendor",
            ],
            "messages": [AIMessage(content="No matching vendors found.")],
        }

    top = ranked[0]

    prompt = f"""You are a senior procurement strategist. A client needs '{service}' and we found {len(ranked)} qualified vendors.

Top vendors (ranked by fit score):
{json.dumps(ranked[:5], indent=2)}

Write a concise 3-4 sentence executive recommendation explaining why the top vendor is the best choice,
key differentiators vs. alternatives, and any caveats. Follow with 3 bullet-point action items."""

    summary = _call_llm(prompt) or _fallback_find_best(top, ranked, service)

    recs = [
        f"Proceed with {top.get('name')} (fit score: {top.get('fit_score', 0):.1f}/100) as primary vendor",
        f"Issue RFP or contract negotiation with {top.get('name')}",
        "Set milestone and SLA review cadence before project kickoff",
    ]
    if len(ranked) > 1:
        recs.append(f"Keep {ranked[1].get('name')} as backup vendor option")

    return {
        "llm_summary": summary,
        "recommendations": recs,
        "messages": [AIMessage(content=summary)],
    }


def _fallback_find_best(top: Dict, ranked: list, service: str) -> str:
    return (
        f"For '{service}', {top.get('name')} is the top recommendation with a fit score of "
        f"{top.get('fit_score', 0):.1f}/100. They lead on quality ({top.get('quality_score', 'N/A')}/100) "
        f"and on-time delivery ({(top.get('on_time_rate', 0) or 0) * 100:.0f}%). "
        f"{len(ranked)} vendors evaluated in total."
    )


# ---------------------------------------------------------------------------
# Single-vendor assessment summary
# ---------------------------------------------------------------------------


def _summarize_assessment(state: VendorState) -> Dict[str, Any]:
    if state.get("error"):
        return {
            "llm_summary": f"Assessment failed: {state['error']}",
            "recommendations": ["Verify vendor identity and retry"],
            "messages": [AIMessage(content=f"Error: {state['error']}")],
        }

    vendor = state.get("vendor_details") or {}
    scores = state.get("evaluation_scores") or {}
    risks = state.get("risk_items") or []
    strengths = state.get("strengths") or []
    weaknesses = state.get("weaknesses") or []
    overall = state.get("overall_score", 0.0)
    sla_pct = state.get("sla_compliance")

    context = {
        "vendor_name": vendor.get("name", state.get("vendor_name")),
        "overall_score": overall,
        "sla_compliance": sla_pct,
        "scores": scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risk_count": len(risks),
        "high_risks": [r["description"] for r in risks if r.get("severity") == "high"],
    }

    prompt = f"""You are a senior vendor relationship manager. Summarise this vendor assessment for an executive audience.

Assessment Data:
{json.dumps(context, indent=2)}

Write 3-4 sentences covering: overall vendor health, top concerns, and a clear recommendation.
Keep it factual and actionable."""

    summary = _call_llm(prompt) or _fallback_assessment(context)

    # Rule-based recommendations
    recs = []
    if overall < 60:
        recs.append("Consider initiating a vendor replacement search immediately")
    elif overall < 75:
        recs.append("Schedule a formal Quarterly Business Review with the vendor")

    high_risks = [r for r in risks if r.get("severity") == "high"]
    if high_risks:
        recs.append(f"Address {len(high_risks)} high-severity risk(s) within 2 weeks")

    if sla_pct is not None and sla_pct < 90:
        recs.append("Issue formal SLA breach notice and request remediation plan")

    if weaknesses:
        recs.append(
            f"Work with vendor on improvement areas: {', '.join(weaknesses[:2])}"
        )

    if not recs:
        recs.append("Continue standard monitoring cadence — vendor in good standing")

    return {
        "llm_summary": summary,
        "recommendations": recs,
        "messages": [AIMessage(content=summary)],
    }


def _fallback_assessment(ctx: Dict) -> str:
    return (
        f"{ctx.get('vendor_name', 'Vendor')} achieved an overall score of {ctx.get('overall_score', 0):.1f}/100. "
        f"SLA compliance: {ctx.get('sla_compliance') or 'N/A'}%. "
        f"Identified {ctx.get('risk_count', 0)} risk(s), "
        f"including {len(ctx.get('high_risks', []))} high-severity. "
        f"Key strengths: {', '.join(ctx.get('strengths', [])) or 'none'}."
    )


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------


def _call_llm(prompt: str) -> str | None:
    try:
        from llm.model_factory import get_llm

        llm = get_llm(temperature=0.3)
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        logger.warning("LLM call failed in summarize_node: %s", e)
        return None
