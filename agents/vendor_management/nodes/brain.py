"""
Node: brain_node (Reasoning)
Responsibility: Think using <think> tags and decide on the next tool call or final answer.
"""

import re
import logging
from typing import Any, Dict, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from agents.vendor_management.schemas import VendorState

logger = logging.getLogger(__name__)

def brain_node(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    """
    The reasoning hub of the agent. Mandates <think> tags for DeepSeek-style logic.
    """
    from llm.model_factory import get_llm
    from agents.registry import ToolRegistry
    
    # In a production environment, we'd inject the registry.
    # Here we simulate fetching the tools for this agent.
    # We use a singleton or a cached registry for performance.
    from agents.registry import registry
    tools = registry.get_tools_for_agent("vendor_management")
    
    llm = get_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = """You are the Strategic Brain of the PilotH Vendor Management Agent.
Your goal is to solve complex enterprise procurement and vendor management tasks.

REASONING RULES:
1. Always start your response with a <think> block.
2. Inside <think>, analyze the user's intent, identify missing data, and plan which tool to call.
3. If multiple tools are needed, call them one by one.
4. If you have the final answer, provide it AFTER the </think> block.

DATA ORGANIZATION & TOOL MANDATE:
1. If a user asks about SLA compliance, performance, or metrics for a specific vendor_id (e.g., 'V-001'), you MUST call 'sla_monitor'.
2. If searching for vendors, always use 'vendor_search' or 'vendor_matcher'.
3. DO NOT apologize for lack of data until you have first called the relevant tool.
4. Use 'dynamic_sql_executor' for complex multi-table queries (JOINS).
5. Respect all user-provided filters (budget, rating, industry, etc.) found in the request or context. If a filter is specified, ensure the tool arguments reflect it.
"""

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    response = llm_with_tools.invoke(messages, config=config)
    content = response.content or ""
    
    # Extract thought
    thought = ""
    thought_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()
    
    # Check for tool calls
    tool_calls = getattr(response, "tool_calls", [])
    
    return {
        "thought": thought,
        "messages": [response],
        "next_step": "tools" if tool_calls else "summarize"
    }
