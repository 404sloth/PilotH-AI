"""
Base agent class providing common functionality for all specialized agents.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, ValidationError
from langgraph.graph import StateGraph
from langchain_core.tools import BaseTool

from human_loop.manager import HITLManager
from llm.model_factory import ModelFactory
from config.settings import Settings


class AgentInputError(Exception):
    """Raised when input validation fails."""

    pass


class AgentOutputError(Exception):
    """Raised when output validation fails."""

    pass


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.

    Subclasses must define:
        - name: unique identifier string
        - get_subgraph(): returns compiled LangGraph StateGraph
        - (optional) input_schema and output_schema Pydantic models
    """

    def __init__(
        self,
        config: Settings,
        tool_registry: Any = None,  # Will be ToolRegistry instance
        hitl_manager: Optional[HITLManager] = None,
    ):
        self.config = config
        self.tool_registry = tool_registry
        self.hitl = hitl_manager or HITLManager(config.hitl_threshold)

        # Initialize LLM with tools bound if tools are provided
        self.llm = ModelFactory.get_model(config)
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent."""
        pass

    @property
    def tools(self) -> List[BaseTool]:
        """Return list of tools available to this agent."""
        if self.tool_registry:
            return self.tool_registry.get_tools_for_agent(self.name)
        return []

    @property
    def input_schema(self) -> Optional[Type[BaseModel]]:
        """Pydantic model for validating input. Override in subclass."""
        return None

    @property
    def output_schema(self) -> Optional[Type[BaseModel]]:
        """Pydantic model for validating output. Override in subclass."""
        return None

    def validate_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input data against the agent's input schema."""
        if self.input_schema is None:
            return data
        try:
            validated = self.input_schema(**data)
            return validated.model_dump()
        except ValidationError as e:
            raise AgentInputError(f"Invalid input for agent '{self.name}': {e}")

    def validate_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate output data against the agent's output schema."""
        if self.output_schema is None:
            return data
        try:
            validated = self.output_schema(**data)
            return validated.model_dump()
        except ValidationError as e:
            raise AgentOutputError(f"Invalid output from agent '{self.name}': {e}")

    @abstractmethod
    def get_subgraph(self) -> StateGraph:
        """
        Return a compiled LangGraph StateGraph for this agent's workflow.

        The graph should use the agent's state schema and include all nodes
        and edges. It will be invoked by the orchestrator.
        """
        pass

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's workflow with validated input.

        Args:
            input_data: Raw input dictionary (will be validated)

        Returns:
            Validated output dictionary

        Raises:
            AgentInputError: If input validation fails
            AgentOutputError: If output validation fails
        """
        validated_input = self.validate_input(input_data)
        graph = self.get_subgraph()

        # Run the graph (uses checkpointer from orchestrator context if provided)
        result = graph.invoke(validated_input)

        validated_output = self.validate_output(result)
        return validated_output

    async def aexecute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Async version of execute."""
        validated_input = self.validate_input(input_data)
        graph = self.get_subgraph()
        result = await graph.ainvoke(validated_input)
        validated_output = self.validate_output(result)
        return validated_output
