"""
Fallback Handler — graceful degradation when agents fail or are unavailable.

Strategies (in order):
  1. Retry with exponential backoff
  2. Route to a simpler alternative agent/action
  3. Return a structured error with guidance
  4. Notify via Slack (if configured)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds


class FallbackHandler:
    """
    Called by OrchestratorController when an agent returns an error
    or raises an unhandled exception.
    """

    def handle(
        self,
        error: Exception,
        agent_name: str,
        action: str,
        payload: Dict[str, Any],
        attempt: int = 1,
    ) -> Dict[str, Any]:
        """
        Determine fallback strategy based on error type and attempt count.

        Returns:
            Dict with keys: status, message, retry_recommended, fallback_agent
        """
        logger.warning(
            "[FallbackHandler] Agent='%s' action='%s' attempt=%d error=%s",
            agent_name,
            action,
            attempt,
            error,
        )

        # Strategy 1: retry (first 2 attempts)
        if attempt <= 2:
            wait = _BACKOFF_BASE * (2 ** (attempt - 1))
            logger.info("Backoff %.1fs before retry %d", wait, attempt + 1)
            time.sleep(wait)
            return {
                "status": "retry",
                "retry_recommended": True,
                "message": f"Transient error — retrying (attempt {attempt + 1}).",
                "fallback_agent": None,
            }

        # Strategy 2: rule-based fallback to simpler action
        fallback = self._get_fallback_action(agent_name, action)
        if fallback:
            logger.info("Falling back to %s", fallback)
            return {
                "status": "fallback",
                "retry_recommended": False,
                "message": f"Primary action failed; using fallback: {fallback}.",
                "fallback_agent": fallback,
            }

        # Strategy 3: graceful error response
        self._notify_ops(agent_name, action, error)
        return {
            "status": "failed",
            "retry_recommended": False,
            "message": f"Agent '{agent_name}' is unavailable. Please try again later.",
            "fallback_agent": None,
            "error": str(error),
        }

    def _get_fallback_action(self, agent_name: str, action: str) -> Optional[str]:
        """Map failed agent/action to a simpler alternative."""
        _fallback_map: Dict[str, str] = {
            "meetings_communication:schedule": "meetings_communication:brief",
            "vendor_management:full_assessment": "vendor_management:find_best",
        }
        return _fallback_map.get(f"{agent_name}:{action}")

    def _notify_ops(self, agent_name: str, action: str, error: Exception) -> None:
        """Send a Slack alert to ops channel (mock)."""
        try:
            from agents.communication.tools.slack_tool import (
                SlackNotifierTool,
                SlackInput,
            )

            SlackNotifierTool().execute(
                SlackInput(
                    channel="#ops-alerts",
                    message=f":red_circle: Agent `{agent_name}` ({action}) failed after retries: `{error}`",
                )
            )
        except Exception:
            pass  # never let the fallback itself raise
