#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔮 TelBattle Phase 2 - Fusion System
سیستم Fusion: ارتقای کارت‌ها از Normal به Epic و Epic به Legend
"""

import sqlite3
import logging
from typing import List, Tuple, Optional, Dict
from datetime import datetime

from game_core import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.card_action_requests import lookup_in, record_in

logger = logging.getLogger(__name__)


class FusionResult:
    """نتیجه Fusion"""
    def __init__(self, success: bool, upgraded_card: Optional[Card] = None,
                 consumed_cards: Optional[List[Card]] = None, error: Optional[str] = None,
                 xp_gained: int = 0, old_level: int = 1, new_level: int = 1,
                 replayed: bool = False, error_code: Optional[str] = None):
        self.success = success
        self.upgraded_card = upgraded_card
        self.consumed_cards = consumed_cards or []
        self.error = error
        self.xp_gained = xp_gained
        self.old_level = old_level
        self.new_level = new_level
        self.replayed = replayed
        self.error_code = error_code


class FusionSystem:
    """
    سیستم Fusion فاز ۲
    
    قوانین:
    - بازیکن 3 کارت انتخاب می‌کند
    - بازیکن تصمیم می‌گیرد کدام یک ارتقا یابد
    - همیشه موفق (100%)
    - 2 کارت دیگر به pool بازمی‌گردند (فقط در Normal→Epic)
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db

    @staticmethod
    def _card_snapshot_in(conn: sqlite3.Connection, user_id: int, card_id: str) -> Optional[Card]:
        row = conn.execute(
            """SELECT c.card_id,c.name,COALESCE(pc.rarity_override,c.rarity) AS rarity,
                      COALESCE(v.power,c.power) AS power,COALESCE(v.speed,c.speed) AS speed,
                      COALESCE(v.iq,c.iq) AS iq,COALESCE(v.popularity,c.popularity) AS popularity,
                      COALESCE(v.abilities,c.abilities) AS abilities,
                      COALESCE(v.card_effects,c.card_effects) AS card_effects,
                      c.dialogs,c.biography,COALESCE(v.image_path,c.image_path) AS image_path,
                      COALESCE(v.card_type,c.card_type) AS card_type,c.created_at
               FROM cards c JOIN player_cards pc ON pc.card_id=c.card_id AND pc.user_id=?
               LEFT JOIN card_variants v ON v.card_id=c.card_id
                   AND v.rarity=COALESCE(pc.rarity_override,c.rarity)
               WHERE c.card_id=?""",
            (user_id, card_id),
        ).fetchone()
        return Card.from_dict(dict(row)) if row else None
    
    def can_fuse_to_epic(self, user_id: int) -> Tuple[bool, List[Card]]:
        """
        بررسی امکان Fusion به Epic
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            (can_fuse, available_normal_cards)
        """
        player_cards = self.db.get_player_cards(user_id)
        normal_cards = [c for c in player_cards if c.rarity == CardRarity.NORMAL]
        
        can_fuse = len(normal_cards) >= 3
        logger.info(f"User {user_id} can_fuse_to_epic: {can_fuse} ({len(normal_cards)} Normal cards)")
        
        return can_fuse, normal_cards
    
    def can_fuse_to_legend(self, user_id: int) -> Tuple[bool, List[Card]]:
        """
        بررسی امکان Fusion به Legend
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            (can_fuse, available_epic_cards)
        """
        player_cards = self.db.get_player_cards(user_id)
        epic_cards = [c for c in player_cards if c.rarity == CardRarity.EPIC]
        
        can_fuse = len(epic_cards) >= 3
        logger.info(f"User {user_id} can_fuse_to_legend: {can_fuse} ({len(epic_cards)} Epic cards)")
        
        return can_fuse, epic_cards
    
    def validate_fusion_cards(self, user_id: int, card_ids: List[str], 
                             selected_card_id: str, target_rarity: CardRarity) -> Tuple[bool, Optional[str]]:
        """
        اعتبارسنجی کارت‌های Fusion
        
        Args:
            user_id: شناسه بازیکن
            card_ids: لیست 3 card_id
            selected_card_id: card_id کارت انتخاب شده برای ارتقا
            target_rarity: rarity مورد نظر (NORMAL یا EPIC)
            
        Returns:
            (is_valid, error_message)
        """
        # بررسی تعداد
        if len(card_ids) != 3:
            return False, f"باید دقیقاً 3 کارت انتخاب کنید (انتخاب شده: {len(card_ids)})"
        
        # بررسی تکراری نبودن
        if len(set(card_ids)) != 3:
            return False, "کارت‌های تکراری انتخاب شده‌اند"
        
        # بررسی اینکه selected_card_id در card_ids باشد
        if selected_card_id not in card_ids:
            return False, "کارت انتخاب شده باید یکی از 3 کارت باشد"
        
        # دریافت کارت‌های بازیکن
        player_cards = self.db.get_player_cards(user_id)
        player_card_ids = {c.card_id: c for c in player_cards}
        
        # بررسی مالکیت
        for card_id in card_ids:
            if card_id not in player_card_ids:
                return False, f"کارت {card_id} در موجودی شما نیست"
        
        # بررسی rarity
        for card_id in card_ids:
            card = player_card_ids[card_id]
            if card.rarity != target_rarity:
                expected = "Normal" if target_rarity == CardRarity.NORMAL else "Epic"
                return False, f"همه کارت‌ها باید {expected} باشند"
        
        return True, None

    def preview(self, user_id: int, card_ids: List[str], selected_card_id: str, target: str) -> Dict:
        source = CardRarity.NORMAL if target == "epic" else CardRarity.EPIC if target == "legend" else None
        if source is None:
            return {"ok": False, "error_code": "invalid_target", "error": "هدف Fusion نامعتبر است"}
        ok, error = self.validate_fusion_cards(user_id, card_ids, selected_card_id, source)
        if not ok:
            return {"ok": False, "error_code": "invalid_fusion", "error": error}
        if not self.db.get_card_variant(selected_card_id, target):
            return {"ok": False, "error_code": "variant_unavailable", "error": f"نسخه {target.title()} کارت انتخاب‌شده آماده نیست"}
        cards = [self.db.get_card_by_id_for_player(card_id, user_id) for card_id in card_ids]
        return {
            "ok": True,
            "target_rarity": target,
            "source_rarity": source.value,
            "retained_card_id": selected_card_id,
            "consumed_card_ids": [card_id for card_id in card_ids if card_id != selected_card_id],
            "cards": [card for card in cards if card],
            "xp": 15 if target == "epic" else 30,
        }

    def _fuse_atomic(self, user_id: int, card_ids: List[str], selected_card_id: str,
                     target: str, request_key: Optional[str] = None) -> FusionResult:
        source = "normal" if target == "epic" else "epic" if target == "legend" else ""
        if len(card_ids) != 3 or len(set(card_ids)) != 3 or selected_card_id not in card_ids or not source:
            return FusionResult(False, error="انتخاب Fusion نامعتبر است")
        consumed_cards = [self.db.get_card_by_id_for_player(card_id, user_id) for card_id in card_ids]
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            payload = {"card_ids": sorted(card_ids), "selected_card_id": selected_card_id, "target": target}
            receipt = lookup_in(conn, user_id, request_key, "fusion_distinct", payload)
            if receipt is not None:
                conn.commit()
                return FusionResult(True, Card.from_dict(receipt["upgraded_card"]),
                                    [Card.from_dict(card) for card in receipt["consumed_cards"]],
                                    xp_gained=receipt["xp_gained"], old_level=receipt["old_level"],
                                    new_level=receipt["new_level"], replayed=True)
            from systems.card_upgrade_system import CardUpgradeSystem
            if CardUpgradeSystem(self.db)._active_match(conn, user_id):
                conn.rollback()
                return FusionResult(False, error="تا پایان مسابقه نمی‌توانی کارت‌ها را ترکیب کنی")
            placeholders = ",".join("?" for _ in card_ids)
            rows = conn.execute(
                f"""SELECT pc.card_id, COALESCE(pc.rarity_override,c.rarity) AS rarity
                    FROM player_cards pc JOIN cards c ON c.card_id=pc.card_id
                    WHERE pc.user_id=? AND pc.card_id IN ({placeholders})""",
                (user_id, *card_ids),
            ).fetchall()
            if len(rows) != 3 or any(row["rarity"] != source for row in rows):
                conn.rollback()
                return FusionResult(False, error=f"هر سه کارت باید {source.title()} و متعلق به شما باشند")
            if not conn.execute("SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?", (selected_card_id, target)).fetchone():
                conn.rollback()
                return FusionResult(False, error=f"نسخه {target.title()} کارت انتخاب‌شده آماده نیست")
            for card_id in card_ids:
                if not CardInventorySystem.consume_in(conn, user_id, card_id, source):
                    raise RuntimeError("fusion_source_missing")
            CardInventorySystem.grant_in(conn, user_id, selected_card_id, target)
            for card_id in card_ids:
                CardInventorySystem.reconcile_active_in(conn, user_id, card_id)
            consumed_ids = [card_id for card_id in card_ids if card_id != selected_card_id]
            conn.execute(
                """INSERT INTO fusion_log(user_id,fusion_type,consumed_card_1,consumed_card_2,consumed_card_3,upgraded_card_id,result_rarity,timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, f"{source.upper()}_TO_{target.upper()}", card_ids[0], card_ids[1], card_ids[2], selected_card_id, target.upper(), datetime.now().isoformat()),
            )
            conn.execute("INSERT OR IGNORE INTO player_progression(user_id,level,total_xp,tier_points,current_tier,last_played_at) VALUES (?,1,0,0,'Bronze',CURRENT_TIMESTAMP)", (user_id,))
            progression = conn.execute("SELECT level,total_xp FROM player_progression WHERE user_id=?", (user_id,)).fetchone()
            xp_gained = 15 if target == "epic" else 30
            old_level = int(progression["level"] or 1)
            total_xp = int(progression["total_xp"] or 0) + xp_gained
            from systems.phase2_systems import LevelSystem
            new_level = LevelSystem.get_level_from_xp(total_xp)
            conn.execute("UPDATE player_progression SET total_xp=?,level=? WHERE user_id=?", (total_xp, new_level, user_id))
            from systems.level_rewards_system import LevelRewardsSystem
            LevelRewardsSystem.grant_crossed_in(conn, user_id, old_level, new_level)
            upgraded = self._card_snapshot_in(conn, user_id, selected_card_id)
            record_in(conn, user_id, request_key, "fusion_distinct", payload,
                      {"xp_gained": xp_gained, "old_level": old_level, "new_level": new_level,
                       "upgraded_card": upgraded.to_dict(),
                       "consumed_cards": [card.to_dict() for card in consumed_cards if card]})
            conn.commit()
            return FusionResult(True, upgraded, [card for card in consumed_cards if card], xp_gained=xp_gained, old_level=old_level, new_level=new_level)
        except ValueError as exc:
            conn.rollback()
            return FusionResult(False, error=str(exc), error_code="idempotency_conflict")
        except Exception as exc:
            conn.rollback()
            logger.error("Atomic Fusion failed: %s", exc, exc_info=True)
            return FusionResult(False, error="Fusion انجام نشد")
        finally:
            conn.close()

    def preview_identical(self, user_id: int, card_id: str, target: str) -> Dict:
        source = "normal" if target == "epic" else "epic" if target == "legend" else None
        if source is None:
            return {"ok": False, "error_code": "invalid_target", "error": "فرم مقصد نامعتبر است"}
        conn = sqlite3.connect(self.db.db_path)
        try:
            count = CardInventorySystem.counts_in(conn, user_id, card_id).get(source, 0)
            variant = conn.execute(
                "SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?", (card_id, target)
            ).fetchone()
            if not variant:
                return {"ok": False, "error_code": "variant_unavailable", "error": "نسخهٔ مقصد آماده نیست", "owned": count}
            return {"ok": count >= 3, "card_id": card_id, "from_rarity": source,
                    "to_rarity": target, "owned": count, "required": 3,
                    "xp": 15 if target == "epic" else 30,
                    "error": None if count >= 3 else "سه نسخهٔ یکسان لازم است"}
        finally:
            conn.close()

    def fuse_identical(self, user_id: int, card_id: str, target: str,
                       request_key: Optional[str] = None) -> FusionResult:
        source = "normal" if target == "epic" else "epic" if target == "legend" else None
        if source is None:
            return FusionResult(False, error="فرم مقصد نامعتبر است")
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            payload = {"card_id": card_id, "target": target}
            receipt = lookup_in(conn, user_id, request_key, "fusion_identical", payload)
            if receipt is not None:
                conn.commit()
                return FusionResult(True, Card.from_dict(receipt["upgraded_card"]),
                                    xp_gained=receipt["xp_gained"], old_level=receipt["old_level"],
                                    new_level=receipt["new_level"], replayed=True)
            from systems.card_upgrade_system import CardUpgradeSystem
            if CardUpgradeSystem(self.db)._active_match(conn, user_id):
                conn.rollback()
                return FusionResult(False, error="تا پایان مسابقه نمی‌توانی کارت‌ها را ترکیب کنی")
            if CardInventorySystem.counts_in(conn, user_id, card_id).get(source, 0) < 3:
                conn.rollback()
                return FusionResult(False, error="سه نسخهٔ یکسان از فرم موردنظر لازم است")
            if not conn.execute(
                "SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?", (card_id, target)
            ).fetchone():
                conn.rollback()
                return FusionResult(False, error="نسخهٔ مقصد آماده نیست")
            if not CardInventorySystem.consume_in(conn, user_id, card_id, source, 3):
                raise RuntimeError("fusion_source_missing")
            CardInventorySystem.grant_in(conn, user_id, card_id, target)
            CardInventorySystem.reconcile_active_in(conn, user_id, card_id)
            conn.execute(
                """INSERT INTO fusion_log
                   (user_id,fusion_type,consumed_card_1,consumed_card_2,consumed_card_3,
                    upgraded_card_id,result_rarity,timestamp)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (user_id, f"IDENTICAL_{source.upper()}_TO_{target.upper()}",
                 card_id, card_id, card_id, card_id, target.upper(), datetime.now().isoformat()),
            )
            conn.execute("INSERT OR IGNORE INTO player_progression(user_id) VALUES(?)", (user_id,))
            row = conn.execute("SELECT level,total_xp FROM player_progression WHERE user_id=?", (user_id,)).fetchone()
            from systems.phase2_systems import LevelSystem
            xp = 15 if target == "epic" else 30
            old_level = int(row[0])
            total_xp = int(row[1]) + xp
            new_level = LevelSystem.get_level_from_xp(total_xp)
            conn.execute("UPDATE player_progression SET total_xp=?,level=? WHERE user_id=?", (total_xp, new_level, user_id))
            from systems.level_rewards_system import LevelRewardsSystem
            LevelRewardsSystem.grant_crossed_in(conn, user_id, old_level, new_level)
            upgraded = self._card_snapshot_in(conn, user_id, card_id)
            record_in(conn, user_id, request_key, "fusion_identical", payload,
                      {"xp_gained": xp, "old_level": old_level, "new_level": new_level,
                       "upgraded_card": upgraded.to_dict()})
            conn.commit()
            return FusionResult(True, upgraded,
                                xp_gained=xp, old_level=old_level, new_level=new_level)
        except ValueError as exc:
            conn.rollback()
            return FusionResult(False, error=str(exc), error_code="idempotency_conflict")
        except Exception:
            conn.rollback()
            logger.exception("Identical-card fusion failed")
            return FusionResult(False, error="ترکیب کارت انجام نشد")
        finally:
            conn.close()
    
    def fuse_to_epic(self, user_id: int, card_ids: List[str], selected_card_id: str,
                     request_key: Optional[str] = None) -> FusionResult:
        """Fuse three distinct Normal characters into one Epic form."""
        return self._fuse_atomic(user_id, card_ids, selected_card_id, "epic", request_key)

    def fuse_to_legend(self, user_id: int, card_ids: List[str], selected_card_id: str,
                       request_key: Optional[str] = None) -> FusionResult:
        """Fuse three distinct Epic characters into one Legend form."""
        return self._fuse_atomic(user_id, card_ids, selected_card_id, "legend", request_key)

    def get_fusion_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        دریافت تاریخچه Fusion
        
        Args:
            user_id: شناسه بازیکن
            limit: تعداد رکوردها
            
        Returns:
            لیست تاریخچه
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT fusion_type, consumed_card_1, consumed_card_2, consumed_card_3,
                       upgraded_card_id, result_rarity, timestamp
                FROM fusion_log
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'fusion_type': row[0],
                    'consumed_cards': [row[1], row[2], row[3]],
                    'upgraded_card_id': row[4],
                    'result_rarity': row[5],
                    'timestamp': row[6]
                })
            
            return history
            
        finally:
            conn.close()
    
    def get_fusion_stats(self, user_id: int) -> Dict:
        """
        دریافت آمار Fusion
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            آمار Fusion
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            # تعداد کل Fusion ها
            cursor.execute('''
                SELECT COUNT(*) FROM fusion_log WHERE user_id = ?
            ''', (user_id,))
            total_fusions = cursor.fetchone()[0]
            
            # تعداد Normal→Epic
            cursor.execute('''
                SELECT COUNT(*) FROM fusion_log 
                WHERE user_id = ? AND fusion_type IN ('NORMAL_TO_EPIC', 'IDENTICAL_NORMAL_TO_EPIC')
            ''', (user_id,))
            normal_to_epic = cursor.fetchone()[0]
            
            # تعداد Epic→Legend
            cursor.execute('''
                SELECT COUNT(*) FROM fusion_log 
                WHERE user_id = ? AND fusion_type IN ('EPIC_TO_LEGEND', 'IDENTICAL_EPIC_TO_LEGEND')
            ''', (user_id,))
            epic_to_legend = cursor.fetchone()[0]
            
            return {
                'total_fusions': total_fusions,
                'normal_to_epic': normal_to_epic,
                'epic_to_legend': epic_to_legend
            }
            
        finally:
            conn.close()


# ==================== HELPER FUNCTIONS ====================

def format_fusion_result(result: FusionResult) -> str:
    """فرمت کردن نتیجه Fusion برای نمایش"""
    if not result.success:
        return f"❌ Fusion ناموفق: {result.error}"
    
    consumed_names = [c.name for c in result.consumed_cards]
    if not consumed_names:
        return (
            f"✨ Fusion موفق!\n\n"
            f"🎴 سه نسخهٔ یکسان مصرف شد.\n"
            f"🌟 کارت ارتقا یافته: {result.upgraded_card.name} "
            f"({result.upgraded_card.rarity.value.title()})"
        )
    
    return (
        f"✨ Fusion موفق!\n\n"
        f"🎴 کارت‌های مصرف شده:\n"
        f"  • {consumed_names[0]}\n"
        f"  • {consumed_names[1]}\n"
        f"  • {consumed_names[2]}\n\n"
        f"🌟 کارت ارتقا یافته:\n"
        f"  • {result.upgraded_card.name} ({result.upgraded_card.rarity.value.title()})"
    )
