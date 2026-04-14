"""
Global shared Pydantic schemas used across multiple agents.
"""

from .common import BaseResponse, PaginatedResponse, ErrorResponse, TimestampMixin
from .user_request import UserRequest, AgentTaskRequest
from .agent_io import AgentInput, AgentOutput
from .tool_io import ToolInput, ToolOutput
from .human_loop import HITLRequest, HITLDecision
from .memory import MemoryEntry, ContextUpdate

__all__ = [
    "BaseResponse", "PaginatedResponse", "ErrorResponse", "TimestampMixin",
    "UserRequest", "AgentTaskRequest",
    "AgentInput", "AgentOutput",
    "ToolInput", "ToolOutput",
    "HITLRequest", "HITLDecision",
    "MemoryEntry", "ContextUpdate",
]
