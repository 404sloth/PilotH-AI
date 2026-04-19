"""
Meetings & Communication Agent.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type
from pydantic import BaseModel

from agents.base_agent import BaseAgent
from config.settings import Settings
from human_loop.manager import HITLManager

from .schemas import CommunicationInput, CommunicationOutput
from .graph import build_communication_graph
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
        ]:
            self.tool_registry.register_tool(tool, self.name)

    @property
    def input_schema(self) -> Type[BaseModel]:
        return CommunicationInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return CommunicationOutput

    def get_subgraph(self):
        return build_communication_graph(
            llm_with_tools=self.llm_with_tools,
            tools=self.tools,
            hitl_manager=self.hitl,
        )

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent workflow.
        """
        validated_input = CommunicationInput(**input_data)
        
        # Build initial state
        state = {
            "messages": [],
            "action": validated_input.action,
            "params": input_data,
        }

        graph = self.get_subgraph()
        result = graph.invoke(state)

        # Convert result to output schema
        output = {
            "action_performed": result.get("action"),
            "success": result.get("error") is None,
            "data": result.get("data", {}),
            "message": (result.get("messages") or [{}])[-1].content
            if result.get("messages")
            else None,
            "error": result.get("error"),
        }

        return self.validate_output(output)
