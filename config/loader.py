"""
YAML Config Loader — reads agents.yaml and tools.yaml into typed Pydantic models.
Called once at startup; results are cached.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent


# ─── Pydantic models for YAML schemas ─────────────────────────────────────────


class HITLConfig(BaseModel):
    enabled: bool = False
    trigger_on: List[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    name: str
    display_name: str
    enabled: bool = True
    module: str
    class_name: str = Field(alias="class")
    description: str = ""
    actions: List[str] = Field(default_factory=list)
    default_action: str = ""
    tools: List[str] = Field(default_factory=list)
    hitl: HITLConfig = Field(default_factory=HITLConfig)
    llm_required: bool = False
    tags: List[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class ToolConfig(BaseModel):
    name: str
    display_name: str
    owner_agent: str
    module: str
    class_name: str = Field(alias="class")
    description: str = ""
    requires_llm: bool = False
    requires_credentials: bool = False
    credentials_env: List[str] = Field(default_factory=list)
    production_note: Optional[str] = None
    rate_limit_per_min: int = 60
    tags: List[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


# ─── Loaders (cached) ─────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def load_agents_config() -> List[AgentConfig]:
    """Load and validate agents.yaml. Returns only enabled agents."""
    path = _CONFIG_DIR / "agents.yaml"
    if not path.exists():
        logger.warning("agents.yaml not found at %s", path)
        return []
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    agents = [AgentConfig(**a) for a in raw.get("agents", [])]
    enabled = [a for a in agents if a.enabled]
    logger.info("Loaded %d agent config(s) from agents.yaml", len(enabled))
    return enabled


@functools.lru_cache(maxsize=1)
def load_tools_config() -> List[ToolConfig]:
    """Load and validate tools.yaml."""
    path = _CONFIG_DIR / "tools.yaml"
    if not path.exists():
        logger.warning("tools.yaml not found at %s", path)
        return []
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    tools = [ToolConfig(**t) for t in raw.get("tools", [])]
    logger.info("Loaded %d tool config(s) from tools.yaml", len(tools))
    return tools


def get_agent_config(name: str) -> Optional[AgentConfig]:
    """Look up a single agent config by name."""
    return next((a for a in load_agents_config() if a.name == name), None)


def get_tool_config(name: str) -> Optional[ToolConfig]:
    """Look up a single tool config by name."""
    return next((t for t in load_tools_config() if t.name == name), None)


def reload_configs() -> None:
    """Clear cache and re-read YAML files (useful during development)."""
    load_agents_config.cache_clear()
    load_tools_config.cache_clear()
    load_agents_config()
    load_tools_config()
