"""
Participant Briefing Tool — fetch enriched attendee profiles using persons DB.
Disambiguates same-name individuals using department, project, role, and location.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class BriefingInput(BaseModel):
    emails:     List[str]      = Field(..., description="Attendee email addresses")
    meeting_context: Optional[str] = Field(None, description="Meeting purpose for tailored bios")


class PersonBrief(BaseModel):
    email:       str
    full_name:   str
    department:  str
    project:     Optional[str]
    role:        str
    location:    str
    timezone:    str
    skills:      List[str]
    bio:         Optional[str]
    slack_handle: Optional[str]
    manager_name: Optional[str]
    disambiguation_note: str   # explains how this person was uniquely identified


class BriefingOutput(BaseModel):
    found:          int
    not_found:      List[str]
    participants:   List[PersonBrief]
    disambiguation_warnings: List[str]   # raised when name collisions detected


class ParticipantBriefingTool(StructuredTool):
    """
    Fetch enriched attendee profiles from the persons database.
    Resolves by email (unique); provides disambiguation notes when names collide.
    """
    name: str = "participant_briefing"
    description: str = (
        "Retrieve enriched attendee profiles from the company directory. "
        "Uses email as unique key to correctly disambiguate people with the same name."
    )
    args_schema: type[BaseModel] = BriefingInput

    def execute(self, inp: BriefingInput) -> BriefingOutput:
        from integrations.data_warehouse.meeting_db import get_person_by_email, find_persons

        briefs: List[PersonBrief] = []
        not_found: List[str]      = []
        disambiguation_warnings: List[str] = []

        for email in inp.emails:
            person = get_person_by_email(email)
            if not person:
                not_found.append(email)
                continue

            # Check for name collisions (same full_name, different person)
            same_name = find_persons(name=person["full_name"], limit=10)
            collisions = [p for p in same_name if p["id"] != person["id"]]
            dambig_note = (
                f"Unique identifier: {email} | {person['department']} | {person['location']}"
            )
            if collisions:
                others = ", ".join(
                    f"{p['full_name']} ({p['department']}, {p['location']})"
                    for p in collisions
                )
                disambiguation_warnings.append(
                    f"⚠ Name collision: '{person['full_name']}' also refers to: {others}. "
                    f"This entry is from {person['department']}, {person['location']}."
                )

            briefs.append(PersonBrief(
                email=email,
                full_name=person["full_name"],
                department=person["department"],
                project=person.get("project"),
                role=person["role"],
                location=person["location"],
                timezone=person["timezone"],
                skills=person.get("skills", []),
                bio=person.get("bio"),
                slack_handle=person.get("slack_handle"),
                manager_name=person.get("manager_name"),
                disambiguation_note=dambig_note,
            ))

        return BriefingOutput(
            found=len(briefs),
            not_found=not_found,
            participants=briefs,
            disambiguation_warnings=disambiguation_warnings,
        )
