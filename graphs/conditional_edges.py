"""
Conditional edge functions for LangGraph graphs.

LangGraph routing is driven by pure functions that receive the current state
and return a string key matching one of the defined branches.

Edge types implemented here:
  1. Binary (approved / rejected)
  2. Action router (n-way dispatch)
  3. Error sentinel (continue / abort / retry)
  4. Risk-level router (none / medium / high)
  5. Loop controller (continue / done) — for iterative / retry patterns
  6. HITL gate (needs_human / auto_approve / rejected)
  7. Agent-to-agent handoff router
"""

from __future__ import annotations

from typing import Any, Dict, Literal


# ─── 1. Binary gate ───────────────────────────────────────────────────────────

def approved_or_rejected(state: Dict[str, Any]) -> str:
    """
    Branch on whether a HITL or validation step was approved.

    Returns: "approved" | "rejected"
    """
    return "approved" if state.get("approved", False) else "rejected"


# ─── 2. N-way action router ───────────────────────────────────────────────────

def route_by_action(state: Dict[str, Any]) -> str:
    """
    Route to a graph branch based on `state["action"]`.
    Falls back to "default" if the action is not recognised.

    Usage in graph builder:
        builder.add_conditional_edges(
            "entry_node",
            route_by_action,
            {"schedule": "fetch_availability", "summarize": "retrieve_transcript",
             "brief": "gather_context", "default": "fallback_node"},
        )
    """
    action = state.get("action", "default")
    allowed = {"schedule", "summarize", "brief", "find_best", "full_assessment",
               "monitor_sla", "track_milestones", "analyze_budget", "default"}
    return action if action in allowed else "default"


# ─── 3. Error sentinel ────────────────────────────────────────────────────────

def continue_or_abort(state: Dict[str, Any]) -> str:
    """
    If state contains an error, route to the abort branch.
    Otherwise continue normally.

    Returns: "continue" | "abort"
    """
    return "abort" if state.get("error") else "continue"


def continue_or_retry(state: Dict[str, Any], max_retries: int = 3) -> str:
    """
    Support retry loops. Retries up to max_retries times on error.

    Returns: "retry" | "continue" | "abort"
    """
    retries = state.get("retry_count", 0)
    if state.get("error") and retries < max_retries:
        return "retry"
    if state.get("error"):
        return "abort"
    return "continue"


# ─── 4. Risk-level router ─────────────────────────────────────────────────────

def route_by_risk(state: Dict[str, Any]) -> str:
    """
    Route based on computed risk score or risk_level string.

    Returns: "risk_none" | "risk_medium" | "risk_high"
    """
    level = state.get("risk_level", "").lower()
    if level in ("high", "critical"):
        return "risk_high"
    if level in ("medium",):
        return "risk_medium"

    # Fallback: numeric score
    score = float(state.get("risk_score", 0))
    if score >= 0.75:
        return "risk_high"
    if score >= 0.40:
        return "risk_medium"
    return "risk_none"


# ─── 5. Loop controller (iterative / retry pattern) ──────────────────────────

def should_loop(state: Dict[str, Any], max_iterations: int = 5) -> str:
    """
    Generic loop gate for iterative refinement nodes.

    Checks `state["iteration"]` against `max_iterations`.
    Returns: "loop" | "done"

    Example use: an LLM that refines its output until a quality threshold is met.
    """
    iteration = state.get("iteration", 0)
    quality = state.get("quality_score", 1.0)   # 0-1, 1.0 = perfect
    quality_threshold = state.get("quality_threshold", 0.8)

    if iteration >= max_iterations:
        return "done"                  # hard stop
    if quality >= quality_threshold:
        return "done"                  # good enough
    return "loop"                      # keep iterating


# ─── 6. HITL gate ─────────────────────────────────────────────────────────────

def hitl_gate(state: Dict[str, Any]) -> str:
    """
    Decide whether human approval is needed.

    Returns:
      "needs_human"   — interrupt the graph (HITL)
      "auto_approve"  — risk is low enough to proceed automatically
      "rejected"      — a prior human explicitly rejected this action
    """
    if state.get("human_rejected", False):
        return "rejected"
    if state.get("requires_approval", False):
        return "needs_human"
    return "auto_approve"


# ─── 7. Agent-to-agent handoff router ────────────────────────────────────────

def route_to_agent(state: Dict[str, Any]) -> str:
    """
    Route from the orchestration graph to the appropriate sub-agent node.

    Reads `state["next_agent"]` set by the orchestrator.
    Returns one of the registered agent keys or "fallback".
    """
    next_agent = state.get("next_agent", "")
    registered = {
        "vendor_management",
        "meetings_communication",
        "finance",
        "hr",
        "operations",
    }
    return next_agent if next_agent in registered else "fallback"


# ─── 8. Multi-step completion checker ────────────────────────────────────────

def all_steps_complete(state: Dict[str, Any]) -> str:
    """
    For parallel fan-out patterns: check if all sub-tasks are done.

    Returns: "all_done" | "pending"
    """
    pending = state.get("pending_tasks", [])
    return "all_done" if not pending else "pending"
