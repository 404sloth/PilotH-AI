"""
LangGraph workflow for the Vendor Management Agent.

Graph topology:
  START → fetch_vendor → [route] → evaluate → risk_detect → summarize → END
                                ↘ summarize (for find_best, skip evaluate+risk)
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


def _route_after_fetch(state: VendorState) -> str:
    """
    Conditional routing after fetch_vendor:
    - FIND_BEST: jump straight to summarize (ranking already done by VendorMatcherTool)
    - Error:     jump to summarize to surface the error gracefully
    - Default:   proceed through evaluate → risk_detect → summarize
    """
    if state.get("error"):
        return "summarize"
    if state.get("action") == "find_best":
        return "summarize"
    return "evaluate"


def build_vendor_graph(
    llm_with_tools=None,
    tools: Optional[list] = None,
    hitl_manager=None,
    checkpointer: Optional[MemorySaver] = None,
) -> StateGraph:
    """
    Build and compile the Vendor Management LangGraph workflow.

    Args:
        llm_with_tools:  LLM with tools bound (reserved for future tool-calling nodes)
        tools:           Tool list (reserved for agent executor pattern)
        hitl_manager:    Human-in-the-loop manager (reserved for interrupt nodes)
        checkpointer:    Optional memory checkpointer for multi-turn persistence

    Returns:
        Compiled StateGraph
    """
    builder = StateGraph(VendorState)

    # Register nodes
    builder.add_node("fetch_vendor", fetch_vendor_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("risk_detect", risk_detect_node)
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
        },
    )

    # Linear path for full assessment / evaluate / sla / milestone actions
    builder.add_edge("evaluate", "risk_detect")
    builder.add_edge("risk_detect", "summarize")
    builder.add_edge("summarize", END)

    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
