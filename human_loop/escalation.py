"""
Escalation Engine — handles high-risk or unresolved HITL tasks.

Escalation triggers:
  1. Task expires without human decision
  2. Risk score exceeds critical threshold
  3. Multiple retries exhausted by an agent
  4. Manual escalation by an operator

Escalation channels (in order of severity):
  LOW    → log to global_context decision log
  MEDIUM → Slack alert to #ops-alerts channel
  HIGH   → Slack + email draft to escalation contact
  CRITICAL → All of the above + auto-reject the pending task
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EscalationLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class EscalationResult:
    def __init__(self, level: EscalationLevel, channels: List[str], message: str):
        self.level    = level
        self.channels = channels
        self.message  = message
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level":     self.level,
            "channels":  self.channels,
            "message":   self.message,
            "timestamp": self.timestamp,
        }


class EscalationEngine:
    """
    Determines escalation level and fires appropriate notifications.
    """

    def __init__(
        self,
        slack_channel: str = "#ops-alerts",
        escalation_email: str = "ops@company.com",
        critical_threshold: float = 0.90,
        high_threshold: float = 0.75,
    ):
        self.slack_channel       = slack_channel
        self.escalation_email    = escalation_email
        self.critical_threshold  = critical_threshold
        self.high_threshold      = high_threshold

    def escalate(
        self,
        task_id:    str,
        agent_name: str,
        action:     str,
        risk_score: float,
        risk_items: List[str],
        context:    str,
        session_id: Optional[str] = None,
        reason:     str = "auto",
    ) -> EscalationResult:
        """
        Determine escalation level and fire notifications.

        Args:
            task_id:    HITL task identifier (or action group ID)
            agent_name: Which agent raised the issue
            risk_score: Computed risk score (0.0–1.0)
            risk_items: List of human-readable risk descriptions
            context:    Short description of what was attempted
            session_id: Session context
            reason:     "auto" | "expired" | "retry_limit" | "manual"

        Returns:
            EscalationResult
        """
        level = self._determine_level(risk_score, reason)
        msg   = self._build_message(task_id, agent_name, action, risk_score, risk_items, context, reason)
        channels = self._fire(level, msg, agent_name, task_id, session_id)
        self._log_to_memory(level, msg, agent_name, session_id)

        result = EscalationResult(level=level, channels=channels, message=msg)
        logger.warning("[ESCALATION] level=%s task=%s agent=%s", level.value, task_id, agent_name)
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _determine_level(self, risk_score: float, reason: str) -> EscalationLevel:
        if reason in ("retry_limit", "expired") or risk_score >= self.critical_threshold:
            return EscalationLevel.CRITICAL
        if risk_score >= self.high_threshold:
            return EscalationLevel.HIGH
        if risk_score >= 0.5:
            return EscalationLevel.MEDIUM
        return EscalationLevel.LOW

    def _build_message(
        self,
        task_id:    str,
        agent_name: str,
        action:     str,
        risk_score: float,
        risk_items: List[str],
        context:    str,
        reason:     str,
    ) -> str:
        items_str = "\n  • ".join(risk_items) if risk_items else "None"
        return (
            f"🚨 PilotH Escalation\n"
            f"Task:   {task_id}\n"
            f"Agent:  {agent_name} / {action}\n"
            f"Reason: {reason}\n"
            f"Risk:   {risk_score:.0%}\n"
            f"Items:\n  • {items_str}\n"
            f"Context: {context}"
        )

    def _fire(
        self,
        level:      EscalationLevel,
        message:    str,
        agent_name: str,
        task_id:    str,
        session_id: Optional[str],
    ) -> List[str]:
        channels: List[str] = []

        # Slack (medium+)
        if level in (EscalationLevel.MEDIUM, EscalationLevel.HIGH, EscalationLevel.CRITICAL):
            try:
                from agents.communication.tools.slack_tool import SlackNotifierTool, SlackInput
                SlackNotifierTool().execute(SlackInput(channel=self.slack_channel, message=message))
                channels.append(f"slack:{self.slack_channel}")
            except Exception as e:
                logger.warning("Slack escalation failed: %s", e)

        # Email draft (high+)
        if level in (EscalationLevel.HIGH, EscalationLevel.CRITICAL):
            try:
                from agents.communication.tools.email_draft_tool import EmailDraftTool, EmailDraftInput
                EmailDraftTool().execute(EmailDraftInput(
                    email_type="followup",
                    recipients=[self.escalation_email],
                    subject=f"[PilotH ESCALATION] {agent_name}/{task_id}",
                    context=message,
                ))
                channels.append(f"email:{self.escalation_email}")
            except Exception as e:
                logger.warning("Email escalation failed: %s", e)

        return channels

    def _log_to_memory(
        self,
        level:      EscalationLevel,
        message:    str,
        agent:      str,
        session_id: Optional[str],
    ) -> None:
        try:
            from memory.global_context import get_global_context
            ctx = get_global_context()
            ctx.log_decision(
                decision=f"ESCALATION [{level.value.upper()}]: {message[:200]}",
                agent=agent,
                session_id=session_id,
                metadata={"level": level.value},
            )
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[EscalationEngine] = None


def get_escalation_engine() -> EscalationEngine:
    global _engine
    if _engine is None:
        _engine = EscalationEngine()
    return _engine
