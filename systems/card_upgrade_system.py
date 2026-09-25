"""Transactional card upgrades shared by the bot and Mini App."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from systems.economy_system import EconomySystem
from systems.phase2_systems import LevelSystem


logger = logging.getLogger(__name__)


class CardUpgradeSystem:
    UPGRADES = {
        "normal_to_epic": {"source": "normal", "target": "epic", "price_key": "upgrade_normal_to_epic", "xp": 15},
        "epic_to_legend": {"source": "epic", "target": "legend", "price_key": "upgrade_epic_to_legend", "xp": 30},
    }

    def __init__(self, db):
        self.db = db

    def _active_match(self, conn: sqlite3.Connection, user_id: int) -> bool:
        row = conn.execute(
            """
            SELECT 1 FROM active_fights
            WHERE (challenger_id=? OR opponent_id=?)
              AND status NOT IN ('completed', 'cancelled', 'expired')
            LIMIT 1
            """,
            (user_id, user_id),
        ).fetchone()
        if row:
            return True
        try:
            row = conn.execute(
                "SELECT 1 FROM solo_fights WHERE player_id=? AND status!='completed' LIMIT 1",
                (user_id,),
            ).fetchone()
            if row:
                return True
        except sqlite3.OperationalError:
            pass
        try:
            rows = conn.execute(
                """
                SELECT r.mode, r.status, r.expires_at, s.state_json
                FROM game_requests r
                LEFT JOIN game_match_states s ON s.request_id=r.request_id
                WHERE (r.creator_id=? OR r.opponent_id=?)
                  AND r.status IN ('accepted', 'active')
                """,
                (user_id, user_id),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for mode, status, expires_at, state_json in rows:
            if status == "accepted":
                # Deck matches live in active_fights; their accepted request
                # is not advanced when the fight finishes.
                if mode == "deck":
                    continue
                deadline = expires_at
            else:
                try:
                    state = json.loads(state_json or "{}")
                    if state.get("phase") in ("completed", "finished"):
                        continue
                    deadline = state.get("deadline")
                except (TypeError, ValueError):
                    continue
            try:
                if not deadline:
                    continue
                expires = datetime.fromisoformat(str(deadline))
                if expires.tzinfo is not None:
                    expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
                if expires > now:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def is_management_locked(self, user_id: int) -> bool:
        conn = sqlite3.connect(self.db.db_path)
        try:
            return self._active_match(conn, user_id)
        finally:
            conn.close()

    def preview(self, user_id: int, card_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT c.name, COALESCE(pc.rarity_override, c.rarity) AS rarity,
                       p.coins
                FROM player_cards pc
                JOIN cards c ON c.card_id=pc.card_id
                JOIN players p ON p.user_id=pc.user_id
                WHERE pc.user_id=? AND pc.card_id=?
                """,
                (user_id, card_id),
            ).fetchone()
            if not row:
                return {"ok": False, "error_code": "card_not_owned", "error": "کارت در کلکسیون شما نیست"}
            upgrade_key = next((key for key, value in self.UPGRADES.items() if value["source"] == row["rarity"]), None)
            if not upgrade_key:
                return {"ok": False, "error_code": "not_upgradeable", "error": "این کارت قابلیت ارتقای بیشتر ندارد"}
            rule = self.UPGRADES[upgrade_key]
            variant = conn.execute(
                "SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?",
                (card_id, rule["target"]),
            ).fetchone()
            if not variant:
                return {"ok": False, "error_code": "variant_unavailable", "error": "نسخه ارتقایافته این کارت هنوز آماده نیست"}
            price = EconomySystem.PRICES[rule["price_key"]]
            return {
                "ok": True,
                "upgrade_key": upgrade_key,
                "card_id": card_id,
                "card_name": row["name"],
                "from_rarity": rule["source"],
                "to_rarity": rule["target"],
                "price": price,
                "xp": rule["xp"],
                "coins": int(row["coins"] or 0),
                "can_afford": int(row["coins"] or 0) >= price,
                "blocked_by_match": self._active_match(conn, user_id),
            }
        finally:
            conn.close()

    def upgrade(self, user_id: int, card_id: str, upgrade_key: str) -> Dict[str, Any]:
        rule = self.UPGRADES.get(upgrade_key)
        if not rule:
            return {"ok": False, "error_code": "invalid_upgrade", "error": "نوع ارتقا نامعتبر است"}
        price = EconomySystem.PRICES[rule["price_key"]]
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            if self._active_match(conn, user_id):
                conn.rollback()
                return {"ok": False, "error_code": "active_match", "error": "تا پایان مسابقه نمی‌توانی کارت را ارتقا بدهی"}
            row = conn.execute(
                """
                SELECT pc.id, c.name, COALESCE(pc.rarity_override, c.rarity) AS rarity,
                       p.coins
                FROM player_cards pc
                JOIN cards c ON c.card_id=pc.card_id
                JOIN players p ON p.user_id=pc.user_id
                WHERE pc.user_id=? AND pc.card_id=?
                """,
                (user_id, card_id),
            ).fetchone()
            if not row:
                conn.rollback()
                return {"ok": False, "error_code": "card_not_owned", "error": "کارت در کلکسیون شما نیست"}
            if row["rarity"] != rule["source"]:
                conn.rollback()
                return {"ok": False, "error_code": "rarity_changed", "error": "وضعیت کارت تغییر کرده؛ صفحه را تازه کن"}
            if not conn.execute(
                "SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?",
                (card_id, rule["target"]),
            ).fetchone():
                conn.rollback()
                return {"ok": False, "error_code": "variant_unavailable", "error": "نسخه ارتقایافته این کارت هنوز آماده نیست"}
            if int(row["coins"] or 0) < price:
                conn.rollback()
                return {"ok": False, "error_code": "insufficient_coins", "error": "سکه کافی نیست"}

            coin_update = conn.execute(
                "UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?",
                (price, user_id, price),
            )
            if coin_update.rowcount != 1:
                conn.rollback()
                return {"ok": False, "error_code": "insufficient_coins", "error": "سکه کافی نیست"}
            card_update = conn.execute(
                "UPDATE player_cards SET rarity_override=? WHERE id=? AND COALESCE(rarity_override, ?) = ?",
                (rule["target"], row["id"], rule["source"], rule["source"]),
            )
            if card_update.rowcount != 1:
                raise RuntimeError("card upgrade race detected")

            conn.execute(
                """
                INSERT OR IGNORE INTO player_progression
                    (user_id, level, total_xp, tier_points, current_tier, last_played_at)
                VALUES (?, 1, 0, 0, 'Bronze', CURRENT_TIMESTAMP)
                """,
                (user_id,),
            )
            progression = conn.execute(
                "SELECT level, total_xp FROM player_progression WHERE user_id=?",
                (user_id,),
            ).fetchone()
            old_level = int(progression["level"] or 1)
            total_xp = int(progression["total_xp"] or 0) + int(rule["xp"])
            new_level = LevelSystem.get_level_from_xp(total_xp)
            conn.execute(
                "UPDATE player_progression SET total_xp=?, level=? WHERE user_id=?",
                (total_xp, new_level, user_id),
            )
            conn.commit()
            return {
                "ok": True,
                "card_id": card_id,
                "card_name": row["name"],
                "from_rarity": rule["source"],
                "to_rarity": rule["target"],
                "price": price,
                "xp_gained": rule["xp"],
                "old_level": old_level,
                "new_level": new_level,
                "coins": int(row["coins"] or 0) - price,
            }
        except Exception:
            conn.rollback()
            logger.exception("Transactional card upgrade failed")
            return {"ok": False, "error_code": "upgrade_failed", "error": "ارتقای کارت انجام نشد"}
        finally:
            conn.close()
