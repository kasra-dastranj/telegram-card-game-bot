"""Preview or apply trial level rewards and mode gates to an existing game DB.

Examples:
  python scripts/configure_trial_progression.py --db game_bot.db --level-coins 2:100 --mode-level easy:5
  python scripts/configure_trial_progression.py --db game_bot.db --level-coins 2:100 --mode-level easy:5 --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from systems.level_rewards_system import ensure_level_reward_schema
from systems.mode_access_system import DEFAULT_MODE_LEVELS, ensure_mode_access_schema


def _level_coin(value: str) -> tuple[int, int]:
    try:
        level_str, coins_str = value.split(":", 1)
        level, coins = int(level_str), int(coins_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected LEVEL:COINS") from exc
    if not 2 <= level <= 30 or coins < 0:
        raise argparse.ArgumentTypeError("level must be 2..30 and coins >= 0")
    return level, coins


def _mode_level(value: str) -> tuple[str, int]:
    try:
        mode, level_str = value.split(":", 1)
        level = int(level_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected MODE:LEVEL") from exc
    if mode not in DEFAULT_MODE_LEVELS or not 1 <= level <= 30:
        raise argparse.ArgumentTypeError(
            f"mode must be one of {', '.join(DEFAULT_MODE_LEVELS)} and level 1..30"
        )
    return mode, level


def _existing(conn: sqlite3.Connection, table: str, key_column: str,
              value_column: str, lookup_key: int | str) -> int | None:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone():
        return None
    # Table and column names only come from the fixed calls below.
    row = conn.execute(
        f"SELECT {value_column} FROM {table} WHERE {key_column}=?", (lookup_key,)
    ).fetchone()
    return int(row[0]) if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Existing SQLite game database")
    parser.add_argument("--level-coins", action="append", type=_level_coin, default=[], metavar="LEVEL:COINS")
    parser.add_argument("--mode-level", action="append", type=_mode_level, default=[], metavar="MODE:LEVEL")
    parser.add_argument("--apply", action="store_true", help="Write the previewed rules atomically")
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error("database file does not exist")
    if not args.level_coins and not args.mode_level:
        parser.error("provide at least one rule")
    if (len({level for level, _ in args.level_coins}) != len(args.level_coins)
            or len({mode for mode, _ in args.mode_level}) != len(args.mode_level)):
        parser.error("each level or mode may only be set once per run")

    changes = []
    with closing(sqlite3.connect(str(args.db), timeout=15)) as conn:
        for level, coins in args.level_coins:
            old = _existing(conn, "level_coin_rules", "level", "coins", level)
            changes.append({"type": "level_coins", "key": level, "old": old, "new": coins})
        for mode, level in args.mode_level:
            old = _existing(conn, "mode_unlock_rules", "mode", "min_level", mode)
            changes.append({"type": "mode_level", "key": mode, "old": old or DEFAULT_MODE_LEVELS[mode], "new": level})
        if args.apply:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                ensure_level_reward_schema(conn)
                ensure_mode_access_schema(conn)
                for level, coins in args.level_coins:
                    conn.execute(
                        """INSERT INTO level_coin_rules(level,coins) VALUES(?,?)
                           ON CONFLICT(level) DO UPDATE SET coins=excluded.coins""",
                        (level, coins),
                    )
                for mode, level in args.mode_level:
                    conn.execute(
                        """INSERT INTO mode_unlock_rules(mode,min_level) VALUES(?,?)
                           ON CONFLICT(mode) DO UPDATE SET min_level=excluded.min_level""",
                        (mode, level),
                    )
    print(json.dumps({"applied": args.apply, "database": str(args.db), "changes": changes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
