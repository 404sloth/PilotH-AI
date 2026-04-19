"""
Base tool class with built-in validation and retries.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type
from pydantic import BaseModel, ValidationError
from langchain_core.tools import BaseTool as LangChainBaseTool
from langchain_core.runnables import RunnableConfig


class ToolExecutionError(Exception):
    """Raised when a tool fails to execute."""

    pass


class StructuredTool(LangChainBaseTool, ABC):
    """
    Enhanced base tool with Pydantic validation and retry logic.

    Subclasses must:
        - Define `name` and `description` class attributes
        - Define `args_schema` as a Pydantic model
        - Implement `execute(validated_input)` method
    """

    args_schema: Type[BaseModel]
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds

    def _run(self, **kwargs: Any) -> Any:
        """
        Internal LangChain tool execution method.

        Validates inputs using args_schema, then calls execute().
        Supports retries on failure.
        """
        from observability.logger import get_logger
        from observability.pii_sanitizer import PIISanitizer
        import time

        logger = get_logger(f"tool_{self.name}")
        start_time = time.time()

        # Sanitize input for logging
        safe_kwargs = PIISanitizer.sanitize_dict(kwargs)

        logger.info("Tool execution started", data={
            "tool": self.name,
            "input_param_count": len(safe_kwargs)
        })

        # Validate input
        try:
            validated = self.args_schema(**kwargs)
        except ValidationError as e:
            logger.error("Tool input validation failed", error=str(e))
            raise ToolExecutionError(f"Tool '{self.name}' input validation failed: {e}")

        # Execute with retries
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                # Support passing config if provided in kwargs or if we have it
                config = kwargs.pop("config", None)
                result = self.execute(validated, config=config)

                execution_time = time.time() - start_time
                safe_result = PIISanitizer.sanitize_output(result) if isinstance(result, dict) else str(result)[:200]

                logger.info("Tool execution completed", data={
                    "tool": self.name,
                    "attempt": attempt + 1,
                    "execution_time_ms": round(execution_time * 1000, 2),
                    "result_type": type(result).__name__
                })

                # If result is a Pydantic model, convert to dict for LangChain
                if isinstance(result, BaseModel):
                    return result.model_dump()
                return result
            except Exception as e:
                last_exception = e
                logger.warning("Tool execution attempt failed", data={
                    "tool": self.name,
                    "attempt": attempt + 1,
                    "error": str(e)
                })
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay)
                    continue

        execution_time = time.time() - start_time
        logger.error("Tool execution failed after all retries", data={
            "tool": self.name,
            "total_attempts": self.max_retries,
            "execution_time_ms": round(execution_time * 1000, 2),
            "final_error": str(last_exception)
        })

        raise ToolExecutionError(
            f"Tool '{self.name}' failed after {self.max_retries} attempts: {last_exception}"
        )

    async def _arun(self, **kwargs: Any) -> Any:
        """Async execution with validation and retries."""
        try:
            validated = self.args_schema(**kwargs)
        except ValidationError as e:
            raise ToolExecutionError(f"Tool '{self.name}' input validation failed: {e}")

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                config = kwargs.pop("config", None)
                result = await self.aexecute(validated, config=config)
                if isinstance(result, BaseModel):
                    return result.model_dump()
                return result
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    import asyncio

                    await asyncio.sleep(self.retry_delay)
                    continue

        raise ToolExecutionError(
            f"Tool '{self.name}' failed after {self.max_retries} attempts: {last_exception}"
        )

    @abstractmethod
    def execute(self, validated_input: BaseModel, config: Optional[RunnableConfig] = None) -> Any:
        """
        Execute the tool's main logic with validated input.

        Args:
            validated_input: Instance of args_schema with validated data

        Returns:
            Tool result (can be any JSON-serializable type or Pydantic model)
        """
        pass

    async def aexecute(self, validated_input: BaseModel, config: Optional[RunnableConfig] = None) -> Any:
        """
        Async version of execute. Override if tool supports async.
        By default, calls sync execute in a thread.
        """
        import asyncio

        return await asyncio.to_thread(self.execute, validated_input, config)
