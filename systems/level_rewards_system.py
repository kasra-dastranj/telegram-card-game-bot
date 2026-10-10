"""Configurable, one-time coin grants when XP crosses a level threshold."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone


def ensure_level_reward_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS level_coin_rules (
        level INTEGER PRIMARY KEY CHECK(level BETWEEN 2 AND 30),
        coins INTEGER NOT NULL CHECK(coins >= 0)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS player_level_coin_awards (
        user_id INTEGER NOT NULL,
        level INTEGER NOT NULL,
        coins INTEGER NOT NULL CHECK(coins >= 0),
        awarded_at TEXT NOT NULL,
        PRIMARY KEY(user_id,level),
        FOREIGN KEY(user_id) REFERENCES players(user_id)
    )""")


class LevelRewardsSystem:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def grant_crossed_in(conn: sqlite3.Connection, user_id: int,
                         old_level: int, new_level: int) -> int:
        """Call inside the same write transaction as the XP award."""
        if new_level <= old_level:
            return 0
        # Matches started before cutover still settle with their old XP policy.
        # Their legacy award path must honor the owner's frozen level prizes.
        from systems.progression_config import enabled_in, config_in
        from systems.reward_ledger import capacities_in
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='foundation_settings'").fetchone():
            if enabled_in(conn) and capacities_in(conn, user_id, config_in(conn)[1])['legacy']:
                return 0
        total = 0
        rules = conn.execute(
            "SELECT level,coins FROM level_coin_rules WHERE level>? AND level<=? AND coins>0 ORDER BY level",
            (old_level, new_level),
        ).fetchall()
        for level, coins in rules:
            changed = conn.execute(
                """INSERT OR IGNORE INTO player_level_coin_awards(user_id,level,coins,awarded_at)
                   VALUES(?,?,?,?)""",
                (user_id, level, coins, datetime.now(timezone.utc).isoformat()),
            )
            if changed.rowcount == 1:
                if conn.execute(
                    "UPDATE players SET coins=coins+? WHERE user_id=?", (coins, user_id)
                ).rowcount != 1:
                    raise ValueError("level reward player missing")
                total += coins
        return total

    @staticmethod
    def add_xp_in(conn: sqlite3.Connection, user_id: int, amount: int) -> tuple[int, int]:
        """Atomic XP/level transition, used by legacy public XP helpers."""
        if type(amount) is not int or amount <= 0:
            raise ValueError("XP amount must be a positive integer")
        from systems.phase2_systems import LevelSystem

        row = conn.execute(
            "SELECT level,total_xp FROM player_progression WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            raise ValueError("player progression missing")
        old_level = int(row[0] or 1)
        total_xp = int(row[1] or 0) + amount
        new_level = LevelSystem.get_level_from_xp(total_xp)
        conn.execute(
            """UPDATE player_progression SET level=?,total_xp=?,last_played_at=?
               WHERE user_id=?""",
            (new_level, total_xp, datetime.now(timezone.utc).isoformat(), user_id),
        )
        LevelRewardsSystem.grant_crossed_in(conn, user_id, old_level, new_level)
        return old_level, new_level

    def set_coin_rule(self, level: int, coins: int) -> None:
        """Balance knob. Rules start empty until the trial values are chosen."""
        if type(level) is not int or not 2 <= level <= 30 or type(coins) is not int or coins < 0:
            raise ValueError("invalid level coin rule")
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO level_coin_rules(level,coins) VALUES(?,?)
                       ON CONFLICT(level) DO UPDATE SET coins=excluded.coins""",
                    (level, coins),
                )
