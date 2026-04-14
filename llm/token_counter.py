"""
Token Counter — tracks LLM token usage across the session.
Supports cost estimation per provider.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Approximate pricing per 1K tokens (USD) — update as models change
_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "llama-3.1-8b-instant": {"input": 0.0001, "output": 0.0001},  # Groq
    "llama3": {"input": 0.0, "output": 0.0},  # Ollama (local = free)
}


@dataclass
class TokenUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        pricing = _PRICING.get(self.model, {"input": 0.002, "output": 0.002})
        return (
            self.input_tokens / 1000 * pricing["input"]
            + self.output_tokens / 1000 * pricing["output"]
        )


class TokenCounter:
    """
    Thread-safe token usage aggregator.
    One instance per session; register with LLM callbacks for auto-tracking.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._usage: Dict[str, TokenUsage] = {}  # model → usage

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Add token counts for a model."""
        with self._lock:
            if model not in self._usage:
                self._usage[model] = TokenUsage(model=model)
            self._usage[model].input_tokens += input_tokens
            self._usage[model].output_tokens += output_tokens

    def record_from_response(self, response: Any, model: str) -> None:
        """
        Try to extract token counts from a LangChain AI message response.
        Falls back silently if metadata is absent.
        """
        try:
            usage_meta = getattr(response, "usage_metadata", None) or {}
            input_t = usage_meta.get("input_tokens", 0)
            output_t = usage_meta.get("output_tokens", 0)
            if input_t or output_t:
                self.record(model, input_t, output_t)
        except Exception:
            pass

    def totals(self) -> Dict[str, Any]:
        """Return aggregate usage across all models."""
        with self._lock:
            total_in = sum(u.input_tokens for u in self._usage.values())
            total_out = sum(u.output_tokens for u in self._usage.values())
            total_cost = sum(u.estimated_cost_usd for u in self._usage.values())
            return {
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "estimated_cost_usd": round(total_cost, 6),
                "by_model": {
                    m: {
                        "input_tokens": u.input_tokens,
                        "output_tokens": u.output_tokens,
                        "total_tokens": u.total_tokens,
                        "estimated_cost_usd": round(u.estimated_cost_usd, 6),
                    }
                    for m, u in self._usage.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._usage.clear()

    def __repr__(self) -> str:
        t = self.totals()
        return f"TokenCounter(total={t['total_tokens']}, cost=${t['estimated_cost_usd']:.6f})"


# ---------------------------------------------------------------------------
# Module-level default counter (importable by any component)
# ---------------------------------------------------------------------------
_default_counter: Optional[TokenCounter] = None


def get_token_counter() -> TokenCounter:
    """Return the process-level singleton token counter."""
    global _default_counter
    if _default_counter is None:
        _default_counter = TokenCounter()
    return _default_counter
