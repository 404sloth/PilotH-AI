"""
Reports & Simulations API Routes
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


# ── Report Routes ────────────────────────────────────────────────────────────

@router.get("/vendor/{vendor_id}/performance", summary="Get vendor performance report")
def get_vendor_performance_report(
    vendor_id: str,
    period_days: int = Query(30, ge=1, le=365),
    format_type: str = Query("json", pattern="^(json|markdown)$"),
):
    """Generate a vendor performance report."""
    from knowledge_base.report_generator import ReportGenerator
    
    gen = ReportGenerator()
    report = gen.generate_vendor_performance_report(vendor_id, period_days)
    
    if format_type == "markdown":
        return {
            "format": "markdown",
            "content": gen.format_as_markdown(report),
        }
    
    return report


@router.get("/agreements/expiry", summary="Get agreement expiry report")
def get_agreement_expiry_report():
    """Generate an agreement expiry and renewal timeline report."""
    from knowledge_base.report_generator import ReportGenerator
    
    gen = ReportGenerator()
    report = gen.generate_agreement_expiry_report()
    
    return report


@router.get("/vendor/{vendor_id}/compliance", summary="Get compliance report")
def get_compliance_report(vendor_id: str):
    """Generate a compliance and risk assessment report."""
    from knowledge_base.report_generator import ReportGenerator
    
    gen = ReportGenerator()
    report = gen.generate_compliance_report(vendor_id)
    
    return report


@router.get("/vendor/{vendor_id}/financial", summary="Get financial analysis")
def get_financial_analysis(vendor_id: str):
    """Generate financial analysis and cost optimization report."""
    from knowledge_base.report_generator import ReportGenerator
    
    gen = ReportGenerator()
    report = gen.generate_financial_analysis(vendor_id)
    
    return report


# ── Simulation Routes ────────────────────────────────────────────────────────

@router.get("/simulations", summary="List simulations")
def list_simulations():
    """List all available interactive simulations."""
    from knowledge_base.simulations import get_simulator
    
    sim = get_simulator()
    scenarios = sim.list_scenarios()
    
    return {
        "scenarios": scenarios,
        "total": len(scenarios),
    }


@router.get("/simulations/{scenario_id}", summary="Get simulation scenario")
def get_simulation(scenario_id: str):
    """Get a complete simulation scenario."""
    from knowledge_base.simulations import get_simulator
    
    sim = get_simulator()
    scenario = sim.get_scenario(scenario_id)
    
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    
    return scenario


@router.get("/simulations/{scenario_id}/step/{step_num}", summary="Get simulation step")
def get_simulation_step(scenario_id: str, step_num: int):
    """Get a specific step from a simulation."""
    from knowledge_base.simulations import get_simulator
    
    sim = get_simulator()
    step = sim.get_scenario_step(scenario_id, step_num)
    
    if not step:
        raise HTTPException(status_code=404, detail=f"Step {step_num} not found in scenario '{scenario_id}'.")
    
    return step


class ChoiceRequest(BaseModel):
    """User's choice in a simulation."""
    choice: str  # A, B, C, or D


@router.post("/simulations/{scenario_id}/step/{step_num}/evaluate", summary="Evaluate simulation choice")
def evaluate_simulation_choice(
    scenario_id: str,
    step_num: int,
    request: ChoiceRequest,
):
    """Evaluate user's choice and provide feedback."""
    from knowledge_base.simulations import get_simulator
    
    sim = get_simulator()
    result = sim.evaluate_choice(scenario_id, step_num, request.choice)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


# ── Utility Routes ──────────────────────────────────────────────────────────

@router.post("/reports/generate-custom", summary="Generate custom report")
def generate_custom_report(
    report_type: str,
    vendor_id: Optional[str] = None,
    **kwargs,
):
    """Generate a custom report based on parameters."""
    from knowledge_base.report_generator import ReportGenerator
    
    gen = ReportGenerator()
    
    report_map = {
        "performance": lambda: gen.generate_vendor_performance_report(vendor_id),
        "expiry": lambda: gen.generate_agreement_expiry_report(),
        "compliance": lambda: gen.generate_compliance_report(vendor_id),
        "financial": lambda: gen.generate_financial_analysis(vendor_id),
    }
    
    if report_type not in report_map:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown report type: {report_type}. Options: {', '.join(report_map.keys())}"
        )
    
    try:
        report = report_map[report_type]()
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
