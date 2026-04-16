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
from llm.model_factory import ConversationManager, Conversation

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
        agent_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message end-to-end with advanced intent parsing and conversation storage.

        Args:
            message:    Natural language user input
            session_id: Existing session or None to create new
            context:    Optional additional context dict
            agent_hint: Optional hint for which agent to prefer

        Returns:
            Dict with result, agent used, session_id, conversation_id, and intent confidence
        """
        from observability.logger import get_logger
        from observability.pii_sanitizer import PIISanitizer

        session_id = session_id or str(uuid.uuid4())
        session = self.session_store.get_or_create(session_id)
        runtime_context = dict(context or {})
        user_message_metadata = dict(runtime_context.pop("user_message_metadata", {}) or {})
        if agent_hint:
            user_message_metadata.setdefault("agent_hint", agent_hint)

        # Get or create conversation
        conversation_id = runtime_context.get("conversation_id")
        if conversation_id:
            conversation = ConversationManager.get_conversation(conversation_id)
            if not conversation:
                conversation = Conversation.create_new(
                    {"session_id": session_id},
                    conversation_id=conversation_id,
                )
        else:
            conversation = Conversation.create_new({"session_id": session_id})
            conversation_id = conversation.id

        otel_logger = get_logger("orchestrator")

        # Add user message to conversation
        conversation.add_message(
            "user",
            message,
            {
                "session_id": session_id,
                **user_message_metadata,
            },
        )

        # Sanitize message before logging
        safe_message = PIISanitizer.sanitize_string(message)
        session.add_message("user", message)

        # 1. Parse intent with advanced parser
        from orchestrator.intent_parser import IntentParser, get_tool_description, TOOL_REGISTRY

        intent = IntentParser(self.config).parse(
            message,
            context=PIISanitizer.sanitize_dict(runtime_context),
            conversation_history=session.get_conversation_history() if hasattr(session, 'get_conversation_history') else None,
            agent_hint=agent_hint,
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
            payload={**intent.get("params", {}), **runtime_context},
            session_id=session_id,
        )

        # 3. Format and filter final output
        formatted_result = self._format_final_output(result, intent)

        # 4. Save to session and global memory
        assistant_response = formatted_result.get("response", "")
        session.add_message("assistant", assistant_response)

        # Add assistant response to conversation
        conversation.add_message("assistant", assistant_response, {
            "agent": intent.get("agent"),
            "action": intent.get("action"),
            "confidence": intent.get("confidence"),
            "session_id": session_id
        })

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
            "conversation_id": conversation_id,
            "response": assistant_response,
            "data": formatted_result.get("data", {}),
            "metadata": {
                "original_query": message,
                "sanitized_query": safe_message,
                "agent": intent.get("agent"),
                "action": intent.get("action"),
                "agent_description": TOOL_REGISTRY.get(intent.get("agent"), {}).get("agent_description"),
                "action_description": get_tool_description(intent.get("agent"), intent.get("action")),
                "tool_descriptions": {
                    action_name: action_info.get("description", "")
                    for action_name, action_info in TOOL_REGISTRY.get(intent.get("agent"), {}).get("actions", {}).items()
                },
                "intent_reasoning": intent.get("reasoning"),
                "params": intent.get("params", {}),
                "confidence": intent.get("confidence"),
                "token_usage": self.token_counter.totals(),
            }
        }

    def _format_final_output(self, result: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format the final output for user consumption, filtering out unnecessary information.
        """
        from observability.pii_sanitizer import PIISanitizer

        agent = intent.get("agent", "")
        action = intent.get("action", "")

        # Extract the most relevant response text
        response_text = ""
        if "llm_summary" in result:
            response_text = result["llm_summary"]
        elif "message" in result:
            response_text = result["message"]
        elif "response" in result:
            response_text = result["response"]
        else:
            # Generate a summary based on the result structure
            response_text = self._generate_response_summary(result, agent, action)

        # Filter data for output - remove internal fields
        filtered_data = {}
        important_keys = {
            "vendor_management": [
                "vendors",
                "ranked_vendors",
                "top_recommendation",
                "overall_score",
                "sla_compliance",
                "evaluation_breakdown",
                "strengths",
                "weaknesses",
                "risks",
                "recommendations",
                "vendor_id",
                "vendor_name",
            ],
            "meetings_communication": ["meeting", "summary", "agenda", "participants"],
            "knowledge_base": ["documents", "total_results", "query"]
        }

        keys_to_include = important_keys.get(agent, [])
        for key in keys_to_include:
            if key in result:
                filtered_data[key] = result[key]

        return {
            "response": response_text,
            "data": filtered_data
        }

    def _generate_response_summary(self, result: Dict[str, Any], agent: str, action: str) -> str:
        """Generate a human-readable summary when no explicit response is available."""
        if agent == "vendor_management":
            if action == "search_vendors":
                vendors = result.get("vendors", [])
                if vendors:
                    names = ", ".join(v.get("name", "Unknown") for v in vendors[:5])
                    return f"I found {len(vendors)} vendors matching your request. Sample matches: {names}."
                return "No vendors found matching your request. Try broadening the filters."

            if action == "find_best":
                vendors = result.get("ranked_vendors", [])
                if vendors:
                    top_vendor = vendors[0]
                    return f"I found {len(vendors)} ranked vendors. The top recommendation is {top_vendor.get('name', 'Unknown')} with a fit score of {top_vendor.get('fit_score', 'N/A')}."
                return "No vendors found matching your criteria. Try adjusting your requirements."
            
            elif action == "full_assessment":
                return f"Completed assessment for vendor. Key findings: {result.get('summary', 'See detailed results below.')}"
            
            elif action == "monitor_sla":
                return f"SLA monitoring complete. Current status: {result.get('status', 'Check details below.')}"
        
        elif agent == "meetings_communication":
            if action == "schedule":
                return f"Meeting scheduled successfully. Details: {result.get('meeting_details', 'See below.')}"
            
            elif action == "summarize":
                return f"Meeting summary generated. Key points: {result.get('key_points', 'See full summary below.')}"
        
        elif agent == "knowledge_base":
            total = result.get("total_results", 0)
            return f"Found {total} relevant documents in the knowledge base. See results below."

        # Default fallback
        return "Task completed successfully. See detailed results below."
