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

logger = logging.getLogger(__name__)


class FusionResult:
    """نتیجه Fusion"""
    def __init__(self, success: bool, upgraded_card: Optional[Card] = None, 
                 consumed_cards: Optional[List[Card]] = None, error: Optional[str] = None):
        self.success = success
        self.upgraded_card = upgraded_card
        self.consumed_cards = consumed_cards or []
        self.error = error


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
    
    def fuse_to_epic(self, user_id: int, card_ids: List[str], selected_card_id: str) -> FusionResult:
        """Fusion 3 Normal → 1 Epic"""
        logger.info(f"User {user_id} Normal→Epic fusion: {card_ids}, selected: {selected_card_id}")
        
        is_valid, error = self.validate_fusion_cards(user_id, card_ids, selected_card_id, CardRarity.NORMAL)
        if not is_valid:
            return FusionResult(False, error=error)
        
        player_cards = self.db.get_player_cards(user_id)
        card_map = {c.card_id: c for c in player_cards}
        consumed_cards = [card_map[cid] for cid in card_ids if cid in card_map]
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            # حذف هر ۳ کارت از موجودی بازیکن
            for card_id in card_ids:
                cursor.execute('''
                    DELETE FROM player_cards 
                    WHERE rowid = (
                        SELECT rowid FROM player_cards 
                        WHERE user_id = ? AND card_id = ?
                        LIMIT 1
                    )
                ''', (user_id, card_id))
            
            # اضافه کردن کارت انتخاب‌شده با rarity_override = 'epic'
            cursor.execute('''
                INSERT INTO player_cards (user_id, card_id, obtained_at, rarity_override)
                VALUES (?, ?, ?, 'epic')
            ''', (user_id, selected_card_id, datetime.now().isoformat()))
            
            # ثبت در fusion_log
            cursor.execute('''
                INSERT INTO fusion_log 
                (user_id, fusion_type, consumed_card_1, consumed_card_2, consumed_card_3,
                 upgraded_card_id, result_rarity, timestamp)
                VALUES (?, 'NORMAL_TO_EPIC', ?, ?, ?, ?, 'EPIC', ?)
            ''', (user_id, card_ids[0], card_ids[1], card_ids[2],
                  selected_card_id, datetime.now().isoformat()))
            
            conn.commit()
            logger.info(f"Fusion OK: {selected_card_id} → Epic for user {user_id}")
            
            upgraded_card = self.db.get_card_by_id_for_player(selected_card_id, user_id)
            return FusionResult(True, upgraded_card=upgraded_card, consumed_cards=consumed_cards)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Fusion failed: {e}", exc_info=True)
            return FusionResult(False, error=f"خطا در Fusion: {str(e)}")
        finally:
            conn.close()
    
    def fuse_to_legend(self, user_id: int, card_ids: List[str], selected_card_id: str) -> FusionResult:
        """Fusion 3 Epic → 1 Legend"""
        logger.info(f"User {user_id} Epic→Legend fusion: {card_ids}, selected: {selected_card_id}")
        
        is_valid, error = self.validate_fusion_cards(user_id, card_ids, selected_card_id, CardRarity.EPIC)
        if not is_valid:
            return FusionResult(False, error=error)
        
        player_cards = self.db.get_player_cards(user_id)
        card_map = {c.card_id: c for c in player_cards}
        consumed_cards = [card_map[cid] for cid in card_ids if cid in card_map]
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            # حذف هر ۳ کارت Epic از موجودی
            for card_id in card_ids:
                cursor.execute('''
                    DELETE FROM player_cards 
                    WHERE rowid = (
                        SELECT rowid FROM player_cards 
                        WHERE user_id = ? AND card_id = ?
                        LIMIT 1
                    )
                ''', (user_id, card_id))
            
            # اضافه کردن کارت انتخاب‌شده با rarity_override = 'legend'
            cursor.execute('''
                INSERT INTO player_cards (user_id, card_id, obtained_at, rarity_override)
                VALUES (?, ?, ?, 'legend')
            ''', (user_id, selected_card_id, datetime.now().isoformat()))
            
            # ثبت در fusion_log
            cursor.execute('''
                INSERT INTO fusion_log 
                (user_id, fusion_type, consumed_card_1, consumed_card_2, consumed_card_3,
                 upgraded_card_id, result_rarity, timestamp)
                VALUES (?, 'EPIC_TO_LEGEND', ?, ?, ?, ?, 'LEGEND', ?)
            ''', (user_id, card_ids[0], card_ids[1], card_ids[2],
                  selected_card_id, datetime.now().isoformat()))
            
            conn.commit()
            logger.info(f"Fusion OK: {selected_card_id} → Legend for user {user_id}")
            
            upgraded_card = self.db.get_card_by_id_for_player(selected_card_id, user_id)
            return FusionResult(True, upgraded_card=upgraded_card, consumed_cards=consumed_cards)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Fusion failed: {e}", exc_info=True)
            return FusionResult(False, error=f"خطا در Fusion: {str(e)}")
        finally:
            conn.close()
    
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
                WHERE user_id = ? AND fusion_type = 'NORMAL_TO_EPIC'
            ''', (user_id,))
            normal_to_epic = cursor.fetchone()[0]
            
            # تعداد Epic→Legend
            cursor.execute('''
                SELECT COUNT(*) FROM fusion_log 
                WHERE user_id = ? AND fusion_type = 'EPIC_TO_LEGEND'
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
    
    return (
        f"✨ Fusion موفق!\n\n"
        f"🎴 کارت‌های مصرف شده:\n"
        f"  • {consumed_names[0]}\n"
        f"  • {consumed_names[1]}\n"
        f"  • {consumed_names[2]}\n\n"
        f"🌟 کارت ارتقا یافته:\n"
        f"  • {result.upgraded_card.name} ({result.upgraded_card.rarity.value.title()})"
    )
