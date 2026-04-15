"""
Metrics Collection System for PilotH.

Tracks:
  - Agent execution metrics (count, duration, success rate)
  - Tool execution metrics (calls, duration, error rate)
  - LLM usage (tokens, cost, latency)
  - Task queue metrics (queued, running, completed, failed)
  - Business metrics (vendor matches, approvals, escalations)
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional


class MetricType(str, Enum):
    """Types of metrics collected."""
    COUNTER = "counter"  # Incremental count
    GAUGE = "gauge"  # Current value
    HISTOGRAM = "histogram"  # Distribution
    TIMER = "timer"  # Duration


@dataclass
class MetricPoint:
    """Single metric data point."""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: str = MetricType.GAUGE.value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MetricsCollector:
    """Thread-safe metrics collector."""

    def __init__(self):
        """Initialize metrics collector."""
        self._lock = Lock()
        self._metrics: Dict[str, List[MetricPoint]] = defaultdict(list)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}

    def increment_counter(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        with self._lock:
            key = self._tag_key(name, tags)
            self._counters[key] += value
            self._record_metric(name, value, MetricType.COUNTER, tags)

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric."""
        with self._lock:
            key = self._tag_key(name, tags)
            self._gauges[key] = value
            self._record_metric(name, value, MetricType.GAUGE, tags)

    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram value (for distributions like latencies)."""
        with self._lock:
            self._record_metric(name, value, MetricType.HISTOGRAM, tags)

    def record_timer(self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a timer metric."""
        with self._lock:
            self._record_metric(name, duration_ms, MetricType.TIMER, tags)

    def _record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Internal: record a metric point."""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags or {},
            metric_type=metric_type.value,
        )
        self._metrics[name].append(point)

    def get_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> int:
        """Get current counter value."""
        key = self._tag_key(name, tags)
        return self._counters.get(key, 0)

    def get_gauge(self, name: str, tags: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get current gauge value."""
        key = self._tag_key(name, tags)
        return self._gauges.get(key)

    def get_metric_history(self, name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent history for a metric."""
        with self._lock:
            points = self._metrics.get(name, [])[-limit:]
            return [p.to_dict() for p in points]

    def get_summary(self) -> Dict[str, Any]:
        """Get overall metrics summary."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "metric_points_collected": sum(len(v) for v in self._metrics.values()),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()

    @staticmethod
    def _tag_key(name: str, tags: Optional[Dict[str, str]]) -> str:
        """Build a tag key for storing metrics."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"


# ── Singleton ──────────────────────────────────────────────────────────────

_collector: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


# ── Convenience functions ──────────────────────────────────────────────────

class MetricsTracker:
    """Context manager for tracking operation metrics."""

    def __init__(self, operation_name: str, agent_name: Optional[str] = None):
        self.operation_name = operation_name
        self.agent_name = agent_name
        self.start_time = None
        self.tags = {}

        if agent_name:
            self.tags["agent"] = agent_name

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000

        mc = get_metrics()

        # Record duration
        mc.record_timer(f"{self.operation_name}.duration", duration_ms, self.tags)

        # Record success/failure
        if exc_type is None:
            mc.increment_counter(f"{self.operation_name}.success", tags=self.tags)
        else:
            mc.increment_counter(f"{self.operation_name}.failure", tags=self.tags)


# ── Agent Metrics ──────────────────────────────────────────────────────────

def record_agent_execution(
    agent_name: str,
    action: str,
    duration_ms: float,
    success: bool,
    token_count: Optional[int] = None,
) -> None:
    """Record agent execution metrics."""
    mc = get_metrics()
    tags = {"agent": agent_name, "action": action}

    mc.record_timer("agent.execution.duration", duration_ms, tags)
    mc.increment_counter("agent.execution.total", tags=tags)

    if success:
        mc.increment_counter("agent.execution.success", tags=tags)
    else:
        mc.increment_counter("agent.execution.failure", tags=tags)

    if token_count:
        mc.record_histogram("agent.tokens_used", token_count, tags)


def record_tool_execution(
    tool_name: str,
    agent_name: str,
    duration_ms: float,
    success: bool,
) -> None:
    """Record tool execution metrics."""
    mc = get_metrics()
    tags = {"tool": tool_name, "agent": agent_name}

    mc.record_timer("tool.execution.duration", duration_ms, tags)
    mc.increment_counter("tool.execution.total", tags=tags)

    if success:
        mc.increment_counter("tool.execution.success", tags=tags)
    else:
        mc.increment_counter("tool.execution.failure", tags=tags)


def record_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: float,
) -> None:
    """Record LLM API call metrics."""
    mc = get_metrics()
    tags = {"model": model}

    mc.increment_counter("llm.calls.total", tags=tags)
    mc.increment_counter("llm.tokens.prompt", prompt_tokens, tags=tags)
    mc.increment_counter("llm.tokens.completion", completion_tokens, tags=tags)
    mc.record_timer("llm.call.duration", duration_ms, tags)


def record_vendor_match(
    vendors_matched: int,
    top_recommendation_confidence: float,
) -> None:
    """Record vendor matching metrics."""
    mc = get_metrics()

    mc.increment_counter("vendor_matching.total")
    mc.record_histogram("vendor_matching.candidates", vendors_matched)
    mc.record_histogram("vendor_matching.confidence", top_recommendation_confidence)


def record_hitl_approval(
    approved: bool,
    risk_score: float,
    resolution_time_minutes: Optional[float] = None,
) -> None:
    """Record human-in-the-loop metrics."""
    mc = get_metrics()
    tags = {"result": "approved" if approved else "rejected"}

    mc.increment_counter("hitl.decisions.total", tags=tags)
    mc.record_histogram("hitl.risk_score", risk_score)

    if resolution_time_minutes:
        mc.record_histogram("hitl.resolution_time", resolution_time_minutes)


def record_task_queue_event(
    event_type: str,  # queued | started | completed | failed
    retry_count: Optional[int] = None,
) -> None:
    """Record task queue metrics."""
    mc = get_metrics()

    mc.increment_counter(f"task_queue.{event_type}")

    if retry_count is not None and retry_count > 0:
        mc.increment_counter("task_queue.retries")


# ── Reporting ──────────────────────────────────────────────────────────────

def get_metrics_report() -> Dict[str, Any]:
    """Get comprehensive metrics report."""
    mc = get_metrics()
    return {
        "summary": mc.get_summary(),
        "agent_metrics": {
            "execution_success": mc.get_counter("agent.execution.success"),
            "execution_failure": mc.get_counter("agent.execution.failure"),
        },
        "tool_metrics": {
            "execution_success": mc.get_counter("tool.execution.success"),
            "execution_failure": mc.get_counter("tool.execution.failure"),
        },
        "llm_metrics": {
            "total_calls": mc.get_counter("llm.calls.total"),
        },
        "vendor_metrics": {
            "total_matches": mc.get_counter("vendor_matching.total"),
        },
        "task_queue_metrics": {
            "queued": mc.get_counter("task_queue.queued"),
            "completed": mc.get_counter("task_queue.completed"),
            "failed": mc.get_counter("task_queue.failed"),
        },
    }
