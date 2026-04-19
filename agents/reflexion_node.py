"""
Reflexion Node.

Evaluates failure contexts, prompts LLM to generate an alternative plan or 
recognize impossible constraints, and saves learnings to memory.
"""

from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from memory.reflection_store import save_reflection

class ReflexionOutput(BaseModel):
    root_cause: str = Field(..., description="Why the workflow or tool failed.")
    improved_plan: str = Field(..., description="Actionable alternative step to take.")
    should_retry: bool = Field(..., description="Whether to retry execution or abort gracefully.")

from langchain_core.runnables import RunnableConfig

def reflexion_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Called when an agent state has an error property or requires human intervention 
    due to unexpected tool failures. Generates learning reflection.
    """
    error = state.get("error")
    action = state.get("action", "unknown_action")
    
    if not error:
        return state
        
    from llm.model_factory import get_llm
    llm = get_llm(temperature=0.2).with_structured_output(ReflexionOutput)
    
    prompt = f"""
    You are evaluating a failed execution of an AI agent workflow.
    
    Attempted Action: {action}
    Failure Context / Error: {error}
    
    Your task:
    1. Identify the root cause of the failure.
    2. Propose an improved plan to safely resolve the issue (e.g. relax constraints, notify user).
    3. Determine if the system should retry immediately or fail gracefully to avoid infinite loops.
    """
    
    try:
        response: ReflexionOutput = llm.invoke([
            SystemMessage(content="You are the system's Reflexion module. Learn from failure."),
            HumanMessage(content=prompt)
        ], config=config)
        
        # Save to memory
        save_reflection(
            agent_name=state.get("agent_name", "generic_agent"),
            task=action,
            failure_context=error,
            improved_plan=response.improved_plan
        )
        
        state["reflection"] = response.model_dump()
        
        if response.should_retry:
            state["error"] = None # Clear error to allow retry 
            # In a real workflow we would set `requires_human_review = False` but it depends on the graph structure.
        
    except Exception as e:
        # Failsafe if reflexion LLM fails
        pass
        
    return state
