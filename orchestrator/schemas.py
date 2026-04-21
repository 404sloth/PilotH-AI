from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Task(BaseModel):
    """A single execution step in a multi-agent plan."""
    agent: str = Field(..., description="Target agent name")
    action: str = Field(..., description="Specific tool or action name")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the tool")
    reasoning: Optional[str] = Field(None, description="Why this step is necessary")
    dependency_index: Optional[int] = Field(None, description="Index of the task this task depends on")

class IntentResult(BaseModel):
    """Output of the advanced Task Planner."""
    plan: List[Task] = Field(..., description="Sequential or parallel execution steps")
    confidence: float = Field(..., ge=0, le=1.0)
    reasoning: str = Field(..., description="Overall strategic rationale for the plan")

class AgentOutput(BaseModel):
    """Standardized output model for all specialized agents."""
    action_performed: str
    llm_summary: str
    thought: Optional[str] = None  # Internal reasoning trace
    data: Dict[str, Any] = Field(default_factory=dict)
    suggestions: List[str] = Field(default_factory=list)
    requires_human_review: bool = False
    error: Optional[str] = None

class TraceEvent(BaseModel):
    """Real-time execution step emitted by the orchestrator."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = Field(..., description="agent | tool | reasoning | status")
    name: str = Field(..., description="Human readable name of the step")
    status: str = Field("running", description="running | completed | error")
    details: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class OrchestratorResponse(BaseModel):
    """Final payload sent to the client dashboard."""
    response: str = Field(..., description="Formatted markdown response")
    agent: str
    action: str
    thought: Optional[str] = None
    intent_reasoning: str
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    suggestions: List[str] = Field(default_factory=list)
    trace: List[TraceEvent] = Field(default_factory=list) # Full step history
