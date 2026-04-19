"""
Tool: VendorSearchTool
Single responsibility: search vendors by name / ID / service_tag / industry / category.
All SQL execution delegated to vendor_db DAL.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool


class VendorSearchInput(BaseModel):
    vendor_name: Optional[str] = Field(None, description="Partial or full vendor name")
    vendor_id: Optional[str] = Field(
        None, description="Exact internal vendor ID (e.g. V-001)"
    )
    service_tag: Optional[str] = Field(
        None, description="Service tag to filter by (e.g. cloud_hosting)"
    )
    industry: Optional[str] = Field(
        None, description="Industry name to filter by (e.g. Technology, Finance)"
    )
    category: Optional[str] = Field(
        None, description="Category name to filter by (e.g. Cloud & Infrastructure)"
    )
    country: Optional[str] = Field(
        None, description="ISO 2-letter country code or full name (e.g. US, United States)"
    )
    tier: Optional[str] = Field(
        None, description="Vendor tier (e.g. preferred, standard, trial)"
    )
    contract_status: Optional[str] = Field(
        None, description="Contract status (e.g. active, expired)"
    )
    limit: int = Field(10, ge=1, le=50, description="Max results to return")


class VendorRecord(BaseModel):
    vendor_id: str
    name: str
    tier: str
    country: str
    contract_status: str
    category: str
    industry: str
    services: List[str]
    quality_score: Optional[float]
    on_time_rate: Optional[float]
    avg_client_rating: Optional[float]
    cost_competitiveness: Optional[float]
    total_projects_completed: Optional[int]
    website: Optional[str]


class VendorSearchOutput(BaseModel):
    found: bool
    count: int = 0
    vendors: List[VendorRecord] = Field(default_factory=list)


class VendorSearchTool(StructuredTool):
    """Search the vendor registry. Returns non-sensitive profile data for matching vendors."""

    name: str = "vendor_search"
    description: str = (
        "Search for vendors by name, ID, service capability, industry, category, or country. "
        "Returns vendor profile data including tier, performance metrics, and services offered."
    )
    args_schema: type[BaseModel] = VendorSearchInput

    def execute(self, validated_input: VendorSearchInput) -> VendorSearchOutput:
        from integrations.data_warehouse.vendor_db import search_vendors

        rows = search_vendors(
            vendor_name=validated_input.vendor_name,
            vendor_id=validated_input.vendor_id,
            service_tag=validated_input.service_tag,
            country=validated_input.country,
            industry=validated_input.industry,
            category=validated_input.category,
            tier=validated_input.tier,
            contract_status=validated_input.contract_status,
            limit=validated_input.limit,
        )

        if not rows:
            return VendorSearchOutput(found=False)

        vendors = [
            VendorRecord(
                vendor_id=r["vendor_id"],
                name=r["name"],
                tier=r.get("tier", "standard"),
                country=r.get("country", "US"),
                contract_status=r.get("contract_status", "unknown"),
                category=r.get("category", "Unknown"),
                industry=r.get("industry", "Unknown"),
                services=r.get("services", []),
                quality_score=r.get("quality_score"),
                on_time_rate=r.get("on_time_rate"),
                avg_client_rating=r.get("avg_client_rating"),
                cost_competitiveness=r.get("cost_competitiveness"),
                total_projects_completed=r.get("total_projects_completed"),
                website=r.get("website"),
            )
            for r in rows
        ]

        return VendorSearchOutput(found=True, count=len(vendors), vendors=vendors)
