"""Conflict resolver tool — suggests alternative meeting slots."""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import List
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class ConflictResolverInput(BaseModel):
    attendee_emails: List[str] = Field(..., description="All attendee emails")
    preferred_start: str = Field(..., description="Preferred start (ISO 8601)")
    preferred_end: str = Field(..., description="Preferred end (ISO 8601)")
    duration_mins: int = Field(60, ge=15, le=480)
    timezone: str = Field("UTC")
    max_alternatives: int = Field(3, ge=1, le=10)


class TimeSlot(BaseModel):
    start: str
    end: str
    label: str


class ConflictResolverOutput(BaseModel):
    conflict_detected: bool
    conflicting_people: List[str]
    alternatives: List[TimeSlot]
    message: str


from langchain_core.runnables import RunnableConfig


class ConflictResolverTool(StructuredTool):
    """
    Check for scheduling conflicts among attendees and suggest alternative slots.
    Uses availability data from the DB.
    """

    name: str = "conflict_resolver"
    description: str = (
        "Detect scheduling conflicts for a proposed meeting time and suggest "
        "the best alternative slots based on all attendees' availability."
    )
    args_schema: type[BaseModel] = ConflictResolverInput

    def execute(
        self, inp: ConflictResolverInput, config: Optional[RunnableConfig] = None
    ) -> ConflictResolverOutput:
        from integrations.data_warehouse.meeting_db import (
            get_person_by_email,
            get_busy_blocks,
        )

        conflicting: List[str] = []
        for email in inp.attendee_emails:
            person = get_person_by_email(email)
            if not person:
                continue
            blocks = get_busy_blocks(
                person["id"], inp.preferred_start, inp.preferred_end
            )
            if blocks:
                conflicting.append(email)

        alternatives: List[TimeSlot] = []
        if conflicting:
            # Try slots in next N½-day increments
            try:
                start_dt = datetime.fromisoformat(
                    inp.preferred_start.replace("Z", "+00:00")
                )
            except ValueError:
                start_dt = datetime.utcnow() + timedelta(hours=24)

            candidate = start_dt + timedelta(days=1)
            for i in range(inp.max_alternatives * 3):
                # Skip weekends
                if candidate.weekday() >= 5:
                    candidate += timedelta(days=1)
                    continue
                slot_end = candidate + timedelta(minutes=inp.duration_mins)
                is_free = True
                for email in inp.attendee_emails:
                    person = get_person_by_email(email)
                    if not person:
                        continue
                    blocks = get_busy_blocks(
                        person["id"], candidate.isoformat(), slot_end.isoformat()
                    )
                    if blocks:
                        is_free = False
                        break
                if is_free:
                    label = candidate.strftime("%A, %d %b %Y at %H:%M UTC")
                    alternatives.append(
                        TimeSlot(
                            start=candidate.isoformat(),
                            end=slot_end.isoformat(),
                            label=label,
                        )
                    )
                    if len(alternatives) >= inp.max_alternatives:
                        break
                candidate += timedelta(hours=4)

        return ConflictResolverOutput(
            conflict_detected=bool(conflicting),
            conflicting_people=conflicting,
            alternatives=alternatives,
            message=(
                f"Conflict detected for: {', '.join(conflicting)}. "
                f"{len(alternatives)} alternative slot(s) found."
                if conflicting
                else "No conflicts detected. Proposed time is available for all attendees."
            ),
        )
