"""Financial Health Tool — Intelligent vendor financial stability analysis."""

from typing import Dict, List, Optional, Type
from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
from langchain_core.runnables import RunnableConfig


class FinancialHealthInput(BaseModel):
    vendor_name: str = Field(..., description="Vendor name to analyze")
    fiscal_year: Optional[int] = Field(2025, description="Fiscal year for data")


class FinancialHealthOutput(BaseModel):
    stability_score: float
    rating: str
    key_metrics: Dict[str, str]
    analysis_summary: str
    liquidity_risk: str


class FinancialHealthTool(StructuredTool):
    name: str = "financial_health"
    description: str = "Perform deep-dive financial health analysis on a vendor including credit rating and stability scores."
    args_schema: Type[BaseModel] = FinancialHealthInput

    def execute(self, inp: FinancialHealthInput, config: Optional[RunnableConfig] = None) -> FinancialHealthOutput:
        # Simulated analysis logic
        score = 8.5 if len(inp.vendor_name) > 5 else 6.2
        rating = "AA+" if score > 8 else "BBB"
        
        return FinancialHealthOutput(
            stability_score=score,
            rating=rating,
            key_metrics={
                "Debt-to-Equity": "0.34",
                "Operating Margin": "22.5%",
                "Revenue Growth": "+15% YoY"
            },
            analysis_summary=f"The financial health of {inp.vendor_name} for FY{inp.fiscal_year} is robust, showing strong liquidity and low leverage.",
            liquidity_risk="Low - Sufficient cash reserves for next 18 months."
        )
