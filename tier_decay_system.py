#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📉 TelBattle Phase 2 - Tier Decay System
سیستم کاهش رتبه با بی‌فعالیت
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


# ==================== TIER DECAY CONSTANTS ====================

PROTECTION_DAYS = {
    "Elite": 7,
    "Diamond": 5,
    "Gold": 3,
    "Silver": 2,
    "Bronze": 1
}

DAILY_DECAY_AMOUNT = 30
MAX_DECAY_PERCENT = 0.50

TIER_THRESHOLDS = {
    "Bronze": (0, 499),
    "Silver": (500, 999),
    "Gold": (1000, 1499),
    "Diamond": (1500, 1999),
    "Elite": (2000, float('inf'))
}


# ==================== TIER DECAY SYSTEM ====================

class TierDecaySystem:
    """
    سیستم Tier Decay
    
    ویژگی‌ها:
    - همه Tier ها Decay دارند (بدون استثنا)
    - هر Tier یک دوره حفاظت دارد
    - Decay روزانه: 30 TP
    - سقف Decay: 50% از TP فعلی
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def get_tier_from_tp(self, tp: int) -> str:
        """
        تعیین Tier بر اساس TP
        
        Args:
            tp: Tier Points
        
        Returns:
            نام Tier
        """
        for tier_name, (min_tp, max_tp) in TIER_THRESHOLDS.items():
            if min_tp <= tp <= max_tp:
                return tier_name
        return "Bronze"
    
    def calculate_decay(
        self,
        last_played_date: datetime,
        current_tp: int,
        current_tier: str
    ) -> Tuple[int, int, int]:
        """
        محاسبه Decay بر اساس روزهای بی‌فعالیت
        
        Args:
            last_played_date: آخرین بازی
            current_tp: TP فعلی
            current_tier: Tier فعلی
        
        Returns:
            (new_tp, decay_amount, days_inactive)
        """
        # محاسبه روزهای بی‌فعالیت
        days_inactive = (datetime.now() - last_played_date).days
        
        # دریافت دوره حفاظت
        protection = PROTECTION_DAYS.get(current_tier, 1)
        
        # اگر هنوز در حفاظت است
        if days_inactive <= protection:
            return current_tp, 0, days_inactive
        
        # روزهای Decay فعال
        decay_days = days_inactive - protection
        
        # محاسبه Decay
        raw_decay = decay_days * DAILY_DECAY_AMOUNT
        max_allowed_decay = int(current_tp * MAX_DECAY_PERCENT)
        actual_decay = min(raw_decay, max_allowed_decay)
        
        # TP جدید
        new_tp = max(0, current_tp - actual_decay)
        
        logger.info(
            f"Decay calculated: {current_tp} → {new_tp} "
            f"(decay: {actual_decay}, days: {days_inactive})"
        )
        
        return new_tp, actual_decay, days_inactive
    
    def apply_decay_to_player(self, user_id: int) -> Dict:
        """اعمال Decay به یک بازیکن"""
        progression = self.db.get_or_create_progression(user_id)
        if not progression:
            return {"success": False, "error": "Progression not found"}
        
        last_played = progression.get('last_played_at', datetime.now())
        if isinstance(last_played, str):
            try:
                last_played = datetime.fromisoformat(last_played)
            except Exception:
                last_played = datetime.now()
        
        current_tp = progression.get('tier_points', 0)
        current_tier = progression.get('current_tier', 'Bronze')
        
        new_tp, decay_amount, days_inactive = self.calculate_decay(last_played, current_tp, current_tier)
        
        if decay_amount == 0:
            return {
                "success": True,
                "decayed": False,
                "days_inactive": days_inactive,
                "protection_remaining": PROTECTION_DAYS.get(current_tier, 1) - days_inactive
            }
        
        new_tier = self.get_tier_from_tp(new_tp)
        tier_changed = new_tier != current_tier
        
        self.db.update_progression(user_id, tier_points=new_tp, current_tier=new_tier)
        
        return {
            "success": True,
            "decayed": True,
            "old_tp": current_tp,
            "new_tp": new_tp,
            "decay_amount": decay_amount,
            "days_inactive": days_inactive,
            "old_tier": current_tier,
            "new_tier": new_tier,
            "tier_changed": tier_changed
        }
    
    def apply_decay_to_all_players(self) -> Dict:
        """
        اعمال Decay به همه بازیکنان
        (برای cron job روزانه)
        
        Returns:
            آمار Decay
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        # دریافت همه بازیکنان
        cursor.execute('''
            SELECT user_id, tier_points, current_tier, last_played_at
            FROM player_progression
        ''')
        
        players = cursor.fetchall()
        conn.close()
        
        stats = {
            "total_players": len(players),
            "decayed_players": 0,
            "tier_changes": 0,
            "total_tp_lost": 0
        }
        
        for user_id, tp, tier, last_played in players:
            result = self.apply_decay_to_player(user_id)
            
            if result.get("decayed"):
                stats["decayed_players"] += 1
                stats["total_tp_lost"] += result["decay_amount"]
                
                if result.get("tier_changed"):
                    stats["tier_changes"] += 1
        
        logger.info(f"Decay applied to all players: {stats}")
        return stats
    
    def get_decay_info(self, user_id: int) -> Dict:
        """دریافت اطلاعات Decay برای نمایش به بازیکن"""
        progression = self.db.get_or_create_progression(user_id)
        if not progression:
            return {"error": "Progression not found"}
        
        last_played = progression.get('last_played_at', datetime.now())
        if isinstance(last_played, str):
            try:
                last_played = datetime.fromisoformat(last_played)
            except Exception:
                last_played = datetime.now()
        
        current_tp = progression.get('tier_points', 0)
        current_tier = progression.get('current_tier', 'Bronze')
        days_inactive = (datetime.now() - last_played).days
        protection = PROTECTION_DAYS.get(current_tier, 1)
        
        if days_inactive <= protection:
            return {
                "in_protection": True,
                "days_inactive": days_inactive,
                "protection_days": protection,
                "days_remaining": protection - days_inactive,
                "next_decay_date": last_played + timedelta(days=protection + 1)
            }
        else:
            decay_days = days_inactive - protection
            estimated_decay = min(
                decay_days * DAILY_DECAY_AMOUNT,
                int(current_tp * MAX_DECAY_PERCENT)
            )
            return {
                "in_protection": False,
                "days_inactive": days_inactive,
                "decay_days": decay_days,
                "estimated_decay": estimated_decay,
                "current_tp": current_tp,
                "estimated_tp_after_decay": max(0, current_tp - estimated_decay)
            }


