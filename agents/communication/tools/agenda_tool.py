"""Agenda generator tool — LLM-driven agenda creation."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
import json


class AgendaInput(BaseModel):
    meeting_title: str = Field(..., description="Meeting title")
    goals: str = Field(..., description="What the meeting aims to achieve")
    duration_minutes: int = Field(60, ge=15, le=480)
    attendee_roles: List[str] = Field(
        default_factory=list, description="Roles of attendees"
    )
    past_context: Optional[str] = Field(
        None, description="Notes from previous related meetings"
    )


class AgendaItem(BaseModel):
    order: int
    topic: str
    duration_mins: int
    description: Optional[str] = None
    presenter_role: Optional[str] = None


class AgendaOutput(BaseModel):
    meeting_title: str
    total_minutes: int
    items: List[AgendaItem]
    summary: str


from langchain_core.runnables import RunnableConfig


class AgendaGeneratorTool(StructuredTool):
    """Generate a structured meeting agenda using LLM based on meeting goals and context."""

    name: str = "agenda_generator"
    description: str = (
        "Generate a time-boxed meeting agenda from meeting goals and attendee context."
    )
    args_schema: type[BaseModel] = AgendaInput

    def execute(
        self, inp: AgendaInput, config: Optional[RunnableConfig] = None
    ) -> AgendaOutput:
        prompt = f"""You are a meeting facilitation expert. Create a structured agenda. Return ONLY valid JSON.

Meeting: {inp.meeting_title}
Duration: {inp.duration_minutes} minutes
Goals: {inp.goals}
Attendee roles: {", ".join(inp.attendee_roles) or "Mixed team"}
Past context: {inp.past_context or "None"}

Return JSON:
{{
  "items": [
    {{"order": 1, "topic": "...", "duration_mins": 10, "description": "...", "presenter_role": "..."}}
  ]
}}
Ensure total duration_mins equals {inp.duration_minutes}. Last item should be 'Next Steps & Action Items'."""

        try:
            from llm.model_factory import get_llm
            from langchain_core.messages import HumanMessage

            llm = get_llm(temperature=0.3)
            resp = llm.invoke([HumanMessage(content=prompt)]).content.strip()
            resp = resp.strip("```json").strip("```").strip()
            data = json.loads(resp)
            items = [AgendaItem(**i) for i in data.get("items", [])]
        except Exception:
            items = self._default_agenda(inp)

        total = sum(i.duration_mins for i in items)
        return AgendaOutput(
            meeting_title=inp.meeting_title,
            total_minutes=total,
            items=items,
            summary=f"{len(items)}-item agenda for '{inp.meeting_title}' ({total} min total)",
        )

    def _default_agenda(self, inp: AgendaInput) -> List[AgendaItem]:
        total = inp.duration_minutes
        fixed = 10  # last item always 10 min
        body = total - fixed
        q, r = divmod(body, 3)
        return [
            AgendaItem(
                order=1,
                topic="Welcome & Objectives",
                duration_mins=q + r,
                description="Set context",
            ),
            AgendaItem(
                order=2,
                topic="Status Update",
                duration_mins=q,
                description="Current progress",
            ),
            AgendaItem(
                order=3,
                topic="Main Discussion: " + inp.goals[:50],
                duration_mins=q,
                description="Core agenda",
            ),
            AgendaItem(
                order=4,
                topic="Next Steps & Action Items",
                duration_mins=fixed,
                description="Assign owners",
            ),
        ]
