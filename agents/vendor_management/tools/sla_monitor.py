"""
Tool: SLAMonitorTool
Single responsibility: fetch SLA compliance metrics for a vendor.
All SQL execution delegated to vendor_db DAL.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class SLAMonitorInput(BaseModel):
    vendor_id: str = Field(..., description="Internal vendor ID")
    period_days: int = Field(30, ge=1, le=365, description="Lookback period in days")


class SLAMetric(BaseModel):
    metric_name: str
    target: float
    actual: float
    unit: str
    compliant: bool
    trend: str  # improving | declining | stable


class SLAMonitorOutput(BaseModel):
    vendor_id: str
    period_start: Optional[str]
    period_end: Optional[str]
    overall_compliance: float  # 0-100 percent
    metrics: List[SLAMetric]
    breaches: List[str]
    recommendations: List[str]
    data_available: bool


from langchain_core.runnables import RunnableConfig


class SLAMonitorTool(StructuredTool):
    """Monitor SLA compliance for a vendor. Returns metrics, breach list, and recommendations."""

    name: str = "sla_monitor"
    description: str = (
        "Check SLA compliance for a vendor. Returns overall compliance percentage, "
        "per-metric detail, breach descriptions, and improvement recommendations."
    )
    args_schema: type[BaseModel] = SLAMonitorInput

    def execute(
        self,
        validated_input: SLAMonitorInput,
        config: Optional[RunnableConfig] = None,
    ) -> SLAMonitorOutput:
        from integrations.data_warehouse.vendor_db import get_sla_compliance

        data = get_sla_compliance(
            vendor_id=validated_input.vendor_id,
            period_days=validated_input.period_days,
        )

        if not data:
            return SLAMonitorOutput(
                vendor_id=validated_input.vendor_id,
                period_start=None,
                period_end=None,
                overall_compliance=0.0,
                metrics=[],
                breaches=["No SLA records found for this vendor"],
                recommendations=["Establish SLA baseline and begin monitoring"],
                data_available=False,
            )

        metrics = [SLAMetric(**m) for m in data["metrics"]]

        breaches = [
            f"{m.metric_name}: actual {m.actual}{m.unit} vs target {m.target}{m.unit} ({m.trend})"
            for m in metrics
            if not m.compliant
        ]

        recommendations: List[str] = []
        if breaches:
            recommendations.append(
                "Schedule SLA review meeting with vendor within 2 weeks"
            )
        for m in metrics:
            if not m.compliant and m.trend == "declining":
                recommendations.append(
                    f"Urgent: '{m.metric_name}' is declining — request root cause analysis"
                )
            elif not m.compliant:
                recommendations.append(
                    f"'{m.metric_name}' below target — escalate via account manager"
                )

        return SLAMonitorOutput(
            vendor_id=validated_input.vendor_id,
            period_start=data["period_start"],
            period_end=data["period_end"],
            overall_compliance=data["overall_compliance"],
            metrics=metrics,
            breaches=breaches,
            recommendations=recommendations,
            data_available=True,
        )
