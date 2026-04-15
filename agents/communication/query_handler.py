"""
Communication Agent Query Handler.

Intelligently routes and handles diverse communication-related queries:
  - Schedule meeting across timezones
  - Send briefing documents
  - Summarize existing meetings
  - Generate agendas
  - Send notifications
  - Resolve scheduling conflicts
  - Track action items
  
Parses natural language intent and maps to appropriate tools.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage

from observability.logger import get_logger
from observability.metrics import get_metrics
from observability.tracing import get_tracer
from observability.pii_sanitizer import sanitize_data

logger = logging.getLogger(__name__)
otel_logger = get_logger("communication.query_handler")


class QueryIntentType(str, Enum):
    """Intent types for communication queries."""
    SCHEDULE = "schedule_meeting"
    SUMMARIZE = "summarize_meeting"
    BRIEF = "generate_briefing"
    AGENDA = "generate_agenda"
    NOTIFY = "send_notification"
    RESOLVE_CONFLICT = "resolve_conflict"
    TRACK_ACTIONS = "track_actions"
    AVAILABILITY = "check_availability"
    UNKNOWN = "unknown"


@dataclass
class ParsedQueryIntent:
    """Result of query intent parsing."""
    intent: QueryIntentType
    confidence: float  # 0-1
    parameters: Dict[str, Any]
    explanation: str
    requires_clarification: bool = False


class CommunicationQueryHandler:
    """
    Intelligent query handler for communication agent.
    
    Flow:
      1. Parse user query to extract intent
      2. Extract parameters (attendees, timezone, time, etc)
      3. Route to appropriate tools
      4. Aggregate results
      5. Return briefing
    """

    def __init__(self):
        """Initialize handler."""
        self.tracer = get_tracer("communication")
        self.metrics = get_metrics()

    def parse_query(self, query: str) -> ParsedQueryIntent:
        """
        Parse natural language query to extract intent and parameters.
        
        Args:
            query: Natural language query string
            
        Returns:
            ParsedQueryIntent with detected intent and extracted parameters
        """
        with self.tracer.trace_operation(
            "query_parsing",
            attributes={"query_length": len(query)}
        ) as span:
            otel_logger.info(
                "Parsing communication query",
                agent="communication",
                action="query_parse",
                data={"query_length": len(query)},
            )

            # Sanitize query for logging
            sanitized_query = sanitize_data(query)

            try:
                # Use LLM to parse intent
                intent, confidence, params, explanation = (
                    self._parse_with_llm(query)
                )
                span.add_event(
                    "intent_detected",
                    {"intent": intent, "confidence": confidence},
                )
            except Exception as e:
                otel_logger.warning(
                    "LLM parsing failed, using rule-based detection",
                    agent="communication",
                    error=str(e),
                )
                intent, confidence, params, explanation = (
                    self._parse_with_rules(query)
                )
                span.add_event("rule_based_parsing_used")

            self.metrics.record_histogram(
                "communication_query.parse_confidence",
                confidence,
                attributes={"intent": intent},
            )
            self.metrics.increment_counter(
                "communication_query.parsed",
                attributes={"intent": intent},
            )

            requires_clarification = confidence < 0.6

            parsed = ParsedQueryIntent(
                intent=QueryIntentType(intent),
                confidence=confidence,
                parameters=params,
                explanation=explanation,
                requires_clarification=requires_clarification,
            )

            otel_logger.info(
                "Query parsing complete",
                agent="communication",
                action="parse_complete",
                data={
                    "intent": parsed.intent.value,
                    "confidence": parsed.confidence,
                    "requires_clarification": requires_clarification,
                },
            )

            return parsed

    def _parse_with_llm(self, query: str) -> tuple:
        """
        Use LLM to parse query intent and extract parameters.
        
        Returns:
            (intent_type, confidence, parameters_dict, explanation)
        """
        from llm.model_factory import get_llm

        prompt = f"""Analyze this communication query and extract the intent and parameters.

Query: "{query}"

