"""
Intent Parser — intelligent agent and tool routing with LLM and PII safety.

This is the primary parser implementation. It preserves the original user
query for agent selection and parameter extraction while using sanitized
payloads for LLM/logging paths that need them.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, List, Tuple

from config.settings import Settings
from observability.logger import get_logger
from observability.pii_sanitizer import PIISanitizer
from observability.metrics import get_metrics
from observability.tracing import get_tracer

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
    """Primary LLM-based intent parser with multi-turn context and tool understanding."""

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
    ) -> Dict[str, Any]:
        """
        Parse user message into structured agent + action + params.

        Args:
            message: User natural language request
            context: Current session/user context
            conversation_history: Previous turns for multi-turn awareness
            agent_hint: Optional hint for which agent to prefer (e.g., "vendor_management")

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

            # Fast-path for conversational queries
            if self._is_conversational(safe_message):
                return {
                    "agent": "system",
                    "action": "conversational",
                    "params": {},
                    "confidence": 1.0,
                    "reasoning": "Detected conversational or help request."
                }

            # If agent_hint provided and valid, use it directly
            if agent_hint and agent_hint in TOOL_REGISTRY:
                span.add_event("using_agent_hint", {"agent": agent_hint})
                result = self._parse_with_agent_hint(message, agent_hint, safe_context)
                if result:
                    result = self._post_process_intent(message, result)
                    self.metrics.increment_counter(
                        "intent_parse.success",
                        tags={"method": "agent_hint"},
                    )
                    return result

            try:
                # Try advanced LLM parsing
                result = self._llm_parse_advanced(
                    safe_message,
                    safe_context,
                    conversation_history,
                    span,
                )
                if result and result.get("confidence", 0) >= 0.5:
                    result = self._post_process_intent(message, result)
                    span.add_event("llm_parse_success", {"confidence": result.get("confidence")})
                    self.metrics.increment_counter(
                        "intent_parse.success",
                        tags={"method": "llm_advanced"},
                    )
                    return result

            except Exception as e:
                otel_logger.warning(f"Advanced LLM parsing failed: {safe_message}", error=str(e))
                self.metrics.increment_counter(
                    "intent_parse.fallback",
                    tags={"reason": "llm_error"},
                )

            # Fallback to keyword-based routing
            span.add_event("fallback_to_keyword_routing")
            result = self._keyword_parse(message)
            result = self._post_process_intent(message, result)
            self.metrics.increment_counter(
                "intent_parse.success",
                tags={"method": "keyword_routing"},
            )
            return result

    def _is_conversational(self, message: str) -> bool:
        lower = message.strip().lower()
        if lower in ["hi", "hello", "hey", "hey!", "hi!", "hello!", "hi pilot", "hi piloth"]:
            return True
        if any(term in lower for term in ["what can you do", "list all features", "help me", "who are you", "what you can able to do"]):
            return True
        return False

    def _llm_parse_advanced(
        self,
        message: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]],
        span,
    ) -> Dict[str, Any]:
        """
        Use LLM with advanced prompting to understand intent.
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
3. Extract all relevant parameters from the message (e.g. for vendor searches, look for specific countries, categories, industries, tiers like 'preferred', or contract status like 'active').
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
        llm = get_llm(temperature=0.0)
        # Check if we should use specialized intent model if configured
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

    def _parse_with_agent_hint(
        self,
        message: str,
        agent_hint: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Parse intent when agent is hinted, focusing on action detection within that agent.
        """
        if agent_hint == "vendor_management":
            return self._parse_vendor_intent(message, hinted=True)
        if agent_hint == "meetings_communication":
            return self._parse_communication_intent(message, hinted=True)

        lower = message.lower()
        agent_info = TOOL_REGISTRY.get(agent_hint, {})
        
        # Score actions within the hinted agent
        scores: Dict[str, int] = {}
        
        for action_key, action_info in agent_info.get("actions", {}).items():
            score = 0
            for trigger in action_info.get("triggers", []):
                if trigger.lower() in lower:
                    score += len(trigger)  # Longer matches score higher
            
            if score > 0:
                scores[action_key] = score
        
        # If we found matching actions, use the best one
        if scores:
            action = max(scores.items(), key=lambda x: x[1])[0]
            return {
                "agent": agent_hint,
                "action": action,
                "params": {},
                "confidence": 0.8,  # Higher confidence for hinted agent
                "reasoning": f"Agent hinted as '{agent_hint}', matched action by keyword triggers",
            }
        
        # If no clear action match, use the agent's default action
        default_action = self._get_default_action(agent_hint)
        if default_action:
            return {
                "agent": agent_hint,
                "action": default_action,
                "params": {},
                "confidence": 0.6,
                "reasoning": f"Agent hinted as '{agent_hint}', using default action",
            }
        
        return None

    def _get_default_action(self, agent: str) -> Optional[str]:
        """Get the default action for an agent."""
        agent_info = TOOL_REGISTRY.get(agent, {})
        actions = agent_info.get("actions", {})
        
        # Look for a default action or pick the first one
        for action_key, action_info in actions.items():
            if action_info.get("default", False):
                return action_key
        
        # If no default, pick the first action
        return next(iter(actions.keys()), None)

    def _keyword_parse(self, message: str) -> Dict[str, Any]:
        """Fallback keyword-based routing with scoring."""
        lower = message.lower()

        if "vendor" in lower:
            # Special case: "list all meetings" contains list and all, but we must favor communication if "meeting" is present
            if "meeting" not in lower:
                return self._parse_vendor_intent(message, hinted=False)
        
        if "meeting" in lower or "schedule" in lower or "brief" in lower:
            return self._parse_communication_intent(message, hinted=False)
        
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
        
        # Special-case cheaper fallback for vendor discovery requests
        if "best" in lower and "vendor" in lower:
            return {
                "agent": "vendor_management",
                "action": "find_best",
                "params": {},
                "confidence": 0.4,
                "reasoning": "Keyword heuristic detected vendor discovery request",
            }

        # Ultimate fallback
        return {
            "agent": "vendor_management",
            "action": "full_assessment",
            "params": {},
            "confidence": 0.3,
            "reasoning": "No clear intent detected, using default agent",
        }

    def _post_process_intent(self, message: str, intent: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Fill missing params and correct obviously inconsistent vendor intents."""
        if not intent:
            return intent

        if intent.get("agent") == "vendor_management":
            # If user mentions "meeting", reconsider
            if "meeting" in message.lower() and "vendor" not in message.lower():
                comm_intent = self._parse_communication_intent(message, hinted=True)
                if comm_intent and comm_intent["confidence"] > 0.6:
                    return comm_intent

            parsed_vendor_intent = self._parse_vendor_intent(message, hinted=True)
            if parsed_vendor_intent:
                merged = dict(intent)
                merged_params = {**parsed_vendor_intent.get("params", {}), **intent.get("params", {})}
                merged["params"] = {k: v for k, v in merged_params.items() if v not in (None, "", [], {})}
                return merged

        return intent

    def _parse_vendor_intent(self, message: str, hinted: bool) -> Dict[str, Any]:
        """Rule-based vendor intent parser with parameter extraction."""
        lower = message.lower()
        
        # Hard exclusion for meeting search
        if "meeting" in lower and "vendor" not in lower:
            return None

        params = self._extract_vendor_params(message)

        discovery_request = (
            ("vendor" in lower and any(term in lower for term in ["list", "show", "browse", "all vendors", "vendor list"]))
            or "different services" in lower
            or "across all category" in lower
            or "across all categories" in lower
            or "industry" in lower
            or "category" in lower
        )
        best_request = (
            "vendor" in lower
            and any(term in lower for term in ["best", "rank", "recommend", "compare"])
        )
        assessment_request = any(
            term in lower
            for term in ["assess vendor", "vendor assessment", "evaluate vendor", "vendor profile", "vendor details", "tell me about vendor"]
        )

        if discovery_request and not params.get("service_required") and not params.get("industry") and not params.get("category"):
            params.setdefault("top_n", 20)
            return {
                "agent": "vendor_management",
                "action": "search_vendors",
                "params": params,
                "confidence": 0.92 if hinted else 0.82,
                "reasoning": "Vendor discovery request asking for a list or browse view.",
            }

        if discovery_request:
            params.setdefault("top_n", 20)
            return {
                "agent": "vendor_management",
                "action": "search_vendors",
                "params": params,
                "confidence": 0.9 if hinted else 0.8,
                "reasoning": "Vendor discovery request with filters.",
            }

        if best_request:
            return {
                "agent": "vendor_management",
                "action": "find_best",
                "params": params,
                "confidence": 0.9 if params.get("service_required") else 0.65,
                "reasoning": "Vendor ranking request detected from best/recommend/compare language.",
            }

        if assessment_request or params.get("vendor_id") or params.get("vendor_name"):
            return {
                "agent": "vendor_management",
                "action": "full_assessment",
                "params": params,
                "confidence": 0.88 if (params.get("vendor_id") or params.get("vendor_name")) else 0.55,
                "reasoning": "Specific vendor assessment request detected.",
            }

        return {
            "agent": "vendor_management",
            "action": "full_assessment",
            "params": params,
            "confidence": 0.3,
            "reasoning": "Default vendor fallback.",
        }

    def _parse_communication_intent(self, message: str, hinted: bool) -> Dict[str, Any]:
        """Rule-based communication intent parser."""
        lower = message.lower()
        
        search_request = any(term in lower for term in ["list meeting", "show meetings", "find meetings", "all meetings", "meeting list"])
        summarize_request = any(term in lower for term in ["summarize", "summary", "notes from"])
        brief_request = any(term in lower for term in ["brief", "prepare for", "briefing"])
        schedule_request = any(term in lower for term in ["schedule", "book", "reserve"])

        if search_request:
            return {
                "agent": "meetings_communication",
                "action": "search_meetings",
                "params": {},
                "confidence": 0.95 if hinted else 0.85,
                "reasoning": "Detected meeting search or listing request.",
            }
        
        if summarize_request:
            return {
                "agent": "meetings_communication",
                "action": "summarize",
                "params": {},
                "confidence": 0.8,
                "reasoning": "Detected meeting summarization request.",
            }

        if schedule_request:
            return {
                "agent": "meetings_communication",
                "action": "schedule",
                "params": {},
                "confidence": 0.8,
                "reasoning": "Detected meeting scheduling request.",
            }

        return {
            "agent": "meetings_communication",
            "action": "brief",
            "params": {},
            "confidence": 0.3,
            "reasoning": "Default communication fallback.",
        }

    def _extract_vendor_params(self, message: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        lower = message.lower()

        service_required = self._extract_service_tag(message)
        if service_required:
            params["service_required"] = service_required

        category = self._extract_category(message)
        if category:
            params["category"] = category

        if "not on industry" not in lower and "not industry" not in lower:
            industry = self._extract_industry(message)
            if industry:
                params["industry"] = industry

        budget = self._extract_budget(message)
        if budget is not None:
            params["budget_monthly"] = budget

        vendor_id_match = re.search(r"\bV-\d+\b", message, flags=re.IGNORECASE)
        if vendor_id_match:
            params["vendor_id"] = vendor_id_match.group(0).upper()

        name_match = re.search(
            r"(?:assess|evaluate|profile|details(?: for)?|tell me about)\s+(?:vendor\s+)?([A-Za-z][A-Za-z0-9&.\- ]{2,})",
            message,
            flags=re.IGNORECASE,
        )
        if name_match and not params.get("vendor_id"):
            params["vendor_name"] = name_match.group(1).strip(" .")

        if "preferred" in lower:
            params["tier"] = "preferred"
        elif "standard" in lower:
            params["tier"] = "standard"
        elif "trial" in lower:
            params["tier"] = "trial"

        if "active" in lower:
            params["contract_status"] = "active"
        elif "expired" in lower:
            params["contract_status"] = "expired"

        if re.search(r"\b(?:us|usa|united states)\b", lower):
            params["country"] = "US"
        elif re.search(r"\beu\b|\beurope\b", lower):
            params["country"] = "EU"
        elif re.search(r"\b(?:gb|uk|united kingdom)\b", lower):
            params["country"] = "GB"

        if "all vendors" in lower or "across all" in lower:
            params["top_n"] = 20

        return params

    def _extract_service_tag(self, message: str) -> Optional[str]:
        lower = message.lower()
        service_map = {
            "cloud hosting": "cloud_hosting",
            "cloud": "cloud_hosting",
            "hosting": "cloud_hosting",
            "cloud storage": "cloud_storage",
            "storage": "cloud_storage",
            "data analytics": "data_analytics",
            "analytics": "data_analytics",
            "bi dashboard": "bi_dashboards",
            "dashboard": "bi_dashboards",
            "ci/cd": "ci_cd_pipelines",
            "cicd": "ci_cd_pipelines",
            "pipeline": "ci_cd_pipelines",
            "backup": "backup_dr",
            "disaster recovery": "backup_dr",
            "communication": "communication_platform",
            "telecom": "telecom",
            "monitor": "monitoring",
            "database": "database_service",
            "api": "api_gateway",
            "security": "security_tools",
            "compliance": "compliance_officer",
            "kubernetes": "managed_kubernetes",
            "devops": "devops_consulting",
            "etl": "etl_pipelines",
            "ml": "ml_engineering",
            "warehouse": "warehousing",
            "freight": "freight_forwarding",
            "delivery": "last_mile_delivery",
        }

        matched_service = None
        matched_len = -1
        for keyword, service_tag in service_map.items():
            if keyword in lower and len(keyword) > matched_len:
                matched_service = service_tag
                matched_len = len(keyword)
        return matched_service

    def _extract_category(self, message: str) -> Optional[str]:
        lower = message.lower()
        category_map = {
            "it services": "IT Services",
            "cloud & infrastructure": "Cloud & Infrastructure",
            "cloud infrastructure": "Cloud & Infrastructure",
            "data analytics": "Data Analytics",
            "devops & ci/cd": "DevOps & CI/CD",
            "devops": "DevOps & CI/CD",
            "cybersecurity": "Cybersecurity",
            "security": "Cybersecurity",
            "manufacturing": "Manufacturing",
            "logistics": "Logistics",
            "marketing & design": "Marketing & Design",
            "marketing": "Marketing & Design",
            "legal & compliance": "Legal & Compliance",
            "legal": "Legal & Compliance",
        }
        for keyword, cat_name in category_map.items():
            if keyword in lower:
                return cat_name
        
        # If "cloud service related categories"
        if "cloud service" in lower and "categories" in lower:
            return "Cloud & Infrastructure"

        return None

    def _extract_industry(self, message: str) -> Optional[str]:
        lower = message.lower()
        industry_map = {
            "technology": "Technology",
            "tech": "Technology",
            "finance": "Finance",
            "banking": "Finance",
            "healthcare": "Healthcare",
            "medical": "Healthcare",
            "logistics": "Logistics",
            "shipping": "Logistics",
            "retail": "Retail",
            "ecommerce": "Retail",
            "manufacturing": "Manufacturing",
            "energy": "Energy",
            "telecom": "Telecommunications",
        }
        
        # Try specific industry pattern: related to 'X' industry or X industry
        match = re.search(r"(?:related to\s+)?['\"]?([A-Za-z]+)['\"]?\s+industry", lower)
        if match:
            industry_val = match.group(1).lower()
            return industry_map.get(industry_val, industry_val.capitalize())

        for keyword, industry_name in industry_map.items():
            if keyword in lower:
                return industry_name
        return None

    def _extract_budget(self, message: str) -> Optional[float]:
        normalized = message.lower().replace(",", "")
        match = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(k|m)?\s*(?:budget|/month|per month|monthly)?", normalized)
        if not match:
            return None
        amount = float(match.group(1))
        suffix = match.group(2)
        if suffix == "k":
            amount *= 1000
        elif suffix == "m":
            amount *= 1_000_000
        return amount

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
