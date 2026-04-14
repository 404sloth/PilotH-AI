"""Human-in-the-Loop package."""

from .manager    import HITLManager, ApprovalTask, get_hitl_manager
from .escalation import EscalationEngine, EscalationLevel, get_escalation_engine
from .feedback   import record_feedback, get_feedback_stats
from .approval   import (
    create_hitl_table, persist_approval_task, update_approval_status,
    load_approval_task, load_pending_approvals, get_approval_history,
)
from .ui_components import (
    approval_card, status_card, agent_progress_card,
    risk_banner, feedback_form, error_card,
)

__all__ = [
    "HITLManager", "ApprovalTask", "get_hitl_manager",
    "EscalationEngine", "EscalationLevel", "get_escalation_engine",
    "record_feedback", "get_feedback_stats",
    "create_hitl_table", "persist_approval_task", "update_approval_status",
    "load_approval_task", "load_pending_approvals", "get_approval_history",
    "approval_card", "status_card", "agent_progress_card",
    "risk_banner", "feedback_form", "error_card",
]
