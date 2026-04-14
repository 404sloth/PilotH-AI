"""
Briefing nodes for the Meeting Agent graph.
Gather context → sentiment → generate agenda → compile one-pager briefing.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import ToolMessage, AIMessage
from agents.communication.schemas import MeetingState


def gather_context_node(state: MeetingState) -> Dict[str, Any]:
    """Fetch participant bios and check global memory for past meeting notes."""
    from agents.communication.tools.briefing_tool import (
        ParticipantBriefingTool,
        BriefingInput,
    )
    from memory.global_context import get_global_context

    participants = state.get("participants") or []
    emails = [p.get("email", "") if isinstance(p, dict) else p for p in participants]
    emails = [e for e in emails if e]

    bios: List[Dict] = []
    if emails:
        tool = ParticipantBriefingTool()
        result = tool.execute(
            BriefingInput(emails=emails, meeting_context=state.get("context"))
        )
        bios = [p.model_dump() for p in result.participants]

    # Fetch past context from global memory
    ctx = get_global_context()
    meeting_id = state.get("meeting_id")
    past = ctx.get(f"meeting:{meeting_id}:summary") if meeting_id else None

    return {
        "participant_bios": bios,
        "messages": [
            ToolMessage(
                content=f"Fetched {len(bios)} participant bio(s). Past notes: {'found' if past else 'none'}.",
                tool_call_id="gather_context",
            )
        ],
    }


def analyze_sentiment_node(state: MeetingState) -> Dict[str, Any]:
    """Run sentiment analysis on meeting context and participant bios."""
    from agents.communication.tools.sentiment_tool import (
        SentimentAnalysisTool,
        SentimentInput,
    )

    texts = []
    if state.get("context"):
        texts.append(state["context"])
    for p in state.get("participant_bios") or []:
        if p.get("bio"):
            texts.append(p["bio"])

    if not texts:
        return {
            "sentiment_results": [],
            "messages": [AIMessage(content="No text to analyse.")],
        }

    tool = SentimentAnalysisTool()
    result = tool.execute(SentimentInput(texts=texts[:10]))

    return {
        "sentiment_results": [r.model_dump() for r in result.records],
        "messages": [
            ToolMessage(
                content=result.summary,
                tool_call_id="analyze_sentiment",
            )
        ],
    }


def generate_agenda_node(state: MeetingState) -> Dict[str, Any]:
    """Generate agenda from meeting goals and attendee context."""
    from agents.communication.tools.agenda_tool import AgendaGeneratorTool, AgendaInput

    roles = [p.get("role", "") for p in (state.get("participant_bios") or [])]

    tool = AgendaGeneratorTool()
    result = tool.execute(
        AgendaInput(
            meeting_title=state.get("title", "Meeting"),
            goals=state.get("context") or "General team discussion",
            duration_minutes=state.get("duration_minutes", 60),
            attendee_roles=roles,
        )
    )

    items = [f"{i.order}. {i.topic} ({i.duration_mins} min)" for i in result.items]

    return {
        "agenda_items": items,
        "messages": [AIMessage(content=result.summary)],
    }


def compile_briefing_node(state: MeetingState) -> Dict[str, Any]:
    """Compile a comprehensive one-pager briefing document."""
    bios = state.get("participant_bios") or []
    agenda = state.get("agenda_items") or []
    sentiment = state.get("sentiment_results") or []
    title = state.get("title", "Meeting")

    avg_sentiment = (
        sum(r.get("score", 0) for r in sentiment) / len(sentiment) if sentiment else 0.0
    )
    sent_label = (
        "Positive"
        if avg_sentiment > 0.1
        else ("Negative" if avg_sentiment < -0.1 else "Neutral")
    )

    bio_sections = []
    for p in bios:
        bio_sections.append(
            f"**{p['full_name']}** ({p['role']}, {p['department']}, {p['location']})\n"
            f"  Skills: {', '.join(p.get('skills', [])[:4])}\n"
            f"  Timezone: {p['timezone']}"
        )

    bio_lines = bio_sections or ["No attendee data available"]
    agenda_lines = [f"- {item}" for item in agenda] or ["- Agenda not yet generated"]

    doc_sections = (
        [
            f"# Pre-Meeting Briefing: {title}",
            f"Sentiment Context: {sent_label} (score: {avg_sentiment:.2f})",
            "",
        ]
        + ["## Attendees"]
        + bio_lines
        + ["", "## Proposed Agenda"]
        + agenda_lines
        + ["", "## Context", state.get("context") or "No context provided."]
    )

    briefing = "\n".join(doc_sections)

    return {
        "briefing_doc": briefing,
        "messages": [
            AIMessage(
                content=f"Briefing compiled for '{title}' ({len(bios)} attendees)."
            )
        ],
    }
