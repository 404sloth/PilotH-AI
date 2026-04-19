"""
LangGraph workflow for the Vendor Management Agent.

Graph topology:
  START → fetch_vendor → [route] → evaluate → sla_analyzer → risk_detect → summarize → END
                                ↘ summarize (for search_vendors)
                                ↘ evaluate (for find_best, then skip later nodes if preferred)
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .schemas import VendorState
from .nodes import (
    fetch_vendor_node,
    evaluate_node,
    risk_detect_node,
    summarize_node,
)
from .nodes.sla_analyzer import sla_analyzer_node


def _route_after_fetch(state: VendorState) -> str:
    """
    Conditional routing after fetch_vendor:
    - SEARCH_VENDORS: jump straight to summarize (discovery already complete)
    - FIND_BEST: jump straight to evaluate to build ranking matrix
    - Error:     jump to summarize to surface the error gracefully
    - Default:   proceed through evaluate → sla_analyzer → risk_detect → summarize
    """
    if state.get("error"):
        return "reflexion"
    if state.get("action") == "search_vendors":
        return "summarize"
    # Even for find_best, we route to "evaluate" so it can build the ComparisonMatrix
    return "evaluate"


def build_vendor_graph(
    llm_with_tools=None,
    tools: Optional[list] = None,
    hitl_manager=None,
    checkpointer: Optional[MemorySaver] = None,
) -> StateGraph:
    """
    Build and compile the Vendor Management LangGraph workflow.
    """
    builder = StateGraph(VendorState)

    # Register nodes
    from agents.reflexion_node import reflexion_node
    builder.add_node("fetch_vendor", fetch_vendor_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("sla_analyzer", sla_analyzer_node)
    builder.add_node("risk_detect", risk_detect_node)
    builder.add_node("reflexion", reflexion_node)
    builder.add_node("summarize", summarize_node)

    # Entry
    builder.add_edge(START, "fetch_vendor")

    # Conditional branch after fetch
    builder.add_conditional_edges(
        "fetch_vendor",
        _route_after_fetch,
        {
            "evaluate": "evaluate",
            "summarize": "summarize",
            "reflexion": "reflexion",
        },
    )

    # Linear path
    builder.add_edge("evaluate", "sla_analyzer")
    builder.add_edge("sla_analyzer", "risk_detect")
    builder.add_edge("risk_detect", "summarize")
    builder.add_edge("reflexion", "summarize")
    builder.add_edge("summarize", END)

    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
