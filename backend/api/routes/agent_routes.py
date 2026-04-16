"""
Generic agent execution router.
POST /agents/{agent_name}/run  — execute any registered agent with natural language prompts.
POST /agents/run — automatically route natural language prompts to appropriate agents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class AgentRunRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}
    agent_hint: str = ""  # Optional hint about which agent to use
    conversation_id: str = ""  # Optional conversation ID for continuity


class AgentRunResponse(BaseModel):
    agent: str
    result: Dict[str, Any]
    task_id: str = None
    conversation_id: str = None
    session_id: str = None


class ConversationInfo(BaseModel):
    id: str
    created_at: str
    updated_at: str
    message_count: int
    last_message: str
    metadata: Dict[str, Any] = {}


class CreateThreadResponse(BaseModel):
    id: str
    created_at: str
    updated_at: str
    message_count: int
    last_message: str
    metadata: Dict[str, Any] = {}


class HistoryMessage(BaseModel):
    role: str
    message: str
    timestamp: str
    agent_type: Optional[str] = None
    action: Optional[str] = None
    metadata: Dict[str, Any] = {}


@router.get("", summary="List registered agents")
def list_agents():
    """Return all registered agent names and their available tools."""
    from backend.services.agent_registry import get_tool_registry

    registry = get_tool_registry()
    return {"agents": registry.list_all_tools()}


@router.post(
    "/run", response_model=AgentRunResponse, summary="Auto-route natural language prompts"
)
def run_auto_agent(request: AgentRunRequest):
    """
    Automatically route natural language prompts to the appropriate agent.
    
    The orchestrator will parse the intent from the prompt and route to the best matching agent.
    """
    from orchestrator.controller import OrchestratorController
    from backend.api.dependencies import get_settings

    controller = OrchestratorController(get_settings())
    
    try:
        # Prepare context with conversation_id
        context = request.context.copy()
        if request.conversation_id:
            context["conversation_id"] = request.conversation_id

        result = controller.handle(
            message=request.prompt,
            context=context,
            agent_hint=request.agent_hint if request.agent_hint else None,
        )

        return AgentRunResponse(
            agent=result.get("metadata", {}).get("agent", "unknown"),
            result={
                "response": result.get("response", ""),
                "data": result.get("data", {}),
                "metadata": result.get("metadata", {})
            },
            conversation_id=result.get("conversation_id"),
            session_id=result.get("session_id"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{agent_name}/run", response_model=AgentRunResponse, summary="Run specific agent with natural language"
)
def run_agent(agent_name: str, request: AgentRunRequest):
    """
    Execute a named agent with a natural language prompt.
    
    The orchestrator will parse the intent, route to appropriate tools, and return formatted results.
    """
    from orchestrator.controller import OrchestratorController
    from backend.api.dependencies import get_settings

    controller = OrchestratorController(get_settings())
    
    try:
        # Prepare context with conversation_id
        context = request.context.copy()
        if request.conversation_id:
            context["conversation_id"] = request.conversation_id

        result = controller.handle(
            message=request.prompt,
            context=context,
            agent_hint=agent_name,  # Use the specified agent as hint
        )

        return AgentRunResponse(
            agent=agent_name,
            result={
                "response": result.get("response", ""),
                "data": result.get("data", {}),
                "metadata": result.get("metadata", {})
            },
            conversation_id=result.get("conversation_id"),
            session_id=result.get("session_id"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations", summary="List conversations")
def list_conversations(limit: int = 50) -> List[ConversationInfo]:
    """List recent conversations for frontend display."""
    from llm.model_factory import ConversationManager

    conversations = ConversationManager.list_conversations(limit=limit)
    return [ConversationInfo(**conv) for conv in conversations]


@router.get("/conversations/{conversation_id}", summary="Get conversation")
def get_conversation(conversation_id: str) -> Dict[str, Any]:
    """Get a specific conversation with all messages."""
    from llm.model_factory import ConversationManager

    conversation = ConversationManager.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation.to_dict()


@router.delete("/conversations/{conversation_id}", summary="Delete conversation")
def delete_conversation(conversation_id: str) -> Dict[str, str]:
    """Delete a conversation."""
    from llm.model_factory import ConversationManager

    success = ConversationManager.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"status": "deleted", "conversation_id": conversation_id}


@router.post("/threads", response_model=CreateThreadResponse, summary="Create thread")
def create_thread() -> CreateThreadResponse:
    """Create an empty conversation thread for chat clients."""
    from llm.model_factory import Conversation

    conversation = Conversation.create_new()
    return CreateThreadResponse(
        id=conversation.id,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        message_count=0,
        last_message="",
        metadata=conversation.metadata or {},
    )


@router.get("/history", response_model=List[HistoryMessage], summary="Get thread history")
def get_history(thread_id: str) -> List[HistoryMessage]:
    """Return flattened history for a conversation/thread."""
    from llm.model_factory import ConversationManager

    conversation = ConversationManager.get_conversation(thread_id)
    if not conversation:
        return []

    return [
        HistoryMessage(
            role=msg.role,
            message=msg.content,
            timestamp=msg.timestamp.isoformat(),
            agent_type=(msg.metadata or {}).get("agent"),
            action=(msg.metadata or {}).get("action"),
            metadata=msg.metadata or {},
        )
        for msg in conversation.messages
    ]


@router.get("/alerts", summary="List UI alerts")
def list_alerts() -> List[Dict[str, Any]]:
    """Return lightweight alerts for the frontend dashboard."""
    from human_loop.manager import get_hitl_manager

    pending_tasks = get_hitl_manager().get_pending()
    alerts = []
    for idx, task in enumerate(pending_tasks, start=1):
        alerts.append(
            {
                "id": idx,
                "title": f"Approval pending for {task.get('agent_name', 'agent')}",
                "description": task.get("context", "Human review is required."),
                "severity": "high" if task.get("risk_score", 0.0) >= 0.8 else "medium",
                "source": task.get("action", "human_loop"),
                "resolved": False,
            }
        )
    return alerts
