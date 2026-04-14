#!/usr/bin/env python3
"""
register_tools.py — Inspect and register all tools from tools.yaml at startup.

Usage:
    .venv/bin/python3 Scripts/register_tools.py              # print registry table
    .venv/bin/python3 Scripts/register_tools.py --validate   # also validate imports
    .venv/bin/python3 Scripts/register_tools.py --json       # output JSON
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import os

# Make project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_all_tools(validate_imports: bool = False) -> list[dict]:
    """Read tools.yaml and optionally validate each class can be imported."""
    from config.loader import load_tools_config
    tools   = load_tools_config()
    results = []

    for t in tools:
        entry = {
            "name":                 t.name,
            "display_name":         t.display_name,
            "owner_agent":          t.owner_agent,
            "module":               t.module,
            "class":                t.class_name,
            "requires_llm":         t.requires_llm,
            "requires_credentials": t.requires_credentials,
            "credentials_env":      t.credentials_env,
            "rate_limit_per_min":   t.rate_limit_per_min,
            "tags":                 t.tags,
            "import_ok":            None,
            "credential_status":    [],
        }

        if validate_imports:
            try:
                mod = importlib.import_module(t.module)
                cls = getattr(mod, t.class_name, None)
                entry["import_ok"] = cls is not None
            except Exception as e:
                entry["import_ok"] = False
                entry["import_error"] = str(e)

        # Check credentials
        if t.requires_credentials:
            for env_var in t.credentials_env:
                val = os.environ.get(env_var, "")
                entry["credential_status"].append({
                    "env": env_var,
                    "set": bool(val),
                    "note": t.production_note or "",
                })

        results.append(entry)

    return results


def print_table(tools: list[dict]) -> None:
    """Print a formatted registry table."""
    print(f"\n{'═'*80}")
    print(f"  PilotH Tool Registry  ({len(tools)} tools)")
    print(f"{'═'*80}")
    print(f"  {'Name':<30} {'Agent':<25} {'LLM':>4} {'Creds':>5} {'Import':>7}")
    print(f"  {'-'*30} {'-'*25} {'-'*4} {'-'*5} {'-'*7}")

    for t in tools:
        import_flag = (
            "  ✓" if t["import_ok"] is True else
            "  ✗" if t["import_ok"] is False else
            "  –"
        )
        print(
            f"  {t['name']:<30} {t['owner_agent']:<25} "
            f"{'yes':>4} " if t['requires_llm'] else f"  {t['name']:<30} {t['owner_agent']:<25}  no  "
            f"{'yes':>5}" if t['requires_credentials'] else " no  "
            f"{import_flag}"
        )

    # Simpler, cleaner version
    print()
    for t in tools:
        llm  = "✓LLM" if t["requires_llm"] else "    "
        cred = "✓CRED" if t["requires_credentials"] else "     "
        imp  = ("✓" if t["import_ok"] is True else ("✗" if t["import_ok"] is False else "–"))
        miss = [c["env"] for c in t.get("credential_status", []) if not c["set"]]
        warn = f"  ⚠ missing: {', '.join(miss)}" if miss else ""
        print(f"  {imp}  {llm} {cred}  {t['name']:<30} → {t['owner_agent']}{warn}")

    print(f"\n  Legend: ✓=ok  ✗=failed  –=not checked  ⚠=missing credentials\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="PilotH Tool Registry Inspector")
    parser.add_argument("--validate", action="store_true", help="Validate tool imports")
    parser.add_argument("--json",     action="store_true", help="Output JSON")
    args = parser.parse_args()

    tools = load_all_tools(validate_imports=args.validate)

    if args.json:
        print(json.dumps(tools, indent=2, default=str))
        return

    print_table(tools)

    if args.validate:
        failed = [t for t in tools if t["import_ok"] is False]
        if failed:
            print(f"  ✗ {len(failed)} import failure(s):")
            for t in failed:
                print(f"    - {t['name']}: {t.get('import_error','unknown')}")
            sys.exit(1)
        else:
            print(f"  All {len(tools)} tool imports validated successfully.\n")


if __name__ == "__main__":
    main()
