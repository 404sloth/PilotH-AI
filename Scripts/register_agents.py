#!/usr/bin/env python3
"""
register_agents.py — Inspect, validate and register all agents from agents.yaml.

Usage:
    .venv/bin/python3 Scripts/register_agents.py              # print registry table
    .venv/bin/python3 Scripts/register_agents.py --validate   # also validate imports + execute
    .venv/bin/python3 Scripts/register_agents.py --json       # output JSON
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_all_agents(validate_imports: bool = False) -> list[dict]:
    """Read agents.yaml and optionally validate each agent class."""
    from config.loader import load_agents_config

    agents = load_agents_config()
    results = []

    for a in agents:
        entry = {
            "name": a.name,
            "display_name": a.display_name,
            "enabled": a.enabled,
            "module": a.module,
            "class": a.class_name,
            "actions": a.actions,
            "default_action": a.default_action,
            "tools": a.tools,
            "hitl_enabled": a.hitl.enabled,
            "hitl_triggers": a.hitl.trigger_on,
            "llm_required": a.llm_required,
            "tags": a.tags,
            "import_ok": None,
            "graph_ok": None,
        }

        if validate_imports:
            try:
                mod = importlib.import_module(a.module)
                cls = getattr(mod, a.class_name, None)
                entry["import_ok"] = cls is not None
            except Exception as e:
                entry["import_ok"] = False
                entry["import_error"] = str(e)

            # Validate graph builds
            try:
                graph_module = a.module.replace(".agent", ".graph")
                gmod = importlib.import_module(graph_module)
                build = next(
                    (
                        getattr(gmod, fn)
                        for fn in dir(gmod)
                        if fn.startswith("build_")
                        and fn.endswith("_graph")
                        and callable(getattr(gmod, fn))
                    ),
                    None,
                )
                if build:
                    graph = build()
                    entry["graph_ok"] = graph is not None
                else:
                    entry["graph_ok"] = False
            except Exception as e:
                entry["graph_ok"] = False
                entry["graph_error"] = str(e)

        results.append(entry)

    return results


def print_table(agents: list[dict]) -> None:
    print(f"\n{'═' * 80}")
    print(f"  PilotH Agent Registry  ({len(agents)} agents)")
    print(f"{'═' * 80}")
    for a in agents:
        enabled = "✓ON " if a["enabled"] else "✗OFF"
        imp = (
            "✓" if a["import_ok"] is True else ("✗" if a["import_ok"] is False else "–")
        )
        grph = (
            "✓" if a["graph_ok"] is True else ("✗" if a["graph_ok"] is False else "–")
        )
        hitl = "HITL" if a["hitl_enabled"] else "    "
        print(
            f"  [{enabled}] {imp}agent {grph}graph  {hitl}  {a['name']:<30}  actions: {', '.join(a['actions'])}"
        )
        if a.get("import_error"):
            print(f"             ✗ import error: {a['import_error']}")
        if a.get("graph_error"):
            print(f"             ✗ graph error:  {a['graph_error']}")
    print("\n  Legend: ✓=ok  ✗=failed  –=not checked  ON/OFF=enabled state\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="PilotH Agent Registry Inspector")
    parser.add_argument(
        "--validate", action="store_true", help="Validate agent imports and graphs"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    agents = load_all_agents(validate_imports=args.validate)

    if args.json:
        print(json.dumps(agents, indent=2, default=str))
        return

    print_table(agents)

    if args.validate:
        imp_fail = [a for a in agents if a["import_ok"] is False]
        graph_fail = [a for a in agents if a["graph_ok"] is False]
        if imp_fail or graph_fail:
            sys.exit(1)
        print(f"  All {len(agents)} agent(s) validated (import + graph).\n")


if __name__ == "__main__":
    main()
