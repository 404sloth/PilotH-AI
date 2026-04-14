"""
Communication Agent Schemas — Pydantic v2.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field
from enum import Enum


class MeetingAction(str, Enum):
    SCHEDULE = "schedule"
    SUMMARIZE = "summarize"
    BRIEF = "brief"


class ParticipantRef(BaseModel):
    """Reference to a meeting participant — email is the unique key."""

    email: str
    name: Optional[str] = None
    role: str = "attendee"  # organizer|presenter|attendee|optional


class MeetingRequestInput(BaseModel):
    action: MeetingAction = Field(MeetingAction.SCHEDULE)
    title: str = Field(..., description="Meeting title")
    participants: List[ParticipantRef] = Field(default_factory=list)
    duration_minutes: int = Field(60, ge=15, le=480)
    preferred_time_range: Optional[str] = Field(
        None, description="e.g. '2024-09-10T09:00/2024-09-10T18:00'"
    )
    timezone: str = Field("UTC")
    context: Optional[str] = Field(None, description="Meeting purpose / agenda goals")
    meeting_id: Optional[str] = Field(
        None, description="Existing meeting ID for summarize/brief"
    )
    transcript: Optional[str] = Field(
        None, description="Meeting transcript for summarization"
    )
    organizer_email: Optional[str] = Field(None)
    location: Optional[str] = Field(None)

    class Config:
        use_enum_values = True


class ActionItem(BaseModel):
    description: str
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"


class MeetingAgentOutput(BaseModel):
    status: str = "success"
    action: str
    meeting_id: Optional[str] = None
    result: Dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None
    agenda: List[str] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    proposed_slots: List[str] = Field(default_factory=list)
    calendar_link: Optional[str] = None
    requires_approval: bool = False
    message: Optional[str] = None
    error: Optional[str] = None


# ── LangGraph internal state ──────────────────────────────────────────────────


class MeetingState(TypedDict, total=False):
    # Input
    action: str
    title: str
    participants: List[Dict[str, Any]]  # ParticipantRef dicts
    duration_minutes: int
    preferred_time_range: Optional[str]
    timezone: str
    context: Optional[str]
    meeting_id: Optional[str]
    transcript: Optional[str]
    organizer_email: Optional[str]
    location: Optional[str]
    session_id: Optional[str]

    # Resolved people (from persons table, disambiguated)
    resolved_participants: List[Dict[str, Any]]

    # Scheduling
    availability: Dict[str, Any]  # email → busy_blocks
    free_slots: List[str]  # ISO datetime strings
    proposed_slots: List[str]
    selected_slot: Optional[str]
    calendar_event_id: Optional[str]
    calendar_link: Optional[str]

    # Briefing/Agenda
    participant_bios: List[Dict[str, Any]]
    sentiment_results: List[Dict[str, Any]]
    agenda_items: List[str]
    briefing_doc: Optional[str]

    # Summarization
    key_points: List[str]
    decisions: List[str]
    risks: List[str]
    action_items: List[ActionItem]
    meeting_summary: Optional[str]
    followup_email: Optional[str]

    # Control
    requires_approval: bool
    error: Optional[str]
    messages: List[Any]
