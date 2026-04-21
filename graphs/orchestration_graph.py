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

    # Planning
    intent: Dict[str, Any]  # The primary intent
    plan: List[Dict[str, Any]]  # Sequential list of agent tasks
    task_index: int  # Current task being executed
    
    # Execution
    agent_results: Dict[str, Any]  # name → result
    dispatched_agents: List[str]  # for history tracking
    retry_count: int
    iteration: int
    
    # Risk & Quality
    quality_score: float
    quality_threshold: float
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
    trace: List[Dict[str, Any]] # Cumulative trace for the UI


# ─── Nodes ────────────────────────────────────────────────────────────────────


def parse_intent_node(state: OrchestrationState) -> Dict[str, Any]:
    """Parse user message and determine initial execution plan."""
    from orchestrator.intent_parser import IntentParser
    from config.settings import Settings

    try:
        settings = Settings()
        result = IntentParser(settings).parse(
            state.get("user_message", ""),
            context=state.get("context", {}),
            conversation_history=state.get("messages", []),
        )
        plan = result.get("plan", [])
        intent_reasoning = result.get("reasoning", "No overhead reasoning provided.")
    except Exception as e:
        logger.warning("Strategic Planning failed: %s", e)
        plan = [{
            "agent": "vendor_management",
            "action": "full_assessment",
            "params": {"query": state.get("user_message")},
            "reasoning": "Fallback plan due to planner failure."
        }]
        intent_reasoning = "Fallback due to planning error."

    return {
        "intent": {"reasoning": intent_reasoning},
        "plan": plan,
        "task_index": 0,
        "retry_count": 0,
        "iteration": 0,
        "dispatched_agents": [],
        "agent_results": {},
        "messages": [AIMessage(content=f"Strategic plan finalized: {len(plan)} tasks identified.\nReasoning: {intent_reasoning}")],
    }


def dispatch_to_agent_node(state: OrchestrationState) -> Dict[str, Any]:
    """Execute the current task in the multi-step plan."""
    from backend.services.agent_registry import get_agent

    plan = state.get("plan", [])
    idx = state.get("task_index", 0)

    if idx >= len(plan):
        return {"error": "Execution index out of bounds for current plan."}

    task = plan[idx]
    agent_name = task["agent"]
    agent = get_agent(agent_name)

    if not agent:
        return {
            "error": f"Agent '{agent_name}' not registered in the ecosystem.",
            "retry_count": state.get("retry_count", 0) + 1,
        }

    try:
        # Build payload with parameters and cross-agent context
        payload = {
            "action": task.get("action", ""),
            "session_id": state.get("session_id"),
            **task.get("params", {}),
        }
        
        # AGENT-TO-AGENT: Share results from previous steps in the chain
        payload["context_history"] = state.get("agent_results", {})
        payload["step_reasoning"] = task.get("reasoning", "")

        logger.info("Dispatching task %d/%d to agent '%s'", idx+1, len(plan), agent_name)
        result = agent.execute(payload)
        
        current_results = dict(state.get("agent_results") or {})
        # Store result by index or agent name (index is safer for multi-call same agent)
        current_results[f"step_{idx}_{agent_name}"] = result
        
        dispatched = list(state.get("dispatched_agents") or [])
        dispatched.append(agent_name)

        return {
            "agent_results": current_results,
            "dispatched_agents": dispatched,
            "task_index": idx + 1,
            "error": result.get("error") if isinstance(result, dict) else None,
            "retry_count": 0,
        }
    except Exception as e:
        logger.exception("Task #%d execution failed for agent '%s'", idx, agent_name)
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
    """Aggregate all agent results into a single final strategic response."""
    results = state.get("agent_results") or {}
    parts = []
    
    # Sort results by step index to maintain logical flow in the response
    sorted_steps = sorted(results.items(), key=lambda x: x[0])

    for key, result in sorted_steps:
        if isinstance(result, dict):
            # Extract agent name from key (step_N_agentname)
            try:
                display_name = key.split("_", 2)[2].replace("_", " ").title()
            except IndexError:
                display_name = "Agent Step"

            msg = result.get("llm_summary") or result.get("summary") or result.get("message") or ""
            if msg:
                parts.append(f"## {display_name}\n{msg}")

    if not parts:
        response = "The requested workflow was completed, but no specific summaries were generated by the agents."
    else:
        response = "\n\n---\n\n".join(parts)

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

def route_tasks(state: OrchestrationState) -> str:
    """Decide if we should run more tasks, retry, or fail."""
    plan = state.get("plan", [])
    idx = state.get("task_index", 0)
    error = state.get("error")
    retry_count = state.get("retry_count", 0)
    
    if error:
        if retry_count < 3:
            return "retry"
        else:
            logger.error("Max retries exceeded for task index %d", idx)
            return "fail"
    
    if idx < len(plan):
        return "continue_task"
    
    return "done"


# ─── Graph Builder ─────────────────────────────────────────────────────────────


def build_orchestration_graph(
    use_checkpointer: bool = False,
    quality_threshold: float = 0.80,
) -> Any:
    """
    Build the top-level orchestration graph.
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

    # ── Workflow ────────────────────────────────────────────────────────────
    builder.add_edge(START, "parse_intent")
    builder.add_edge("parse_intent", "dispatch_to_agent")

    builder.add_conditional_edges(
        "dispatch_to_agent",
        route_tasks,
        {
            "continue_task": "dispatch_to_agent",
            "retry": "retry",
            "fail": "error_response",
            "done": "assess_risk",
        }
    )
    
    builder.add_edge("retry", "dispatch_to_agent")

    builder.add_conditional_edges(
        "assess_risk",
        route_by_risk,
        {
            "risk_high": "hitl_interrupt",
            "risk_medium": "refine_output",
            "risk_none": "refine_output",
        },
    )

    builder.add_conditional_edges(
        "hitl_interrupt",
        hitl_gate,
        {
            "needs_human": "hitl_interrupt",
            "auto_approve": "escalate",
            "rejected": "human_rejected",
        },
    )
    builder.add_edge("escalate", "refine_output")
    builder.add_edge("human_rejected", END)

    builder.add_conditional_edges(
        "refine_output",
        lambda s: should_loop(s, max_iterations=2),
        {
            "loop": "refine_output",
            "done": "compile_response",
        },
    )

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
