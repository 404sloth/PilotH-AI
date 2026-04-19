"""
Node: sl_analyzer
Responsible for analyzing SLA compliance by checking contract clauses and metrics.
"""

from typing import Dict, Any, List
from agents.vendor_management.schemas import VendorState, RiskItem
from agents.vendor_management.tools.contract_parser import ContractParserTool
from agents.vendor_management.tools.sla_monitor import SLAMonitorTool

def default_sla_clauses() -> List[Dict[str, Any]]:
    return [
        {"metric_name": "uptime_percentage", "target": 99.9, "weight": 0.5},
        {"metric_name": "p99_latency", "target": 200, "weight": 0.2},
        {"metric_name": "first_response_time", "target": 60, "weight": 0.15},
        {"metric_name": "avg_resolution_time", "target": 240, "weight": 0.15},
    ]

def sla_analyzer_node(state: VendorState) -> VendorState:
    """
    Compare SLA metrics against contract clauses and generate score/audit trail.
    """
    vendor_id = state.get("vendor_id")
    if not vendor_id:
        return state

    # Fetch SLA Data
    sla_tool = SLAMonitorTool()
    sla_result = sla_tool.execute({"vendor_id": vendor_id, "period_days": 30})
    
    # Ideally get contract details, fallback to defaults
    clauses = default_sla_clauses()
    
    if not hasattr(sla_result, "metrics") or not sla_result.data_available:
        state["sla_compliance"] = 0.0
        state["sla_data"] = {
            "overall_compliance": 0.0,
            "audit_trail": ["No SLA data available"]
        }
        return state

    metrics_map = {m.metric_name: m for m in sla_result.metrics}
    
    total_score = 0.0
    audit_trail = []
    
    for clause in clauses:
        metric = metrics_map.get(clause["metric_name"])
        if not metric:
            audit_trail.append({"clause": clause, "status": "Missing Metric Data", "score": 0})
            continue
            
        # Simplified scoring
        score = 0.0
        if metric.compliant:
            score = 100.0 * clause["weight"]
        else:
            score = 50.0 * clause["weight"] # Partial credit or depending on how bad breach is
            
        total_score += score
        audit_trail.append({
            "clause": clause,
            "metric_data": metric.dict(),
            "status": "Pass" if metric.compliant else "Breach",
            "score": score
        })
        
        if not metric.compliant:
            risk = RiskItem(
                category="SLA Breach",
                description=f"{metric.metric_name} failed. Actual: {metric.actual}{metric.unit} vs Target: {metric.target}{metric.unit}",
                severity="high" if clause["weight"] >= 0.3 else "medium",
                mitigation="Schedule renewal discussion or apply penalty credits"
            )
            state.setdefault("risk_items", []).append(risk.dict())

    state["sla_compliance"] = total_score
    state["sla_data"] = {
        "overall_compliance": total_score,
        "audit_trail": audit_trail,
        "breaches": sla_result.breaches
    }
    
    state.setdefault("recommendations", []).extend(sla_result.recommendations)
    return state
