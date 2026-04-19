"""
Orchestrator Controller — main entry point for all user requests.
Parses intent → decomposes tasks → routes to agents → aggregates results.
"""

from __future__ import annotations

import logging
import uuid
import json
from typing import Any, Dict, Optional, List

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

        if intent.get("agent") == "system" and intent.get("action") == "conversational":
            assistant_response = self._generate_dynamic_help(message, TOOL_REGISTRY)
            result = {"response": assistant_response}
            formatted_result = {"response": assistant_response, "data": {}}
        else:
            # 2. Route to agent
            from orchestrator.agent_router import AgentRouter

            result = AgentRouter().route(
                agent_name=intent["agent"],
                action=intent["action"],
                payload={**intent.get("params", {}), **runtime_context},
                session_id=session_id,
            )

            # 3. Format and filter final output using LLM for intelligent layout
            formatted_result = self._format_final_output_with_llm(result, intent, message)

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

    def _generate_dynamic_help(self, user_query: str, registry: Dict[str, Any]) -> str:
        """Use LLM to generate a professional help message based on current registry."""
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        # Simplify registry for LLM context
        capabilities = []
        for agent_id, info in registry.items():
            if agent_id == "system": continue
            agent_cap = {
                "name": info.get("agent_name"),
                "description": info.get("agent_description"),
                "features": [act["description"] for act in info.get("actions", {}).values()]
            }
            capabilities.append(agent_cap)

        prompt = f"""You are PilotH, an Enterprise Intelligence Console. 
The user is asking about your features or saying hello.
Based on the registered capabilities below, write a professional, welcoming response.

Capabilities:
{json.dumps(capabilities, indent=2)}

User Query: "{user_query}"

Guidelines:
- Be concise but thorough.
- Group features by domain (Vendor Management, Communications, etc.).
- Use bullet points for readability.
- Mention that you can handle complex data requests and formatting.
"""
        try:
            llm = get_llm(temperature=0.3)
            resp = llm.invoke([HumanMessage(content=prompt)])
            return resp.content.strip()
        except Exception:
            return "I am PilotH. I can help with Vendor Management, Meeting Communication, and Knowledge Retrieval. How can I assist?"

    def _format_final_output_with_llm(self, result: Dict[str, Any], intent: Dict[str, Any], original_query: str) -> Dict[str, Any]:
        """Use LLM to intelligently format the raw agent data into a professional enterprise layout."""
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        # If agent already provided a good summary, use it
        if result.get("llm_summary"):
            return {"response": result["llm_summary"], "data": result}

        agent = intent.get("agent", "")
        action = intent.get("action", "")

        prompt = f"""You are a senior enterprise data strategist. Your goal is to transform raw system data into a beautiful, professional, and actionable response for the user.

USER'S REQUEST: "{original_query}"
INTELLIGENCE SOURCE: {agent} (Action: {action})

RAW DATA PAYLOAD:
{json.dumps(result, indent=2)[:5000]}

INSTRUCTIONS:
1. STRUCTURE: Use clear headings (##) and sub-headings (###) to organize information.
2. TABLES: If the data contains lists of items (vendors, meetings, metrics), ALWAYS present them in a clean Markdown Table format.
   - Example: | Name | Status | Expiry |
              |------|--------|--------|
3. BULLETS: Use bullet points for key findings, risks, or recommendations.
4. TYPOGRAPHY: Use **bold** for emphasis and `code` for IDs or specific references.
5. EXPLANATION: After presenting data/tables, provide a concise "Executive Analysis" explaining what the data means for the user.
6. NO PLACEHOLDERS: Do NOT say 'See details below'. You are the detail. Present everything here.
7. PROFESSIONALISM: Maintain a premium, high-trust enterprise tone.

If no relevant data was found, provide a professional explanation of what was searched and suggest specific alternative queries.
"""
        try:
            llm = get_llm(temperature=0.1)  # Low temp for precise formatting
            resp = llm.invoke([HumanMessage(content=prompt)])
            return {"response": resp.content.strip(), "data": result}
        except Exception:
            return {"response": "Request processed successfully. Please refer to the intelligence trace for the raw results.", "data": result}
