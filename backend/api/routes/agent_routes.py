"""
Generic agent execution router.
POST /agents/{agent_name}/run  — execute any registered agent.
"""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class AgentRunResponse(BaseModel):
    agent: str
    result: Dict[str, Any]
    task_id: str = None


@router.get("", summary="List registered agents")
def list_agents():
    """Return all registered agent names and their available tools."""
    from backend.services.agent_registry import get_tool_registry

    registry = get_tool_registry()
    return {"agents": registry.list_all_tools()}


@router.post(
    "/{agent_name}/run", response_model=AgentRunResponse, summary="Run an agent"
)
def run_agent(agent_name: str, body: Dict[str, Any]):
    """
    Execute a named agent with the provided input payload.
    
    Accepts two formats:
    1. Nested (recommended): {"input": {"action": "find_best", "service_tags": ["cloud"], ...}}
    2. Flat (backward compat): {"action": "find_best", "service_tags": ["cloud"], ...}
    """
    from backend.services.agent_registry import get_agent

    agent = get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")

    try:
        # Auto-detect format: if "input" key exists, use it; otherwise treat entire body as input
        input_data = body.get("input") if "input" in body else body
        result = agent.execute(input_data)
        return AgentRunResponse(agent=agent_name, result=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
