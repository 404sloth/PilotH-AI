"""
Structured Logging System for PilotH.

Provides:
  - Context-aware logging with session tracking
  - Automatic PII masking
  - Request/response logging with correlation IDs
  - Performance metrics per operation
  - Structured JSON output for log aggregation
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional


class StructuredLogger:
    """Context-aware logger with automatic PII masking."""

    def __init__(self, name: str, sanitize_pii: bool = True):
        """Initialize structured logger."""
        self.logger = logging.getLogger(name)
        self.sanitize_pii = sanitize_pii
        self.correlation_id = str(uuid.uuid4())
        self.session_stack: List[str] = []

    def _sanitize(self, data: Any) -> Any:
        """Sanitize PII from data."""
        if not self.sanitize_pii:
            return data

        from observability.pii_sanitizer import sanitize_output

        try:
            return sanitize_output(data)
        except Exception:
            return data

    def _build_context(self) -> Dict[str, Any]:
        """Build standard context for all log entries."""
        return {
            "correlation_id": self.correlation_id,
            "session_id": self.session_stack[-1] if self.session_stack else None,
            "timestamp": time.time(),
        }

    def info(
        self,
        message: str,
        agent: Optional[str] = None,
        action: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log info level with context."""
        context = self._build_context()
        context["level"] = "INFO"
        context["message"] = message
        if agent:
            context["agent"] = agent
        if action:
            context["action"] = action
        if data:
            context["data"] = self._sanitize(data)
        context.update(kwargs)

        self.logger.info(json.dumps(context))

    def warning(
        self,
        message: str,
        agent: Optional[str] = None,
        error: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log warning level."""
        context = self._build_context()
        context["level"] = "WARNING"
        context["message"] = message
        if agent:
            context["agent"] = agent
        if error:
            context["error"] = str(error)
        context.update(kwargs)

        self.logger.warning(json.dumps(context))

    def error(
        self,
        message: str,
        agent: Optional[str] = None,
        error: Optional[Exception] = None,
        **kwargs
    ) -> None:
        """Log error level."""
        context = self._build_context()
        context["level"] = "ERROR"
        context["message"] = message
        if agent:
            context["agent"] = agent
        if error:
            context["error"] = str(error)
            context["error_type"] = type(error).__name__
        context.update(kwargs)

        self.logger.error(json.dumps(context))

    def debug(self, message: str, **kwargs) -> None:
        """Log debug level."""
        context = self._build_context()
        context["level"] = "DEBUG"
        context["message"] = message
        context.update(kwargs)

        self.logger.debug(json.dumps(context))

    @contextmanager
    def track_session(self, session_id: str):
        """Context manager for session tracking."""
        self.session_stack.append(session_id)
        try:
            yield
        finally:
            self.session_stack.pop()

    @contextmanager
    def track_operation(self, operation_name: str, **metadata):
        """Track operation timing and success/failure."""
        start_time = time.time()
        context = self._build_context()
        context["operation"] = operation_name
        context["status"] = "started"
        context.update(metadata)

        self.logger.info(json.dumps(context))

        try:
            yield
            duration = time.time() - start_time
            context["status"] = "completed"
            context["duration_ms"] = round(duration * 1000, 2)
            self.logger.info(json.dumps(context))
        except Exception as e:
            duration = time.time() - start_time
            context["status"] = "failed"
            context["duration_ms"] = round(duration * 1000, 2)
            context["error"] = str(e)
            context["error_type"] = type(e).__name__
            self.logger.error(json.dumps(context))
            raise


# ── Singleton functions ────────────────────────────────────────────────────

_loggers: Dict[str, StructuredLogger] = {}


def get_logger(name: str, sanitize_pii: bool = True) -> StructuredLogger:
    """Get or create a StructuredLogger instance."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name, sanitize_pii)
    return _loggers[name]


# ── Convenience functions ──────────────────────────────────────────────────

def log_agent_action(
    agent_name: str,
    action: str,
    input_data: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Log agent action execution."""
    logger = get_logger(f"agent.{agent_name}")

    data = {
        "input": input_data,
        "result": result,
        "duration_ms": duration_ms,
    }

    if error:
        logger.error(f"Action failed: {action}", agent=agent_name, error=error, data=data)
    else:
        logger.info(f"Action completed: {action}", agent=agent_name, data=data)


def log_tool_execution(
    tool_name: str,
    agent_name: str,
    input_args: Optional[Dict[str, Any]] = None,
    output: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Log tool execution."""
    logger = get_logger(f"tool.{tool_name}")

    data = {
        "input": input_args,
        "output": output,
        "duration_ms": duration_ms,
    }

    if error:
        logger.error(
            f"Tool execution failed", agent=agent_name, error=error, data=data
        )
    else:
        logger.info(f"Tool execution completed", agent=agent_name, data=data)


def log_llm_call(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    temperature: float,
    duration_ms: Optional[float] = None,
) -> None:
    """Log LLM API call metrics."""
    logger = get_logger("llm")
    logger.info(
        "LLM call completed",
        data={
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "temperature": temperature,
            "duration_ms": duration_ms,
        },
    )
