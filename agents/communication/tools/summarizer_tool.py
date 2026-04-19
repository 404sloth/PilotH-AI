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

    def execute(self, inp: SummarizerInput, config: Optional[RunnableConfig] = None) -> SummarizerOutput:
        from orchestrator.system_prompts import get_prompt, AgentType, get_system_prompt
        from observability.pii_sanitizer import PIISanitizer
        
        # Sanitize input before LLM call
        sanitized_transcript = PIISanitizer.sanitize_string(inp.transcript)
        sanitized_attendees = [PIISanitizer.sanitize_string(a) for a in inp.attendees]
        
        prompt = get_prompt(
            "meeting_summary",
            transcript=sanitized_transcript,
            meeting_title=inp.meeting_title or "N/A",
        )

        try:
            from llm.model_factory import get_llm
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(temperature=0.0, max_tokens=2000)
            
            # Add system context
            system_msg = SystemMessage(content=get_system_prompt(AgentType.COMMUNICATION))
            
            # Pass config to ensure tracing is maintained
            resp = llm.invoke([system_msg, HumanMessage(content=prompt)], config=config).content.strip()
            resp = resp.strip("```json").strip("```").strip()
            data = json.loads(resp)
            return SummarizerOutput(
                executive_summary=data.get("executive_summary", ""),
                key_decisions=data.get("decisions", data.get("key_decisions", [])),
                action_items=[ActionItemRaw(**a) for a in data.get("action_items", [])],
                risks=data.get("risks", []),
                follow_up_needed=data.get("requires_followup", data.get("follow_up_needed", True)),
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
