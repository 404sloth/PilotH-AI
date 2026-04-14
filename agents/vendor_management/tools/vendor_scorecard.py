"""
Tool: VendorScorecardTool
Single responsibility: produce a comprehensive enriched scorecard for a vendor.
Aggregates performance, SLA, milestones, and contract in one DAL call.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class VendorScorecardInput(BaseModel):
    vendor_id: str = Field(..., description="Internal vendor ID to retrieve full scorecard for")


class VendorScorecardOutput(BaseModel):
    vendor_id:           str
    name:                str
    tier:                str
    overall_score:       float   # derived composite 0-100
    quality_score:       Optional[float]
    on_time_rate:        Optional[float]
    avg_client_rating:   Optional[float]
    sla_compliance:      Optional[float]
    active_projects:     int
    delayed_milestones:  int
    has_active_contract: bool
    contract_value:      Optional[float]
    summary:             str


class VendorScorecardTool(StructuredTool):
    """
    Retrieve a full enriched scorecard for a vendor — aggregates perf, SLA, milestones, contract.
    """

    name: str = "vendor_scorecard"
    description: str = (
        "Produce a comprehensive scorecard for a single vendor including performance metrics, "
        "SLA compliance, milestone health, and contract status."
    )
    args_schema: type[BaseModel] = VendorScorecardInput

    def execute(self, validated_input: VendorScorecardInput) -> VendorScorecardOutput:
        from integrations.data_warehouse.vendor_db import get_vendor_scorecard

        data = get_vendor_scorecard(validated_input.vendor_id)

        if not data or not data.get("vendor"):
            return VendorScorecardOutput(
                vendor_id=validated_input.vendor_id,
                name="Unknown",
                tier="unknown",
                overall_score=0.0,
                quality_score=None,
                on_time_rate=None,
                avg_client_rating=None,
                sla_compliance=None,
                active_projects=0,
                delayed_milestones=0,
                has_active_contract=False,
                contract_value=None,
                summary=f"Vendor {validated_input.vendor_id} not found.",
            )

        v = data["vendor"]
        sla = data.get("sla") or {}
        milestones = data.get("milestones") or []
        contract = data.get("contract")

        delayed_ms = sum(1 for m in milestones if m.get("status") == "delayed")
        active_projects = len({m["project_id"] for m in milestones if m.get("status") != "completed"})

        # Compute derived overall score
        q  = float(v.get("quality_score") or 0)
        ot = (float(v.get("on_time_rate") or 0)) * 100
        r  = float(v.get("avg_client_rating") or 0) / 5.0 * 100
        sc = float(sla.get("overall_compliance") or 100)
        delay_penalty = min(delayed_ms * 5, 20)   # -5pts per delayed milestone, max -20
        overall = round((q * 0.30 + ot * 0.25 + r * 0.20 + sc * 0.25) - delay_penalty, 1)
        overall = max(0.0, min(100.0, overall))

        lines = [
            f"{v['name']} ({v.get('tier', '').upper()}) — Overall Score: {overall}/100",
            f"Quality: {q:.0f}/100 | On-Time: {ot:.0f}% | Client Rating: {v.get('avg_client_rating', 'N/A')}/5",
            f"SLA Compliance: {sla.get('overall_compliance', 'N/A')}% | Delayed Milestones: {delayed_ms}",
        ]
        if contract:
            lines.append(f"Active Contract: {contract.get('contract_reference')} — ${contract.get('total_value', 0):,.0f} {contract.get('currency', 'USD')}")

        return VendorScorecardOutput(
            vendor_id=validated_input.vendor_id,
            name=v["name"],
            tier=v.get("tier", "standard"),
            overall_score=overall,
            quality_score=v.get("quality_score"),
            on_time_rate=v.get("on_time_rate"),
            avg_client_rating=v.get("avg_client_rating"),
            sla_compliance=sla.get("overall_compliance"),
            active_projects=active_projects,
            delayed_milestones=delayed_ms,
            has_active_contract=contract is not None,
            contract_value=contract.get("total_value") if contract else None,
            summary=" | ".join(lines),
        )
