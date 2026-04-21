"""
LangGraph workflow for the Vendor Management Agent.

Graph topology:
  START → fetch_vendor → [route] → evaluate → sla_analyzer → risk_detect → summarize → END
                                ↘ summarize (for search_vendors)
                                ↘ evaluate (for find_best, then skip later nodes if preferred)
"""

from __future__ import annotations
import logging
from typing import Optional, Any
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from .schemas import VendorState
from .nodes.brain import brain_node
from .nodes.tool_node import action_node
from .nodes.summarize import summarize_node

logger = logging.getLogger(__name__)


class LoggingToolNode(ToolNode):
    def invoke(self, input: Any, config: Optional[RunnableConfig] = None) -> Any:
        # ToolNode expects a list of tool calls in the last message
        last_msg = input["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                logger.info(f" [TOOL CALL] {tc['name']} with args: {tc['args']}")

        result = super().invoke(input, config)

        # Log the result
        if "messages" in result:
            last_result = result["messages"][-1]
            logger.info(f" [TOOL RESULT] {last_result.content[:1000]}...")

        return result


def _route_next(state: VendorState) -> str:
    """
    Decide whether to execute tools or finish.
    """
    return state.get("next_step", "summarize")


def build_vendor_graph(
    llm_with_tools=None,
    tools: Optional[list] = None,
    hitl_manager=None,
    checkpointer: Optional[MemorySaver] = None,
) -> StateGraph:
    """
    Build and compile the Vendor Management LangGraph workflow.
    Uses a dynamic reasoning loop (ReAct pattern).
    """
    builder = StateGraph(VendorState)

    # 1. Define Nodes
    builder.add_node("brain", brain_node)

    if tools:
        builder.add_node("action", LoggingToolNode(tools))
    else:
        builder.add_node("action", action_node)

    builder.add_node("summarize", summarize_node)
    # 2. Entry Point
    builder.add_edge(START, "brain")

    # 3. Reasoning -> Tool or Summary
    builder.add_conditional_edges(
        "brain",
        _route_next,
        {
            "tools": "action",
            "summarize": "summarize",
        },
    )

    # 4. Tool Loop: Action -> Brain (reflect on results)
    builder.add_edge("action", "brain")

    # 5. Terminate
    builder.add_edge("summarize", END)

    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
