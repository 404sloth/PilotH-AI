"""
LangGraph workflow for the Meetings & Communication Agent.

Graph topology:
  START → route →
    [schedule]: resolve_participants → fetch_availability → find_common_slots
                → propose_slots → create_event → hitl_check → finalize → END
    [summarize]: retrieve_transcript → extract_key_points → generate_summary
                 → draft_followup → finalize → END
    [brief]:     gather_context → analyze_sentiment → generate_agenda
                 → compile_briefing → finalize → END
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .schemas import MeetingState
from .nodes import (
    # Scheduling
    resolve_participants_node,
    fetch_availability_node,
    find_common_slots_node,
    propose_slots_node,
    create_event_node,
    # Summarization
    retrieve_transcript_node,
    extract_key_points_node,
    generate_summary_node,
    draft_followup_node,
    # Briefing
    gather_context_node,
    analyze_sentiment_node,
    generate_agenda_node,
    compile_briefing_node,
    # Common
    finalize_node,
    hitl_check_node,
)


def _route_action(state: MeetingState) -> str:
    """Dispatch to the correct sub-graph based on action."""
    action = state.get("action", "schedule")
    if action == "summarize":
        return "retrieve_transcript"
    if action == "brief":
        return "gather_context"
    return "resolve_participants"  # default: schedule


def build_meeting_graph(
    checkpointer: Optional[MemorySaver] = None,
) -> StateGraph:
    """
    Build and compile the Meeting & Communication LangGraph workflow.

    Args:
        checkpointer: Optional LangGraph memory checkpointer for HITL resume.

    Returns:
        Compiled StateGraph.
    """
    builder = StateGraph(MeetingState)

    # ── Scheduling sub-graph ────────────────────────────────────────────────
    builder.add_node("resolve_participants", resolve_participants_node)
    builder.add_node("fetch_availability", fetch_availability_node)
    builder.add_node("find_common_slots", find_common_slots_node)
    builder.add_node("propose_slots", propose_slots_node)
    builder.add_node("create_event", create_event_node)
    builder.add_node("hitl_check", hitl_check_node)

    builder.add_edge("resolve_participants", "fetch_availability")
    builder.add_edge("fetch_availability", "find_common_slots")
    builder.add_edge("find_common_slots", "propose_slots")
    builder.add_edge("propose_slots", "create_event")
    builder.add_edge("create_event", "hitl_check")
    builder.add_edge("hitl_check", "finalize")

    # ── Summarization sub-graph ────────────────────────────────────────────
    builder.add_node("retrieve_transcript", retrieve_transcript_node)
    builder.add_node("extract_key_points", extract_key_points_node)
    builder.add_node("generate_summary", generate_summary_node)
    builder.add_node("draft_followup", draft_followup_node)

    builder.add_edge("retrieve_transcript", "extract_key_points")
    builder.add_edge("extract_key_points", "generate_summary")
    builder.add_edge("generate_summary", "draft_followup")
    builder.add_edge("draft_followup", "finalize")

    # ── Briefing sub-graph ─────────────────────────────────────────────────
    builder.add_node("gather_context", gather_context_node)
    builder.add_node("analyze_sentiment", analyze_sentiment_node)
    builder.add_node("generate_agenda", generate_agenda_node)
    builder.add_node("compile_briefing", compile_briefing_node)

    builder.add_edge("gather_context", "analyze_sentiment")
    builder.add_edge("analyze_sentiment", "generate_agenda")
    builder.add_edge("generate_agenda", "compile_briefing")
    builder.add_edge("compile_briefing", "finalize")

    # ── Shared finalize ────────────────────────────────────────────────────
    builder.add_node("finalize", finalize_node)
    builder.add_edge("finalize", END)

    # ── Entry → conditional routing ────────────────────────────────────────
    builder.add_conditional_edges(
        START,
        _route_action,
        {
            "resolve_participants": "resolve_participants",
            "retrieve_transcript": "retrieve_transcript",
            "gather_context": "gather_context",
        },
    )

    if checkpointer:
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_after=["create_event"],  # HITL pause point
        )
    return builder.compile()
