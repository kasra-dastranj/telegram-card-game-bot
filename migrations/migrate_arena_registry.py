#!/usr/bin/env python3
"""Add and seed the Arena Registry without changing live gameplay rules.

Usage: python migrations/migrate_arena_registry.py [path/to/game_bot.db] [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from systems.arena_registry import ArenaRegistry


def _arena_count(db_path: str) -> int:
    if not Path(db_path).exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='arenas'"
        ).fetchone()
        return int(conn.execute("SELECT COUNT(*) FROM arenas").fetchone()[0]) if exists else 0
    finally:
        conn.close()


def _copy_database(source_path: str, target_path: str) -> None:
    source = sqlite3.connect(source_path) if Path(source_path).exists() else sqlite3.connect(":memory:")
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def migrate(db_path: str, dry_run: bool = False) -> dict:
    """Run the additive migration, optionally against a disposable DB copy."""
    actual_path = str(Path(db_path))
    before = _arena_count(actual_path)
    if dry_run:
        with tempfile.TemporaryDirectory(prefix="arena-registry-dry-run-") as folder:
            target = str(Path(folder) / "preview.db")
            _copy_database(actual_path, target)
            registry = ArenaRegistry(target)
            total = len(registry.list_arenas(include_archived=True))
            return {
                "success": True,
                "dry_run": True,
                **registry.seed_report,
                "existing": before,
                "total": total,
                "registry_version": registry.registry_version(),
            }
    registry = ArenaRegistry(actual_path)
    total = len(registry.list_arenas(include_archived=True))
    return {
        "success": True,
        "dry_run": False,
        **registry.seed_report,
        "existing": before,
        "total": total,
        "registry_version": registry.registry_version(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", nargs="?", default="game_bot.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(migrate(args.db_path, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
