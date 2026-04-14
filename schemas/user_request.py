"""User request schemas."""
from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class UserRequest(BaseModel):
    session_id:  str              = Field(..., description="Unique session identifier")
    message:     str              = Field(..., description="Natural language user message")
    context:     Dict[str, Any]   = Field(default_factory=dict)
    user_id:     Optional[str]    = None


class AgentTaskRequest(BaseModel):
    agent_name:  str
    action:      str
    input_data:  Dict[str, Any]   = Field(default_factory=dict)
    session_id:  Optional[str]    = None
    priority:    str              = "medium"  # low | medium | high | critical
