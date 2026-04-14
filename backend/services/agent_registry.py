"""
Agent service registry — wires together all agents, tools, and config at startup.
Used by the FastAPI application lifespan to initialise the system once.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from config.settings import Settings
from agents.registry import ToolRegistry
from human_loop.manager import HITLManager

logger = logging.getLogger(__name__)

# Module-level singletons (initialised once per process)
_tool_registry: Optional[ToolRegistry] = None
_agents: Dict[str, object] = {}


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def initialise_agents(config: Settings) -> Dict[str, object]:
    """
    Instantiate and register all agents.
    Add new agents here as the platform grows.
    """
    global _agents
    if _agents:
        return _agents  # already initialised

    registry = get_tool_registry()
    hitl     = HITLManager(config.hitl_threshold)

    # ── Vendor Management Agent ──────────────────────────────
    from agents.vendor_management.agent import VendorManagementAgent
    vendor_agent = VendorManagementAgent(config=config, tool_registry=registry, hitl_manager=hitl)
    _agents["vendor_management"] = vendor_agent

    # ── Meetings & Communication Agent ───────────────────────
    from agents.communication.agent import MeetingCommunicationAgent
    meeting_agent = MeetingCommunicationAgent(config=config, tool_registry=registry, hitl_manager=hitl)
    _agents["meetings_communication"] = meeting_agent

    logger.info("Agents initialised: %s", list(_agents.keys()))
    logger.info("Tool registry: %s", registry.list_all_tools())
    return _agents


def get_agent(name: str) -> Optional[object]:
    """Return a registered agent by name."""
    return _agents.get(name)
