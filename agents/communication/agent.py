"""
Meetings & Communication Agent.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel
from langchain_core.runnables import RunnableConfig

from agents.base_agent import BaseAgent
from config.settings import Settings
from human_loop.manager import HITLManager

from .schemas import MeetingRequestInput, MeetingAgentOutput
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
    MeetingSearchTool,
)
from .tools.stakeholder_echo import StakeholderEchoTool
from tools.data_tools.sql_executor import DynamicSQLExecutorTool



class CommunicationAgent(BaseAgent):
    """
    Agent responsible for scheduling, meeting analysis, and briefings.
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
        """Register tools with the shared registry."""
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
            MeetingSearchTool(),
            StakeholderEchoTool(),
            DynamicSQLExecutorTool(),
        ]:

            self.tool_registry.register_tool(tool, self.name)

    @property
    def input_schema(self) -> Type[BaseModel]:
        return MeetingRequestInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return MeetingAgentOutput

    def get_subgraph(self):
        return build_meeting_graph(
            llm_with_tools=self.llm_with_tools,
            tools=self.tools,
            hitl_manager=self.hitl,
        )

    def execute(self, input_data: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """
        Execute the communication workflow with full Pydantic validation.
        """
        validated_in = MeetingRequestInput(**input_data)
        
        # Build initial LangGraph state
        state_input: Dict[str, Any] = {
            "action": validated_in.action,
            "title": validated_in.title,
            "participants": [p.dict() for p in validated_in.participants],
            "duration_minutes": validated_in.duration_minutes,
            "preferred_time_range": validated_in.preferred_time_range,
            "timezone": validated_in.timezone,
            "context": validated_in.context,
            "meeting_id": validated_in.meeting_id,
            "transcript": validated_input.transcript if hasattr(validated_in, 'transcript') else input_data.get('transcript'),
            "organizer_email": validated_in.organizer_email,
            "location": validated_in.location,
            "session_id": input_data.get("session_id"),
            "messages": input_data.get("messages", []),
            # Pass cross-agent context
            "context_history": validated_in.context_history,
            "step_reasoning": validated_in.step_reasoning,
        }
        
        # Handle transcript edge case if not in pydantic (check MeetingRequestInput)
        if "transcript" in input_data:
            state_input["transcript"] = input_data["transcript"]

        graph = self.get_subgraph()
        config = config or {}
        if "recursion_limit" not in config:
            config["recursion_limit"] = 50
            
        result = graph.invoke(state_input, config=config)

        # Map internal state → Standardized MeetingAgentOutput
        output_data: Dict[str, Any] = {
            "action_performed": validated_in.action,
            "llm_summary": result.get("meeting_summary") or result.get("briefing_doc") or result.get("error"),
            "thought": result.get("thought"),
            "data": {
                "meeting_id": result.get("meeting_id"),
                "agenda": result.get("agenda_items", []),
                "action_items": [i.dict() if hasattr(i, 'dict') else i for i in result.get("action_items", [])],
                "proposed_slots": result.get("proposed_slots", []),
                "calendar_link": result.get("calendar_link"),
            },
            "suggestions": [
                f"Schedule follow-up for {validated_in.title}",
                "Send summary to participants"
            ],
            "requires_human_review": result.get("requires_approval", False),
            "error": result.get("error"),
        }

        return self.validate_output(output_data)
