"""Agent I/O schemas."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    agent_name:  str
    action:      str
    payload:     Dict[str, Any]   = Field(default_factory=dict)
    session_id:  Optional[str]    = None


class AgentOutput(BaseModel):
    agent_name:       str
    action:           str
    status:           str           = "success"   # success | error | pending_human
    result:           Dict[str, Any] = Field(default_factory=dict)
    requires_human:   bool          = False
    error:            Optional[str] = None
    token_usage:      Optional[Dict[str, Any]] = None
