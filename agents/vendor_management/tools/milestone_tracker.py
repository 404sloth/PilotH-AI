"""
Tool: MilestoneTrackerTool
Single responsibility: retrieve and analyse project milestone status for a vendor.
All SQL execution delegated to vendor_db DAL.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class MilestoneTrackerInput(BaseModel):
    vendor_id:  str            = Field(..., description="Internal vendor ID")
    project_id: Optional[str] = Field(None, description="Specific project ID (optional)")


class Milestone(BaseModel):
    id:                    str
    project_id:            str
    project_name:          str
    name:                  str
    due_date:              str
    status:                str   # not_started | in_progress | completed | delayed | at_risk
    completion_percentage: float
    notes:                 Optional[str]
    days_overdue:          int


class MilestoneTrackerOutput(BaseModel):
    vendor_id:      str
    project_id:     Optional[str]
    total:          int
    completed:      int
    in_progress:    int
    delayed:        int
    at_risk:        int
    not_started:    int
    milestones:     List[Milestone]
    overall_status: str   # on_track | at_risk | delayed
    recommendations: List[str]


class MilestoneTrackerTool(StructuredTool):
    """
    Retrieve and analyse project milestones for a vendor.
    Identifies delays, at-risk items, and produces action recommendations.
    """

    name: str = "milestone_tracker"
    description: str = (
        "Retrieve milestone status for a vendor's active projects. "
        "Flags delayed and at-risk milestones with prioritised recommendations."
    )
    args_schema: type[BaseModel] = MilestoneTrackerInput

    def execute(self, validated_input: MilestoneTrackerInput) -> MilestoneTrackerOutput:
        from integrations.data_warehouse.vendor_db import get_milestones

        rows = get_milestones(
            vendor_id=validated_input.vendor_id,
            project_id=validated_input.project_id,
        )

        milestones = [
            Milestone(
                id=r["id"],
                project_id=r["project_id"],
                project_name=r.get("project_name", ""),
                name=r["name"],
                due_date=r["due_date"],
                status=r["status"],
                completion_percentage=float(r["completion_percentage"]),
                notes=r.get("notes"),
                days_overdue=int(r.get("days_overdue") or 0),
            )
            for r in rows
        ]

        completed   = sum(1 for m in milestones if m.status == "completed")
        in_progress = sum(1 for m in milestones if m.status == "in_progress")
        delayed     = sum(1 for m in milestones if m.status == "delayed")
        at_risk     = sum(1 for m in milestones if m.status == "at_risk")
        not_started = sum(1 for m in milestones if m.status == "not_started")

        overall_status = (
            "delayed"  if delayed  > 0 else
            "at_risk"  if at_risk  > 0 else
            "on_track"
        )

        recommendations: List[str] = []
        if delayed:
            names = [m.name for m in milestones if m.status == "delayed"]
            worst = max((m for m in milestones if m.status == "delayed"), key=lambda m: m.days_overdue, default=None)
            recommendations.append(
                f"[CRITICAL] {len(names)} delayed milestone(s): {', '.join(names)}. "
                + (f"Worst: '{worst.name}' is {worst.days_overdue}d overdue." if worst else "")
            )

        if at_risk:
            names = [m.name for m in milestones if m.status == "at_risk"]
            recommendations.append(f"[WARNING] At-risk milestones: {', '.join(names)} — review resource allocation.")

        if overall_status != "on_track":
            recommendations.append("Schedule an urgent status call with the vendor project lead.")

        if not milestones:
            recommendations.append("No milestone data available. Request project plan from vendor.")

        return MilestoneTrackerOutput(
            vendor_id=validated_input.vendor_id,
            project_id=validated_input.project_id,
            total=len(milestones),
            completed=completed,
            in_progress=in_progress,
            delayed=delayed,
            at_risk=at_risk,
            not_started=not_started,
            milestones=milestones,
            overall_status=overall_status,
            recommendations=recommendations,
        )