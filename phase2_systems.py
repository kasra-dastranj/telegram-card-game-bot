#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎮 TelBattle Phase 2 - Core Systems
سیستم‌های پایه فاز ۲: Level, XP, Tier, TP, Decay
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ==================== XP SOURCES ====================

XP_SOURCES = {
    "normal_win": 10,
    "normal_loss": 3,
    "risk_win": 25,
    "risk_loss": 5,
    "card_upgrade_epic": 15,
    "card_upgrade_legend": 30,
    "daily_quest": 20,
    "weekly_rank_1": 100,
    "weekly_rank_2": 50,
    "weekly_rank_3": 30
}

# ==================== TIER CONFIGURATION ====================

TIER_RANGES = {
    "Bronze": (0, 499),
    "Silver": (500, 999),
    "Gold": (1000, 1499),
    "Diamond": (1500, 1999),
    "Elite": (2000, 999999)
}

TIER_PROTECTION_DAYS = {
    "Elite": 7,
    "Diamond": 5,
    "Gold": 3,
    "Silver": 2,
    "Bronze": 1
}

# ==================== MODELS ====================

@dataclass
class PlayerProgression:
    """مدل پیشرفت بازیکن"""
    user_id: int
    level: int
    total_xp: int
    tier_points: int
    current_tier: str
    last_played_at: datetime
    
    @classmethod
    def from_db_row(cls, row: tuple):
        """ایجاد از رکورد دیتابیس"""
        return cls(
            user_id=row[0],
            level=row[1],
            total_xp=row[2],
            tier_points=row[3],
            current_tier=row[4],
            last_played_at=datetime.fromisoformat(row[5]) if row[5] else datetime.now()
        )

# ==================== LEVEL & XP SYSTEM ====================

class LevelSystem:
    """سیستم Level و XP"""
    
    @staticmethod
    def xp_for_level(level: int) -> int:
        """محاسبه XP مورد نیاز برای رسیدن به level"""
        if level == 1:
            return 0
        return 100 + (level - 2) * 50
    
    @staticmethod
    def total_xp_for_level(level: int) -> int:
        """محاسبه مجموع XP مورد نیاز برای رسیدن به level (تجمعی)"""
        if level == 1:
            return 0
        total = 0
        for lv in range(2, level + 1):
            total += LevelSystem.xp_for_level(lv)
        return total
    
    @staticmethod
    def get_level_from_xp(total_xp: int) -> int:
        """محاسبه level بر اساس total XP"""
        level = 1
        while level < 30:
            required_xp = LevelSystem.total_xp_for_level(level + 1)
            if total_xp < required_xp:
                break
            level += 1
        return level
    
    @staticmethod
    def get_xp_progress(total_xp: int) -> Tuple[int, int, int]:
        """
        دریافت پیشرفت XP فعلی
        
        Returns:
            (current_level, xp_in_current_level, xp_needed_for_next_level)
        """
        current_level = LevelSystem.get_level_from_xp(total_xp)
        
        if current_level >= 30:
            return 30, 0, 0
        
        xp_for_current = LevelSystem.total_xp_for_level(current_level)
        xp_for_next = LevelSystem.total_xp_for_level(current_level + 1)
        
        xp_in_current = total_xp - xp_for_current
        xp_needed = xp_for_next - xp_for_current
        
        return current_level, xp_in_current, xp_needed

# ==================== TIER & TP SYSTEM ====================

