"""
Workflow Engine — executes multi-step, multi-agent workflows
with support for sequential, parallel, and conditional execution.

Delegates to the LangGraph orchestration graph for complex flows.
For simple single-agent requests, calls the agent directly.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from config.settings import Settings

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Higher-level abstraction above the orchestration graph.
    Manages session context, task sequencing, and result aggregation.
    """

    def __init__(self, config: Settings) -> None:
        self.config = config

    def run(
        self,
        tasks: List[Dict[str, Any]],
        session_id: str,
        mode: str = "sequential",
    ) -> Dict[str, Any]:
        """
        Execute a list of agent tasks.

        Args:
            tasks:      [{"agent": str, "action": str, "params": dict, "priority": str}]
            session_id: Current session identifier.
            mode:       "sequential" | "parallel" | "graph"

        Returns:
            Aggregated results dict.
        """
        if mode == "graph":
            return self._run_via_graph(tasks, session_id)
        if mode == "parallel":
            return self._run_parallel(tasks, session_id)
        return self._run_sequential(tasks, session_id)

    # ─── Sequential ─────────────────────────────────────────────────────────

    def _run_sequential(self, tasks: List[Dict], session_id: str) -> Dict[str, Any]:
        """Run tasks one after another, passing context forward."""
        from orchestrator.agent_router import AgentRouter
        router  = AgentRouter()
        results = {}
        carry_context: Dict[str, Any] = {}

        for task in tasks:
            agent  = task["agent"]
            action = task["action"]
            params = {**task.get("params", {}), **carry_context}
            try:
                result = router.route(agent, action, params, session_id)
                results[f"{agent}:{action}"] = result
                # carry forward key fields for next task
                if isinstance(result, dict):
                    carry_context.update({
                        k: v for k, v in result.items()
                        if k in ("meeting_id", "vendor_id", "summary", "calendar_link")
                    })
            except Exception as e:
                logger.error("Task %s/%s failed: %s", agent, action, e)
                results[f"{agent}:{action}"] = {"error": str(e)}

        return {"mode": "sequential", "session_id": session_id, "results": results}

    # ─── Parallel ────────────────────────────────────────────────────────────

    def _run_parallel(self, tasks: List[Dict], session_id: str) -> Dict[str, Any]:
        """Run tasks concurrently using a thread pool."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from orchestrator.agent_router import AgentRouter
        router  = AgentRouter()
        results = {}

        def _run_one(task: Dict) -> tuple:
            key = f"{task['agent']}:{task['action']}"
            try:
                res = router.route(task["agent"], task["action"], task.get("params", {}), session_id)
                return key, res
            except Exception as e:
                return key, {"error": str(e)}

        with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
            futures = {pool.submit(_run_one, t): t for t in tasks}
            for future in as_completed(futures):
                key, res = future.result()
                results[key] = res

        return {"mode": "parallel", "session_id": session_id, "results": results}

    # ─── Graph ───────────────────────────────────────────────────────────────

    def _run_via_graph(self, tasks: List[Dict], session_id: str) -> Dict[str, Any]:
        """Run through the top-level orchestration graph."""
        from graphs.orchestration_graph import build_orchestration_graph
        graph = build_orchestration_graph()
        first = tasks[0] if tasks else {}
        initial_state = {
            "session_id":      session_id,
            "user_message":    first.get("action", ""),
            "context":         first.get("params", {}),
            "intent":          {"agent": first.get("agent",""), "action": first.get("action",""), "params": first.get("params",{})},
            "next_agent":      first.get("agent", "vendor_management"),
            "messages":        [],
            "retry_count":     0,
            "iteration":       0,
            "quality_score":   0.0,
            "quality_threshold": 0.8,
            "risk_score":      0.0,
            "agent_results":   {},
            "requires_approval": False,
            "approved":        False,
            "human_rejected":  False,
        }
        result = graph.invoke(initial_state)
        return {"mode": "graph", "session_id": session_id, "final_response": result.get("final_response"), "results": result.get("agent_results", {})}
