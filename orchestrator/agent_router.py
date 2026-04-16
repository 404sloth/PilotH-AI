"""
Agent Router — dispatches tasks to registered agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AgentRouter:
    def route(
        self,
        agent_name: str,
        action: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from backend.services.agent_registry import get_agent

        agent = get_agent(agent_name)
        if not agent:
            # Try to initialize agent on demand
            logger.warning("Agent '%s' not available, attempting lazy initialization", agent_name)
            self._initialize_agent_on_demand(agent_name)
            agent = get_agent(agent_name)

        if not agent:
            return {
                "error": f"Agent '{agent_name}' is not available. LLM providers may be misconfigured.",
                "action": action,
                "agent": agent_name,
                "status": "failed"
            }

        try:
            input_data = {"action": action, "session_id": session_id, **payload}
            logger.info("Routing to agent='%s' action='%s'", agent_name, action)
            return agent.execute(input_data)
        except Exception as e:
            logger.error("Agent execution failed: %s", str(e))
            return {
                "error": f"Agent execution failed: {str(e)}",
                "action": action,
                "agent": agent_name,
                "status": "failed"
            }

    def _initialize_agent_on_demand(self, agent_name: str) -> None:
        """Attempt to initialize an agent that failed during startup."""
        try:
            from backend.services.agent_registry import get_tool_registry, _agents
            from human_loop.manager import HITLManager
            from backend.api.dependencies import get_settings

            # Try to initialize just this agent
            config = get_settings()
            registry = get_tool_registry()
            hitl = HITLManager(config.hitl_threshold)

            if agent_name == "vendor_management":
                from agents.vendor_management.agent import VendorManagementAgent
                agent = VendorManagementAgent(config=config, tool_registry=registry, hitl_manager=hitl)
                _agents[agent_name] = agent
                logger.info("✓ Vendor Management Agent initialized on demand")
            elif agent_name == "meetings_communication":
                from agents.communication.agent import MeetingCommunicationAgent
                agent = MeetingCommunicationAgent(config=config, tool_registry=registry, hitl_manager=hitl)
                _agents[agent_name] = agent
                logger.info("✓ Meetings & Communication Agent initialized on demand")
            elif agent_name == "knowledge_base":
                from agents.knowledge_base.agent import KnowledgeBaseAgent
                agent = KnowledgeBaseAgent(config=config, tool_registry=registry, hitl_manager=hitl)
                _agents[agent_name] = agent
                logger.info("✓ Knowledge Base Agent initialized on demand")
        except Exception as e:
            logger.warning("Failed to initialize agent '%s' on demand: %s", agent_name, str(e))
