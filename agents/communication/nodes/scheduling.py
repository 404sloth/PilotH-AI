"""
Scheduling nodes for the Meeting Agent graph.
Resolves participants → checks availability → finds slots → creates calendar event.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage, AIMessage
from agents.communication.schemas import MeetingState


def resolve_participants_node(state: MeetingState) -> Dict[str, Any]:
    """
    Resolve participant emails to full person records (disambiguates same names).
    """
    from agents.communication.tools.briefing_tool import ParticipantBriefingTool, BriefingInput

    participants = state.get("participants") or []
    emails = [p.get("email") or p if isinstance(p, str) else p.get("email", "") for p in participants]
    emails = [e for e in emails if e]

    if not emails:
        return {"error": "No participant emails provided", "requires_approval": False}

    tool   = ParticipantBriefingTool()
    result = tool.execute(BriefingInput(emails=emails))

    return {
        "resolved_participants": [p.model_dump() for p in result.participants],
        "messages": [ToolMessage(
            content=f"Resolved {result.found}/{len(emails)} participant(s). "
                    + (f"Not found: {result.not_found}" if result.not_found else ""),
            tool_call_id="resolve_participants",
        )],
    }


def fetch_availability_node(state: MeetingState) -> Dict[str, Any]:
    """Fetch busy calendar blocks for all resolved participants."""
    from agents.communication.tools.calendar_tools import GoogleCalendarAvailabilityTool, AvailabilityInput

    emails = [p["email"] for p in (state.get("resolved_participants") or []) if p.get("email")]
    if not emails:
        return {"availability": {}, "messages": [ToolMessage(content="No emails to check.", tool_call_id="fetch_avail")]}

    now     = datetime.utcnow()
    from_t  = now.isoformat()
    to_t    = (now + timedelta(days=7)).isoformat()

    tool   = GoogleCalendarAvailabilityTool()
    result = tool.execute(AvailabilityInput(attendee_emails=emails, from_time=from_t, to_time=to_t))

    availability = {}
    for block in result.busy_blocks:
        availability.setdefault(block.email, []).append({"start": block.start_time, "end": block.end_time})

    return {
        "availability": availability,
        "messages": [ToolMessage(content=result.summary, tool_call_id="fetch_availability")],
    }


def find_common_slots_node(state: MeetingState) -> Dict[str, Any]:
    """Pure Python: compute overlapping free windows among all attendees."""
    availability = state.get("availability") or {}
    duration     = state.get("duration_minutes", 60)

    now  = datetime.utcnow()
    candidates = []
    dt = now + timedelta(hours=2)
    for _ in range(40):
        if dt.weekday() < 5 and 8 <= dt.hour < 17:
            slot_end = dt + timedelta(minutes=duration)
            all_free = True
            for email, blocks in availability.items():
                for b in blocks:
                    try:
                        bs = datetime.fromisoformat(b["start"].replace("Z",""))
                        be = datetime.fromisoformat(b["end"].replace("Z",""))
                        if not (slot_end <= bs or dt >= be):
                            all_free = False
                            break
                    except Exception:
                        pass
                if not all_free:
                    break
            if all_free:
                candidates.append(dt.isoformat())
        dt += timedelta(hours=4)

    if not candidates:
        next_day = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        candidates = [next_day.isoformat(), (next_day + timedelta(hours=4)).isoformat()]

    return {
        "free_slots": candidates[:5],
        "messages": [AIMessage(content=f"Found {len(candidates)} free slot(s).")],
    }


def propose_slots_node(state: MeetingState) -> Dict[str, Any]:
    """Select the top 3 slots and format them for display."""
    free_slots = state.get("free_slots") or []
    duration   = state.get("duration_minutes", 60)
    timezone   = state.get("timezone", "UTC")
    proposed: List[str] = []

    for slot in free_slots[:3]:
        try:
            dt  = datetime.fromisoformat(slot)
            end = dt + timedelta(minutes=duration)
            proposed.append(f"{dt.strftime('%A %d %b %Y %H:%M')} – {end.strftime('%H:%M')} {timezone}")
        except Exception:
            proposed.append(slot)

    return {
        "proposed_slots": proposed,
        "selected_slot":  free_slots[0] if free_slots else None,
        "messages": [AIMessage(content=f"Proposed {len(proposed)} slot(s).")],
    }


def create_event_node(state: MeetingState) -> Dict[str, Any]:
    """
    Create the calendar event. Sets requires_approval=True if external attendees detected.
    After this node, HITL interrupt fires if requires_approval is True.
    """
    from agents.communication.tools.calendar_tools import GoogleCalendarCreateTool, CalendarCreateInput

    selected    = state.get("selected_slot")
    duration    = state.get("duration_minutes", 60)
    participants = state.get("resolved_participants") or []

    if not selected:
        return {"error": "No slot selected", "requires_approval": False}

    try:
        start_dt = datetime.fromisoformat(selected)
    except Exception:
        start_dt = datetime.utcnow() + timedelta(days=1)

    end_dt = start_dt + timedelta(minutes=duration)
    emails = [p["email"] for p in participants if p.get("email")]

    tool   = GoogleCalendarCreateTool()
    result = tool.execute(CalendarCreateInput(
        title=state.get("title", "Meeting"),
        attendee_emails=emails,
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        timezone=state.get("timezone", "UTC"),
        description=state.get("context"),
        location=state.get("location"),
    ))

    meeting_id = f"MTG-{uuid.uuid4().hex[:6].upper()}"
    from integrations.data_warehouse.meeting_db import create_meeting, add_attendees, get_person_by_email

    organizer = state.get("organizer_email", emails[0] if emails else None)
    org_person = get_person_by_email(organizer) if organizer else None
    org_id     = org_person["id"] if org_person else "P-001"

    create_meeting(
        meeting_id=meeting_id,
        title=state.get("title", "Meeting"),
        organizer_id=org_id,
        duration_mins=duration,
        timezone=state.get("timezone", "UTC"),
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        description=state.get("context"),
    )
    add_attendees(meeting_id, [
        {"person_id": p["id"], "role": p.get("role","attendee"), "rsvp": "pending"}
        for p in participants if p.get("id")
    ])

    return {
        "meeting_id":        meeting_id,
        "calendar_event_id": result.event_id,
        "calendar_link":     result.calendar_link,
        "requires_approval": result.has_external,
        "messages": [ToolMessage(content=result.message, tool_call_id="create_event")],
    }
