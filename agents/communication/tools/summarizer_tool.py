"""Meeting summarizer tool — LLM-driven structured output."""

from __future__ import annotations
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class SummarizerInput(BaseModel):
    transcript: str = Field(..., description="Raw meeting transcript or notes")
    meeting_title: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    duration_mins: Optional[int] = None


class ActionItemRaw(BaseModel):
    description: str
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"


class SummarizerOutput(BaseModel):
    executive_summary: str
    key_decisions: List[str]
    action_items: List[ActionItemRaw]
    risks: List[str]
    follow_up_needed: bool
    sentiment: str  # positive | neutral | concerns_raised


class MeetingSummarizerTool(StructuredTool):
    """
    Extract structured summary, decisions, action items, and risks from a meeting transcript.
    Uses LLM with structured output; falls back to rule-based extraction.
    """

    name: str = "meeting_summarizer"
    description: str = (
        "Summarise a meeting transcript into key decisions, action items, and risks."
    )
    args_schema: type[BaseModel] = SummarizerInput

    def execute(self, inp: SummarizerInput) -> SummarizerOutput:
        prompt = f"""You are an expert meeting analyst. Analyse the following transcript and return ONLY valid JSON.

Meeting: {inp.meeting_title or "N/A"}
Attendees: {", ".join(inp.attendees) or "Unknown"}
Duration: {inp.duration_mins or "N/A"} minutes

Transcript:
{inp.transcript[:4000]}

Return JSON:
{{
  "executive_summary": "<3-4 sentences>",
  "key_decisions": ["<decision 1>", ...],
  "action_items": [{{"description": "...", "assignee": "...", "due_date": "YYYY-MM-DD", "priority": "medium"}}],
  "risks": ["<risk 1>", ...],
  "follow_up_needed": true/false,
  "sentiment": "positive|neutral|concerns_raised"
}}"""

        try:
            from llm.model_factory import get_llm
            from langchain_core.messages import HumanMessage

            llm = get_llm(temperature=0.0)
            resp = llm.invoke([HumanMessage(content=prompt)]).content.strip()
            resp = resp.strip("```json").strip("```").strip()
            data = json.loads(resp)
            return SummarizerOutput(
                executive_summary=data.get("executive_summary", ""),
                key_decisions=data.get("key_decisions", []),
                action_items=[ActionItemRaw(**a) for a in data.get("action_items", [])],
                risks=data.get("risks", []),
                follow_up_needed=data.get("follow_up_needed", True),
                sentiment=data.get("sentiment", "neutral"),
            )
        except Exception:
            return self._rule_based(inp)

    def _rule_based(self, inp: SummarizerInput) -> SummarizerOutput:
        lines = inp.transcript.split("\n")
        decisions = [
            l.strip()
            for l in lines
            if any(
                kw in l.lower() for kw in ["decided", "agreed", "approved", "confirmed"]
            )
        ]
        actions = [
            l.strip()
            for l in lines
            if any(
                kw in l.lower()
                for kw in ["action:", "todo:", "will", "should", "must", "owner:"]
            )
        ]
        risks = [
            l.strip()
            for l in lines
            if any(kw in l.lower() for kw in ["risk", "concern", "issue", "blocker"])
        ]
        return SummarizerOutput(
            executive_summary=f"Meeting '{inp.meeting_title}' concluded. {len(decisions)} decision(s) made.",
            key_decisions=decisions[:5],
            action_items=[ActionItemRaw(description=a) for a in actions[:5]],
            risks=risks[:3],
            follow_up_needed=bool(actions),
            sentiment="neutral",
        )
