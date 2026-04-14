"""
Meetings & Communication Agent.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel

from agents.base_agent import BaseAgent
from config.settings import Settings
from human_loop.manager import HITLManager

from .schemas import MeetingRequestInput, MeetingAgentOutput, MeetingState
from .graph import build_meeting_graph
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
)


class MeetingCommunicationAgent(BaseAgent):
    """
    Meetings & Communication Agent.

    Actions:
    ────────
    • schedule   — smart multi-timezone scheduling with conflict resolution
    • summarize  — extract structured summary, decisions, action items from transcript
    • brief      — generate pre-meeting briefing with sentiment and agenda
    """

    name: str = "meetings_communication"

    def __init__(
        self,
        config: Settings,
        tool_registry=None,
        hitl_manager: Optional[HITLManager] = None,
    ):
        super().__init__(config, tool_registry, hitl_manager)
        self._register_tools()

    def _register_tools(self) -> None:
        if not self.tool_registry:
            return
        for tool in [
            GoogleCalendarCreateTool(),
            GoogleCalendarAvailabilityTool(),
            TimezoneConverterTool(),
            EmailDraftTool(),
            ParticipantBriefingTool(),
            SentimentAnalysisTool(),
            MeetingSummarizerTool(),
            AgendaGeneratorTool(),
            SlackNotifierTool(),
            ActionItemTrackerTool(),
            ConflictResolverTool(),
        ]:
            self.tool_registry.register_tool(tool, self.name)

    @property
    def input_schema(self) -> Type[BaseModel]:
        return MeetingRequestInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return MeetingAgentOutput

    def get_subgraph(self):
        return build_meeting_graph()

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        validated = MeetingRequestInput(**input_data)

        # Map to LangGraph state
        state_input: Dict[str, Any] = {
            "action": validated.action,
            "title": validated.title,
            "participants": [p.model_dump() for p in validated.participants],
            "duration_minutes": validated.duration_minutes,
            "preferred_time_range": validated.preferred_time_range,
            "timezone": validated.timezone,
            "context": validated.context,
            "meeting_id": validated.meeting_id,
            "transcript": validated.transcript,
            "organizer_email": validated.organizer_email,
            "location": validated.location,
            "session_id": input_data.get("session_id"),
            "messages": [],
            "requires_approval": False,
        }

        graph = self.get_subgraph()
        result: MeetingState = graph.invoke(state_input)

        # Map → output schema
        action_items_raw = result.get("action_items") or []
        from .schemas import ActionItem

        action_items = [
            (a if isinstance(a, ActionItem) else ActionItem(**a))
            for a in action_items_raw
        ]

        output: Dict[str, Any] = {
            "status": "success" if not result.get("error") else "error",
            "action": validated.action,
            "meeting_id": result.get("meeting_id"),
            "result": {
                "availability": result.get("availability", {}),
                "free_slots": result.get("free_slots", []),
                "briefing": result.get("briefing_doc"),
                "followup_email": result.get("followup_email"),
            },
            "summary": result.get("meeting_summary") or result.get("briefing_doc"),
            "agenda": result.get("agenda_items", []),
            "action_items": [a.model_dump() for a in action_items],
            "proposed_slots": result.get("proposed_slots", []),
            "calendar_link": result.get("calendar_link"),
            "requires_approval": result.get("requires_approval", False),
            "message": (result.get("messages") or [{}])[-1].content
            if result.get("messages")
            else None,
            "error": result.get("error"),
        }

        return self.validate_output(output)
