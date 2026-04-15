"""
Financial Analysis Tool — Analyze vendor spending and cost optimization.

Features:
  - Historical spend analysis
  - Budget variance tracking
  - Cost optimization recommendations
  - Discount negotiation insights
  - Cost per unit calculations
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool

logger = logging.getLogger(__name__)


class VendorFinancialInput(BaseModel):
    """Input schema for financial analysis."""
    vendor_id: str = Field(..., description="Vendor ID to analyze")
    action: str = Field("analyze", description="analyze, optimize, forecast, or compare")
    time_period_months: int = Field(12, ge=1, le=36, description="Time period for analysis in months")


class VendorFinancialTool(StructuredTool):
    """Analyze vendor spending and identify optimization opportunities."""
    
    name: str = "vendor_financial_analysis"
    description: str = "Analyze spending patterns, budgets, and identify cost optimization opportunities"
    args_schema: type[BaseModel] = VendorFinancialInput
    
    def execute(self, validated_input: VendorFinancialInput) -> Dict[str, Any]:
        """Execute financial analysis."""
        try:
            result = {
                "vendor_id": validated_input.vendor_id,
                "timestamp": datetime.now().isoformat(),
                "period_months": validated_input.time_period_months,
            }
            
            if validated_input.action == "analyze":
                result.update(self._analyze_spending(validated_input.vendor_id, validated_input.time_period_months))
            elif validated_input.action == "optimize":
                result.update(self._identify_optimizations(validated_input.vendor_id))
            elif validated_input.action == "forecast":
                result.update(self._forecast_spending(validated_input.vendor_id, validated_input.time_period_months))
            elif validated_input.action == "compare":
                result.update(self._compare_with_market(validated_input.vendor_id))
            else:
                raise ValueError(f"Unknown action: {validated_input.action}")
            
            return result
        except Exception as e:
            logger.error(f"[Tool] {self.name} failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _analyze_spending(self, vendor_id: str, months: int) -> Dict[str, Any]:
        """Analyze historical spending patterns."""
        # Generate realistic monthly data
        today = datetime.now()
        monthly_data = []
        
        for i in range(months, 0, -1):
            month_date = today - timedelta(days=30 * i)
            # Simulate slightly increasing spend with seasonal variation
            base_spend = 50000
            seasonal_factor = 1.0 + (0.1 if month_date.month in [11, 12] else 0)
            growth_factor = 1.0 + (0.02 * (months - i))
            
            monthly_spend = base_spend * seasonal_factor * growth_factor
            monthly_data.append({
                "month": month_date.strftime("%Y-%m"),
                "amount": round(monthly_spend, 2),
            })
        
        total_spend = sum(m["amount"] for m in monthly_data)
        avg_spend = total_spend / len(monthly_data)
        max_spend = max(m["amount"] for m in monthly_data)
        min_spend = min(m["amount"] for m in monthly_data)
        
        return {
            "spending_analysis": {
                "total_spend_period": round(total_spend, 2),
                "average_monthly_spend": round(avg_spend, 2),
                "max_monthly_spend": round(max_spend, 2),
                "min_monthly_spend": round(min_spend, 2),
                "monthly_data": monthly_data,
                "year_over_year_growth": "2.8%",
                "budget_allocated": 706445,
                "budget_variance": round(((total_spend - 600000) / 600000) * 100, 1),
                "on_track": total_spend < 706445,
            }
        }
    
    def _identify_optimizations(self, vendor_id: str) -> Dict[str, Any]:
        """Identify cost optimization opportunities."""
        optimizations = [
            {
                "opportunity": "Commit to 24-month term",
                "current_rate": "$50,000/month",
                "potential_savings": "$15,000/year",
                "percentage_savings": 5.0,
                "implementation_difficulty": "Easy",
                "timeline": "2-3 weeks to negotiate",
                "notes": "Requires vendor agreement, provides price protection"
            },
            {
                "opportunity": "Consolidate redundant services",
                "current_rate": "$8,000/month",
                "potential_savings": "$96,000/year",
                "percentage_savings": 3.2,
                "implementation_difficulty": "Medium",
                "timeline": "1-2 months for migration",
                "notes": "Review current service portfolio, identify overlaps"
            },
            {
                "opportunity": "Right-size capacity",
                "current_rate": "$12,000/month",
                "potential_savings": "$72,000/year",
                "percentage_savings": 2.4,
                "implementation_difficulty": "Medium",
                "timeline": "1 month for analysis",
                "notes": "Audit current usage, scale down if over-provisioned"
            },
            {
                "opportunity": "Volume discount negotiation",
                "current_rate": "$50,000/month",
                "potential_savings": "$5,000/year",
                "percentage_savings": 1.7,
                "implementation_difficulty": "Easy",
                "timeline": "Immediate",
                "notes": "Total spend qualifies for enterprise pricing"
            },
        ]
        
        total_potential_savings = sum(float(o["potential_savings"].split('/')[0].replace('$', '').replace(',', '')) for o in optimizations)
        
        return {
            "optimization_analysis": {
                "total_optimization_opportunities": len(optimizations),
                "total_potential_annual_savings": f"${total_potential_savings:,.0f}",
                "total_percentage_savings": sum(o["percentage_savings"] for o in optimizations),
                "opportunities": optimizations,
                "quick_wins": [opt["opportunity"] for opt in optimizations if opt["implementation_difficulty"] == "Easy"],
            }
        }
    
    def _forecast_spending(self, vendor_id: str, months: int) -> Dict[str, Any]:
        """Forecast future spending."""
        today = datetime.now()
        forecast_months = 12
        
        forecast_data = []
        base_spend = 50000
        growth_rate = 0.025  # 2.5% monthly growth
        
        for i in range(1, forecast_months + 1):
            month_date = today + timedelta(days=30 * i)
            forecasted_spend = base_spend * ((1 + growth_rate) ** i)
            
            forecast_data.append({
                "month": month_date.strftime("%Y-%m"),
                "forecasted_spend": round(forecasted_spend, 2),
                "confidence": "High" if i <= 3 else ("Medium" if i <= 6 else "Low"),
            })
        
        annual_forecast = sum(m["forecasted_spend"] for m in forecast_data)
        
        return {
            "spending_forecast": {
                "forecast_period_months": forecast_months,
                "annual_forecasted_spend": round(annual_forecast, 2),
                "growth_assumptions": "2.5% monthly growth based on historical trend",
                "forecast_data": forecast_data,
                "budget_recomendation": f"${int(annual_forecast * 1.1):,}",
                "budget_recommendation_note": "Recommend 10% buffer for contingencies",
            }
        }
    
    def _compare_with_market(self, vendor_id: str) -> Dict[str, Any]:
        """Compare vendor pricing with market rates."""
        return {
            "market_comparison": {
                "our_rate": "$50,000/month",
                "market_average": "$48,000/month",
                "market_range": "$42,000 - $65,000/month",
                "competitiveness": "On par with market",
                "pricing_assessment": "Competitive but not the lowest",
                "recommendations": [
                    "Current pricing is fair for the service level provided",
                    "Monitor market rates semi-annually",
                    "Consider RFP in 6 months if price becomes uncompetitive",
                ],
                "comparable_vendors": [
                    {"name": "Competitor A", "estimated_rate": "$47,000/month", "notes": "Similar SLA"},
                    {"name": "Competitor B", "estimated_rate": "$52,000/month", "notes": "Premium features"},
                    {"name": "Competitor C", "estimated_rate": "$43,000/month", "notes": "Reduced support"},
                ]
            }
        }
