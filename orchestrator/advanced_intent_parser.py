"""
Advanced Intent Parser v2 — Intelligent agent and tool routing with LLM and PII safety.

Features:
  ✓ LLM-based intent detection with structured JSON output
  ✓ Tool capability matching (LLM understands what each tool can do)
  ✓ PII sanitization before LLM calls
  ✓ Confidence scoring and fallback routing
  ✓ Multi-turn context awareness
  ✓ Robust error handling with graceful degradation
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, List, Tuple

from config.settings import Settings
from observability.logger import get_logger
from observability.pii_sanitizer import PIISanitizer
from observability.metrics import get_metrics
from observability.tracing import get_tracer

logger = logging.getLogger(__name__)
otel_logger = get_logger("advanced_intent_parser")


# ── Tool Registry with Descriptions ────────────────────────────────────────

TOOL_REGISTRY = {
    "vendor_management": {
        "agent_name": "vendor_management",
        "agent_description": "Intelligent vendor evaluation and management system",
        "actions": {
            "find_best": {
                "description": "Find and rank best vendors for a specific service with quality/cost/availability filters",
                "triggers": [
                    "find best vendor",
                    "best supplier",
                    "compare vendors",
                    "rank vendors",
                    "which vendor is best",
                    "vendor recommendation",
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
        },
    },
}


class AdvancedIntentParser:
    """Advanced LLM-based intent parser with multi-turn context and tool understanding."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.tracer = get_tracer("advanced_intent_parser")
        self.metrics = get_metrics()

    def parse(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Parse user message into structured agent + action + params.

        Args:
            message: User natural language request
            context: Current session/user context
            conversation_history: Previous turns for multi-turn awareness

        Returns:
            {
                "agent": "vendor_management|meetings_communication",
                "action": "find_best|full_assessment|...",
                "params": {extracted parameters},
                "confidence": 0.0-1.0,
                "reasoning": "Why this choice was made",
                "tool_calls": [...] # Optional direct tool calls
            }
        """
        with self.tracer.trace_operation("intent_parsing", attributes={"message_length": len(message)}) as span:
            context = context or {}
            
            # Sanitize context Before LLM call
            safe_context = PIISanitizer.sanitize_dict(context)
            safe_message = PIISanitizer.sanitize_string(message)

            try:
                # Try advanced LLM parsing
                result = self._llm_parse_advanced(
                    safe_message,
                    safe_context,
                    conversation_history,
                    span,
                )
                if result and result.get("confidence", 0) >= 0.5:
                    span.add_event("llm_parse_success", {"confidence": result.get("confidence")})
                    self.metrics.increment_counter(
                        "intent_parse.success",
                        attributes={"method": "llm_advanced"},
                    )
                    return result

            except Exception as e:
                otel_logger.warning("Advanced LLM parsing failed", error=str(e), message=safe_message)
                self.metrics.increment_counter(
                    "intent_parse.fallback",
                    attributes={"reason": "llm_error"},
                )

            # Fallback to keyword-based routing
            span.add_event("fallback_to_keyword_routing")
            result = self._keyword_parse(safe_message)
            self.metrics.increment_counter(
                "intent_parse.success",
                attributes={"method": "keyword_routing"},
            )
            return result

    def _llm_parse_advanced(
        self,
        message: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]],
        span,
    ) -> Dict[str, Any]:
        """
        Use LLM with advanced prompting to understand intent.
        
        Returns structured JSON with agent, action, params, confidence.
        """
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        # Build tool descriptions for LLM
        tool_descriptions = self._build_tool_descriptions()

        # Build system prompt
        system_prompt = f"""You are an intelligent agent dispatcher with expertise in:
1. Vendor management and procurement
2. Meeting scheduling and communication
3. Enterprise automation

Your job: Understand user requests and determine which agent and action to execute.

Available Agents and Tools:
{tool_descriptions}

Instructions:
1. Carefully analyze the user request
2. Match to the most relevant agent and action
3. Extract all relevant parameters from the message
4. Provide confidence score (0.0-1.0) based on clarity
5. Explain your reasoning

Context:
{json.dumps(context, indent=2)[:500]}

Return ONLY valid JSON with NO markdown:
{{
    "agent": "<agent_name>",
    "action": "<action_name>",
    "params": {{<extracted_parameters>}},
    "confidence": <float>,
    "reasoning": "<explanation>"
}}"""

        # Add conversation history if available
        messages = [SystemMessage(content=system_prompt)]
        if conversation_history:
            for turn in conversation_history[-5:]:  # Last 5 turns for context
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))

        messages.append(HumanMessage(content=f"User request: {message}"))

        # Call LLM
        llm = get_llm(temperature=0.0, max_tokens=1000)
        response = llm.invoke(messages)
        content = response.content.strip()

        # Parse JSON response
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)

        # Validate agent and action
        if not self._is_valid_agent_action(parsed.get("agent"), parsed.get("action")):
            return None

        return {
            "agent": parsed.get("agent"),
            "action": parsed.get("action"),
            "params": parsed.get("params", {}),
            "confidence": parsed.get("confidence", 0.7),
            "reasoning": parsed.get("reasoning", ""),
        }

    def _keyword_parse(self, message: str) -> Dict[str, Any]:
        """Fallback keyword-based routing with scoring."""
        lower = message.lower()
        
        # Score each possible agent+action combination
        scores: Dict[Tuple[str, str], int] = {}
        
        for agent_key, agent_info in TOOL_REGISTRY.items():
            for action_key, action_info in agent_info.get("actions", {}).items():
                # Calculate score based on triggers
                score = 0
                for trigger in action_info.get("triggers", []):
                    if trigger.lower() in lower:
                        score += len(trigger)  # Longer matches score higher
                
                if score > 0:
                    scores[(agent_key, action_key)] = score
        
        # Pick highest scoring agent+action
        if scores:
            agent, action = max(scores.items(), key=lambda x: x[1])[0]
            return {
                "agent": agent,
                "action": action,
                "params": {},
                "confidence": min(0.6, len(scores.keys()) * 0.2),  # Lower confidence for keyword matching
                "reasoning": f"Matched by keyword triggers",
            }
        
        # Ultimate fallback
        return {
            "agent": "vendor_management",
            "action": "full_assessment",
            "params": {},
            "confidence": 0.3,
            "reasoning": "No clear intent detected, using default agent",
        }

    def _build_tool_descriptions(self) -> str:
        """Build comprehensive tool descriptions for LLM understanding."""
        descriptions = []
        
        for agent_key, agent_info in TOOL_REGISTRY.items():
            descriptions.append(f"\n=== {agent_info.get('agent_name')} ===")
            descriptions.append(f"Description: {agent_info.get('agent_description')}")
            descriptions.append("Actions:")
            
            for action_key, action_info in agent_info.get("actions", {}).items():
                descriptions.append(f"\n  • {action_key}")
                descriptions.append(f"    Description: {action_info.get('description')}")
                descriptions.append(f"    Triggers: {', '.join(action_info.get('triggers', []))}")
                
                if action_info.get("required_params"):
                    descriptions.append(f"    Required: {', '.join(action_info.get('required_params'))}")
                if action_info.get("optional_params"):
                    descriptions.append(f"    Optional: {', '.join(action_info.get('optional_params'))}")
        
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
    
    Args:
        message: User request
        config: App settings
        context: Optional session context
    
    Returns:
        Parsed intent dict
    """
    parser = AdvancedIntentParser(config)
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
