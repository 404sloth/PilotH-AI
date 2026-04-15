"""
Distributed Tracing System for PilotH.

Enables:
  - Request tracing across agents and tools
  - LangSmith integration for LLM observability
  - Span creation and linking
  - Trace export to external systems
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """A single trace span."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "running"  # running | success | error
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["start_time"] = self.start_time
        d["end_time"] = self.end_time
        return d

    def finish(self, status: str = "success", error: Optional[str] = None) -> None:
        """Mark span as finished."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status or "success"
        self.error = error

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })


class TraceContext:
    """Manages active trace and span contexts."""

    def __init__(self):
        self.trace_id = str(uuid.uuid4())
        self.current_span_id: Optional[str] = None
        self.spans: List[Span] = []
        self._span_stack: List[str] = []

    def create_span(
        self,
        operation_name: str,
        parent_span_id: Optional[str] = None,
    ) -> Span:
        """Create a new span."""
        span = Span(
            span_id=str(uuid.uuid4()),
            trace_id=self.trace_id,
            parent_span_id=parent_span_id or self.current_span_id,
            operation_name=operation_name,
        )
        self.spans.append(span)
        return span

    def push_span(self, span_id: str) -> None:
        """Push a span onto the stack."""
        self._span_stack.append(span_id)
        self.current_span_id = span_id

    def pop_span(self) -> Optional[str]:
        """Pop a span from the stack."""
        if self._span_stack:
            return self._span_stack.pop()
        return None

    def get_spans(self) -> List[Dict[str, Any]]:
        """Get all recorded spans."""
        return [s.to_dict() for s in self.spans]


class DistributedTracer:
    """Manages distributed tracing."""

    def __init__(self, service_name: str = "piloth"):
        """Initialize tracer."""
        self.service_name = service_name
        self.context = TraceContext()
        self.logger = logging.getLogger(f"trace.{service_name}")

    @contextmanager
    def trace_operation(
        self,
        operation_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Context manager for tracing an operation."""
        span = self.context.create_span(operation_name)
        self.context.push_span(span.span_id)

        if attributes:
            span.attributes.update(attributes)

        try:
            yield span
            span.finish(status="success")
        except Exception as e:
            span.finish(status="error", error=str(e))
            raise
        finally:
            self.context.pop_span()

    def record_span(
        self,
        operation_name: str,
        duration_ms: float,
        status: str = "success",
        attributes: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record a span that has already completed."""
        span = self.context.create_span(operation_name)
        span.attributes.update(attributes or {})
        span.end_time = span.start_time + (duration_ms / 1000)
        span.duration_ms = duration_ms
        span.status = status
        span.error = error

    def export_trace(self) -> Dict[str, Any]:
        """Export the current trace."""
        return {
            "trace_id": self.context.trace_id,
            "service": self.service_name,
            "timestamp": time.time(),
            "spans": self.context.get_spans(),
        }

    def log_trace(self) -> None:
        """Log the trace as JSON."""
        trace_data = self.export_trace()
        self.logger.info(json.dumps(trace_data))


# ── Global tracer instance ─────────────────────────────────────────────────

_tracer: Optional[DistributedTracer] = None


def get_tracer(service_name: str = "piloth") -> DistributedTracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = DistributedTracer(service_name)
    return _tracer


# ── LangSmith integration (if available) ───────────────────────────────────

def init_langsmith_tracing() -> bool:
    """Initialize LangSmith tracing if configured."""
    try:
        api_key = os.getenv("LANGSMITH_API_KEY")
        if not api_key:
            return False

        from langsmith import Client
        from langchain.callbacks.tracers.langsmith import LangSmithTracer

        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = api_key
        os.environ["LANGSMITH_PROJECT"] = os.getenv(
            "LANGSMITH_PROJECT", "piloth-vendor"
        )
        logging.info("✓ LangSmith tracing initialized")
        return True
    except ImportError:
        logging.warning("LangSmith not installed; skipping LangSmith setup")
        return False
    except Exception as e:
        logging.warning(f"Failed to initialize LangSmith: {e}")
        return False


# ── Agent-specific tracing ────────────────────────────────────────────────

def trace_agent_action(
    agent_name: str,
    action: str,
    session_id: Optional[str] = None,
) -> DistributedTracer:
    """Create a tracer for an agent action."""
    tracer = get_tracer(f"agent.{agent_name}")
    attributes = {
        "agent": agent_name,
        "action": action,
    }
    if session_id:
        attributes["session_id"] = session_id

    # Start operation (user would use as context manager)
    return tracer


def trace_tool_call(
    tool_name: str,
    agent_name: str,
) -> DistributedTracer:
    """Create a tracer for a tool call."""
    tracer = get_tracer(f"tool.{tool_name}")
    attributes = {
        "tool": tool_name,
        "agent": agent_name,
    }
    return tracer


def trace_llm_call(
    model: str,
    provider: str,
) -> DistributedTracer:
    """Create a tracer for an LLM call."""
    tracer = get_tracer("llm")
    attributes = {
        "model": model,
        "provider": provider,
    }
    return tracer


# ── Export utilities ───────────────────────────────────────────────────────

def export_all_traces() -> List[Dict[str, Any]]:
    """Export all recorded traces."""
    traces = []
    # In a real system, this would aggregate traces from all tracer instances
    tracer = get_tracer()
    traces.append(tracer.export_trace())
    return traces


def get_trace_summary() -> Dict[str, Any]:
    """Get summary of trace statistics."""
    tracer = get_tracer()
    trace = tracer.export_trace()

    spans = trace["spans"]
    total_duration = sum(s.get("duration_ms", 0) for s in spans)
    success_count = sum(1 for s in spans if s.get("status") == "success")
    error_count = sum(1 for s in spans if s.get("status") == "error")

    return {
        "trace_id": trace["trace_id"],
        "total_spans": len(spans),
        "successful_spans": success_count,
        "failed_spans": error_count,
        "total_duration_ms": total_duration,
        "service": trace["service"],
    }