class TierSystem:
    """سیستم Tier و TP"""
    
    @staticmethod
    def get_tier_from_tp(tier_points: int) -> str:
        """تعیین Tier بر اساس TP"""
        for tier_name, (min_tp, max_tp) in TIER_RANGES.items():
            if min_tp <= tier_points <= max_tp:
                return tier_name
        return "Bronze"
    
    @staticmethod
    def calculate_tp_change(
        winner_tier: str,
        loser_tier: str,
        match_type: str = "normal"
    ) -> Tuple[int, int]:
        """
        محاسبه تغییر TP برای برنده و بازنده
        
        Args:
            winner_tier: Tier برنده
            loser_tier: Tier بازنده
            match_type: "normal" یا "risk"
            
        Returns:
            (tp_gain_winner, tp_loss_loser)
        """
        # Base gain/loss
        if match_type == "risk":
            base_gain = 25
            base_loss = 15
        else:  # normal
            base_gain = 15
            base_loss = 10
        
        # Tier difference multiplier
        tier_order = ["Bronze", "Silver", "Gold", "Diamond", "Elite"]
        
        try:
            winner_idx = tier_order.index(winner_tier)
            loser_idx = tier_order.index(loser_tier)
        except ValueError:
            # اگر tier نامعتبر بود، از مقادیر پیش‌فرض استفاده کن
            return base_gain, base_loss
        
        tier_diff = loser_idx - winner_idx
        
        # اگر برنده tier پایین‌تری داره (upset)، بیشتر TP می‌گیره
        if tier_diff < 0:  # برنده tier بالاتری داره
            tp_gain = max(5, base_gain + (tier_diff * 5))
        else:  # برنده tier پایین‌تری داره یا برابر
            tp_gain = base_gain + (tier_diff * 5)
        
        # بازنده همیشه base_loss می‌ده
        tp_loss = base_loss
        
        return tp_gain, tp_loss
    
    @staticmethod
    def get_protection_days(tier: str) -> int:
        """دریافت روزهای حفاظت برای tier"""
        return TIER_PROTECTION_DAYS.get(tier, 1)

# ==================== DECAY SYSTEM ====================

class DecaySystem:
    """سیستم Decay برای Tier"""
    
    DAILY_DECAY_AMOUNT = 30
    MAX_DECAY_PERCENT = 0.50
    
    @staticmethod
    def calculate_decay(
        current_tp: int,
        current_tier: str,
        last_played_at: datetime
    ) -> Tuple[int, int]:
        """
        محاسبه Decay بر اساس بی‌فعالیت
        
        Args:
            current_tp: TP فعلی
            current_tier: Tier فعلی
            last_played_at: آخرین زمان بازی
            
        Returns:
            (new_tp, decay_amount)
        """
        now = datetime.now()
        days_inactive = (now - last_played_at).days
        
        # دریافت روزهای حفاظت
        protection_days = TierSystem.get_protection_days(current_tier)
        
        # اگر هنوز در دوره حفاظت هست
        if days_inactive <= protection_days:
            return current_tp, 0
        
        # محاسبه روزهای decay
        decay_days = days_inactive - protection_days
        
        # محاسبه decay خام
        raw_decay = decay_days * DecaySystem.DAILY_DECAY_AMOUNT
        
        # محاسبه حداکثر decay (50% از TP فعلی)
        max_decay = int(current_tp * DecaySystem.MAX_DECAY_PERCENT)
        
        # اعمال محدودیت
        actual_decay = min(raw_decay, max_decay)
        
        # محاسبه TP جدید
        new_tp = max(0, current_tp - actual_decay)
        
        return new_tp, actual_decay

# ==================== DATABASE OPERATIONS ====================

