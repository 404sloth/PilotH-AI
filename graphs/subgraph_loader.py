"""
Subgraph Loader — dynamically loads agent sub-graphs by name.

Each agent's graph is compiled independently and can be embedded as a
LangGraph subgraph inside the top-level orchestration graph.
"""

from __future__ import annotations

import importlib
import logging
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def load_subgraph(agent_name: str) -> Optional[Any]:
    """
    Dynamically load and compile a subgraph for the given agent.

    Strategy:
      1. Read agents.yaml to find the agent's module.
      2. Import its graph.py and call build_*_graph().
      3. Cache the compiled result.

    Args:
        agent_name: Key from agents.yaml (e.g. "vendor_management")

    Returns:
        Compiled LangGraph StateGraph, or None if not found.
    """
    from config.loader import get_agent_config

    cfg = get_agent_config(agent_name)
    if not cfg:
        logger.warning("No config found for agent '%s'", agent_name)
        return None

    # Derive graph module: agents.vendor_management.agent → agents.vendor_management.graph
    graph_module_path = cfg.module.replace(".agent", ".graph")
    try:
        mod = importlib.import_module(graph_module_path)
    except ImportError as e:
        logger.error("Cannot import graph module '%s': %s", graph_module_path, e)
        return None

    # Find the build_*_graph function
    build_fn = None
    for attr_name in dir(mod):
        if (
            attr_name.startswith("build_")
            and attr_name.endswith("_graph")
            and callable(getattr(mod, attr_name))
        ):
            build_fn = getattr(mod, attr_name)
            break

    if not build_fn:
        logger.error("No build_*_graph() found in '%s'", graph_module_path)
        return None

    compiled = build_fn()
    logger.info(
        "Subgraph loaded for agent '%s' via %s.%s",
        agent_name,
        graph_module_path,
        build_fn.__name__,
    )
    return compiled


def reload_subgraph(agent_name: str) -> Optional[Any]:
    """Force-reload a subgraph (clears cache for that agent)."""
    load_subgraph.cache_clear()
    return load_subgraph(agent_name)


def list_available_subgraphs() -> list[str]:
    """Return names of all enabled agents that have loadable subgraphs."""
    from config.loader import load_agents_config

    return [a.name for a in load_agents_config() if a.enabled]
