"""Pay a weekly leaderboard snapshot at most once per period."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from systems.phase2_systems import LevelSystem, XP_SOURCES


class WeeklyRewardsSystem:
    COINS_BY_RANK = {1: 100, 2: 50, 3: 30}

    def __init__(self, db):
        self.db = db

    def leaderboard_for_period(self, start_utc: datetime, end_utc: datetime) -> list[dict]:
        """Rank positive fight-history scores in one completed, fixed interval."""
        with closing(sqlite3.connect(self.db.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT fh.user_id, SUM(COALESCE(fh.score_gained, 0)) AS period_score
                FROM fight_history fh
                JOIN players p ON p.user_id=fh.user_id
                WHERE datetime(fh.fought_at) >= datetime(?)
                  AND datetime(fh.fought_at) < datetime(?)
                GROUP BY fh.user_id
                HAVING period_score > 0
                ORDER BY period_score DESC, fh.user_id ASC
                LIMIT 10
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()
        return [{"user_id": user_id, "period_score": score} for user_id, score in rows]

    def distribute(self, period_key: str, leaderboard: list[dict]) -> list[tuple[int, int, int]]:
        from systems.progression_config import enabled
        if enabled(self.db):
            from systems.progression_leaderboard import ProgressionLeaderboard
            return ProgressionLeaderboard(self.db).settle('weekly')
        """Atomically record the period and pay its top ten players.

        An empty return value means the period was already paid or had no winners.
        """
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_reward_batches (
                    period_key TEXT PRIMARY KEY,
                    awards_json TEXT NOT NULL,
                    awarded_at TEXT NOT NULL
                )
            """)
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM weekly_reward_batches WHERE period_key=?", (period_key,)
            ).fetchone():
                conn.rollback()
                return []

            awarded = []
            for rank, player in enumerate(leaderboard[:10], 1):
                user_id = int(player["user_id"])
                coins = self.COINS_BY_RANK.get(rank, 10)
                xp = XP_SOURCES.get(f"weekly_rank_{rank}", 0)
                if conn.execute(
                    "UPDATE players SET coins=coins+? WHERE user_id=?", (coins, user_id)
                ).rowcount != 1:
                    raise ValueError(f"Weekly winner {user_id} has no player record")
                if xp:
                    conn.execute(
                        "INSERT OR IGNORE INTO player_progression(user_id) VALUES(?)", (user_id,)
                    )
                    old_level, old_xp = conn.execute(
                        "SELECT level,total_xp FROM player_progression WHERE user_id=?", (user_id,)
                    ).fetchone()
                    total_xp = old_xp + xp
                    new_level = LevelSystem.get_level_from_xp(total_xp)
                    conn.execute(
                        "UPDATE player_progression SET total_xp=?, level=? WHERE user_id=?",
                        (total_xp, new_level, user_id),
                    )
                    from systems.level_rewards_system import LevelRewardsSystem
                    LevelRewardsSystem.grant_crossed_in(conn, user_id, int(old_level or 1), new_level)
                awarded.append((rank, user_id, coins))

            conn.execute(
                "INSERT INTO weekly_reward_batches(period_key,awards_json,awarded_at) VALUES(?,?,?)",
                (period_key, json.dumps(awarded), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return awarded
