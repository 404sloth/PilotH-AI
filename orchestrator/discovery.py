from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool
from backend.services.agent_registry import get_tool_registry, _agents

logger = logging.getLogger(__name__)

class CapabilityDiscoverer:
    """
    Dynamically discovers registered agents and their tools to build
    a semantic map for the LLM Planner.
    """

    @staticmethod
    def get_system_capabilities() -> str:
        """
        Returns a formatted string describing all available agents and tools.
        """
        registry = get_tool_registry()
        capabilities = []

        capability_map = registry.list_all_tools() # agent -> [tool_names]
        
        for agent_name, agent_obj in _agents.items():
            agent_desc = getattr(agent_obj, "description", "Specialized Agent")
            capabilities.append(f"AGENT: {agent_name}")
            capabilities.append(f"DESCRIPTION: {agent_desc}")
            capabilities.append("AVAILABLE TOOLS:")
            
            tools = registry.get_tools_for_agent(agent_name)
            for tool in tools:
                arg_info = ""
                if tool.args_schema:
                    try:
                        args = tool.args_schema.schema().get("properties", {})
                        arg_info = ", ".join([f"{k} ({v.get('type', 'any')})" for k, v in args.items()])
                    except Exception:
                        arg_info = "standard params"
                
                capabilities.append(f"  - {tool.name}: {tool.description}")
                if arg_info:
                    capabilities.append(f"    Parameters: {arg_info}")
            
            capabilities.append("---")

        return "\n".join(capabilities)

    @staticmethod
    def get_tool_catalog() -> List[Dict[str, Any]]:
        """
        Returns a structured list of all tools with their metadata.
        """
        registry = get_tool_registry()
        catalog = []

        for agent_name in registry.list_agents():
            tools = registry.get_tools_for_agent(agent_name)
            for tool in tools:
                catalog.append({
                    "name": tool.name,
                    "agent": agent_name,
                    "description": tool.description,
                    "args": tool.args_schema.schema() if tool.args_schema else None
                })
        return catalog
