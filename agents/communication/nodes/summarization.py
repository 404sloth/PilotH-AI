"""
Summarization nodes for the Meeting Agent graph.
Retrieve transcript → extract key points → generate summary → draft follow-up.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import ToolMessage, AIMessage
from agents.communication.schemas import MeetingState, ActionItem
from langchain_core.runnables import RunnableConfig

def retrieve_transcript_node(state: MeetingState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Retrieve transcript from state or DB. Falls back to a prompt for input.
    In production: fetch from recording service (Zoom/Teams) or storage bucket.
    """
    transcript = state.get("transcript")
    meeting_id = state.get("meeting_id")

    if not transcript and meeting_id:
        from integrations.data_warehouse.meeting_db import get_meeting_full

        mtg = get_meeting_full(meeting_id)
        if mtg:
            sections = []
            if mtg.get("description"):
                sections.append(f"Meeting: {mtg['description']}")
            for agenda in mtg.get("agenda", []):
                sections.append(
                    f"Topic: {agenda['topic']} ({agenda['duration_mins']} min)"
                )
            if sections:
                transcript = "\n".join(sections)

    if not transcript:
        transcript = state.get("context", "No transcript available.")

    return {
        "transcript": transcript,
        "messages": [
            ToolMessage(
                content=f"Transcript retrieved ({len(transcript)} chars).",
                tool_call_id="retrieve_transcript",
            )
        ],
    }


def extract_key_points_node(state: MeetingState, config: RunnableConfig) -> Dict[str, Any]:
    """Use MeetingSummarizerTool (LLM) to extract structured content."""
    from agents.communication.tools.summarizer_tool import (
        MeetingSummarizerTool,
        SummarizerInput,
    )

    transcript = state.get("transcript", "")
    participants = state.get("resolved_participants") or []
    attendee_names = [p.get("full_name", p.get("email", "")) for p in participants]

    tool = MeetingSummarizerTool()
    result = tool.execute(
        SummarizerInput(
            transcript=transcript,
            meeting_title=state.get("title"),
            attendees=attendee_names,
            duration_mins=state.get("duration_minutes"),
        ),
        config=config
    )

    action_items: List[ActionItem] = [
        ActionItem(
            description=a.description,
            assignee=a.assignee,
            due_date=a.due_date,
            priority=a.priority,
        )
        for a in result.action_items
    ]

    return {
        "key_points": result.key_decisions,
        "decisions": result.key_decisions,
        "risks": result.risks,
        "action_items": action_items,
        "messages": [
            AIMessage(
                content=f"Extracted {len(result.key_decisions)} decision(s), {len(action_items)} action(s)."
            )
        ],
    }


def generate_summary_node(state: MeetingState, config: RunnableConfig) -> Dict[str, Any]:
    """Format executive summary and save to global memory."""
    from memory.global_context import get_global_context

    decisions = state.get("decisions", [])
    action_items = state.get("action_items", [])
    risks = state.get("risks", [])
    meeting_id = state.get("meeting_id", "unknown")

    decision_lines = [f"- {d}" for d in decisions] or ["- No decisions recorded"]
    action_lines = [
        f"- [{a.priority.upper()}] {a.description}"
        + (f" (Owner: {a.assignee})" if a.assignee else "")
        for a in action_items
    ] or ["- No action items"]
    risk_lines = [f"- {r}" for r in risks] or ["- No risks identified"]

    sections = (
        [f"# Meeting Summary: {state.get('title', 'Untitled')}", ""]
        + ["## Key Decisions"]
        + decision_lines
        + ["", "## Action Items"]
        + action_lines
        + ["", "## Risks"]
        + risk_lines
    )

    summary = "\n".join(sections)

    # Persist to global memory
    ctx = get_global_context()
    ctx.set(
        f"meeting:{meeting_id}:summary",
        {
            "summary": summary,
            "decisions": decisions,
            "action_items": [a.model_dump() for a in action_items],
        },
        agent="meetings_communication",
        ttl_seconds=86400 * 30,  # 30 days
    )
    ctx.log_decision(
        decision=f"Meeting '{state.get('title')}' summarised with {len(decisions)} decisions.",
        agent="meetings_communication",
        session_id=state.get("session_id"),
    )

    return {
        "meeting_summary": summary,
        "messages": [
            AIMessage(content=f"Summary generated and saved for meeting {meeting_id}.")
        ],
    }


def draft_followup_node(state: MeetingState, config: RunnableConfig) -> Dict[str, Any]:
    """Draft follow-up email using EmailDraftTool."""
    from agents.communication.tools.email_draft_tool import (
        EmailDraftTool,
        EmailDraftInput,
    )

    participants = state.get("resolved_participants") or []
    recipient_emails = [p.get("email", "") for p in participants if p.get("email")]
    action_items = state.get("action_items") or []

    context_lines = [state.get("meeting_summary", "")]
    context_lines += [
        f"Action: {a.description} (Owner: {a.assignee or 'TBD'})"
        for a in action_items[:5]
    ]

    tool = EmailDraftTool()
    result = tool.execute(
        EmailDraftInput(
            email_type="followup",
            recipients=recipient_emails or ["team@company.com"],
            subject=f"Follow-up: {state.get('title', 'Meeting')}",
            context="\n".join(context_lines),
        ),
        config=config
    )

    return {
        "followup_email": result.body,
        "messages": [
            AIMessage(content=f"Follow-up email drafted. Subject: {result.subject}")
        ],
    }
