#!/usr/bin/env python3
"""
seed_data.py — Reset and re-seed the SQLite database with representative mock data.

Usage:
    .venv/bin/python3 Scripts/seed_data.py              # seed if empty
    .venv/bin/python3 Scripts/seed_data.py --reset      # drop all data first
    .venv/bin/python3 Scripts/seed_data.py --db path/to/custom.sqlite
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def reset_db(db_path: str) -> None:
    """Remove the database file entirely and let init_db() recreate it."""
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"  Removed existing database: {db_path}")
    else:
        print(f"  No existing database at {db_path} — creating fresh.")


def seed(db_path: str, reset: bool = False) -> None:
    from integrations.data_warehouse import sqlite_client

    if db_path:
        os.environ["SQLITE_DB_PATH"] = db_path
        sqlite_client.DB_PATH = db_path

    if reset:
        reset_db(sqlite_client.DB_PATH)

    print(f"\n  Seeding database at: {sqlite_client.DB_PATH}")
    sqlite_client.init_db(seed=True)
    print("  ✓ Vendor tables seeded")
    print("  ✓ Persons & meetings tables seeded")

    # Verify counts
    from integrations.data_warehouse.sqlite_client import get_db_connection

    with get_db_connection() as conn:
        for table in [
            "vendors",
            "persons",
            "meetings",
            "calendar_events",
            "contracts",
            "milestones",
        ]:
            try:
                cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  → {table:<25} {count:>4} row(s)")
            except Exception:
                print(f"  → {table:<25} (not found)")

    print("\n  Database seed complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="PilotH Database Seeder")
    parser.add_argument(
        "--reset", action="store_true", help="Drop existing data before seeding"
    )
    parser.add_argument("--db", default="", help="Override database path")
    args = parser.parse_args()
    seed(args.db, reset=args.reset)


if __name__ == "__main__":
    main()
