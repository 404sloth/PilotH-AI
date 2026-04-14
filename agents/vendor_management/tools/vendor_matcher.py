"""
Tool: VendorMatcherTool
Single responsibility: find and rank the best vendors for a given client project requirement.
This is the core 'choose best vendor' tool.
All SQL execution delegated to vendor_db DAL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class VendorMatcherInput(BaseModel):
    service_tag: str = Field(
        ...,
        description="Service category required (e.g. cloud_hosting, data_analytics, ci_cd_pipelines)",
    )
    budget_monthly: Optional[float] = Field(
        None, description="Maximum monthly budget in USD"
    )
    min_quality_score: float = Field(
        75.0, ge=0, le=100, description="Minimum quality score (0-100)"
    )
    min_on_time_rate: float = Field(
        0.85, ge=0, le=1.0, description="Minimum on-time delivery rate (0-1)"
    )
    min_avg_client_rating: float = Field(
        4.0, ge=1, le=5, description="Minimum average client rating (1-5)"
    )
    required_tier: Optional[str] = Field(
        None, description="Required vendor tier: preferred | standard | trial"
    )
    country: Optional[str] = Field(
        None,
        description="Restrict to vendors in a specific country (ISO code, e.g. US)",
    )
    top_n: int = Field(5, ge=1, le=20, description="Number of top vendors to return")
    client_project_id: Optional[str] = Field(
        None, description="Client project ID to persist selections (optional)"
    )


class RankedVendor(BaseModel):
    rank: int
    vendor_id: str
    name: str
    tier: str
    fit_score: float  # 0-100 composite score
    quality_score: Optional[float]
    on_time_rate: Optional[float]
    avg_client_rating: Optional[float]
    cost_competitiveness: Optional[float]
    monthly_rate: Optional[float]
    currency: Optional[str]
    services: List[str]
    selection_reason: str


class VendorMatcherOutput(BaseModel):
    service_required: str
    candidates_found: int
    ranked_vendors: List[RankedVendor]
    top_recommendation: Optional[str] = None  # vendor_id of #1


class VendorMatcherTool(StructuredTool):
    """
    Given a service type and project requirements, rank all capable vendors by fit score.
    Supports multiple vendors for the same service — returns ranked shortlist.
    """

    name: str = "vendor_matcher"
    description: str = (
        "Find and rank the best vendors for a specific service based on project requirements "
        "such as quality, budget, reliability, rating, and tier. Use this when you need to "
        "compare multiple vendors offering the same service and select the best fit."
    )
    args_schema: type[BaseModel] = VendorMatcherInput

    def execute(self, validated_input: VendorMatcherInput) -> VendorMatcherOutput:
        from integrations.data_warehouse.vendor_db import (
            find_best_vendors_for_service,
            save_vendor_selection,
        )

        requirements: Dict[str, Any] = {
            "min_quality_score": validated_input.min_quality_score,
            "min_on_time_rate": validated_input.min_on_time_rate,
            "min_avg_client_rating": validated_input.min_avg_client_rating,
        }
        if validated_input.budget_monthly is not None:
            requirements["max_monthly_budget"] = validated_input.budget_monthly
        if validated_input.required_tier:
            requirements["required_tier"] = validated_input.required_tier

        rows = find_best_vendors_for_service(
            service_tag=validated_input.service_tag,
            requirements=requirements,
            country=validated_input.country,
            top_n=validated_input.top_n,
        )

        ranked: List[RankedVendor] = []
        for i, r in enumerate(rows, start=1):
            reason = _build_reason(r, i)
            rv = RankedVendor(
                rank=i,
                vendor_id=r["vendor_id"],
                name=r["name"],
                tier=r.get("tier", "standard"),
                fit_score=r["fit_score"],
                quality_score=r.get("quality_score"),
                on_time_rate=r.get("on_time_rate"),
                avg_client_rating=r.get("avg_client_rating"),
                cost_competitiveness=r.get("cost_competitiveness"),
                monthly_rate=r.get("monthly_rate"),
                currency=r.get("currency", "USD"),
                services=r.get("services", []),
                selection_reason=reason,
            )
            ranked.append(rv)

            # Persist if we have a client project context
            if validated_input.client_project_id:
                save_vendor_selection(
                    client_project_id=validated_input.client_project_id,
                    vendor_id=r["vendor_id"],
                    fit_score=r["fit_score"],
                    selected=(i == 1),
                    reason=reason,
                )

        return VendorMatcherOutput(
            service_required=validated_input.service_tag,
            candidates_found=len(ranked),
            ranked_vendors=ranked,
            top_recommendation=ranked[0].vendor_id if ranked else None,
        )


def _build_reason(vendor: Dict[str, Any], rank: int) -> str:
    """Generate a human-readable explanation of why this vendor ranked here."""
    parts = []
    q = vendor.get("quality_score", 0)
    ot = (vendor.get("on_time_rate") or 0) * 100
    r = vendor.get("avg_client_rating", 0)
    cost = vendor.get("cost_competitiveness", 0)
    exp = vendor.get("total_projects_completed", 0)
    rate = vendor.get("monthly_rate")

    if q >= 90:
        parts.append(f"exceptional quality ({q:.0f}/100)")
    elif q >= 80:
        parts.append(f"strong quality ({q:.0f}/100)")

    if ot >= 95:
        parts.append(f"outstanding on-time rate ({ot:.0f}%)")
    elif ot >= 88:
        parts.append(f"reliable delivery ({ot:.0f}% on-time)")

    if r >= 4.7:
        parts.append(f"top-rated by clients ({r:.1f}/5)")
    elif r >= 4.3:
        parts.append(f"highly-rated by clients ({r:.1f}/5)")

    if cost >= 85:
        parts.append("very cost-competitive")
    elif cost >= 75:
        parts.append("competitively priced")

    if exp >= 200:
        parts.append(f"extensive track record ({exp} projects)")
    elif exp >= 100:
        parts.append(f"solid experience ({exp} projects)")

    if rate:
        parts.append(f"${rate:,.0f}/month")

    if vendor.get("tier") == "preferred":
        parts.append("preferred tier")

    prefix = {
        1: "Top choice — ",
        2: "Strong runner-up — ",
        3: "Solid alternative — ",
    }.get(rank, "Option — ")
    return prefix + (", ".join(parts) if parts else "meets minimum requirements")