# ==================== DATABASE OPERATIONS ====================

def add_decay_columns(db_path: str):
    """
    اضافه کردن ستون‌های مورد نیاز برای Decay
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            ALTER TABLE player_progression
            ADD COLUMN last_played_at TEXT
        ''')
        conn.commit()
        logger.info("Added last_played_at column")
    except sqlite3.OperationalError:
        logger.info("last_played_at column already exists")
    
    conn.close()


def update_last_played(db_path: str, user_id: int):
    """
    بروزرسانی last_played_at بعد از هر بازی
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE player_progression
        SET last_played_at = ?
        WHERE user_id = ?
    ''', (datetime.now().isoformat(), user_id))
    
    conn.commit()
    conn.close()


# ==================== HELPER FUNCTIONS ====================

def format_decay_message(decay_info: Dict) -> str:
    """
    فرمت کردن پیام Decay برای نمایش
    
    Args:
        decay_info: اطلاعات Decay
    
    Returns:
        پیام فرمت شده
    """
    if not decay_info.get("decayed"):
        days = decay_info.get("days_inactive", 0)
        remaining = decay_info.get("protection_remaining", 0)
        
        return f"""
✅ شما در دوره حفاظت هستید

📅 روزهای بی‌فعالیت: {days}
🛡️ روزهای حفاظت باقی‌مانده: {remaining}

💡 تا {remaining} روز دیگر می‌توانید بدون نگرانی استراحت کنید!
"""
    
    old_tp = decay_info["old_tp"]
    new_tp = decay_info["new_tp"]
    decay = decay_info["decay_amount"]
    days = decay_info["days_inactive"]
    
    text = f"""
⚠️ Tier Decay اعمال شد!

📉 TP شما: {old_tp} → {new_tp} (-{decay})
📅 روزهای بی‌فعالیت: {days}
"""
    
    if decay_info.get("tier_changed"):
        old_tier = decay_info["old_tier"]
        new_tier = decay_info["new_tier"]
        text += f"\n🔻 Tier: {old_tier} → {new_tier}"
    
    text += "\n\n💡 برای جلوگیری از Decay، حداقل هر چند روز یکبار بازی کنید!"
    
    return text.strip()