class ProgressionDB:
    """عملیات دیتابیس برای سیستم پیشرفت"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_progression(self, user_id: int) -> Optional[PlayerProgression]:
        """دریافت پیشرفت بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT user_id, level, total_xp, tier_points, current_tier, last_played_at
                FROM player_progression
                WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            if row:
                return PlayerProgression.from_db_row(row)
            return None
            
        finally:
            conn.close()
    
    def update_progression(self, progression: PlayerProgression) -> bool:
        """بروزرسانی پیشرفت بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE player_progression
                SET level = ?, total_xp = ?, tier_points = ?, 
                    current_tier = ?, last_played_at = ?
                WHERE user_id = ?
            ''', (
                progression.level,
                progression.total_xp,
                progression.tier_points,
                progression.current_tier,
                progression.last_played_at.isoformat(),
                progression.user_id
            ))
            
            conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating progression for user {progression.user_id}: {e}")
            return False
        finally:
            conn.close()
    
    def add_xp(self, user_id: int, amount: int, source: str) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        اضافه کردن XP به بازیکن
        
        Returns:
            (success, old_level, new_level)
        """
        progression = self.get_progression(user_id)
        if not progression:
            logger.error(f"Progression not found for user {user_id}")
            return False, None, None
        
        old_level = progression.level
        progression.total_xp += amount
        progression.level = LevelSystem.get_level_from_xp(progression.total_xp)
        progression.last_played_at = datetime.now()
        
        success = self.update_progression(progression)
        
        if success:
            logger.info(f"Added {amount} XP to user {user_id} from {source}. Level: {old_level} → {progression.level}")
        
        return success, old_level, progression.level
    
    def add_tp(self, user_id: int, amount: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        اضافه کردن TP به بازیکن
        
        Returns:
            (success, old_tier, new_tier)
        """
        progression = self.get_progression(user_id)
        if not progression:
            logger.error(f"Progression not found for user {user_id}")
            return False, None, None
        
        old_tier = progression.current_tier
        progression.tier_points = max(0, progression.tier_points + amount)
        progression.current_tier = TierSystem.get_tier_from_tp(progression.tier_points)
        progression.last_played_at = datetime.now()
        
        success = self.update_progression(progression)
        
        if success:
            logger.info(f"Added {amount} TP to user {user_id}. Tier: {old_tier} → {progression.current_tier}")
        
        return success, old_tier, progression.current_tier
    
    def apply_decay_to_all(self) -> Dict[str, int]:
        """
        اعمال Decay به همه بازیکنان بی‌فعال
        
        Returns:
            آمار decay اعمال شده
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {
            "total_checked": 0,
            "decayed": 0,
            "tier_changes": 0,
            "total_tp_lost": 0
        }
        
        try:
            # دریافت همه بازیکنان
            cursor.execute('''
                SELECT user_id, level, total_xp, tier_points, current_tier, last_played_at
                FROM player_progression
            ''')
            
            rows = cursor.fetchall()
            stats["total_checked"] = len(rows)
            
            for row in rows:
                progression = PlayerProgression.from_db_row(row)
                
                # محاسبه decay
                new_tp, decay_amount = DecaySystem.calculate_decay(
                    progression.tier_points,
                    progression.current_tier,
                    progression.last_played_at
                )
                
                if decay_amount > 0:
                    old_tier = progression.current_tier
                    progression.tier_points = new_tp
                    progression.current_tier = TierSystem.get_tier_from_tp(new_tp)
                    
                    # بروزرسانی
                    cursor.execute('''
                        UPDATE player_progression
                        SET tier_points = ?, current_tier = ?
                        WHERE user_id = ?
                    ''', (new_tp, progression.current_tier, progression.user_id))
                    
                    stats["decayed"] += 1
                    stats["total_tp_lost"] += decay_amount
                    
                    if old_tier != progression.current_tier:
                        stats["tier_changes"] += 1
                        logger.info(f"User {progression.user_id} decayed: {old_tier} → {progression.current_tier} (-{decay_amount} TP)")
            
            conn.commit()
            logger.info(f"Decay applied: {stats}")
            
        except Exception as e:
            logger.error(f"Error applying decay: {e}")
        finally:
            conn.close()
        
        return stats

# ==================== HELPER FUNCTIONS ====================

def format_xp_bar(current_xp: int, needed_xp: int, bar_length: int = 10) -> str:
    """ساخت XP bar نموداری"""
    if needed_xp == 0:
        progress = 1.0
    else:
        progress = min(1.0, current_xp / needed_xp)
    
    filled = int(bar_length * progress)
    empty = bar_length - filled
    
    bar = "█" * filled + "░" * empty
    percentage = int(progress * 100)
    
    return f"{bar} {percentage}%"

def format_tier_badge(tier: str) -> str:
    """ساخت badge برای tier"""
    badges = {
        "Bronze": "🥉",
        "Silver": "🥈",
        "Gold": "🥇",
        "Diamond": "💎",
        "Elite": "👑"
    }
    return badges.get(tier, "❓")
