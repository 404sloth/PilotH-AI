from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, List, Tuple

from config.settings import Settings
from orchestrator.schemas import IntentResult
from observability.logger import get_logger
from observability.pii_sanitizer import PIISanitizer
from observability.metrics import get_metrics
from observability.tracing import get_tracer
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)
otel_logger = get_logger("intent_parser")


# ── Tool Registry with Descriptions ────────────────────────────────────────

TOOL_REGISTRY = {
    "system": {
        "agent_name": "system",
        "agent_description": "System-level operations and general conversational assistance",
        "actions": {
            "conversational": {
                "description": "Handle greetings, general questions, and capability inquiries",
                "triggers": [
                    "hello", "hi", "hey", "help", "what can you do", "features", "capabilities", "what you can able to do"
                ],
                "required_params": [],
                "optional_params": [],
                "default": True,
            }
        }
    },
    "vendor_management": {
        "agent_name": "vendor_management",
        "agent_description": "Intelligent vendor evaluation and management system",
        "actions": {
            "search_vendors": {
                "description": "List or browse vendors across all services, categories, or a filtered service/country/industry/category",
                "triggers": [
                    "list vendors",
                    "list all vendors",
                    "show vendors",
                    "all vendors",
                    "browse vendors",
                    "vendor list",
                    "vendors for different services",
                ],
                "required_params": [],
                "optional_params": ["service_required", "country", "vendor_name", "vendor_id", "industry", "category", "tier", "contract_status", "top_n"],
                "default": True,
            },
            "find_best": {
                "description": "Find and rank best vendors for a specific service with quality/cost/availability filters",
                "triggers": [
                    "find best vendor",
                    "best cloud vendor",
                    "find the best",
                    "best supplier",
                    "compare vendors",
                    "rank vendors",
                    "which vendor is best",
                    "vendor recommendation",
                    "best vendor",
                ],
                "required_params": ["service_required"],
                "optional_params": ["budget_monthly", "min_quality_score", "required_tier", "country"],
            },
            "full_assessment": {
                "description": "Complete vendor assessment including quality, reliability, SLA compliance, and risk analysis",
                "triggers": [
                    "assess vendor",
                    "vendor assessment",
                    "evaluate vendor",
                    "vendor details",
                    "tell me about vendor",
                    "vendor profile",
                ],
                "required_params": ["vendor_id", "vendor_name"],
                "optional_params": [],
            },
            "monitor_sla": {
                "description": "Check vendor SLA compliance, breaches, and performance metrics",
                "triggers": [
                    "check sla",
                    "sla compliance",
                    "vendor compliance",
                    "are they meeting sla",
                    "sla breach",
                    "performance metrics",
                ],
                "required_params": ["vendor_id"],
                "optional_params": [],
            },
            "track_milestones": {
                "description": "Monitor project milestone status with a vendor, identify delays and risks",
                "triggers": [
                    "track milestones",
                    "project status",
                    "milestone progress",
                    "are milestones delayed",
                    "project delays",
                    "delivery status",
                ],
                "required_params": ["vendor_id"],
                "optional_params": ["project_id"],
            },
            "summarize_contract": {
                "description": "Parse and summarize vendor contract terms, risk clauses, and key conditions",
                "triggers": [
                    "summarize contract",
                    "contract terms",
                    "what does contract say",
                    "contract analysis",
                    "contract review",
                    "contract key points",
                ],
                "required_params": ["contract_reference"],
                "optional_params": ["vendor_id"],
            },
        },
    },
    "meetings_communication": {
        "agent_name": "meetings_communication",
        "agent_description": "Intelligent meeting scheduling, summarization, and communication management",
        "actions": {
            "schedule": {
                "description": "Smart multi-timezone meeting scheduling with automatic conflict resolution and availability checking",
                "triggers": [
                    "schedule meeting",
                    "book meeting",
                    "schedule call",
                    "find meeting time",
                    "when can we meet",
                    "meeting slot",
                    "reserve time",
                ],
                "required_params": ["title", "participants"],
                "optional_params": ["preferred_time_range", "timezone", "duration_minutes", "location"],
            },
            "summarize": {
                "description": "Extract meeting summary, key decisions, action items, and sentiment from transcript or recording",
                "triggers": [
                    "summarize meeting",
                    "meeting summary",
                    "what was discussed",
                    "action items",
                    "decisions made",
                    "meeting notes",
                    "transcript summary",
                ],
                "required_params": ["meeting_id", "transcript"],
                "optional_params": [],
            },
            "brief": {
                "description": "Generate pre-meeting briefing with participant context, sentiment, proposed agenda, and key talking points",
                "triggers": [
                    "brief meeting",
                    "meeting briefing",
                    "prepare for meeting",
                    "agenda",
                    "meeting context",
                    "talking points",
                    "pre-meeting brief",
                ],
                "required_params": ["title", "participants"],
                "optional_params": ["context"],
            },
            "search_meetings": {
                "description": "Search for meetings by title, participant email, or date range",
                "triggers": [
                    "list meetings",
                    "show meetings",
                    "find meetings",
                    "all meetings",
                    "search meetings",
                    "meeting list",
                ],
                "required_params": [],
                "optional_params": ["title", "attendee_email", "date_from", "date_to", "limit"],
            },
        },
    },
    "knowledge_base": {
        "agent_name": "knowledge_base",
        "agent_description": "Semantic search and retrieval from vendor documents, agreements, and communications",
        "actions": {
            "search": {
                "description": "Search across knowledge base collections using semantic similarity",
                "triggers": [
                    "search knowledge base",
                    "find information about",
                    "what do we know about",
                    "look up",
                    "search for",
                    "find documents",
                    "query knowledge",
                    "information on",
                    "details about",
                    "tell me about",
                ],
                "required_params": ["query"],
                "optional_params": ["collection", "limit"],
            },
        },
    },
}


