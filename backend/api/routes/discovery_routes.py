"""
Routes for Agent-to-Agent Service Discovery.

Exposes AgentCards dynamically so external agents or internal orchestrators
can dynamically discover capabilities and JSON schemas at runtime.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict

from agents.agent_card import AgentCard, AgentCapability
from backend.services.agent_registry import _agents

router = APIRouter()

@router.get("/discovery", response_model=Dict[str, List[AgentCard]])
async def get_agent_discovery():
    """
    Returns the AgentCards for all registered agents.
    Provides schema definitions for A2A calling protocols.
    """
    cards = []
    
    for agent_name, agent_instance in _agents.items():
        # Dynamically build capabilities based on tools or known actions
        capabilities = []
        for tool in agent_instance.tools:
            schema = tool.args_schema.schema() if tool.args_schema else {}
            capabilities.append(AgentCapability(
                name=tool.name,
                description=tool.description,
                input_schema=schema,
                output_schema=None  # We typically extract this via typing if needed
            ))
            
        card = AgentCard(
            id=agent_name,
            name=agent_name.replace("_", " ").title(),
            description=agent_instance.__class__.__doc__ or f"{agent_name} logic",
            endpoint=f"/api/v1/agents/{agent_name}/execute",
            auth_required=True,
            capabilities=capabilities,
            metadata={"version": "1.0", "langgraph_enabled": True}
        )
        cards.append(card)
        
    return {"agents": cards}
