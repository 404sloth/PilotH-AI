"""
Communication Agent Query Handler.

Intelligently routes and handles diverse communication-related queries:
  - Schedule meeting across timezones
  - Send briefing documents
  - Summarize existing meetings
  - Generate agendas
  - Search/List meetings
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .schemas import CommunicationAction
from .tools import (
    GoogleCalendarCreateTool,
    GoogleCalendarAvailabilityTool,
    TimezoneConverterTool,
    EmailDraftTool,
    ParticipantBriefingTool,
    SentimentAnalysisTool,
    MeetingSummarizerTool,
    AgendaGeneratorTool,
    SlackNotifierTool,
    ActionItemTrackerTool,
    ConflictResolverTool,
    MeetingSearchTool,
)

logger = logging.getLogger(__name__)


class CommunicationQueryHandler:
    """
    Dispatcher logic for the Communication Agent subgraph.
    Maps high-level intent → specific tool executions.
    """

    def handle_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for tool dispatch.
        """
        try:
            if action == "schedule":
                return self._handle_schedule(params)
            elif action == "summarize":
                return self._handle_summarize(params)
            elif action == "brief":
                return self._handle_brief(params)
            elif action == "search_meetings":
                return self._handle_search(params)
            else:
                return {"error": f"Unsupported communication action: {action}"}
        except Exception as e:
            logger.error("Error in CommunicationQueryHandler: %s", e)
            return {"error": str(e)}

    def _handle_schedule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = GoogleCalendarCreateTool()
        # Input validation and formatting logic here
        result = tool.execute(tool.args_schema(**params))
        return result.model_dump()

    def _handle_summarize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = MeetingSummarizerTool()
        result = tool.execute(tool.args_schema(**params))
        return result.model_dump()

    def _handle_brief(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = ParticipantBriefingTool()
        result = tool.execute(tool.args_schema(**params))
        return result.model_dump()

    def _handle_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool = MeetingSearchTool()
        # Extract params carefully
        search_params = {
            "title": params.get("title") or params.get("query"),
            "attendee_email": params.get("attendee_email"),
            "date_from": params.get("date_from"),
            "date_to": params.get("date_to"),
            "limit": params.get("limit") or 20,
        }
        result = tool.execute(tool.args_schema(**search_params))
        return result.model_dump()


_handler: Optional[CommunicationQueryHandler] = None


def get_query_handler() -> CommunicationQueryHandler:
    """Get or create the global query handler."""
    global _handler
    if _handler is None:
        _handler = CommunicationQueryHandler()
    return _handler