class IntentParser:
    """Advanced LLM-based Task Planner with dynamic tool discovery."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.tracer = get_tracer("intent_parser")
        self.metrics = get_metrics()

    def parse(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        agent_hint: Optional[str] = None,
        config: Optional[RunnableConfig] = None,
    ) -> Dict[str, Any]:
        """
        Parse user message into a strategic execution plan (list of tasks).
        """
        with self.tracer.trace_operation("task_planning", attributes={"message_length": len(message)}) as span:
            context = context or {}
            
            # Sanitize context
            safe_context = PIISanitizer.sanitize_dict(context)
            safe_message = PIISanitizer.sanitize_string(message)

            # Fast-path for simple greetings (optional, but keeps basic UX responsive)
            if self._is_simple_greeting(safe_message):
                return {
                    "plan": [{
                        "agent": "system",
                        "action": "conversational",
                        "params": {},
                        "reasoning": "Greeting detected."
                    }],
                    "confidence": 1.0,
                    "reasoning": "Simple greeting fast-path triggered."
                }

            try:
                # Primary Path: Dynamic LLM Planning
                result = self._generate_strategic_plan(
                    safe_message,
                    safe_context,
                    conversation_history,
                    span,
                    config,
                )
                if result:
                    self.metrics.increment_counter("planner.success")
                    return result.model_dump()

            except Exception as e:
                logger.error(f"Task Planning failed: {e}")
                self.metrics.increment_counter("planner.failure")

            # Fallback: Default to a safe assessment of the main topic
            return {
                "plan": [{
                    "agent": "vendor_management",
                    "action": "full_assessment",
                    "params": {"query": safe_message},
                    "reasoning": "Planner failed, falling back to general assessment."
                }],
                "confidence": 0.2,
                "reasoning": "Planning error, using safe fallback."
            }

    def _extract_json(self, text: str) -> str:
        """
        Robustly extract the last JSON block from a potentially verbose LLM response.
        Useful for models that include schema definitions or conversational filler.
        """
        # Look for JSON blocks between markdown or markers
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_blocks:
            return json_blocks[-1]
            
        # Fallback: find the main object boundaries
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
            
        return text

    def _is_simple_greeting(self, message: str) -> bool:
        lower = message.strip().lower()
        return lower in ["hi", "hello", "hey", "hi!", "hello!", "hey pilot"]

    def _generate_strategic_plan(
        self,
        message: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]],
        span,
        config: Optional[RunnableConfig] = None,
    ) -> Optional[IntentResult]:
        """
        Build a multi-step execution plan using dynamic tool metadata.
        """
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.output_parsers import PydanticOutputParser
        from orchestrator.discovery import CapabilityDiscoverer

        parser = PydanticOutputParser(pydantic_object=IntentResult)
        system_capabilities = CapabilityDiscoverer.get_system_capabilities()

        system_prompt = f"""You are the Master Strategic Planner for PilotH. 
