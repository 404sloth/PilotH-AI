"""
LLM abstraction layer.

Priority:
    1. OpenAI (gpt-4o) — if OPENAI_API_KEY is set
    2. Groq  (llama-3.1) — if GROQ_API_KEY is set
    3. Ollama (local)    — always available as fallback

All callers import `get_llm()` and never reference a provider directly.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


def get_llm(
    prefer: Optional[str] = None,
    temperature: float = 0.0,
    model_override: Optional[str] = None,
) -> BaseChatModel:
    """
    Return an LLM instance following the project's fallback chain.

    Args:
        prefer:         Force a specific provider ("openai" | "groq" | "ollama").
                        If None, auto-selects based on available API keys.
        temperature:    Sampling temperature (0.0 = deterministic).
        model_override: Override the default model name for the chosen provider.

    Returns:
        A LangChain-compatible BaseChatModel instance.
    """
    provider = prefer or _detect_provider()
    logger.info("LLM provider selected: %s", provider)

    if provider == "openai":
        return _build_openai(temperature, model_override)
    if provider == "groq":
        return _build_groq(temperature, model_override)
    return _build_ollama(temperature, model_override)


def _detect_provider() -> str:
    """Auto-detect best available provider."""
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "ollama"


def _build_openai(temperature: float, model: Optional[str]) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    except ImportError as e:
        raise RuntimeError(
            "langchain-openai not installed. Run: pip install langchain-openai"
        ) from e


def _build_groq(temperature: float, model: Optional[str]) -> BaseChatModel:
    try:
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY"),
        )
    except ImportError as e:
        raise RuntimeError(
            "langchain-groq not installed. Run: pip install langchain-groq"
        ) from e


def _build_ollama(temperature: float, model: Optional[str]) -> BaseChatModel:
    try:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or os.getenv("OLLAMA_MODEL", "llama3"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    except ImportError as e:
        raise RuntimeError(
            "langchain-ollama not installed. Run: pip install langchain-ollama"
        ) from e


class ModelFactory:
    """
    Backwards-compatible factory used by BaseAgent.
    Reads provider preference from Settings object.
    """

    @staticmethod
    def get_model(config) -> BaseChatModel:
        prefer = getattr(config, "llm_primary", None)
        openai_model = getattr(config, "openai_model", None)
        groq_model = getattr(config, "groq_model", None)
        ollama_model = getattr(config, "ollama_model", None)

        if prefer == "openai":
            return get_llm("openai", model_override=openai_model)
        if prefer == "groq":
            return get_llm("groq", model_override=groq_model)
        if prefer == "ollama":
            return get_llm("ollama", model_override=ollama_model)
        return get_llm()
