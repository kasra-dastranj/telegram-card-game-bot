#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 TelBattle Phase 2 - Card Missions System
سیستم ماموریت‌های کارت برای ارتقا به Legend
"""

import sqlite3
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ==================== MISSION TYPES ====================

MISSION_TYPES = {
    "speed_wins": {
        "name_fa": "برد با سرعت",
        "description": "با این کارت {target} برد سرعتی بگیر",
        "check_func": "check_speed_wins"
    },
    "power_wins": {
        "name_fa": "برد با قدرت",
        "description": "با این کارت {target} برد قدرتی بگیر",
        "check_func": "check_power_wins"
    },
    "iq_wins": {
        "name_fa": "برد با هوش",
        "description": "با این کارت {target} برد هوشی بگیر",
        "check_func": "check_iq_wins"
    },
    "popularity_wins": {
        "name_fa": "برد با محبوبیت",
        "description": "با این کارت {target} برد محبوبیتی بگیر",
        "check_func": "check_popularity_wins"
    },
    "total_wins": {
        "name_fa": "برد کلی",
        "description": "با این کارت {target} بار ببر",
        "check_func": "check_total_wins"
    },
    "defeat_specific": {
        "name_fa": "شکست کارت خاص",
        "description": "کارت {target_card} را {target} بار شکست بده",
        "check_func": "check_defeat_specific"
    },
    "risk_wins": {
        "name_fa": "برد در Risk",
        "description": "با این کارت {target} بار در مود Risk ببر",
        "check_func": "check_risk_wins"
    },
    "consecutive_wins": {
        "name_fa": "برد متوالی",
        "description": "با این کارت {target} برد پشت سر هم بگیر",
        "check_func": "check_consecutive_wins"
    }
}


# ==================== CARD MISSIONS SYSTEM ====================

class CardMissionsSystem:
    """
    سیستم Card Missions
    
    ویژگی‌ها:
    - هر کارت Epic یک ماموریت برای Legend شدن دارد
    - انواع مختلف ماموریت
    - Progress tracking
    - پاداش Legend بعد از تکمیل
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def create_mission(
        self,
        card_id: str,
        mission_type: str,
        target: int,
        target_card: str = None
    ) -> bool:
        """
        ایجاد ماموریت برای یک کارت
        
        Args:
            card_id: شناسه کارت
            mission_type: نوع ماموریت
            target: هدف (تعداد)
            target_card: کارت هدف (برای defeat_specific)
        
        Returns:
            موفقیت
        """
        if mission_type not in MISSION_TYPES:
            logger.error(f"Invalid mission type: {mission_type}")
            return False
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO card_missions
            (card_id, mission_type, target, target_card, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (card_id, mission_type, target, target_card, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Mission created for {card_id}: {mission_type} (target: {target})")
        return True
    
    def get_mission(self, card_id: str) -> Optional[Dict]:
        """
        دریافت ماموریت یک کارت
        
        Args:
            card_id: شناسه کارت
        
        Returns:
            اطلاعات ماموریت
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_id, mission_type, target, target_card, created_at
            FROM card_missions
            WHERE card_id = ?
        ''', (card_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            mission_info = MISSION_TYPES.get(result[1], {})
            
            return {
                "card_id": result[0],
                "mission_type": result[1],
                "target": result[2],
                "target_card": result[3],
                "created_at": result[4],
                "name_fa": mission_info.get("name_fa", "ماموریت"),
                "description": mission_info.get("description", "").format(
                    target=result[2],
                    target_card=result[3] or ""
                )
            }
        
        return None
    
    def get_player_mission_progress(self, user_id: int, card_id: str) -> Optional[Dict]:
        """
        دریافت پیشرفت ماموریت بازیکن
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
        
        Returns:
            اطلاعات پیشرفت
        """
        # دریافت ماموریت
        mission = self.get_mission(card_id)
        if not mission:
            return None
        
        # دریافت پیشرفت
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT current_progress, completed, completed_at
            FROM player_card_missions
            WHERE user_id = ? AND card_id = ?
        ''', (user_id, card_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            progress = result[0]
            completed = bool(result[1])
            completed_at = result[2]
        else:
            # ایجاد رکورد جدید
            progress = 0
            completed = False
            completed_at = None
            
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO player_card_missions
                (user_id, card_id, current_progress, completed)
                VALUES (?, ?, 0, 0)
            ''', (user_id, card_id))
            conn.commit()
            conn.close()
        
        return {
            **mission,
            "current_progress": progress,
            "completed": completed,
            "completed_at": completed_at,
            "progress_percent": int((progress / mission["target"]) * 100) if mission["target"] > 0 else 0
        }
    
    def update_mission_progress(
        self,
        user_id: int,
        card_id: str,
        increment: int = 1
    ) -> Dict:
        """
        بروزرسانی پیشرفت ماموریت
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
            increment: مقدار افزایش
        
        Returns:
            وضعیت جدید
        """
        progress = self.get_player_mission_progress(user_id, card_id)
        if not progress:
            return {"success": False, "error": "Mission not found"}
        
        if progress["completed"]:
            return {"success": False, "error": "Mission already completed"}
        
        # افزایش پیشرفت
        new_progress = progress["current_progress"] + increment
        completed = new_progress >= progress["target"]
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        if completed:
            cursor.execute('''
                UPDATE player_card_missions
                SET current_progress = ?, completed = 1, completed_at = ?
                WHERE user_id = ? AND card_id = ?
            ''', (new_progress, datetime.now().isoformat(), user_id, card_id))
        else:
            cursor.execute('''
                UPDATE player_card_missions
                SET current_progress = ?
                WHERE user_id = ? AND card_id = ?
            ''', (new_progress, user_id, card_id))
        
        conn.commit()
        conn.close()
        
        logger.info(
            f"Mission progress updated: user={user_id}, card={card_id}, "
            f"progress={new_progress}/{progress['target']}, completed={completed}"
        )
        
        return {
            "success": True,
            "current_progress": new_progress,
            "target": progress["target"],
            "completed": completed,
            "just_completed": completed and (new_progress - increment < progress["target"])
        }
    
    def claim_mission_reward(self, user_id: int, card_id: str) -> Dict:
        """دریافت پاداش ماموریت (ارتقا به Legend با rarity_override)"""
        progress = self.get_player_mission_progress(user_id, card_id)
        if not progress:
            return {"success": False, "error": "Mission not found"}
        
        if not progress["completed"]:
            return {"success": False, "error": "Mission not completed yet"}
        
        # بررسی اینکه بازیکن کارت Epic دارد
        player_cards = self.db.get_player_cards(user_id)
        card = next((c for c in player_cards if c.card_id == card_id and c.rarity.value == "epic"), None)
        
        if not card:
            return {"success": False, "error": "You don't have this card as Epic"}
        
        # ارتقا با rarity_override
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE player_cards SET rarity_override='legend' WHERE user_id=? AND card_id=?",
            (user_id, card_id)
        )
        
        # علامت‌گذاری پاداش دریافت شده
        cursor.execute('''
            UPDATE player_card_missions
            SET reward_claimed=1, reward_claimed_at=?
            WHERE user_id=? AND card_id=?
        ''', (datetime.now().isoformat(), user_id, card_id))
        conn.commit()
        conn.close()
        
        logger.info(f"Mission reward claimed: user={user_id}, card={card_id} → Legend")
        
        return {
            "success": True,
            "card_id": card_id,
            "card_name": card.name
        }
    
    def check_and_update_mission(
        self,
        user_id: int,
        card_id: str,
        match_data: Dict
    ) -> Optional[Dict]:
        """
        بررسی و بروزرسانی خودکار ماموریت بعد از بازی
        
        Args:
            user_id: شناسه بازیکن
            card_id: کارت استفاده شده
            match_data: اطلاعات بازی
        
        Returns:
            نتیجه بروزرسانی (اگر مرتبط باشد)
        """
        mission = self.get_mission(card_id)
        if not mission:
            return None
        
        mission_type = mission["mission_type"]
        
        # بررسی شرایط بر اساس نوع ماموریت
        should_increment = False
        
        if mission_type == "total_wins" and match_data.get("won"):
            should_increment = True
        
        elif mission_type == "speed_wins" and match_data.get("won"):
            if match_data.get("winning_stat") == "speed":
                should_increment = True
        
        elif mission_type == "power_wins" and match_data.get("won"):
            if match_data.get("winning_stat") == "power":
                should_increment = True
        
        elif mission_type == "iq_wins" and match_data.get("won"):
            if match_data.get("winning_stat") == "iq":
                should_increment = True
        
        elif mission_type == "popularity_wins" and match_data.get("won"):
            if match_data.get("winning_stat") == "popularity":
                should_increment = True
        
        elif mission_type == "risk_wins" and match_data.get("won"):
            if match_data.get("match_type") == "risk":
                should_increment = True
        
        elif mission_type == "defeat_specific" and match_data.get("won"):
            if match_data.get("opponent_card_id") == mission.get("target_card"):
                should_increment = True
        
        if should_increment:
            return self.update_mission_progress(user_id, card_id)
        
        return None


# ==================== DATABASE OPERATIONS ====================

def create_missions_tables(db_path: str):
    """
    ایجاد جداول مورد نیاز برای Missions
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # جدول تعریف ماموریت‌ها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_missions (
            card_id TEXT PRIMARY KEY,
            mission_type TEXT NOT NULL,
            target INTEGER NOT NULL,
            target_card TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    
    # جدول پیشرفت بازیکنان
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_card_missions (
            user_id INTEGER,
            card_id TEXT,
            current_progress INTEGER DEFAULT 0,
            completed BOOLEAN DEFAULT 0,
            completed_at TEXT,
            reward_claimed BOOLEAN DEFAULT 0,
            reward_claimed_at TEXT,
            PRIMARY KEY (user_id, card_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id),
            FOREIGN KEY (card_id) REFERENCES card_missions (card_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Missions tables created")


# ==================== HELPER FUNCTIONS ====================

def format_mission_progress(progress: Dict) -> str:
    """
    فرمت کردن پیشرفت ماموریت
    
    Args:
        progress: اطلاعات پیشرفت
    
    Returns:
        پیام فرمت شده
    """
    if progress["completed"]:
        text = f"""
✅ **ماموریت تکمیل شد!**

🎯 {progress['description']}

📊 پیشرفت: {progress['current_progress']}/{progress['target']} (100%)
✨ تاریخ تکمیل: {progress['completed_at'][:10]}

🏆 پاداش: ارتقا به Legend
💡 برای دریافت پاداش از منوی کارت استفاده کنید
"""
    else:
        progress_bar = "█" * int(progress['progress_percent'] / 10) + "░" * (10 - int(progress['progress_percent'] / 10))
        
        text = f"""
🎯 **ماموریت کارت**

{progress['description']}

📊 پیشرفت: {progress['current_progress']}/{progress['target']} ({progress['progress_percent']}%)
[{progress_bar}]

💡 با ادامه بازی ماموریت را تکمیل کنید!
"""
    
    return text.strip()
