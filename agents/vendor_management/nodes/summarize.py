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
from langchain_core.runnables import RunnableConfig
from agents.vendor_management.schemas import VendorState

import re

def summarize_node(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Generate the final executive output, filtering out internal <think> tracks.
    """
    from llm.model_factory import get_llm
    
    action = state.get("action")
    
    # Route to specialized summarizers if applicable
    if action == "SEARCH_VENDORS":
        res = _summarize_vendor_search(state, config)
    elif action == "FIND_BEST":
        res = _summarize_find_best(state, config)
    elif action == "FULL_ASSESSMENT":
        res = _summarize_assessment(state, config)
    elif action == "SUMMARIZE_CONTRACT":
        res = _summarize_contract(state, config)
    else:
        # Fallback synthesis
        last_message = state["messages"][-1]
        raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
        clean_summary = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
        
        if not clean_summary:
            llm = get_llm(temperature=0.4)
            history = "\n".join([f"{m.type}: {m.content}" for m in state["messages"][-5:]])
            prompt = f"Synthesize a final executive answer based on this interaction history:\n\n{history}"
            clean_summary = llm.invoke([HumanMessage(content=prompt)], config=config).content.strip()
        
        res = {"llm_summary": clean_summary, "messages": [AIMessage(content=clean_summary)]}

    # Ensure thought is propagated
    res["thought"] = state.get("thought")
    return res


# ---------------------------------------------------------------------------
# SEARCH_VENDORS summary
...
def _summarize_contract(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    contract = state.get("contract_data") or {}
    vendor_name = state.get("vendor_name") or "the vendor"

    if not contract:
        return {
            "llm_summary": f"No active contract found for {vendor_name}.",
            "messages": [AIMessage(content=f"No contract found for {vendor_name}.")],
        }

    context = {
        "vendor_name": vendor_name,
        "ref": contract.get("contract_reference"),
        "expiry": contract.get("expiration_date"),
        "value": f"{contract.get('total_value', 0):,} {contract.get('currency', 'USD')}",
        "summary": contract.get("summary"),
        "deliverables": contract.get("deliverables", []),
        "conditions": contract.get("conditions", []),
    }

    prompt = f"""You are a legal and procurement expert. Summarize the status of the contract for '{vendor_name}'.

Contract Data:
{json.dumps(context, indent=2)}

Provide a 3-4 sentence professional summary focusing on the status (active/expiring), key terms, and any upcoming milestones or renewals."""

    summary = _call_llm(prompt, config) or f"Contract {context['ref']} for {vendor_name} is active until {context['expiry']}. Total value is {context['value']}."

    return {
        "llm_summary": summary,
        "messages": [AIMessage(content=summary)],
    }
# ---------------------------------------------------------------------------


def _summarize_vendor_search(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    vendors = state.get("vendors") or []
    service_filter = state.get("service_required")
    industry_filter = state.get("industry")
    country = state.get("country")

    if not vendors:
        scope_parts = []
        if service_filter: scope_parts.append(f"service '{service_filter}'")
        if industry_filter: scope_parts.append(f"industry '{industry_filter}'")
        if country: scope_parts.append(f"country '{country}'")
        scope = " and ".join(scope_parts) or "the requested filters"
        
        summary = f"No vendors found matching {scope}."
        return {
            "llm_summary": summary,
            "recommendations": [
                "Try broadening the search terms or removing filters",
                "Check the knowledge base for manual vendor lists",
            ],
            "messages": [AIMessage(content=summary)],
        }

    vendor_names = [v.get("name", "Unknown") for v in vendors]
    
    prompt = f"""You are a procurement analyst. We found {len(vendors)} vendors matching the search criteria.

Search Criteria:
- Service: {service_filter or 'Any'}
- Industry: {industry_filter or 'Any'}
- Country: {country or 'Any'}
- Tier: {state.get('tier') or 'Any'}
- Status: {state.get('contract_status') or 'Any'}

Vendor List:
{', '.join(vendor_names)}

Provide a helpful 2-3 sentence summary of what was found. List the names of the top 5 vendors explicitly."""

    summary = _call_llm(prompt, config) or _fallback_vendor_search(vendors, service_filter, industry_filter, country)

    return {
        "llm_summary": summary,
        "recommendations": [
            "Select a vendor for a deep-dive assessment",
            "Use 'find_best' to rank these vendors by project requirements"
        ],
        "messages": [AIMessage(content=summary)],
    }


def _fallback_vendor_search(vendors: list, service: str, industry: str, country: str) -> str:
    names = ", ".join(v.get("name") for v in vendors[:5])
    filters = []
    if service: filters.append(f"service '{service}'")
    if industry: filters.append(f"industry '{industry}'")
    if country: filters.append(f"in {country}")
    filter_text = " matching " + " and ".join(filters) if filters else ""
    
    return f"Found {len(vendors)} vendor(s){filter_text}. Top matches include: {names}."


# ---------------------------------------------------------------------------
# FIND_BEST summary
# ---------------------------------------------------------------------------


def _summarize_find_best(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
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

Write a highly detailed executive recommendation format in Markdown. 
Mention the top vendor '{top.get('name')}' and their fit score of {top.get('fit_score', 0):.1f}/100.
Filters applied: Tier: {state.get('tier') or 'Any'}, Status: {state.get('contract_status') or 'Any'}.
Explain why they are better than the runner-ups based on the data provided.
Include a Markdown table comparing the top 3 vendors, showing columns for Vendor, Cost, SLA Score, Reliability, and Fit Score."""

    summary = _call_llm(prompt, config) or _fallback_find_best(top, ranked, service)

    return {
        "llm_summary": summary,
        "recommendations": [
            f"Initiate engagement with {top.get('name')}",
            "Review full scorecard comparison in the metadata results"
        ],
        "messages": [AIMessage(content=summary)],
    }


def _fallback_find_best(top: Dict, ranked: list, service: str) -> str:
    return (
        f"For '{service}', {top.get('name')} is the top recommendation with a fit score of "
        f"{top.get('fit_score', 0):.1f}/100. They lead on quality ({top.get('quality_score', 'N/A')}/100). "
        f"{len(ranked)} vendors were evaluated."
    )


# ---------------------------------------------------------------------------
# Single-vendor assessment summary
# ---------------------------------------------------------------------------


def _summarize_assessment(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    if state.get("error"):
        return {
            "llm_summary": f"Assessment failed: {state['error']}",
            "recommendations": ["Verify vendor identity and retry"],
            "messages": [AIMessage(content=f"Error: {state['error']}")],
        }

    vendor = state.get("vendor_details") or {}
    scores = state.get("evaluation_scores") or {}
    risks = state.get("risk_items") or []
    overall = state.get("overall_score", 0.0)
    sla_pct = state.get("sla_compliance")
    vendor_name = vendor.get("name") or state.get("vendor_name") or "the vendor"

    # Identify top strengths and weaknesses for the LLM
    strengths = state.get("strengths") or []
    weaknesses = state.get("weaknesses") or []

    context = {
        "vendor_name": vendor_name,
        "overall_score": overall,
        "sla_compliance": sla_pct,
        "scores": scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risk_count": len(risks),
    }

    prompt = f"""You are a senior vendor relationship manager. Summarise this vendor assessment for '{vendor_name}'.

Assessment Data:
{json.dumps(context, indent=2)}

Write a 4-5 sentence professional summary. 
Start by stating the overall score of {overall:.1f}/100.
Mention specific strengths ({', '.join(strengths[:2])}) and concerns ({', '.join(weaknesses[:2])}).
If SLA compliance is mentioned ({sla_pct}%), include it."""

    summary = _call_llm(prompt, config) or _fallback_assessment(context)

    return {
        "llm_summary": summary,
        "recommendations": state.get("recommendations") or ["No specific recommendations at this time."],
        "messages": [AIMessage(content=summary)],
    }


def _fallback_assessment(ctx: Dict) -> str:
    name = ctx.get('vendor_name', 'The vendor')
    return (
        f"{name} achieved an overall score of {ctx.get('overall_score', 0):.1f}/100. "
        f"SLA compliance: {ctx.get('sla_compliance') or 'N/A'}%. "
        f"Key strengths: {', '.join(ctx.get('strengths', [])) or 'none'}."
    )


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------


def _call_llm(prompt: str, config: RunnableConfig) -> str | None:
    try:
        from llm.model_factory import get_llm

        llm = get_llm(temperature=0.4)
        response = llm.invoke([HumanMessage(content=prompt)], config=config)
        return response.content.strip()
    except Exception as e:
        logger.warning("LLM call failed in summarize_node: %s", e)
        return None