Return JSON with:
{{
    "intent": one of [schedule_meeting, summarize_meeting, generate_briefing, 
                      generate_agenda, send_notification, resolve_conflict, 
                      track_actions, check_availability, unknown],
    "confidence": <float 0-1, how sure you are>,
    "parameters": {{
        "attendees": [<email or name>, ...] or null,
        "timezone": <timezone str or null>,
        "datetime": <ISO datetime or null>,
        "meeting_id": <string or null>,
        "meeting_title": <string or null>,
        "topic": <string or null>,
        "action_type": <schedule|notify|check or null>,
        "urgency": <high|normal|low>
    }},
    "explanation": <why you detected this intent>
}}"""

        try:
            llm = get_llm(temperature=0.0)
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            # Clean up markdown formatting
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            parsed = json.loads(content)
            return (
                parsed.get("intent", "unknown"),
                parsed.get("confidence", 0.5),
                parsed.get("parameters", {}),
                parsed.get("explanation", ""),
            )

        except Exception as e:
            logger.warning(f"LLM parsing failed: {e}")
            raise

    def _parse_with_rules(self, query: str) -> tuple:
        """
        Rule-based fallback for intent detection.
        
        Returns:
            (intent_type, confidence, parameters_dict, explanation)
        """
        query_lower = query.lower()
        
        # Intent detection rules
        if any(w in query_lower for w in ["schedule", "book", "meeting", "call"]):
            return (
                "schedule_meeting",
                0.7,
                {"action_type": "schedule"},
                "Detected scheduling request",
            )
        
        if any(w in query_lower for w in ["summarize", "summary", "recap", "debrief"]):
            return (
                "summarize_meeting",
                0.75,
                {"action_type": "summarize"},
                "Detected meeting summarization request",
            )
        
        if any(w in query_lower for w in ["brief", "briefing", "prepare", "readiness"]):
            return (
                "generate_briefing",
                0.7,
                {"action_type": "brief"},
                "Detected briefing generation request",
            )
        
        if any(w in query_lower for w in ["agenda", "prepare meeting", "meeting plan"]):
            return (
                "generate_agenda",
                0.75,
                {"action_type": "agenda"},
                "Detected agenda generation request",
            )
        
        if any(w in query_lower for w in ["notify", "inform", "message", "slack", "email"]):
            return (
                "send_notification",
                0.7,
                {"action_type": "notify"},
                "Detected notification request",
            )
        
        if any(w in query_lower for w in ["conflict", "overlap", "double-booked", "availability"]):
            return (
                "resolve_conflict",
                0.65,
                {"action_type": "check_availability"},
                "Detected scheduling conflict",
            )
        
        if any(w in query_lower for w in ["action", "tasks", "follow-up", "track"]):
            return (
                "track_actions",
                0.7,
                {"action_type": "track"},
                "Detected action item tracking request",
            )
        
        return (
            "unknown",
            0.3,
            {},
            "Could not determine specific intent",
        )

    def build_context_from_intent(
        self,
        parsed_intent: ParsedQueryIntent,
    ) -> Dict[str, Any]:
        """
        Build execution context from parsed intent.
        
        Args:
            parsed_intent: The parsed query intent
            
        Returns:
            Context dict for tool execution
        """
        return {
            "intent": parsed_intent.intent.value,
            "confidence": parsed_intent.confidence,
            "parameters": parsed_intent.parameters,
            "requires_clarification": parsed_intent.requires_clarification,
            "timestamp": __import__("time").time(),
        }

    def handle_requires_clarification(
        self,
        parsed_intent: ParsedQueryIntent,
    ) -> str:
        """Generate clarification request for ambiguous query."""
        intent = parsed_intent.intent.value
        params = parsed_intent.parameters

        clarifications = []

        if intent == "schedule_meeting":
            if not params.get("attendees"):
                clarifications.append("Who should attend the meeting?")
            if not params.get("datetime"):
                clarifications.append("When would you like to schedule the meeting?")
            if not params.get("timezone"):
                clarifications.append("What timezone should we use?")

        elif intent == "send_notification":
            if not params.get("attendees"):
                clarifications.append("Who should receive the notification?")
            if not params.get("topic"):
                clarifications.append("What is the notification about?")

        elif intent == "summarize_meeting":
            if not params.get("meeting_id"):
                clarifications.append("Which meeting would you like to summarize?")

        if clarifications:
            return "I need some clarification:\n" + "\n".join(
                f"- {c}" for c in clarifications
            )

        return "Please provide more details about your request."

    def extract_parameters_from_query(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """
        Extract structured parameters from natural language query.
        
        Args:
            query: Natural language query
            
        Returns:
            Dict of extracted parameters
        """
        import re
        from datetime import datetime

        params = {}

        # Extract email addresses
        emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", query)
        if emails:
            params["attendees"] = emails

        # Extract time patterns (HH:MM, tomorrow, next Friday, etc)
        if "tomorrow" in query.lower():
            tomorrow = datetime.now().replace(hour=10, minute=0) + __import__("datetime").timedelta(days=1)
            params["datetime"] = tomorrow.isoformat()
        elif match := re.search(r"(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", query):
            hour = int(match.group(1))
            if match.group(3) and match.group(3).lower().startswith('p'):
                hour += 12
            params["time"] = f"{hour:02d}:{match.group(2)}"

        # Extract timezone
        timezones = ["UTC", "EST", "CST", "MST", "PST", "IST", "GMT"]
        for tz in timezones:
            if tz in query.upper():
                params["timezone"] = tz
                break

        # Extract meeting titles/topics
        topic_match = re.search(r"about\s+(.+?)(?:\s+with|\s+at|\s+on|$)", query)
        if topic_match:
            params["topic"] = topic_match.group(1)

        return params


# Global handler instance
_handler: Optional[CommunicationQueryHandler] = None


def get_query_handler() -> CommunicationQueryHandler:
    """Get or create the global query handler."""
    global _handler
    if _handler is None:
        _handler = CommunicationQueryHandler()
    return _handler
