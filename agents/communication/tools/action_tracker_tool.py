"""Action item tracker — saves to DB and mocks project management system."""

from __future__ import annotations
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class ActionItem(BaseModel):
    description: str
    assignee_email: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"


class ActionTrackerInput(BaseModel):
    meeting_id: str = Field(..., description="Meeting this action belongs to")
    action_items: List[ActionItem] = Field(...)


class TrackedItem(BaseModel):
    task_id: str
    description: str
    assignee_name: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: str
    status: str = "open"
    jira_url: Optional[str] = None  # mock Jira link


class ActionTrackerOutput(BaseModel):
    meeting_id: str
    created: int
    items: List[TrackedItem]
    summary: str


class ActionItemTrackerTool(StructuredTool):
    """
    Save action items to the meeting DB and return mock project-management task links.
    PRODUCTION: Swap _create_task with real Jira/Asana/Linear SDK call.
    """

    name: str = "action_item_tracker"
    description: str = "Track meeting action items in the database. Returns task IDs and mock PM links."
    args_schema: type[BaseModel] = ActionTrackerInput

    def execute(self, inp: ActionTrackerInput) -> ActionTrackerOutput:
        from integrations.data_warehouse.meeting_db import (
            save_action_items,
            get_person_by_email,
        )

        tracked: List[TrackedItem] = []
        db_items = []

        for item in inp.action_items:
            person = (
                get_person_by_email(item.assignee_email)
                if item.assignee_email
                else None
            )
            task_id = f"TASK-{uuid.uuid4().hex[:6].upper()}"
            db_items.append(
                {
                    "assignee_id": person["id"] if person else None,
                    "description": item.description,
                    "due_date": item.due_date,
                    "priority": item.priority,
                }
            )
            tracked.append(
                TrackedItem(
                    task_id=task_id,
                    description=item.description,
                    assignee_name=person["full_name"]
                    if person
                    else item.assignee_email,
                    assignee_id=person["id"] if person else None,
                    due_date=item.due_date,
                    priority=item.priority,
                    jira_url=f"https://jira.company.com/browse/{task_id}",
                )
            )

        save_action_items(inp.meeting_id, db_items)

        return ActionTrackerOutput(
            meeting_id=inp.meeting_id,
            created=len(tracked),
            items=tracked,
            summary=f"Created {len(tracked)} task(s) for meeting {inp.meeting_id}.",
        )
