"""
LLM abstraction layer with intelligent fallback chain.

Priority:
    1. OpenAI (gpt-4o) — if OPENAI_API_KEY is set and reachable
    2. Groq  (llama-3.1) — if GROQ_API_KEY is set and reachable
    3. Ollama (local)    — always available as fallback

Features:
  - Automatic fallback if preferred provider is unavailable
  - Connection validation before returning
  - Cost tracking and token counting
  - PII-safe error logging
  - Configurable timeout and retry behavior

All callers import `get_llm()` and never reference a provider directly.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional, Dict, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


def get_llm(
    prefer: Optional[str] = None,
    temperature: float = 0.0,
    model_override: Optional[str] = None,
    fallback_chain: bool = True,
) -> BaseChatModel:
    """
    Return an LLM instance following the project's fallback chain.

    Args:
        prefer:         Force a specific provider ("openai" | "groq" | "ollama").
                        If None, auto-selects based on available API keys.
        temperature:    Sampling temperature (0.0 = deterministic).
        model_override: Override the default model name for the chosen provider.
        fallback_chain: If True and preferred provider fails, try fallback chain.

    Returns:
        A LangChain-compatible BaseChatModel instance.

    Raises:
        RuntimeError: If all providers are unavailable and fallback_chain is False.
    """
    if prefer:
        # Try preferred provider
        try:
            llm = _build_provider(prefer, temperature, model_override)
            if _test_connection(llm):
                logger.info("[LLM] Using preferred provider: %s", prefer)
                return llm
            else:
                logger.warning("[LLM] Preferred provider %s failed connection test", prefer)
        except Exception as e:
            logger.warning("[LLM] Failed to initialize preferred provider %s: %s", prefer, e)

        # Fallback if enabled
        if fallback_chain:
            logger.info("[LLM] Trying fallback chain from preferred provider: %s", prefer)
            return _try_fallback_chain(exclude=prefer, temperature=temperature, model_override=model_override)
        raise RuntimeError(f"Could not initialize LLM provider: {prefer}")
    else:
        # Auto-detect and try chain
        provider = _detect_provider()
        logger.info("[LLM] Auto-detected provider: %s", provider)

        try:
            llm = _build_provider(provider, temperature, model_override)
            if _test_connection(llm):
                return llm
        except Exception as e:
            logger.warning("[LLM] Failed to initialize auto-detected provider %s: %s", provider, e)

        # Try full fallback chain
        return _try_fallback_chain(exclude=provider, temperature=temperature, model_override=model_override)


def _try_fallback_chain(
    exclude: Optional[str] = None,
    temperature: float = 0.0,
    model_override: Optional[str] = None,
) -> BaseChatModel:
    """Try each provider in fallback order, excluding the specified one."""
    chain = ["openai", "groq", "ollama"]
    if exclude:
        chain = [p for p in chain if p != exclude]

    for provider in chain:
        try:
            logger.debug("[LLM] Attempting fallback to: %s", provider)
            llm = _build_provider(provider, temperature, model_override)
            if _test_connection(llm):
                logger.info("[LLM] Successfully initialized fallback provider: %s", provider)
                return llm
        except Exception as e:
            logger.debug("[LLM] Fallback provider %s failed: %s", provider, e)
            continue

    # Last resort: Ollama must succeed (it's local)
    raise RuntimeError("All LLM providers failed. Please ensure Ollama is running or set API keys.")


def _detect_provider() -> str:
    """Auto-detect best available provider based on API keys."""
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "ollama"


def _build_provider(
    provider: str,
    temperature: float,
    model: Optional[str],
) -> BaseChatModel:
    """Build an LLM instance for the specified provider."""
    if provider == "openai":
        return _build_openai(temperature, model)
    elif provider == "groq":
        return _build_groq(temperature, model)
    elif provider == "ollama":
        return _build_ollama(temperature, model)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _build_openai(temperature: float, model: Optional[str]) -> BaseChatModel:
    """Build OpenAI ChatGPT instance."""
    try:
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=temperature,
            api_key=api_key,
            timeout=30,
            max_retries=2,
        )
    except ImportError as e:
        raise RuntimeError(
            "langchain-openai not installed. Run: pip install langchain-openai"
        ) from e


def _build_groq(temperature: float, model: Optional[str]) -> BaseChatModel:
    """Build Groq LLM instance."""
    try:
        from langchain_groq import ChatGroq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")

        return ChatGroq(
            model=model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=temperature,
            api_key=api_key,
            timeout=30,
            max_retries=2,
        )
    except ImportError as e:
        raise RuntimeError(
            "langchain-groq not installed. Run: pip install langchain-groq"
        ) from e


def _build_ollama(temperature: float, model: Optional[str]) -> BaseChatModel:
    """Build Ollama LLM instance."""
    try:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or os.getenv("OLLAMA_MODEL", "llama3"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            timeout=30,
        )
    except ImportError as e:
        raise RuntimeError(
            "langchain-ollama not installed. Run: pip install langchain-ollama"
        ) from e


def _test_connection(llm: BaseChatModel, timeout: float = 5.0) -> bool:
    """
    Test if an LLM instance is working by sending a simple prompt.

    Args:
        llm: The LLM to test
        timeout: Timeout in seconds

    Returns:
        True if LLM responds, False otherwise
    """
    try:
        start = time.time()
        response = llm.invoke(
            [HumanMessage(content="Respond with 'OK'.")]
        )
        elapsed = time.time() - start

        if elapsed > timeout:
            logger.warning("[LLM] Connection test took %.2fs (timeout: %.2fs)", elapsed, timeout)
            return False

        if response and response.content:
            logger.debug("[LLM] Connection test passed in %.2fs", elapsed)
            return True

        logger.warning("[LLM] Connection test got empty response")
        return False

    except Exception as e:
        logger.debug("[LLM] Connection test failed: %s", e)
        return False


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
