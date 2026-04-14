"""
Top-level Orchestration Graph — the master LangGraph StateGraph that
coordinates all registered agents, handles cross-agent routing, retries,
HITL gates, risk escalation, and iterative refinement loops.

Edge types demonstrated:
  ┌─ Conditional routing       (route_to_agent)
  ├─ Binary gate               (approved_or_rejected)
  ├─ Risk-level routing        (route_by_risk)
  ├─ Error / retry loop        (continue_or_retry)
  ├─ HITL gate                 (hitl_gate → NodeInterrupt)
  ├─ Parallel fan-out          (send multiple sub-agents simultaneously)
  └─ Agent repetition / loop   (should_loop for iterative refinement)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graphs.conditional_edges import (
    continue_or_retry,
    hitl_gate,
    route_by_risk,
    should_loop,
)

logger = logging.getLogger(__name__)


# ─── Orchestration State ──────────────────────────────────────────────────────


class OrchestrationState(TypedDict, total=False):
    # Input
    session_id: str
    user_message: str
    context: Dict[str, Any]

    # Routing
    intent: Dict[str, Any]  # {agent, action, params}
    next_agent: str
    dispatched_agents: List[str]  # for fan-out tracking

    # Execution
    agent_results: Dict[str, Any]  # name → result
    pending_tasks: List[str]  # for parallel completion check
    retry_count: int
    iteration: int
    quality_score: float
    quality_threshold: float

    # Risk & HITL
    risk_score: float
    risk_level: str
    risk_items: List[str]
    requires_approval: bool
    approved: bool
    human_rejected: bool

    # Output
    final_response: str
    error: Optional[str]
    messages: List[Any]


# ─── Nodes ────────────────────────────────────────────────────────────────────


def parse_intent_node(state: OrchestrationState) -> Dict[str, Any]:
    """Parse user message and determine target agent + action."""
    from orchestrator.intent_parser import IntentParser
    from config.settings import Settings

    try:
        intent = IntentParser(Settings()).parse(
            state.get("user_message", ""),
            state.get("context", {}),
        )
    except Exception as e:
        logger.warning("Intent parsing failed: %s", e)
        intent = {
            "agent": "vendor_management",
            "action": "full_assessment",
            "params": {},
        }
    return {
        "intent": intent,
        "next_agent": intent.get("agent", "vendor_management"),
        "retry_count": 0,
        "iteration": 0,
        "messages": [AIMessage(content=f"Intent parsed: {intent}")],
    }


def dispatch_to_agent_node(state: OrchestrationState) -> Dict[str, Any]:
    """Dispatch task to the appropriate agent subgraph and capture result."""
    from backend.services.agent_registry import get_agent

    agent_name = state.get("next_agent", "vendor_management")
    intent = state.get("intent", {})
    agent = get_agent(agent_name)

    if not agent:
        return {
            "error": f"Agent '{agent_name}' not registered.",
            "retry_count": state.get("retry_count", 0) + 1,
        }

    try:
        payload = {
            "action": intent.get("action", ""),
            "session_id": state.get("session_id"),
            **intent.get("params", {}),
        }
        result = agent.execute(payload)
        current_results = dict(state.get("agent_results") or {})
        current_results[agent_name] = result
        return {
            "agent_results": current_results,
            "error": result.get("error"),
            "retry_count": 0,
        }
    except Exception as e:
        logger.exception("Agent '%s' execution failed", agent_name)
        return {
            "error": str(e),
            "retry_count": state.get("retry_count", 0) + 1,
        }


def retry_node(state: OrchestrationState) -> Dict[str, Any]:
    """Increment retry counter and log the retry attempt."""
    count = state.get("retry_count", 0)
    logger.warning("Retrying agent dispatch (attempt %d)", count + 1)
    return {
        "retry_count": count + 1,
        "error": None,  # clear error so dispatch retries cleanly
        "messages": [AIMessage(content=f"Retrying... attempt {count + 1}")],
    }


def assess_risk_node(state: OrchestrationState) -> Dict[str, Any]:
    """
    Derive risk level from agent results.
    In production: call a dedicated risk-scoring model.
    """
    results = state.get("agent_results") or {}
    risk_items = []
    score = 0.0

    for agent_name, result in results.items():
        if isinstance(result, dict):
            if result.get("requires_approval"):
                risk_items.append(f"{agent_name}: requires human approval")
                score = max(score, 0.8)
            if result.get("error"):
                risk_items.append(f"{agent_name}: returned error")
                score = max(score, 0.5)

    level = "high" if score >= 0.75 else ("medium" if score >= 0.40 else "none")
    return {
        "risk_score": score,
        "risk_level": level,
        "risk_items": risk_items,
        "requires_approval": bool(risk_items and score >= 0.75),
    }


def hitl_interrupt_node(state: OrchestrationState) -> Dict[str, Any]:
    """Raise NodeInterrupt to pause graph for human review."""
    try:
        from langgraph.errors import NodeInterrupt

        raise NodeInterrupt(
            "Human approval required.\n"
            f"Risk items: {state.get('risk_items', [])}\n"
            f"Session: {state.get('session_id')}"
        )
    except ImportError:
        return {"requires_approval": True}


def refine_output_node(state: OrchestrationState) -> Dict[str, Any]:
    """
    Iterative refinement node — runs multiple times in a loop
    until quality_score meets quality_threshold.

    Demonstrates the 'agent repetition / loop' pattern.
    """
    iteration = state.get("iteration", 0)
    results = state.get("agent_results") or {}

    # Simulate quality scoring (replace with real LLM judge)
    all_results = list(results.values())
    quality = 0.6 + (iteration * 0.15)  # improves with each iteration
    quality = min(quality, 1.0)

    return {
        "iteration": iteration + 1,
        "quality_score": quality,
        "messages": [
            AIMessage(content=f"Refinement pass {iteration + 1}: quality={quality:.2f}")
        ],
    }


def compile_response_node(state: OrchestrationState) -> Dict[str, Any]:
    """Aggregate all agent results into a single final response."""
    results = state.get("agent_results") or {}
    parts = []
    for agent_name, result in results.items():
        if isinstance(result, dict):
            msg = result.get("summary") or result.get("message") or ""
            if msg:
                parts.append(f"[{agent_name.replace('_', ' ').title()}]\n{msg}")

    response = "\n\n".join(parts) if parts else "Workflow completed."
    return {
        "final_response": response,
        "messages": [AIMessage(content=response)],
    }


def escalate_node(state: OrchestrationState) -> Dict[str, Any]:
    """Handle high-risk escalation (alert, log, notify)."""
    from memory.global_context import get_global_context

    ctx = get_global_context()
    ctx.log_decision(
        decision=f"HIGH RISK ESCALATION: {state.get('risk_items')}",
        agent="orchestrator",
        session_id=state.get("session_id"),
    )
    logger.critical("ESCALATION: %s", state.get("risk_items"))
    return {"messages": [AIMessage(content="⚠ Risk escalated to operations team.")]}


def error_response_node(state: OrchestrationState) -> Dict[str, Any]:
    """Build a user-facing error response when all retries are exhausted."""
    return {
        "final_response": f"Unable to complete request. Error: {state.get('error', 'Unknown error')}",
        "messages": [AIMessage(content="Request failed after retries.")],
    }


def human_rejected_node(state: OrchestrationState) -> Dict[str, Any]:
    """Handle explicit human rejection of a HITL action."""
    return {
        "final_response": "Action was declined by human oversight.",
        "messages": [AIMessage(content="Human review: action rejected.")],
    }


# ─── Graph Builder ─────────────────────────────────────────────────────────────


def build_orchestration_graph(
    use_checkpointer: bool = False,
    quality_threshold: float = 0.80,
) -> Any:
    """
    Build the top-level orchestration graph.

    Topology:
      START → parse_intent
            → dispatch_to_agent  ←─────────────┐
            ↓ (continue_or_retry)               │ retry loop
            → assess_risk                       │
            ↓ (route_by_risk)                   │
          ┌─→ hitl_interrupt  (high risk → HITL)│
          │       ↓ (hitl_gate)                 │
          │       ├─ needs_human → [PAUSE]       │
          │       ├─ rejected    → human_rejected│
          │       └─ auto_approve ──────────────┤
          └─→ escalate_node   (if risk=high + auto)     │
            → refine_output  ↺ loop until quality_threshold
            → compile_response
            → END
    """
    builder = StateGraph(OrchestrationState)

    # ── Register nodes ──────────────────────────────────────────────────────
    builder.add_node("parse_intent", parse_intent_node)
    builder.add_node("dispatch_to_agent", dispatch_to_agent_node)
    builder.add_node("retry", retry_node)
    builder.add_node("assess_risk", assess_risk_node)
    builder.add_node("hitl_interrupt", hitl_interrupt_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("refine_output", refine_output_node)
    builder.add_node("compile_response", compile_response_node)
    builder.add_node("error_response", error_response_node)
    builder.add_node("human_rejected", human_rejected_node)

    # ── Linear entry ────────────────────────────────────────────────────────
    builder.add_edge(START, "parse_intent")
    builder.add_edge("parse_intent", "dispatch_to_agent")

    # ── Retry loop after dispatch ────────────────────────────────────────────
    # continue_or_retry returns "retry" | "continue" | "abort"
    builder.add_conditional_edges(
        "dispatch_to_agent",
        lambda s: continue_or_retry(s, max_retries=3),
        {
            "continue": "assess_risk",
            "retry": "retry",
            "abort": "error_response",
        },
    )
    builder.add_edge("retry", "dispatch_to_agent")  # loop back

    # ── Risk routing after assessment ─────────────────────────────────────
    builder.add_conditional_edges(
        "assess_risk",
        route_by_risk,
        {
            "risk_high": "hitl_interrupt",
            "risk_medium": "refine_output",  # medium risk → refine first
            "risk_none": "refine_output",
        },
    )

    # ── HITL gate ─────────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "hitl_interrupt",
        hitl_gate,
        {
            "needs_human": "hitl_interrupt",  # graph pauses here (NodeInterrupt)
            "auto_approve": "escalate",  # log it but continue
            "rejected": "human_rejected",
        },
    )
    builder.add_edge("escalate", "refine_output")
    builder.add_edge("human_rejected", END)

    # ── Iterative refinement loop ─────────────────────────────────────────
    # should_loop returns "loop" | "done"
    builder.add_conditional_edges(
        "refine_output",
        lambda s: should_loop(s, max_iterations=3),
        {
            "loop": "refine_output",  # repeat the node
            "done": "compile_response",
        },
    )

    # ── Terminal edges ─────────────────────────────────────────────────────
    builder.add_edge("compile_response", END)
    builder.add_edge("error_response", END)

    # ── Compile ────────────────────────────────────────────────────────────
    checkpointer = MemorySaver() if use_checkpointer else None
    if checkpointer:
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_after=["hitl_interrupt"],
        )
    return builder.compile()
