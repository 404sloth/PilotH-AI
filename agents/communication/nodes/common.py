"""
Common / finalize node shared across all sub-graphs.
Handles HITL interrupt and global memory persistence.
"""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import AIMessage
from agents.communication.schemas import MeetingState


def finalize_node(state: MeetingState) -> Dict[str, Any]:
    """
    Finalize the meeting workflow:
    - Save summary/decisions to global memory
    - Send Slack notification to organiser
    - Return final status message
    """
    from memory.global_context import get_global_context
    from agents.communication.tools.slack_tool import SlackNotifierTool, SlackInput

    ctx = get_global_context()
    action = state.get("action", "unknown")

    # --- Persist final state ---
    meeting_id = state.get("meeting_id")
    if meeting_id:
        ctx.set(
            f"meeting:{meeting_id}:final_state",
            {
                "action": action,
                "proposed_slots": state.get("proposed_slots", []),
                "calendar_link": state.get("calendar_link"),
                "summary": state.get("meeting_summary"),
                "agenda": state.get("agenda_items", []),
                "action_item_count": len(state.get("action_items") or []),
            },
            agent="meetings_communication",
            session_id=state.get("session_id"),
        )

    # --- Slack notification (mock) ---
    organizer_email = state.get("organizer_email", "")
    if organizer_email:
        from integrations.data_warehouse.meeting_db import get_person_by_email

        person = get_person_by_email(organizer_email)
        slack_handle = person.get("slack_handle") if person else None
        if slack_handle:
            channel = slack_handle
            msg = _build_slack_msg(state, action)
            SlackNotifierTool().execute(SlackInput(channel=channel, message=msg))

    # --- Build output message ---
    action_summary = {
        "schedule": f"Meeting scheduled. Link: {state.get('calendar_link', 'N/A')}",
        "summarize": f"Summary complete. {len(state.get('action_items') or [])} action item(s) created.",
        "brief": f"Briefing compiled for {len(state.get('participant_bios') or [])} attendees.",
    }.get(action, "Workflow complete.")

    return {
        "messages": [AIMessage(content=action_summary)],
    }


def hitl_check_node(state: MeetingState) -> Dict[str, Any]:
    """
    Fire a NodeInterrupt if state.requires_approval is True.
    Pauses the graph for human review of external-attendee calendar events.
    """
    if not state.get("requires_approval", False):
        return {}

    try:
        from langgraph.errors import NodeInterrupt

        raise NodeInterrupt(
            "Human approval required: external attendees detected in calendar event. "
            f"Meeting: {state.get('title')}. "
            f"Calendar link: {state.get('calendar_link')}. "
            "Approve to proceed with sending invites."
        )
    except ImportError:
        # Graceful degradation if NodeInterrupt not available
        return {"requires_approval": True}


def _build_slack_msg(state: MeetingState, action: str) -> str:
    title = state.get("title", "Meeting")
    if action == "schedule":
        slots = state.get("proposed_slots", [])
        return (
            f":calendar: *{title}* has been scheduled.\n"
            + (f"Proposed slot: {slots[0]}" if slots else "")
            + (
                f"\n:link: <{state.get('calendar_link')}|Open in Calendar>"
                if state.get("calendar_link")
                else ""
            )
        )
    elif action == "summarize":
        n = len(state.get("action_items") or [])
        return f":memo: *{title}* summary ready. {n} action item(s) assigned."
    elif action == "brief":
        n = len(state.get("participant_bios") or [])
        return (
            f":briefcase: Pre-meeting briefing for *{title}* ({n} attendees) is ready."
        )
    return f":robot_face: Meeting workflow complete: *{title}*"
