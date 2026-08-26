"""Transactional Claim, card mission rewards, and skin management."""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List

from systems.card_missions_system import MISSION_TYPES
from systems.phase2_systems import LevelSystem


class PlayerRewardsSystem:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _claim_status_from(last_claim: str | None) -> Dict[str, Any]:
        now = datetime.now()
        if last_claim:
            try:
                claimed = datetime.fromisoformat(last_claim)
                if claimed.date() == now.date():
                    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
                    return {"can_claim": False, "remaining_seconds": max(0, int((midnight - now).total_seconds()))}
            except ValueError:
                pass
        return {"can_claim": True, "remaining_seconds": 0}

    def claim_status(self, user_id: int) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path)
        try:
            row = conn.execute("SELECT last_claim FROM players WHERE user_id=?", (user_id,)).fetchone()
            status = self._claim_status_from(row[0] if row else None)
            pool = conn.execute(
                """
                SELECT COUNT(*) FROM cards c
                WHERE c.rarity='normal' AND NOT EXISTS (
                    SELECT 1 FROM player_cards pc
                    WHERE pc.user_id=? AND pc.card_id=c.card_id
                      AND COALESCE(pc.rarity_override,c.rarity) IN ('epic','legend')
                )
                """,
                (user_id,),
            ).fetchone()[0]
            return {**status, "pool_count": int(pool)}
        finally:
            conn.close()

    def claim_daily(self, user_id: int) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            player = conn.execute("SELECT last_claim FROM players WHERE user_id=?", (user_id,)).fetchone()
            if not player:
                conn.rollback()
                return {"ok": False, "error_code": "player_not_found", "error": "بازیکن پیدا نشد"}
            status = self._claim_status_from(player["last_claim"])
            if not status["can_claim"]:
                conn.rollback()
                return {"ok": False, "error_code": "already_claimed", "error": "کارت روزانه امروز دریافت شده است", **status}
            rows = conn.execute(
                """
                SELECT c.card_id FROM cards c
                WHERE c.rarity='normal' AND NOT EXISTS (
                    SELECT 1 FROM player_cards pc
                    WHERE pc.user_id=? AND pc.card_id=c.card_id
                      AND COALESCE(pc.rarity_override,c.rarity) IN ('epic','legend')
                )
                """,
                (user_id,),
            ).fetchall()
            if not rows:
                rows = conn.execute("SELECT card_id FROM cards WHERE rarity='normal'").fetchall()
            if not rows:
                conn.rollback()
                return {"ok": False, "error_code": "empty_pool", "error": "کارتی برای دریافت وجود ندارد"}
            card_id = random.choice(rows)["card_id"]
            conn.execute(
                "INSERT OR IGNORE INTO player_cards(user_id,card_id,obtained_at) VALUES (?,?,?)",
                (user_id, card_id, datetime.now().isoformat()),
            )
            conn.execute("UPDATE players SET last_claim=? WHERE user_id=?", (datetime.now().isoformat(), user_id))
            conn.commit()
            return {"ok": True, "card_id": card_id}
        except Exception:
            conn.rollback()
            return {"ok": False, "error_code": "claim_failed", "error": "دریافت کارت انجام نشد"}
        finally:
            conn.close()

    def missions(self, user_id: int) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT m.card_id, c.name AS card_name, m.mission_type, m.target, m.target_card,
                       COALESCE(pm.current_progress,0) AS current_progress,
                       COALESCE(pm.completed,0) AS completed,
                       COALESCE(pm.reward_claimed,0) AS reward_claimed,
                       COALESCE(pc.rarity_override,c.rarity) AS rarity
                FROM card_missions m
                JOIN cards c ON c.card_id=m.card_id
                JOIN player_cards pc ON pc.card_id=m.card_id AND pc.user_id=?
                LEFT JOIN player_card_missions pm ON pm.user_id=? AND pm.card_id=m.card_id
                ORDER BY completed DESC, current_progress DESC, c.name COLLATE NOCASE
                """,
                (user_id, user_id),
            ).fetchall()
            result = []
            for row in rows:
                info = MISSION_TYPES.get(row["mission_type"], {})
                result.append({
                    "mission_id": row["card_id"], "card_id": row["card_id"], "card_name": row["card_name"],
                    "mission_type": row["mission_type"], "name": info.get("name_fa", "ماموریت کارت"),
                    "description": info.get("description", "").format(target=row["target"], target_card=row["target_card"] or ""),
                    "target": int(row["target"]), "current_progress": int(row["current_progress"]),
                    "progress_percent": min(100, int(int(row["current_progress"]) * 100 / max(1, int(row["target"])))),
                    "completed": bool(row["completed"]), "reward_claimed": bool(row["reward_claimed"]),
                    "rarity": row["rarity"], "can_claim": bool(row["completed"]) and not bool(row["reward_claimed"]) and row["rarity"] == "epic",
                })
            return result
        finally:
            conn.close()

    def claim_mission(self, user_id: int, card_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT pm.completed, pm.reward_claimed, c.name,
                       COALESCE(pc.rarity_override,c.rarity) AS rarity
                FROM player_card_missions pm
                JOIN player_cards pc ON pc.user_id=pm.user_id AND pc.card_id=pm.card_id
                JOIN cards c ON c.card_id=pm.card_id
                WHERE pm.user_id=? AND pm.card_id=?
                """,
                (user_id, card_id),
            ).fetchone()
            if not row:
                conn.rollback(); return {"ok": False, "error_code": "mission_not_found", "error": "ماموریت پیدا نشد"}
            if not row["completed"]:
                conn.rollback(); return {"ok": False, "error_code": "mission_incomplete", "error": "ماموریت هنوز کامل نشده است"}
            if row["reward_claimed"]:
                conn.rollback(); return {"ok": False, "error_code": "reward_claimed", "error": "پاداش قبلاً دریافت شده است"}
            if row["rarity"] != "epic":
                conn.rollback(); return {"ok": False, "error_code": "epic_required", "error": "این پاداش فقط برای نسخه Epic قابل دریافت است"}
            if not conn.execute("SELECT 1 FROM card_variants WHERE card_id=? AND rarity='legend'", (card_id,)).fetchone():
                conn.rollback(); return {"ok": False, "error_code": "variant_unavailable", "error": "نسخه Legend این کارت آماده نیست"}
            conn.execute("UPDATE player_cards SET rarity_override='legend' WHERE user_id=? AND card_id=?", (user_id, card_id))
            conn.execute("UPDATE player_card_missions SET reward_claimed=1,reward_claimed_at=? WHERE user_id=? AND card_id=? AND reward_claimed=0", (datetime.now().isoformat(), user_id, card_id))
            conn.execute("INSERT OR IGNORE INTO player_progression(user_id,level,total_xp,tier_points,current_tier,last_played_at) VALUES (?,1,0,0,'Bronze',CURRENT_TIMESTAMP)", (user_id,))
            xp = conn.execute("SELECT total_xp FROM player_progression WHERE user_id=?", (user_id,)).fetchone()[0] + 30
            conn.execute("UPDATE player_progression SET total_xp=?,level=? WHERE user_id=?", (xp, LevelSystem.get_level_from_xp(xp), user_id))
            conn.commit()
            return {"ok": True, "card_id": card_id, "card_name": row["name"], "xp_gained": 30}
        except Exception:
            conn.rollback(); return {"ok": False, "error_code": "mission_claim_failed", "error": "دریافت پاداش انجام نشد"}
        finally:
            conn.close()

    def skins(self, user_id: int, card_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        try:
            owned = conn.execute("SELECT 1 FROM player_cards WHERE user_id=? AND card_id=?", (user_id, card_id)).fetchone()
            if not owned:
                return {"ok": False, "error_code": "card_not_owned", "error": "کارت در کلکسیون شما نیست"}
            active = conn.execute("SELECT skin_id FROM active_skins WHERE user_id=? AND card_id=?", (user_id, card_id)).fetchone()
            rows = conn.execute(
                """
                SELECT s.*, CASE WHEN ps.skin_id IS NULL THEN 0 ELSE 1 END AS unlocked
                FROM skins s LEFT JOIN player_skins ps ON ps.skin_id=s.skin_id AND ps.user_id=?
                WHERE s.card_id=? ORDER BY s.price,s.name
                """,
                (user_id, card_id),
            ).fetchall()
            return {"ok": True, "active_skin_id": active[0] if active else None, "skins": [dict(row) for row in rows]}
        finally:
            conn.close()

    def purchase_skin(self, user_id: int, card_id: str, skin_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT s.price,p.coins FROM skins s JOIN players p ON p.user_id=?
                JOIN player_cards pc ON pc.user_id=p.user_id AND pc.card_id=s.card_id
                WHERE s.skin_id=? AND s.card_id=?
                """, (user_id, skin_id, card_id),
            ).fetchone()
            if not row:
                conn.rollback(); return {"ok": False, "error_code": "skin_not_accessible", "error": "پوسته برای این کارت در دسترس نیست"}
            if conn.execute("SELECT 1 FROM player_skins WHERE user_id=? AND skin_id=?", (user_id, skin_id)).fetchone():
                conn.rollback(); return {"ok": False, "error_code": "already_owned", "error": "این پوسته را قبلاً گرفته‌ای"}
            if row["coins"] < row["price"]:
                conn.rollback(); return {"ok": False, "error_code": "insufficient_coins", "error": "سکه کافی نیست"}
            conn.execute("UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?", (row["price"], user_id, row["price"]))
            conn.execute("INSERT INTO player_skins(user_id,skin_id,unlocked_at) VALUES (?,?,?)", (user_id, skin_id, datetime.now().isoformat()))
            conn.commit(); return {"ok": True, "skin_id": skin_id, "coins_spent": row["price"], "coins": row["coins"] - row["price"]}
        except Exception:
            conn.rollback(); return {"ok": False, "error_code": "skin_purchase_failed", "error": "خرید پوسته انجام نشد"}
        finally:
            conn.close()

    def activate_skin(self, user_id: int, card_id: str, skin_id: str | None) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT 1 FROM player_cards WHERE user_id=? AND card_id=?", (user_id, card_id)).fetchone():
                conn.rollback(); return {"ok": False, "error_code": "card_not_owned", "error": "کارت در کلکسیون شما نیست"}
            if skin_id and not conn.execute("SELECT 1 FROM skins s JOIN player_skins ps ON ps.skin_id=s.skin_id WHERE ps.user_id=? AND s.card_id=? AND s.skin_id=?", (user_id, card_id, skin_id)).fetchone():
                conn.rollback(); return {"ok": False, "error_code": "skin_not_owned", "error": "این پوسته را برای کارت انتخاب‌شده نداری"}
            if skin_id:
                conn.execute("INSERT OR REPLACE INTO active_skins(user_id,card_id,skin_id) VALUES (?,?,?)", (user_id, card_id, skin_id))
            else:
                conn.execute("DELETE FROM active_skins WHERE user_id=? AND card_id=?", (user_id, card_id))
            conn.commit(); return {"ok": True, "card_id": card_id, "skin_id": skin_id}
        except Exception:
            conn.rollback(); return {"ok": False, "error_code": "skin_activation_failed", "error": "فعال‌سازی پوسته انجام نشد"}
        finally:
            conn.close()
