"""
Node: evaluate_node
Responsibility: use LLM to evaluate vendor performance and produce
structured scores, strengths, and weaknesses from real data.

Features:
  - PII sanitization before LLM calls
  - Structured logging with correlation IDs
  - Metrics recording (LLM calls, evaluation time)
  - Distributed tracing for request tracking
  - Historical performance integration
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, AIMessage

from agents.vendor_management.schemas import VendorState
from observability.logger import get_logger
from observability.metrics import get_metrics
from observability.tracing import get_tracer
from observability.pii_sanitizer import PIISanitizer, sanitize_data

logger = logging.getLogger(__name__)
otel_logger = get_logger("vendor_management.evaluate")


def _safe_float(value: Any, default: float) -> float:
    """Convert numeric-ish values safely, tolerating sanitizer placeholders."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


from langchain_core.runnables import RunnableConfig

def evaluate_node(state: VendorState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Evaluate a single vendor using LLM reasoning over real scorecard data.
    Skipped for FIND_BEST action (evaluation is embedded in VendorMatcherTool).
    
    Flow:
      1. Validate state and action
      2. Fetch vendor, SLA, milestone data
      3. Build evaluation context with sanitized data
      4. Call LLM with sanitized payload
      5. Parse and return scores
      6. Record metrics and traces
    """
    tracer = get_tracer("vendor_management")
    metrics = get_metrics()
    start_time = time.time()

    with tracer.trace_operation(
        "vendor_evaluation",
        attributes={
            "vendor_id": state.get("vendor_id"),
            "action": state.get("action"),
        }
    ) as span:
        action = state.get("action", "full_assessment")

        # FIND_BEST doesn't need a separate evaluate step
        if action == "find_best":
            otel_logger.info("Skipping evaluation for FIND_BEST action", agent="vendor_management")
            return {}

        vendor_details = state.get("vendor_details") or {}
        sla_data = state.get("sla_data") or {}
        milestone_data = state.get("milestone_data") or []
        
        if state.get("error"):
            otel_logger.error(
                "State contains error, skipping evaluation",
                agent="vendor_management",
                error=state.get("error"),
            )
            return {}

        if not vendor_details:
            otel_logger.warning("No vendor details found", agent="vendor_management")
            return {"evaluation_scores": {}, "strengths": [], "weaknesses": []}

        # Load SLA and milestone data if not already in state
        if not sla_data and state.get("vendor_id"):
            try:
                from agents.vendor_management.tools.sla_monitor import (
                    SLAMonitorTool,
                    SLAMonitorInput,
                )
                sla_result = SLAMonitorTool().execute(
                    SLAMonitorInput(vendor_id=state["vendor_id"])
                )
                sla_data = sla_result.model_dump()
                span.add_event("sla_data_loaded")
            except Exception as e:
                otel_logger.warning(
                    "Failed to load SLA data",
                    agent="vendor_management",
                    error=str(e),
                )

        if not milestone_data and state.get("vendor_id"):
            try:
                from agents.vendor_management.tools.milestone_tracker import (
                    MilestoneTrackerTool,
                    MilestoneTrackerInput,
                )
                ms_result = MilestoneTrackerTool().execute(
                    MilestoneTrackerInput(vendor_id=state["vendor_id"])
                )
                milestone_data = [m.model_dump() for m in ms_result.milestones]
                span.add_event("milestone_data_loaded")
            except Exception as e:
                otel_logger.warning(
                    "Failed to load milestone data",
                    agent="vendor_management",
                    error=str(e),
                )

        # Build evaluation context
        vendor_context = _build_vendor_context(
            vendor_details, sla_data, milestone_data
        )
        
        # CRITICAL: Sanitize vendor context before sending to LLM
        sanitized_context = sanitize_data(vendor_context)
        
        otel_logger.info(
            "Starting LLM evaluation",
            agent="vendor_management",
            action="llm_evaluate",
            data={
                "vendor_name": vendor_details.get("name"),
                "sla_compliance": sla_data.get("overall_compliance"),
            },
        )

        span.add_event("evaluation_start", {"vendor_name": vendor_details.get("name")})

        # Call LLM with sanitized data and the passed config
        scores, strengths, weaknesses, overall = _evaluate_with_llm(
            sanitized_context, vendor_details.get("name"), tracer, span, config
        )

        duration_ms = (time.time() - start_time) * 1000
        
        # Record metrics
        metrics.record_histogram(
            "vendor_evaluation.duration_ms",
            duration_ms,
            tags={"action": action},
        )
        metrics.increment_counter(
            "vendor_evaluation.success",
            tags={"action": action},
        )
        
        otel_logger.info(
            "Vendor evaluation complete",
            agent="vendor_management",
            action="evaluation_complete",
            data={
                "vendor_name": vendor_details.get("name"),
                "overall_score": overall,
                "duration_ms": duration_ms,
            },
        )

        span.add_event(
            "evaluation_complete",
            {
                "overall_score": overall,
                "duration_ms": duration_ms,
            },
        )

        return {
            "evaluation_scores": scores,
            "overall_score": overall,
            "sla_data": sla_data,
            "milestone_data": milestone_data,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "messages": [
                AIMessage(
                    content=f"Evaluation complete for {vendor_details.get('name')}. Score: {overall:.1f}/100."
                )
            ],
            "evaluation_duration_ms": duration_ms,
        }


def _build_vendor_context(
    vendor: Dict[str, Any],
    sla: Dict[str, Any],
    milestones: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the vendor evaluation context."""
    return {
        "vendor": {
            "name": vendor.get("name"),
            "tier": vendor.get("tier"),
            "category": vendor.get("category"),
            "quality_score": vendor.get("quality_score"),
            "on_time_rate": vendor.get("on_time_rate"),
            "avg_client_rating": vendor.get("avg_client_rating"),
            "cost_competitiveness": vendor.get("cost_competitiveness"),
            "communication_score": vendor.get("communication_score"),
            "innovation_score": vendor.get("innovation_score"),
            "total_projects": vendor.get("total_projects_completed"),
        },
        "sla": {
            "overall_compliance": sla.get("overall_compliance"),
            "breach_count": len(sla.get("breaches", [])),
        },
        "milestones": {
            "delayed": sum(1 for m in milestones if m.get("status") == "delayed"),
            "at_risk": sum(1 for m in milestones if m.get("status") == "at_risk"),
        },
    }


def _evaluate_with_llm(
    vendor_context: Dict[str, Any],
    vendor_name: str,
    tracer,
    parent_span,
    config: RunnableConfig,
) -> tuple:
    """
    Call LLM to evaluate vendor using sanitized context and system prompts.
    
    Returns:
      (scores, strengths, weaknesses, overall_score)
    """
    from llm.model_factory import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage
    from orchestrator.system_prompts import get_prompt
    
    metrics = get_metrics()
    start_time = time.time()

    with tracer.trace_operation(
        "llm_vendor_evaluation",
        attributes={"vendor_name": vendor_name}
    ) as span:
        try:
            # Use enhanced system prompt for vendor evaluation
            prompt = get_prompt(
                "vendor_evaluation",
                vendor_data=vendor_context,
                vendor_name=vendor_name
            )

            llm = get_llm(temperature=0.0, max_tokens=2000)
            
            # Add system context from system prompts
            from orchestrator.system_prompts import AgentType, get_system_prompt
            system_msg = SystemMessage(content=get_system_prompt(AgentType.VENDOR_MANAGEMENT))
            
            # Record LLM call with config to propagate tracing
            response = llm.invoke([system_msg, HumanMessage(content=prompt)], config=config)
            
            duration_ms = (time.time() - start_time) * 1000
            metrics.record_histogram(
                "llm_call.duration_ms",
                duration_ms,
                tags={"model": "vendor_evaluation"},
            )
            metrics.increment_counter(
                "llm_call.success",
                tags={"model": "vendor_evaluation"},
            )
            
            content = response.content.strip()

            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            parsed = json.loads(content)
            scores = parsed.get("evaluation_scores", {})
            strengths = parsed.get("strengths", [])
            weaknesses = parsed.get("weaknesses", [])
            overall = round(sum(scores.values()) / len(scores), 1) if scores else 0.0

            span.add_event(
                "llm_response_parsed",
                {"overall_score": overall, "duration_ms": duration_ms},
            )
            
            otel_logger.debug(
                "LLM evaluation successful",
                agent="vendor_management",
                data={"overall_score": overall, "duration_ms": duration_ms},
            )
            
            return scores, strengths, weaknesses, overall

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            otel_logger.warning(
                "LLM evaluation failed, using rule-based fallback",
                agent="vendor_management",
                error=str(e),
            )
            
            # Record failed LLM call
            metrics.increment_counter(
                "llm_call.failure",
                tags={"model": "vendor_evaluation"},
            )
            
            span.add_event(
                "llm_failed",
                {"error": str(e), "duration_ms": duration_ms},
            )

            # Fall back to rule-based evaluation
            vc = vendor_context.get("vendor", {})
            sc = vendor_context.get("sla", {})
            ms = vendor_context.get("milestones", {})
            
            q = _safe_float(vc.get("quality_score") or 50, 50)
            ot = _safe_float(vc.get("on_time_rate") or 0.5, 0.5) * 100
            comm = _safe_float(vc.get("communication_score") or 50, 50)
            cost = _safe_float(vc.get("cost_competitiveness") or 50, 50)
            inno = _safe_float(vc.get("innovation_score") or 50, 50)
            slap = _safe_float(sc.get("overall_compliance") or 100, 100)

            delayed = ms.get("delayed", 0)
            penalty = min(delayed * 5, 20)

            scores = {
                "quality": q,
                "reliability": max(ot - penalty, 0),
                "sla_compliance": slap,
                "communication": comm,
                "cost": cost,
                "innovation": inno,
            }
            overall = round(sum(scores.values()) / len(scores), 1)

            strengths = [k for k, v in scores.items() if v >= 85]
            weaknesses = [k for k, v in scores.items() if v < 70]

            span.add_event(
                "fallback_evaluation_complete",
                {"overall_score": overall},
            )

            return (
                scores,
                [f"Strong {s}" for s in strengths],
                [f"Needs improvement: {w}" for w in weaknesses],
                overall,
            )

