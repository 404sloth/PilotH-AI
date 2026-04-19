"""
Agent Card & A2A Protocol.

Defines standard schemas for Agent-to-Agent (A2A) communication, including
identity, capabilities, expected input/output schemas, and endpoint bindings.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AgentCapability(BaseModel):
    name: str = Field(..., description="Name of the capability or standard action")
    description: str = Field(..., description="Human-readable description of what it does")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema for inputs")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema for outputs")


class AgentCard(BaseModel):
    """
    Standardised identity card for any agent in the PilotH-AI platform.
    Served via HTTP for service discovery.
    """
    id: str = Field(..., description="Unique slug for the agent (e.g. 'vendor_management')")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="High-level description of agent's domain")
    endpoint: str = Field(..., description="REST or RPC endpoint URL pattern. e.g. /api/v1/agents/{id}/execute")
    auth_required: bool = Field(True, description="Whether this agent requires a valid JWT or Token to invoke")
    capabilities: List[AgentCapability] = Field(default_factory=list, description="Available actions and their schemas")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional properties (version, author, latencies)")
