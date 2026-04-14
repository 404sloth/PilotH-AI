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
            raise ValueError(f"Agent '{agent_name}' is not registered.")

        input_data = {"action": action, "session_id": session_id, **payload}
        logger.info("Routing to agent='%s' action='%s'", agent_name, action)
        return agent.execute(input_data)
