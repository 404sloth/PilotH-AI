"""
Task Decomposer — breaks a complex multi-part user request into ordered subtasks.

For simple, single-agent requests, returns a single-task list.
For complex requests (e.g. "schedule a meeting AND analyse the vendor"),
it uses LLM to extract independent sub-goals.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from config.settings import Settings

logger = logging.getLogger(__name__)


class TaskDecomposer:
    """
    Decomposes a user request into 1-N subtasks, each routable to an agent.
    """

    def __init__(self, config: Settings) -> None:
        self.config = config

    def decompose(
        self,
        message: str,
        context: Dict[str, Any],
        max_tasks: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Args:
            message:   Raw user message.
            context:   Session context dict.
            max_tasks: Maximum number of subtasks to extract.

        Returns:
            List of task dicts: [{agent, action, params, priority}]
        """
        try:
            return self._llm_decompose(message, context, max_tasks)
        except Exception as e:
            logger.warning("LLM decomposition failed (%s), returning single task.", e)
            from orchestrator.intent_parser import IntentParser
            intent = IntentParser(self.config).parse(message, context)
            return [{
                "agent":    intent["agent"],
                "action":   intent["action"],
                "params":   intent.get("params", {}),
                "priority": "medium",
            }]

    def _llm_decompose(
        self,
        message: str,
        context: Dict[str, Any],
        max_tasks: int,
    ) -> List[Dict[str, Any]]:
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage

        llm    = get_llm(temperature=0.0)
        prompt = f"""You are a task decomposition engine. Break the user request into up to {max_tasks} independent subtasks.

Available agents: vendor_management, meetings_communication

User request: "{message}"
Context: {json.dumps(context, default=str)[:400]}

Return ONLY valid JSON array:
[
  {{"agent": "<name>", "action": "<action>", "params": {{}}, "priority": "high|medium|low"}},
  ...
]
If only one task, return a single-element array."""

        resp   = llm.invoke([HumanMessage(content=prompt)])
        raw    = resp.content.strip().strip("```json").strip("```").strip()
        tasks  = json.loads(raw)
        if not isinstance(tasks, list):
            raise ValueError("LLM did not return a list")
        return tasks[:max_tasks]
