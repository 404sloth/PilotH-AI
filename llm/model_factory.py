"""
LLM abstraction layer with intelligent fallback chain and lazy loading.

Priority (with lazy validation):
    1. OpenAI (gpt-4o) — if OPENAI_API_KEY is set
    2. Groq  (llama-3.1) — if GROQ_API_KEY is set
    3. Ollama (local)    — always available as fallback

Features:
  - Lazy loading: Models are only validated when actually used
  - Automatic fallback with graceful degradation
  - Connection validation with retries
  - Comprehensive error handling and logging
  - PII-safe error messages
  - Configurable timeout and retry behavior
  - Conversation storage for frontend integration

All callers import `get_llm()` and never reference a provider directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

logger = logging.getLogger(__name__)

# Conversation storage
CONVERSATIONS_DIR = Path("data/conversations")
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ConversationMessage:
    """Represents a single message in a conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata or {}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMessage':
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {})
        )


@dataclass
class Conversation:
    """Represents a complete conversation session."""
    id: str
    messages: List[ConversationMessage]
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata or {}
        }

    def save(self) -> None:
        """Save conversation to disk."""
        file_path = CONVERSATIONS_DIR / f"{self.id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, conversation_id: str) -> Optional['Conversation']:
        """Load conversation from disk."""
        file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load conversation {conversation_id}: {e}")
            return None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        return cls(
            id=data["id"],
            messages=[ConversationMessage.from_dict(msg) for msg in data["messages"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {})
        )

    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a message to the conversation."""
        message = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        self.save()

    @classmethod
    def create_new(cls, metadata: Optional[Dict[str, Any]] = None) -> 'Conversation':
        """Create a new conversation."""
        now = datetime.now()
        conversation = cls(
            id=str(uuid.uuid4()),
            messages=[],
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        conversation.save()
        return conversation


class ConversationManager:
    """Manages conversation storage and retrieval."""

    @staticmethod
    def list_conversations(limit: int = 50) -> List[Dict[str, Any]]:
        """List recent conversations."""
        if not CONVERSATIONS_DIR.exists():
            return []

        conversations = []
        for file_path in sorted(CONVERSATIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                conversations.append({
                    "id": data["id"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "message_count": len(data["messages"]),
                    "last_message": data["messages"][-1]["content"][:100] if data["messages"] else "",
                    "metadata": data.get("metadata", {})
                })
                if len(conversations) >= limit:
                    break
            except Exception as e:
                logger.warning(f"Failed to read conversation file {file_path}: {e}")

        return conversations

    @staticmethod
    def get_conversation(conversation_id: str) -> Optional[Conversation]:
        """Get a specific conversation."""
        return Conversation.load(conversation_id)

    @staticmethod
    def delete_conversation(conversation_id: str) -> bool:
        """Delete a conversation."""
        file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.warning(f"Failed to delete conversation {conversation_id}: {e}")
        return False


def get_llm(
    prefer: Optional[str] = None,
    temperature: float = 0.0,
    model_override: Optional[str] = None,
    max_tokens: Optional[int] = None,
    fallback_chain: bool = True,
    lazy_validation: bool = True,
) -> BaseChatModel:
    """
    Return an LLM instance with intelligent fallback and lazy loading.

    Args:
        prefer:         Force a specific provider ("openai" | "groq" | "ollama").
                        If None, auto-selects based on available API keys.
        temperature:    Sampling temperature (0.0 = deterministic).
        model_override: Override the default model name for the chosen provider.
        fallback_chain: If True and preferred provider fails, try fallback chain.
        lazy_validation: If True, skip connection validation during initialization.

    Returns:
        A LangChain-compatible BaseChatModel instance.

    Raises:
        RuntimeError: If all providers are unavailable and fallback_chain is False.
    """
    if prefer:
        # Try preferred provider with lazy loading
        try:
            llm = _build_provider_lazy(prefer, temperature, model_override, max_tokens)
            if not lazy_validation:
                if not _test_connection(llm):
                    raise RuntimeError(f"Preferred provider {prefer} failed connection test")
            logger.info("[LLM] Selected provider: %s", prefer)
            return llm
        except Exception as e:
            logger.warning("[LLM] Failed to initialize preferred provider %s: %s", prefer, str(e)[:100])
            if not fallback_chain:
                raise RuntimeError(f"Could not initialize LLM provider: {prefer}") from e

        # Fallback chain
        return _try_fallback_chain_lazy(
            exclude=prefer,
            temperature=temperature,
            model_override=model_override,
            max_tokens=max_tokens,
            lazy_validation=lazy_validation,
        )
    else:
        # Auto-detect and try chain
        provider = _detect_provider()
        logger.info("[LLM] Auto-detected provider: %s", provider)

        try:
            llm = _build_provider_lazy(provider, temperature, model_override)
            if not lazy_validation:
                if not _test_connection(llm):
                    raise RuntimeError(f"Auto-detected provider {provider} failed connection test")
            return llm
        except Exception as e:
            logger.warning("[LLM] Failed to initialize auto-detected provider %s: %s", provider, str(e)[:100])

        # Try full fallback chain
        return _try_fallback_chain_lazy(exclude=provider, temperature=temperature, model_override=model_override, lazy_validation=lazy_validation)


def _try_fallback_chain_lazy(
    exclude: Optional[str] = None,
    temperature: float = 0.0,
    model_override: Optional[str] = None,
    max_tokens: Optional[int] = None,
    lazy_validation: bool = True,
) -> BaseChatModel:
    """Try each provider in fallback order with lazy loading."""
    chain = ["openai", "groq", "ollama"]
    if exclude:
        chain = [p for p in chain if p != exclude]

    last_error = None
    for provider in chain:
        try:
            logger.debug("[LLM] Attempting provider: %s", provider)
            llm = _build_provider_lazy(provider, temperature, model_override, max_tokens)
            if lazy_validation or _test_connection(llm):
                logger.info("[LLM] Successfully initialized provider: %s", provider)
                return llm
        except Exception as e:
            error_msg = str(e)[:100]
            logger.debug("[LLM] Provider %s failed: %s", provider, error_msg)
            last_error = e
            continue

    # If we get here, all providers failed
    if last_error:
        raise RuntimeError(f"All LLM providers failed. Last error: {str(last_error)[:100]}") from last_error
    else:
        raise RuntimeError("All LLM providers failed. Please check configuration.")


def _detect_provider() -> str:
    """Auto-detect best available provider based on API keys."""
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return "ollama"


def _build_provider_lazy(
    provider: str,
    temperature: float,
    model: Optional[str],
    max_tokens: Optional[int],
) -> BaseChatModel:
    """Build an LLM instance for the specified provider with lazy loading."""
    if provider == "openai":
        return _build_openai_lazy(temperature, model, max_tokens)
    elif provider == "groq":
        return _build_groq_lazy(temperature, model, max_tokens)
    elif provider == "ollama":
        return _build_ollama_lazy(temperature, model, max_tokens)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _build_openai_lazy(
    temperature: float,
    model: Optional[str],
    max_tokens: Optional[int],
) -> BaseChatModel:
    """Build OpenAI ChatGPT instance with lazy loading."""
    try:
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        kwargs = {
            "model": model or os.getenv("OPENAI_MODEL", "gpt-4o"),
            "temperature": temperature,
            "api_key": api_key,
            "timeout": 30,
            "max_retries": 2,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs)
    except ImportError as e:
        raise RuntimeError(
            "langchain-openai not installed. Run: pip install langchain-openai"
        ) from e


def _build_groq_lazy(
    temperature: float,
    model: Optional[str],
    max_tokens: Optional[int],
) -> BaseChatModel:
    """Build Groq LLM instance with lazy loading."""
    try:
        from langchain_groq import ChatGroq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")

        kwargs = {
            "model": model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            "temperature": temperature,
            "api_key": api_key,
            "timeout": 30,
            "max_retries": 2,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatGroq(**kwargs)
    except ImportError as e:
        raise RuntimeError(
            "langchain-groq not installed. Run: pip install langchain-groq"
        ) from e


def _build_ollama_lazy(
    temperature: float,
    model: Optional[str],
    max_tokens: Optional[int],
) -> BaseChatModel:
    """Build Ollama LLM instance with lazy loading."""
    try:
        from langchain_ollama import ChatOllama

        kwargs = {
            "model": model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            "temperature": temperature,
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "timeout": 30,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatOllama(**kwargs)
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
            [HumanMessage(content="Respond with exactly 'OK' and nothing else.")]
        )
        elapsed = time.time() - start

        if elapsed > timeout:
            logger.warning("[LLM] Connection test took %.2fs (timeout: %.2fs)", elapsed, timeout)
            return False

        if response and response.content and "OK" in response.content.strip():
            logger.debug("[LLM] Connection test passed in %.2fs", elapsed)
            return True

        logger.warning("[LLM] Connection test got unexpected response: %s", response.content[:50] if response else "None")
        return False

    except Exception as e:
        logger.debug("[LLM] Connection test failed: %s", str(e)[:100])
        return False


class ModelFactory:
    """
    Backwards-compatible factory used by BaseAgent.
    Reads provider preference from Settings object.
    """

    @staticmethod
    def get_model(config) -> BaseChatModel:
        """Get LLM model with lazy loading to prevent startup failures."""
        prefer = getattr(config, "llm_primary", None)
        openai_model = getattr(config, "openai_model", None)
        groq_model = getattr(config, "groq_model", None)
        ollama_model = getattr(config, "ollama_model", None)

        try:
            if prefer == "openai":
                return get_llm("openai", model_override=openai_model, lazy_validation=True)
            if prefer == "groq":
                return get_llm("groq", model_override=groq_model, lazy_validation=True)
            if prefer == "ollama":
                return get_llm("ollama", model_override=ollama_model, lazy_validation=True)
            return get_llm(lazy_validation=True)
        except Exception as e:
            logger.warning("[LLM] Model factory failed, using Ollama fallback: %s", str(e)[:100])
            # Always return Ollama as last resort - it might work even if connection test fails
            return get_llm("ollama", lazy_validation=True)


# Enhanced prompt templates for better LLM responses
class PromptTemplates:
    """Enhanced prompt templates with comprehensive context."""

    @staticmethod
    def intent_parser_system_prompt(available_agents: Dict[str, Any]) -> str:
        """Generate comprehensive system prompt for intent parsing."""
        agent_descriptions = []
        for agent_name, agent_info in available_agents.items():
            agent_descriptions.append(f"""
## {agent_info.get('agent_name', agent_name)}
**Purpose**: {agent_info.get('agent_description', 'No description available')}
**Available Actions**:
{chr(10).join(f"- {action}: {info.get('description', 'No description')}" for action, info in agent_info.get('actions', {}).items())}
**Trigger Phrases**:
{chr(10).join(f"- {trigger}" for action, info in agent_info.get('actions', {}).items() for trigger in info.get('triggers', []))}
""")

        return f"""You are an intelligent agent dispatcher for PilotH, a comprehensive enterprise automation platform.

Your role is to analyze user requests and determine the most appropriate agent and action to handle them.

## Available Agents
{chr(10).join(agent_descriptions)}

## Analysis Guidelines
1. **Understand Context**: Consider the full conversation history and any provided context
2. **Match Intent**: Look for explicit or implicit requests that match agent capabilities
3. **Extract Parameters**: Identify specific requirements, constraints, or preferences
4. **Confidence Scoring**: Rate your confidence from 0.0 to 1.0 based on clarity and match quality
5. **Fallback Logic**: If unclear, prefer general-purpose agents over rejecting requests

## Response Format
Return ONLY valid JSON with this exact structure:
{{
    "agent": "agent_name",
    "action": "action_name",
    "params": {{
        "parameter_name": "extracted_value"
    }},
    "confidence": 0.85,
    "reasoning": "Brief explanation of your decision"
}}

## Important Notes
- Be flexible with phrasing - users may describe needs in many ways
- Consider conversation context for multi-turn interactions
- Default to helpful actions when intent is ambiguous
- Always provide reasoning for your choices"""

    @staticmethod
    def agent_execution_prompt(agent_name: str, action: str, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Generate comprehensive execution prompt for agents."""
        return f"""You are {agent_name}, an expert AI agent in the PilotH enterprise automation platform.

## Task
Execute the action: **{action}**

## Parameters
{json.dumps(params, indent=2)}

## Context
{json.dumps(context, indent=2)}

## Guidelines
1. **Be Thorough**: Provide comprehensive, actionable responses
2. **Use Data**: Leverage available information and tools
3. **Be Precise**: Include specific details, numbers, and recommendations
4. **Explain Reasoning**: Show your thought process and decision criteria
5. **Handle Errors**: If issues arise, explain them clearly and suggest alternatives

## Response Format
Provide a detailed, well-structured response that directly addresses the user's needs.
Include relevant data, analysis, and next steps where appropriate."""

    @staticmethod
    def conversation_summary_prompt(messages: List[Dict[str, Any]]) -> str:
        """Generate prompt for conversation summarization."""
        conversation_text = chr(10).join([
            f"{msg['role'].title()}: {msg['content']}"
            for msg in messages[-20:]  # Last 20 messages for context
        ])

        return f"""Summarize the following conversation for context awareness:

## Recent Conversation
{conversation_text}

## Summary Guidelines
- Capture key topics, decisions, and outcomes
- Note any ongoing tasks or unresolved issues
- Highlight user preferences or constraints
- Keep summary concise but comprehensive
- Focus on information relevant to current context

## Summary"""
