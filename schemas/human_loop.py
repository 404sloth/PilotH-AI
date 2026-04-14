"""Human-in-the-loop schemas."""
from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class HITLRequest(BaseModel):
    approval_id:  str
    agent:        str
    context:      str
    state:        Dict[str, Any] = Field(default_factory=dict)
    urgency:      str = "medium"


class HITLDecision(BaseModel):
    approval_id: str
    approved:    bool
    feedback:    Optional[str] = None
