"""One-time XP and Score awards for completed real-player modes."""

from __future__ import annotations

from datetime import datetime, timezone

from systems.phase2_systems import LevelSystem, TierSystem, XP_SOURCES
from systems.level_rewards_system import LevelRewardsSystem


class MatchRewardsSystem:
    RARITY_RANK = {"normal": 1, "epic": 2, "legend": 3, "rare": 4}

    @classmethod
    def _card_rarity(cls, conn, user_id: int, card_id: str | None) -> int:
        if not card_id:
            return 1
        row = conn.execute(
            """SELECT COALESCE(pc.rarity_override,c.rarity)
               FROM player_cards pc JOIN cards c ON c.card_id=pc.card_id
               WHERE pc.user_id=? AND pc.card_id=?""",
            (user_id, card_id),
        ).fetchone()
        return cls.RARITY_RANK.get(str(row[0]).lower(), 1) if row else 1

    @classmethod
    def normal_pvp_awards(cls, conn, players: list[int], winner_id: int | None,
                          cards: dict[str, str]) -> dict[int, dict]:
        """Use the Telegram three-round XP and 5/10/20 rarity Score rule."""
        first, second = players
        result = {}
        for user_id, opponent_id in ((first, second), (second, first)):
            won = winner_id == user_id
            score = 0
            if won:
                own = cls._card_rarity(conn, user_id, cards.get(str(user_id)))
                other = cls._card_rarity(conn, opponent_id, cards.get(str(opponent_id)))
                score = 20 if own < other else 10 if own == other else 5
            result[user_id] = {
                "result": "tie" if winner_id is None else "win" if won else "loss",
                "xp": XP_SOURCES["normal_win"] if won else XP_SOURCES["normal_loss"],
                "score": score,
                "card_id": cards.get(str(user_id)),
                "opponent_card_id": cards.get(str(opponent_id)),
                "opponent_id": opponent_id,
            }
        return result

    @staticmethod
    def easy_awards(players: list[int], winner_ids: list[int],
                    cards: dict[str, str]) -> dict[int, dict]:
        """Award once per full Easy session; no single opposing rarity exists."""
        sole_winner = winner_ids[0] if len(winner_ids) == 1 else None
        awards = {}
        for user_id in players:
            won = sole_winner == user_id
            awards[user_id] = {
                "result": "win" if won else "tie" if user_id in winner_ids else "loss",
                "xp": XP_SOURCES["normal_win"] if won else XP_SOURCES["normal_loss"],
                "score": 10 if won else 0,
                "card_id": cards.get(str(user_id)),
                "opponent_card_id": None,
                "opponent_id": None,
            }
        return awards

    @staticmethod
    def award(conn, request_id: str, mode: str, awards: dict[int, dict]) -> dict[str, dict]:
        """Run inside the match-completion transaction. Retry returns prior awards."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_reward_events (
                request_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                xp INTEGER NOT NULL,
                score INTEGER NOT NULL,
                hearts_lost INTEGER NOT NULL DEFAULT 0,
                tp_delta INTEGER NOT NULL DEFAULT 0,
                awarded_at TEXT NOT NULL,
                PRIMARY KEY(request_id,user_id)
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(match_reward_events)")}
        if "hearts_lost" not in columns:
            conn.execute("ALTER TABLE match_reward_events ADD COLUMN hearts_lost INTEGER NOT NULL DEFAULT 0")
        if "tp_delta" not in columns:
            conn.execute("ALTER TABLE match_reward_events ADD COLUMN tp_delta INTEGER NOT NULL DEFAULT 0")
        result = {}
        now = datetime.now(timezone.utc).isoformat()
        for user_id, item in awards.items():
            prior = conn.execute(
                "SELECT xp,score FROM match_reward_events WHERE request_id=? AND user_id=?",
                (request_id, user_id),
            ).fetchone()
            if prior:
                result[str(user_id)] = {"xp": prior[0], "score": prior[1]}
                continue
            xp, score = int(item["xp"]), int(item["score"])
            hearts_lost, tp_delta = int(item.get("hearts_lost", 0)), int(item.get("tp_delta", 0))
            if xp < 0 or score < 0 or hearts_lost < 0:
                raise ValueError("negative_match_reward")
            if conn.execute(
                """UPDATE players SET total_score=total_score+?,
                   hearts=MAX(0,COALESCE(hearts,0)-?) WHERE user_id=?""",
                (score, hearts_lost, user_id)
            ).rowcount != 1:
                raise ValueError(f"Match player {user_id} has no player record")
            conn.execute("INSERT OR IGNORE INTO player_progression(user_id) VALUES(?)", (user_id,))
            old_level, total_xp, tier_points, current_tier = conn.execute(
                "SELECT level,total_xp,tier_points,current_tier FROM player_progression WHERE user_id=?", (user_id,)
            ).fetchone()
            total_xp = int(total_xp or 0) + xp
            tier_points = max(0, int(tier_points or 0) + tp_delta)
            tier = TierSystem.get_tier_from_tp(tier_points) if tp_delta else current_tier
            new_level = LevelSystem.get_level_from_xp(total_xp)
            conn.execute(
                """UPDATE player_progression SET total_xp=?,level=?,tier_points=?,
                   current_tier=?,last_played_at=? WHERE user_id=?""",
                (total_xp, new_level, tier_points,
                 tier, now, user_id),
            )
            LevelRewardsSystem.grant_crossed_in(conn, user_id, int(old_level or 1), new_level)
            conn.execute(
                """INSERT INTO fight_history
                   (user_id,user_card_id,opponent_card_id,stat_used,result,score_gained,
                    hearts_lost,fought_at,fight_type,opponent_user_id,xp_gained)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, item.get("card_id"), item.get("opponent_card_id"),
                 item.get("stat_used"), item["result"], score, hearts_lost,
                 now, mode, item.get("opponent_id"), xp),
            )
            conn.execute(
                """INSERT INTO match_reward_events
                   (request_id,user_id,mode,xp,score,hearts_lost,tp_delta,awarded_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (request_id, user_id, mode, xp, score, hearts_lost, tp_delta, now),
            )
            card_id = item.get("card_id")
            if card_id and item["result"] == "win":
                mission = conn.execute(
                    "SELECT mission_type,target,target_card FROM card_missions WHERE card_id=?",
                    (card_id,),
                ).fetchone()
                if mission:
                    mission_type, target, target_card = mission
                    eligible = (mission_type == "total_wins"
                                or mission_type == "risk_wins" and mode == "risk"
                                or mission_type == "defeat_specific" and item.get("opponent_card_id") == target_card
                                or mission_type in ("power_wins", "speed_wins", "iq_wins", "popularity_wins")
                                and item.get("stat_used") == mission_type.removesuffix("_wins"))
                    if eligible and target > 0:
                        conn.execute(
                            """INSERT OR IGNORE INTO player_card_missions
                               (user_id,card_id,current_progress,completed) VALUES(?,?,0,0)""",
                            (user_id, card_id),
                        )
                        conn.execute(
                            """UPDATE player_card_missions SET
                               current_progress=MIN(?,current_progress+1),
                               completed=CASE WHEN current_progress+1>=? THEN 1 ELSE 0 END,
                               completed_at=CASE WHEN current_progress+1>=? THEN COALESCE(completed_at,?) ELSE completed_at END
                               WHERE user_id=? AND card_id=? AND completed=0 AND reward_claimed=0""",
                            (target, target, target, now, user_id, card_id),
                        )
            result[str(user_id)] = {"xp": xp, "score": score}
        return result
