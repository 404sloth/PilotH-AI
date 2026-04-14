"""
Agent Tool Registry.

Maintains the mapping of agent_name → list of tools.
Central registry allows the orchestrator and agents to discover tools
without tight coupling.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Simple in-process tool registry.

    Usage:
        registry = ToolRegistry()
        registry.register_tool(MyTool(), agent_name="my_agent")
        tools = registry.get_tools_for_agent("my_agent")
    """

    def __init__(self) -> None:
        self._registry: Dict[str, List[BaseTool]] = {}

    def register_tool(self, tool: BaseTool, agent_name: str) -> None:
        """Register a tool for a specific agent."""
        self._registry.setdefault(agent_name, [])
        existing_names = {t.name for t in self._registry[agent_name]}
        if tool.name in existing_names:
            logger.debug("Tool '%s' already registered for agent '%s' — skipping.", tool.name, agent_name)
            return
        self._registry[agent_name].append(tool)
        logger.info("Registered tool '%s' for agent '%s'.", tool.name, agent_name)

    def get_tools_for_agent(self, agent_name: str) -> List[BaseTool]:
        """Return all tools registered for a given agent."""
        return list(self._registry.get(agent_name, []))

    def list_agents(self) -> List[str]:
        """Return names of all agents with registered tools."""
        return list(self._registry.keys())

    def list_all_tools(self) -> Dict[str, List[str]]:
        """Return agent → tool-name mapping for observability."""
        return {agent: [t.name for t in tools] for agent, tools in self._registry.items()}
