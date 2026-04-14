"""
Orchestrator Controller — main entry point for all user requests.
Parses intent → decomposes tasks → routes to agents → aggregates results.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from config.settings import Settings
from memory.session_store import get_session_store
from memory.global_context import get_global_context
from llm.token_counter import get_token_counter

logger = logging.getLogger(__name__)


class OrchestratorController:
    """
    Central router and coordinator.

    Workflow:
      1. Parse intent from user message (IntentParser)
      2. Decompose into subtasks (TaskDecomposer)
      3. Route each subtask to the appropriate agent (AgentRouter)
      4. Aggregate results and save to memory
    """

    def __init__(self, config: Settings) -> None:
        self.config  = config
        self.session_store = get_session_store()
        self.global_ctx    = get_global_context()
        self.token_counter = get_token_counter()

    def handle(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message end-to-end.

        Args:
            message:    Natural language user input
            session_id: Existing session or None to create new
            context:    Optional additional context dict

        Returns:
            Dict with result, agent used, and session_id
        """
        session_id = session_id or str(uuid.uuid4())
        session    = self.session_store.get_or_create(session_id)
        session.add_message("user", message)

        # 1. Parse intent
        from orchestrator.intent_parser import IntentParser
        intent = IntentParser(self.config).parse(message, session.context)

        logger.info("[%s] Intent: %s → agent=%s", session_id, intent["action"], intent["agent"])

        # 2. Route to agent
        from orchestrator.agent_router import AgentRouter
        result = AgentRouter().route(
            agent_name=intent["agent"],
            action=intent["action"],
            payload={**intent.get("params", {}), **(context or {})},
            session_id=session_id,
        )

        # 3. Save to session and global memory
        session.add_message("assistant", str(result.get("llm_summary", result.get("message", ""))))
        self.global_ctx.append_to_list(
            f"session:{session_id}:results",
            {"intent": intent, "result_keys": list(result.keys())},
            agent="orchestrator",
            session_id=session_id,
        )

        return {
            "session_id":    session_id,
            "intent":        intent,
            "result":        result,
            "token_usage":   self.token_counter.totals(),
        }
