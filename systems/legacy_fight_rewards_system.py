"""Atomic, replay-safe settlement for Telegram three-round/Deck fights."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from systems.match_rewards_system import MatchRewardsSystem
from systems.phase2_systems import TierSystem, XP_SOURCES


class LegacyFightRewardsSystem:
    RANK = {"normal": 1, "epic": 2, "legend": 3, "rare": 4}

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _rarity(value) -> str:
        return str(getattr(value, "value", value)).lower()

    def settle_three_round(self, fight_id: str, challenger_id: int, opponent_id: int,
                           challenger_card, opponent_card, result_type: str) -> dict:
        if result_type not in {"challenger_wins", "opponent_wins", "tie"}:
            raise ValueError("invalid fight result")
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("""CREATE TABLE IF NOT EXISTS fight_reward_settlements (
                    fight_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    settled_at TEXT NOT NULL
                )""")
                prior = conn.execute(
                    "SELECT payload FROM fight_reward_settlements WHERE fight_id=?", (fight_id,)
                ).fetchone()
                if prior:
                    return {**json.loads(prior[0]), "fresh": False}
                fight = conn.execute(
                    "SELECT challenger_id,opponent_id,status FROM active_fights WHERE fight_id=?",
                    (fight_id,),
                ).fetchone()
                if not fight or fight[0] != challenger_id or fight[1] != opponent_id:
                    raise ValueError("fight not found or players changed")
                if fight[2] in ("completed", "cancelled", "expired"):
                    raise ValueError("fight is no longer active")
                ledger_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='match_reward_events'"
                ).fetchone()
                if ledger_exists and conn.execute(
                    "SELECT 1 FROM match_reward_events WHERE request_id=? LIMIT 1",
                    (f"fight:{fight_id}",),
                ).fetchone():
                    raise ValueError("partial fight settlement exists")

                users = (challenger_id, opponent_id)
                old = {}
                for user_id in users:
                    row = conn.execute(
                        "SELECT level,current_tier FROM player_progression WHERE user_id=?",
                        (user_id,),
                    ).fetchone()
                    old[user_id] = {"level": int(row[0] or 1) if row else 1,
                                    "tier": str(row[1] or "Bronze") if row else "Bronze"}

                winner = challenger_id if result_type == "challenger_wins" else (
                    opponent_id if result_type == "opponent_wins" else None
                )
                score = 0
                if winner is not None:
                    mine = challenger_card if winner == challenger_id else opponent_card
                    rival = opponent_card if winner == challenger_id else challenger_card
                    my_rank = self.RANK.get(self._rarity(mine.rarity), 1)
                    their_rank = self.RANK.get(self._rarity(rival.rarity), 1)
                    score = 20 if my_rank < their_rank else 10 if my_rank == their_rank else 5
                    loser = opponent_id if winner == challenger_id else challenger_id
                    gain, loss = TierSystem.calculate_tp_change(
                        old[winner]["tier"], old[loser]["tier"]
                    )
                else:
                    loser = None
                    gain = loss = 0
                awards = {}
                for user_id, rival_id, card, other in (
                    (challenger_id, opponent_id, challenger_card, opponent_card),
                    (opponent_id, challenger_id, opponent_card, challenger_card),
                ):
                    won = user_id == winner
                    awards[user_id] = {
                        "result": "tie" if winner is None else "win" if won else "loss",
                        "xp": XP_SOURCES["normal_win"] if won else XP_SOURCES["normal_loss"],
                        "score": score if won else 0,
                        "hearts_lost": 1 if user_id == loser else 0,
                        "tp_delta": gain if won else -loss if user_id == loser else 0,
                        "card_id": card.card_id,
                        "opponent_card_id": other.card_id,
                        "opponent_id": rival_id,
                    }
                paid = MatchRewardsSystem.award(conn, f"fight:{fight_id}", "pvp", awards)
                result = {"awards": {}, "result_type": result_type}
                for user_id in users:
                    row = conn.execute(
                        "SELECT level,current_tier FROM player_progression WHERE user_id=?",
                        (user_id,),
                    ).fetchone()
                    result["awards"][str(user_id)] = {
                        **paid[str(user_id)],
                        "hearts_lost": awards[user_id]["hearts_lost"],
                        "tp_delta": awards[user_id]["tp_delta"],
                        "old_level": old[user_id]["level"],
                        "new_level": int(row[0]),
                        "old_tier": old[user_id]["tier"],
                        "new_tier": row[1],
                    }
                conn.execute("UPDATE active_fights SET status='completed' WHERE fight_id=?", (fight_id,))
                conn.execute(
                    "INSERT INTO fight_reward_settlements(fight_id,payload,settled_at) VALUES(?,?,?)",
                    (fight_id, json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
                )
                return {**result, "fresh": True}

    def settle_single_round(self, fight_id: str, challenger_id: int, opponent_id: int,
                            result_type: str, awards: dict[int, dict]) -> dict:
        """Settle the older one-round PvP rules without changing their score formula."""
        if result_type not in {"challenger_wins", "opponent_wins", "tie"}:
            raise ValueError("invalid fight result")
        if set(awards) != {challenger_id, opponent_id}:
            raise ValueError("both fight players need an award record")
        with closing(sqlite3.connect(self.db.db_path, timeout=15)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("""CREATE TABLE IF NOT EXISTS fight_reward_settlements (
                    fight_id TEXT PRIMARY KEY,payload TEXT NOT NULL,settled_at TEXT NOT NULL
                )""")
                prior = conn.execute(
                    "SELECT payload FROM fight_reward_settlements WHERE fight_id=?", (fight_id,)
                ).fetchone()
                if prior:
                    return {**json.loads(prior[0]), "fresh": False}
                fight = conn.execute(
                    "SELECT challenger_id,opponent_id,status FROM active_fights WHERE fight_id=?",
                    (fight_id,),
                ).fetchone()
                if not fight or (fight[0], fight[1]) != (challenger_id, opponent_id):
                    raise ValueError("fight not found or players changed")
                if fight[2] in ("completed", "cancelled", "expired"):
                    raise ValueError("fight is no longer active")
                ledger = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='match_reward_events'"
                ).fetchone()
                if ledger and conn.execute(
                    "SELECT 1 FROM match_reward_events WHERE request_id=? LIMIT 1",
                    (f"fight:{fight_id}",),
                ).fetchone():
                    raise ValueError("partial fight settlement exists")
                old = {}
                for uid in (challenger_id, opponent_id):
                    row = conn.execute(
                        "SELECT level,current_tier FROM player_progression WHERE user_id=?", (uid,)
                    ).fetchone()
                    old[uid] = {"level": int(row[0] or 1) if row else 1,
                                "tier": str(row[1] or "Bronze") if row else "Bronze"}
                winner = challenger_id if result_type == "challenger_wins" else (
                    opponent_id if result_type == "opponent_wins" else None
                )
                if winner is not None:
                    loser = opponent_id if winner == challenger_id else challenger_id
                    gain, loss = TierSystem.calculate_tp_change(
                        old[winner]["tier"], old[loser]["tier"]
                    )
                else:
                    loser = None
                    gain = loss = 0
                for uid in (challenger_id, opponent_id):
                    awards[uid] = {
                        **awards[uid],
                        "tp_delta": gain if uid == winner else -loss if uid == loser else 0,
                    }
                paid = MatchRewardsSystem.award(conn, f"fight:{fight_id}", "pvp", awards)
                result = {"awards": {}, "result_type": result_type}
                for uid in (challenger_id, opponent_id):
                    row = conn.execute(
                        "SELECT level,current_tier FROM player_progression WHERE user_id=?", (uid,)
                    ).fetchone()
                    result["awards"][str(uid)] = {
                        **paid[str(uid)],
                        "hearts_lost": int(awards[uid].get("hearts_lost", 0)),
                        "tp_delta": awards[uid]["tp_delta"],
                        "old_level": old[uid]["level"],
                        "new_level": int(row[0]),
                        "old_tier": old[uid]["tier"],
                        "new_tier": row[1],
                    }
                conn.execute("UPDATE active_fights SET status='completed' WHERE fight_id=?", (fight_id,))
                conn.execute(
                    "INSERT INTO fight_reward_settlements(fight_id,payload,settled_at) VALUES(?,?,?)",
                    (fight_id, json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
                )
                return {**result, "fresh": True}
