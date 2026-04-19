"""Risk Sentinel Tool — Proactive vendor risk monitoring."""

from typing import Dict, List, Optional, Type
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
from langchain_core.runnables import RunnableConfig


class RiskSentinelInput(BaseModel):
    vendor_id: Optional[str] = Field(None, description="Vendor ID (e.g., V-001)")
    vendor_name: Optional[str] = Field(None, description="Vendor Name")
    category: Optional[str] = Field(None, description="Category (for industry-wide risks)")


class RiskSentinelOutput(BaseModel):
    risk_level: str
    summary: str
    incidents: List[str]
    sentiment_trend: str
    geopolitcal_risk: str


class RiskSentinelTool(StructuredTool):
    name: str = "risk_sentinel"
    description: str = "Monitor geopolitical, financial, and news-based risks for a vendor or category."
    args_schema: Type[BaseModel] = RiskSentinelInput

    def execute(self, inp: RiskSentinelInput, config: Optional[RunnableConfig] = None) -> RiskSentinelOutput:
        # Simulated logic: In production, fetch from news APIs or risk feeds
        vendor = inp.vendor_name or inp.vendor_id or "Selected Portfolio"
        
        # Determine risk based on name patterns for demo/validation
        lower_v = vendor.lower()
        if "cloud" in lower_v or "aws" in lower_v or "azure" in lower_v:
            return RiskSentinelOutput(
                risk_level="Low",
                summary=f"Market stability for {vendor} remains high. No major infrastructure outages reported in last 24h.",
                incidents=["Minor latency reported in EU-West-1 region (resolved)", "API documentation update"],
                sentiment_trend="Stable",
                geopolitcal_risk="Minimal (Diversified)",
            )
        
        return RiskSentinelOutput(
            risk_level="Medium",
            summary=f"Increasing regulatory scrutiny in {inp.category or 'Technology'} sector may impact {vendor}.",
            incidents=["GDPR compliance audit initiated by EU authorities", "Quarterly financial report shows increased debt ratio"],
            sentiment_trend="Cautious",
            geopolitcal_risk="Moderate (Supply Chain Sensitivity)",
        )
