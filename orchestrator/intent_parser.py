"""
Intent Parser — maps user natural language to agent + action + params.
Uses LLM with structured output; falls back to keyword routing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from config.settings import Settings

logger = logging.getLogger(__name__)

# Keyword-based fallback routing table
_ROUTING_TABLE = {
    # Vendor management
    "vendor": ("vendor_management", "full_assessment"),
    "supplier": ("vendor_management", "full_assessment"),
    "contract": ("vendor_management", "summarize_contract"),
    "sla": ("vendor_management", "monitor_sla"),
    "milestone": ("vendor_management", "track_milestones"),
    "best vendor": ("vendor_management", "find_best"),
    # Meetings
    "schedule": ("meetings_communication", "schedule"),
    "meeting": ("meetings_communication", "schedule"),
    "agenda": ("meetings_communication", "brief"),
    "brief": ("meetings_communication", "brief"),
    "summarize": ("meetings_communication", "summarize"),
    "summary": ("meetings_communication", "summarize"),
    "follow-up": ("meetings_communication", "summarize"),
    # Default
}


class IntentParser:
    def __init__(self, config: Settings) -> None:
        self.config = config

    def parse(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Try LLM parsing first; fall back to keyword routing."""
        try:
            return self._llm_parse(message, context)
        except Exception as e:
            logger.warning("LLM intent parse failed (%s), using keyword fallback.", e)
            return self._keyword_parse(message)

    def _llm_parse(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage

        llm = get_llm(temperature=0.0)
        prompt = f"""Map this user request to a structured intent. Return ONLY valid JSON.

Available agents and actions:
- vendor_management: find_best, full_assessment, monitor_sla, track_milestones, summarize_contract
- meetings_communication: schedule, summarize, brief

User message: "{message}"
Context: {json.dumps(context, default=str)[:500]}

Return JSON: {{"agent": "<name>", "action": "<action>", "params": {{...}}}}"""

        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip().strip("```json").strip("```").strip()
        parsed = json.loads(content)
        return {
            "agent": parsed.get("agent", "vendor_management"),
            "action": parsed.get("action", "full_assessment"),
            "params": parsed.get("params", {}),
        }

    def _keyword_parse(self, message: str) -> Dict[str, Any]:
        lower = message.lower()
        for keyword, (agent, action) in sorted(
            _ROUTING_TABLE.items(), key=lambda x: -len(x[0])
        ):
            if keyword in lower:
                return {"agent": agent, "action": action, "params": {}}
        return {"agent": "vendor_management", "action": "full_assessment", "params": {}}
