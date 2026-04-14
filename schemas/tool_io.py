"""Tool I/O schemas."""

from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ToolInput(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}


class ToolOutput(BaseModel):
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
