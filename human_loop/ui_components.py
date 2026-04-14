"""
UI Components — JSON payloads that the frontend renders as interactive HITL cards.

These functions build structured dicts that the WebSocket manager broadcasts
to connected clients. The frontend (React/Vue/plain JS) interprets the
`component_type` and renders the correct UI widget.

No HTML is generated here — only clean, typed JSON structures.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


# ── Component builders ────────────────────────────────────────────────────────

def approval_card(
    task_id:    str,
    agent_name: str,
    action:     str,
    context:    str,
    risk_score: float,
    risk_items: List[str],
    expires_at: float,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Approval request card — rendered as a modal or inline card with
    Approve / Reject buttons and optional comment field.

    Frontend action: POST /hitl/decision {task_id, approved, feedback}
    """
    return {
        "component_type":  "approval_card",
        "task_id":         task_id,
        "agent_name":      agent_name,
        "action":          action,
        "context":         context,
        "risk_score":      round(risk_score, 3),
        "risk_score_label": _risk_label(risk_score),
        "risk_color":      _risk_color(risk_score),
        "risk_items":      risk_items,
        "session_id":      session_id,
        "expires_in_secs": max(0, int(expires_at - time.time())),
        "actions": [
            {"label": "✅ Approve", "value": "approve", "variant": "success"},
            {"label": "❌ Reject",  "value": "reject",  "variant": "danger"},
        ],
        "has_feedback_field": True,
        "feedback_placeholder": "Optional: explain your decision…",
    }


def status_card(
    task_id:  str,
    status:   str,
    message:  str,
    feedback: str = "",
) -> Dict[str, Any]:
    """
    Status update card — notifies connected clients of a decision outcome.
    """
    return {
        "component_type": "status_card",
        "task_id":        task_id,
        "status":         status,
        "message":        message,
        "feedback":       feedback,
        "timestamp":      time.time(),
        "icon": {
            "approved":  "✅",
            "rejected":  "❌",
            "expired":   "⏰",
            "cancelled": "🚫",
        }.get(status, "ℹ️"),
    }


def agent_progress_card(
    session_id: str,
    agent_name: str,
    action:     str,
    step:       str,
    total_steps: int,
    current_step: int,
    message:    str,
    status:     str = "running",    # running | done | error
) -> Dict[str, Any]:
    """
    Live progress card — shown during long-running agent workflows.
    Frontend can render as a progress bar with step labels.
    """
    return {
        "component_type":  "agent_progress",
        "session_id":      session_id,
        "agent_name":      agent_name,
        "action":          action,
        "step":            step,
        "current_step":    current_step,
        "total_steps":     total_steps,
        "progress_pct":    round((current_step / max(total_steps, 1)) * 100, 1),
        "message":         message,
        "status":          status,
        "timestamp":       time.time(),
    }


def risk_banner(
    risk_level: str,
    risk_score: float,
    risk_items: List[str],
    agent_name: str,
) -> Dict[str, Any]:
    """
    Risk assessment banner — displayed before an approval card
    to give the human reviewer context on what triggered HITL.
    """
    return {
        "component_type": "risk_banner",
        "agent_name":     agent_name,
        "risk_level":     risk_level,
        "risk_score":     round(risk_score, 3),
        "risk_color":     _risk_color(risk_score),
        "risk_label":     _risk_label(risk_score),
        "risk_items":     risk_items,
        "timestamp":      time.time(),
    }


def feedback_form(
    session_id: str,
    agent_name: str,
    action:     str,
    task_id:    Optional[str] = None,
) -> Dict[str, Any]:
    """
    Post-interaction feedback form — shown after an agent completes a workflow.
    Frontend renders as a star rating + optional comment.

    Frontend action: POST /feedback {session_id, agent_name, rating, comment, categories}
    """
    return {
        "component_type":   "feedback_form",
        "session_id":       session_id,
        "agent_name":       agent_name,
        "action":           action,
        "task_id":          task_id,
        "rating_max":       5,
        "category_options": ["accuracy", "speed", "clarity", "completeness", "relevance"],
        "has_comment_field": True,
        "comment_placeholder": "Any additional feedback?",
        "timestamp":        time.time(),
    }


def error_card(
    session_id: str,
    agent_name: str,
    error:      str,
    recoverable: bool = True,
) -> Dict[str, Any]:
    """
    Error notification card — shown when an agent fails fatally.
    """
    return {
        "component_type": "error_card",
        "session_id":     session_id,
        "agent_name":     agent_name,
        "error":          error,
        "recoverable":    recoverable,
        "suggested_action": "Retry" if recoverable else "Contact support",
        "timestamp":      time.time(),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _risk_label(score: float) -> str:
    if score >= 0.9: return "Critical"
    if score >= 0.75: return "High"
    if score >= 0.5:  return "Medium"
    return "Low"


def _risk_color(score: float) -> str:
    if score >= 0.9:  return "#dc2626"   # red-600
    if score >= 0.75: return "#ea580c"   # orange-600
    if score >= 0.5:  return "#ca8a04"   # yellow-600
    return "#16a34a"                     # green-600
