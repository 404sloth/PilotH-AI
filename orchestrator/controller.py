"""
Orchestrator Controller — main entry point for all user requests.
Parses intent → decomposes tasks → routes to agents → aggregates results.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

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
        self.config = config
        self.session_store = get_session_store()
        self.global_ctx = get_global_context()
        self.token_counter = get_token_counter()

    def handle(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message end-to-end with advanced intent parsing.

        Args:
            message:    Natural language user input
            session_id: Existing session or None to create new
            context:    Optional additional context dict

        Returns:
            Dict with result, agent used, session_id, and intent confidence
        """
        from observability.logger import get_logger
        from observability.pii_sanitizer import PIISanitizer
        
        session_id = session_id or str(uuid.uuid4())
        session = self.session_store.get_or_create(session_id)
        
        otel_logger = get_logger("orchestrator")
        
        # Sanitize message before logging
        safe_message = PIISanitizer.sanitize_string(message)
        session.add_message("user", message)

        # 1. Parse intent with advanced parser
        from orchestrator.advanced_intent_parser import AdvancedIntentParser

        intent = AdvancedIntentParser(self.config).parse(
            safe_message,
            context=PIISanitizer.sanitize_dict(context or {}),
            conversation_history=session.get_conversation_history() if hasattr(session, 'get_conversation_history') else None
        )

        otel_logger.info(
            "Intent parsed",
            agent="orchestrator",
            action="intent_parsing",
            data={
                "agent": intent.get("agent"),
                "action": intent.get("action"),
                "confidence": intent.get("confidence"),
            }
        )

        logger.info(
            "[%s] Intent: %s → agent=%s (confidence: %.2f)",
            session_id,
            intent.get("action"),
            intent.get("agent"),
            intent.get("confidence", 0),
        )

        # 2. Route to agent
        from orchestrator.agent_router import AgentRouter

        result = AgentRouter().route(
            agent_name=intent["agent"],
            action=intent["action"],
            payload={**intent.get("params", {}), **(context or {})},
            session_id=session_id,
        )

        # 3. Save to session and global memory
        session.add_message(
            "assistant", str(result.get("llm_summary", result.get("message", "")))
        )
        self.global_ctx.append_to_list(
            f"session:{session_id}:results",
            {
                "intent": intent,
                "result_keys": list(result.keys()),
                "confidence": intent.get("confidence"),
            },
            agent="orchestrator",
            session_id=session_id,
        )

        return {
            "session_id": session_id,
            "intent": intent,
            "result": result,
            "token_usage": self.token_counter.totals(),
        }
