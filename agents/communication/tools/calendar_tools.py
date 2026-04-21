"""
Calendar Tools — Google Calendar create & availability (mock + real stub).
Mock uses SQLite calendar_events table; swap for googleapiclient in production.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


# ─── Create Event ─────────────────────────────────────────────────────────────


class CalendarCreateInput(BaseModel):
    title: str = Field(..., description="Event title")
    attendee_emails: List[str] = Field(..., description="List of attendee emails")
    start_time: str = Field(..., description="ISO 8601 start datetime")
    end_time: str = Field(..., description="ISO 8601 end datetime")
    timezone: str = Field("UTC")
    description: Optional[str] = None
    location: Optional[str] = None
    organizer_email: Optional[str] = None


class CalendarCreateOutput(BaseModel):
    created: bool
    event_id: Optional[str] = None
    calendar_link: Optional[str] = None
    has_external: bool = False  # True if non-company emails present
    message: str = ""


class GoogleCalendarCreateTool(StructuredTool):
    """
    Create a Google Calendar event.
    Mock: logs the event and returns success.
    """

    name: str = "google_calendar_create"
    description: str = (
        "Schedule a new meeting in Google Calendar. "
        "Requires title, start/end times (ISO), and attendee emails."
    )
    args_schema: type[BaseModel] = CalendarCreateInput

    def execute(
        self, inp: CalendarCreateInput, config: Optional[RunnableConfig] = None
    ) -> CalendarCreateOutput:
        from integrations.data_warehouse.meeting_db import (
            get_person_by_email,
            create_calendar_event,
        )

        COMPANY_DOMAIN = "company.com"
        external = [
            e for e in inp.attendee_emails if not e.endswith(f"@{COMPANY_DOMAIN}")
        ]
        event_id = f"GCAL-{uuid.uuid4().hex[:8].upper()}"

        # Store for each resolved person
        for email in inp.attendee_emails:
            person = get_person_by_email(email)
            if person:
                create_calendar_event(
                    person_id=person["id"],
                    title=inp.title,
                    start_time=inp.start_time,
                    end_time=inp.end_time,
                    timezone=inp.timezone,
                    external_id=event_id,
                    description=inp.description,
                    location=inp.location,
                )

        return CalendarCreateOutput(
            created=True,
            event_id=event_id,
            calendar_link=f"https://calendar.google.com/event?eid={event_id}",
            has_external=bool(external),
            message=f"Event '{inp.title}' created for {len(inp.attendee_emails)} attendees."
            + (f" External attendees detected: {external}" if external else ""),
        )


# ─── Availability ─────────────────────────────────────────────────────────────


class AvailabilityInput(BaseModel):
    attendee_emails: List[str] = Field(
        ..., description="Emails to check availability for"
    )
    from_time: str = Field(..., description="Start of window (ISO 8601)")
    to_time: str = Field(..., description="End of window (ISO 8601)")


class BusyBlock(BaseModel):
    email: str
    start_time: str
    end_time: str
    title: Optional[str] = None


class AvailabilityOutput(BaseModel):
    checked: List[str]
    not_found: List[str]
    busy_blocks: List[BusyBlock]
    summary: str


class GoogleCalendarAvailabilityTool(StructuredTool):
    """
    Check availability for multiple users in Google Calendar.
    Mock: returns randomized availability based on the day.
    """

    name: str = "google_calendar_availability"
    description: str = (
        "Check when a set of users is free to meet. Returns a list of 'busy' blocks."
    )
    args_schema: type[BaseModel] = AvailabilityInput

    def execute(
        self, inp: AvailabilityInput, config: Optional[RunnableConfig] = None
    ) -> AvailabilityOutput:
        from integrations.data_warehouse.meeting_db import (
            get_person_by_email,
            get_busy_blocks,
        )

        busy_blocks: List[BusyBlock] = []
        checked, not_found = [], []

        for email in inp.attendee_emails:
            person = get_person_by_email(email)
            if not person:
                not_found.append(email)
                continue
            checked.append(email)
            blocks = get_busy_blocks(person["id"], inp.from_time, inp.to_time)
            for b in blocks:
                busy_blocks.append(
                    BusyBlock(
                        email=email,
                        start_time=b["start_time"],
                        end_time=b["end_time"],
                        title=b.get("title"),
                    )
                )

        return AvailabilityOutput(
            checked=checked,
            not_found=not_found,
            busy_blocks=busy_blocks,
            summary=f"Checked {len(checked)} attendees, found {len(busy_blocks)} busy block(s).",
        )
