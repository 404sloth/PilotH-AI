"""Memory schemas."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class MemoryEntry(BaseModel):
    key:         str
    value:       Any
    agent:       Optional[str] = None
    session_id:  Optional[str] = None
    ttl_seconds: Optional[float] = None


class ContextUpdate(BaseModel):
    session_id: str
    key:        str
    value:      Any