Your goal is to decompose user requests into a high-precision execution plan using registered agents and tools.

AVAILABLE SYSTEM CAPABILITIES:
{system_capabilities}

STRATEGIC DIRECTIVES:
1. Break down complex requests into SEQUENTIAL or DEPENDENT steps.
2. Ensure data flows logically: e.g., if you need to summarize a meeting, you first need to FIND it.
3. If the user's intent is vague, start with a BROAD search or assessment.
4. Extract all entity IDs, names, and filters into task 'params'.
5. Always provide 'reasoning' for why a particular tool/agent was selected for each step.

CONTEXT:
{json.dumps(context)[:500]}

IMPORTANT: Provide ONLY the raw JSON object for the plan. 
DO NOT include the JSON schema ($defs, properties, etc.) in your response. 
DO NOT provide any conversational text outside the JSON block.

OUTPUT FORMAT:
{parser.get_format_instructions()}
"""

        messages = [SystemMessage(content=system_prompt)]
        if conversation_history:
            # Inject history as context but keep it concise
            history_str = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in conversation_history[-10:]])
            messages.append(SystemMessage(content=f"PAST CONVERSATION HISTORY:\n{history_str}"))

        messages.append(HumanMessage(content=f"USER REQUEST: {message}"))

        llm = get_llm(temperature=0) # High precision
        response = llm.invoke(messages, config=config)
        
        try:
            # Robust extraction before parsing
            json_blob = self._extract_json(response.content)
            intent = parser.parse(json_blob)
            return intent
        except Exception as e:
            logger.error(f"Planner output parsing failed: {e}\nRaw Content: {response.content}")
            return None
        descriptions = []
        for agent_key, agent_info in TOOL_REGISTRY.items():
            descriptions.append(f"\nAGENT: {agent_info.get('agent_name')}")
            for action_key, action_info in agent_info.get("actions", {}).items():
                params = action_info.get("required_params", []) + action_info.get("optional_params", [])
                param_str = f" Params: {', '.join(params)}" if params else ""
                descriptions.append(f"  - {action_key}: {action_info.get('description')}{param_str}")
        return "\n".join(descriptions)

    def _is_valid_agent_action(self, agent: str, action: str) -> bool:
        """Validate that agent and action exist in registry."""
        if agent not in TOOL_REGISTRY:
            return False
        
        agent_info = TOOL_REGISTRY.get(agent, {})
        if action not in agent_info.get("actions", {}):
            return False
        
        return True


# ── Utility Functions ─────────────────────────────────────────────────────

def parse_intent(
    message: str,
    config: Settings,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Quick utility function to parse intent using advanced parser.
    """
    parser = IntentParser(config)
    return parser.parse(message, context)


def get_tool_description(agent: str, action: str) -> str:
    """Get description of a specific tool for help/documentation."""
    agent_info = TOOL_REGISTRY.get(agent, {})
    action_info = agent_info.get("actions", {}).get(action, {})
    return action_info.get("description", "No description available")


def list_available_actions(agent: Optional[str] = None) -> Dict[str, Any]:
    """List all available agent actions."""
    if agent:
        return TOOL_REGISTRY.get(agent, {})
    return TOOL_REGISTRY


AdvancedIntentParser = IntentParser
