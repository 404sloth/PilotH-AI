"""
LLM package — exposes the primary get_llm() factory and ModelFactory shim.
"""

from .model_factory import get_llm, ModelFactory

__all__ = ["get_llm", "ModelFactory"]
