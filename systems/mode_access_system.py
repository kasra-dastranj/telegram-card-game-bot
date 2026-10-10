"""One source of truth for mode level gates across game entry points."""

from __future__ import annotations

import sqlite3
from contextlib import closing


DEFAULT_MODE_LEVELS = {
    "quick": 1,
    "deck": 1,
    "easy": 1,
    "mini_three_round": 1,
    "risk": 7,
}
MODE_LABELS = {"mini_three_round": "نبرد سه‌راندی", "quick": "Quick", "deck": "Deck", "easy": "Easy", "risk": "Risk"}


def ensure_mode_access_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS mode_unlock_rules (
        mode TEXT PRIMARY KEY,
        min_level INTEGER NOT NULL CHECK(min_level BETWEEN 1 AND 30)
    )""")
    conn.executemany(
        "INSERT OR IGNORE INTO mode_unlock_rules(mode,min_level) VALUES(?,?)",
        DEFAULT_MODE_LEVELS.items(),
    )


class ModeAccessSystem:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def check_in(conn: sqlite3.Connection, user_id: int, mode: str) -> tuple[bool, str]:
        if mode not in DEFAULT_MODE_LEVELS:
            raise ValueError("invalid mode")
        row = conn.execute(
            "SELECT min_level FROM mode_unlock_rules WHERE mode=?", (mode,)
        ).fetchone()
        min_level = int(row[0]) if row else DEFAULT_MODE_LEVELS[mode]
        from systems.progression_config import enabled_in, config_in
        if enabled_in(conn):
            min_level = config_in(conn)[1]['mode_levels'][mode]
        progression = conn.execute(
            "SELECT level FROM player_progression WHERE user_id=?", (user_id,)
        ).fetchone()
        level = int(progression[0]) if progression else 1
        if level < min_level:
            return False, f"برای ورود به {MODE_LABELS[mode]} باید Level {min_level} باشید (Level فعلی: {level})"
        return True, ""

    def check(self, user_id: int, mode: str) -> tuple[bool, str]:
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            return self.check_in(conn, user_id, mode)

    def min_level(self, mode: str) -> int:
        if mode not in DEFAULT_MODE_LEVELS:
            raise ValueError("invalid mode")
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            from systems.progression_config import enabled_in, config_in
            if enabled_in(conn):
                return config_in(conn)[1]['mode_levels'][mode]
            row = conn.execute(
                "SELECT min_level FROM mode_unlock_rules WHERE mode=?", (mode,)
            ).fetchone()
        return int(row[0]) if row else DEFAULT_MODE_LEVELS[mode]

    def set_min_level(self, mode: str, level: int) -> None:
        """Set a reversible trial rule; defaults preserve the shipped gates."""
        if mode not in DEFAULT_MODE_LEVELS or type(level) is not int or not 1 <= level <= 30:
            raise ValueError("invalid mode level rule")
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO mode_unlock_rules(mode,min_level) VALUES(?,?)
                       ON CONFLICT(mode) DO UPDATE SET min_level=excluded.min_level""",
                    (mode, level),
                )
