#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎨 TelBattle Phase 2 - Skins System
سیستم پوسته‌های کارت
"""

import sqlite3
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ==================== SKIN TYPES ====================

SKIN_TYPES = {
    "normal": {
        "name_fa": "عادی",
        "price": 50,
        "description": "پوسته عادی"
    },
    "special": {
        "name_fa": "ویژه",
        "price": 150,
        "description": "پوسته ویژه با افکت خاص"
    },
    "seasonal": {
        "name_fa": "فصلی",
        "price": 100,
        "description": "پوسته فصلی محدود"
    },
    "event": {
        "name_fa": "رویداد",
        "price": 0,
        "description": "پوسته رایگان از رویداد"
    },
    "premium": {
        "name_fa": "پرمیوم",
        "price": 300,
        "description": "پوسته پرمیوم با انیمیشن"
    }
}


# ==================== SKINS SYSTEM ====================

class SkinsSystem:
    """
    سیستم Skins
    
    ویژگی‌ها:
    - فقط ظاهر کارت را تغییر می‌دهد
    - هیچ تاثیری بر آمار ندارد
    - خرید با سکه
    - انواع مختلف (عادی، ویژه، فصلی، رویداد)
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def create_skin(
        self,
        skin_id: str,
        card_id: str,
        name: str,
        skin_type: str,
        image_path: str,
        price: int = None,
        is_seasonal: bool = False,
        season_end: str = None,
        description: str = ""
    ) -> bool:
        """
        ایجاد یک پوسته جدید
        
        Args:
            skin_id: شناسه پوسته
            card_id: شناسه کارت
            name: نام پوسته
            skin_type: نوع پوسته
            image_path: مسیر تصویر
            price: قیمت (None = از نوع استفاده می‌شود)
            is_seasonal: آیا فصلی است
            season_end: تاریخ پایان فصل
            description: توضیحات
        
        Returns:
            موفقیت
        """
        if skin_type not in SKIN_TYPES:
            logger.error(f"Invalid skin type: {skin_type}")
            return False
        
        # قیمت پیش‌فرض از نوع
        if price is None:
            price = SKIN_TYPES[skin_type]["price"]
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO skins
            (skin_id, card_id, name, skin_type, image_path, price, 
             is_seasonal, season_end, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            skin_id, card_id, name, skin_type, image_path, price,
            is_seasonal, season_end, description, datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Skin created: {name} for card {card_id}")
        return True
    
    def get_skin(self, skin_id: str) -> Optional[Dict]:
        """
        دریافت اطلاعات یک پوسته
        
        Args:
            skin_id: شناسه پوسته
        
        Returns:
            اطلاعات پوسته
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT skin_id, card_id, name, skin_type, image_path, price,
                   is_seasonal, season_end, description, created_at
            FROM skins
            WHERE skin_id = ?
        ''', (skin_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "skin_id": result[0],
                "card_id": result[1],
                "name": result[2],
                "skin_type": result[3],
                "image_path": result[4],
                "price": result[5],
                "is_seasonal": bool(result[6]),
                "season_end": result[7],
                "description": result[8],
                "created_at": result[9]
            }
        
        return None
    
    def get_card_skins(self, card_id: str) -> List[Dict]:
        """
        دریافت همه پوسته‌های یک کارت
        
        Args:
            card_id: شناسه کارت
        
        Returns:
            لیست پوسته‌ها
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT skin_id, card_id, name, skin_type, image_path, price,
                   is_seasonal, season_end, description, created_at
            FROM skins
            WHERE card_id = ?
            ORDER BY price DESC
        ''', (card_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        skins = []
        for row in results:
            skins.append({
                "skin_id": row[0],
                "card_id": row[1],
                "name": row[2],
                "skin_type": row[3],
                "image_path": row[4],
                "price": row[5],
                "is_seasonal": bool(row[6]),
                "season_end": row[7],
                "description": row[8],
                "created_at": row[9]
            })
        
        return skins
    
    def unlock_skin(self, user_id: int, skin_id: str) -> Dict:
        """
        باز کردن یک پوسته برای بازیکن
        
        Args:
            user_id: شناسه بازیکن
            skin_id: شناسه پوسته
        
        Returns:
            نتیجه
        """
        # دریافت اطلاعات پوسته
        skin = self.get_skin(skin_id)
        if not skin:
            return {"success": False, "error": "پوسته یافت نشد"}
        
        # بررسی اینکه قبلاً باز نشده باشد
        if self.has_skin(user_id, skin_id):
            return {"success": False, "error": "شما قبلاً این پوسته را دارید"}
        
        # بررسی سکه
        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)
        
        if coins < skin["price"]:
            return {
                "success": False,
                "error": f"سکه کافی ندارید! نیاز: {skin['price']}, دارید: {coins}"
            }
        
        # کسر سکه
        ok, err = self.db.spend_coins(user_id, skin["price"])
        if not ok:
            return {"success": False, "error": err}
        
        # باز کردن پوسته
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO player_skins (user_id, skin_id, unlocked_at)
            VALUES (?, ?, ?)
        ''', (user_id, skin_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Skin unlocked: {skin_id} for user {user_id}")
        
        return {
            "success": True,
            "skin_id": skin_id,
            "coins_spent": skin["price"],
            "remaining_coins": coins - skin["price"]
        }
    
    def has_skin(self, user_id: int, skin_id: str) -> bool:
        """
        بررسی اینکه بازیکن پوسته را دارد
        
        Args:
            user_id: شناسه بازیکن
            skin_id: شناسه پوسته
        
        Returns:
            True اگر دارد
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 1 FROM player_skins
            WHERE user_id = ? AND skin_id = ?
        ''', (user_id, skin_id))
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    def get_player_skins(self, user_id: int, card_id: str = None) -> List[Dict]:
        """
        دریافت پوسته‌های باز شده بازیکن
        
        Args:
            user_id: شناسه بازیکن
            card_id: فیلتر بر اساس کارت (اختیاری)
        
        Returns:
            لیست پوسته‌ها
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        if card_id:
            cursor.execute('''
                SELECT s.skin_id, s.card_id, s.name, s.skin_type, s.image_path,
                       ps.unlocked_at
                FROM skins s
                JOIN player_skins ps ON s.skin_id = ps.skin_id
                WHERE ps.user_id = ? AND s.card_id = ?
                ORDER BY ps.unlocked_at DESC
            ''', (user_id, card_id))
        else:
            cursor.execute('''
                SELECT s.skin_id, s.card_id, s.name, s.skin_type, s.image_path,
                       ps.unlocked_at
                FROM skins s
                JOIN player_skins ps ON s.skin_id = ps.skin_id
                WHERE ps.user_id = ?
                ORDER BY ps.unlocked_at DESC
            ''', (user_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        skins = []
        for row in results:
            skins.append({
                "skin_id": row[0],
                "card_id": row[1],
                "name": row[2],
                "skin_type": row[3],
                "image_path": row[4],
                "unlocked_at": row[5]
            })
        
        return skins
    
    def set_active_skin(self, user_id: int, card_id: str, skin_id: str) -> Dict:
        """
        تنظیم پوسته فعال برای یک کارت
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
            skin_id: شناسه پوسته (None = پیش‌فرض)
        
        Returns:
            نتیجه
        """
        # بررسی اینکه بازیکن پوسته را دارد
        if skin_id and not self.has_skin(user_id, skin_id):
            return {"success": False, "error": "شما این پوسته را ندارید"}
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        if skin_id:
            # تنظیم پوسته فعال
            cursor.execute('''
                INSERT OR REPLACE INTO active_skins
                (user_id, card_id, skin_id)
                VALUES (?, ?, ?)
            ''', (user_id, card_id, skin_id))
        else:
            # حذف پوسته فعال (بازگشت به پیش‌فرض)
            cursor.execute('''
                DELETE FROM active_skins
                WHERE user_id = ? AND card_id = ?
            ''', (user_id, card_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Active skin set: card={card_id}, skin={skin_id}, user={user_id}")
        
        return {
            "success": True,
            "card_id": card_id,
            "skin_id": skin_id
        }
    
    def get_active_skin(self, user_id: int, card_id: str) -> Optional[str]:
        """
        دریافت پوسته فعال یک کارت
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
        
        Returns:
            skin_id یا None
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT skin_id FROM active_skins
            WHERE user_id = ? AND card_id = ?
        ''', (user_id, card_id))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def get_card_image_with_skin(self, user_id: int, card_id: str) -> str:
        """
        دریافت مسیر تصویر کارت با پوسته فعال
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
        
        Returns:
            مسیر تصویر
        """
        # دریافت پوسته فعال
        active_skin_id = self.get_active_skin(user_id, card_id)
        
        if active_skin_id:
            skin = self.get_skin(active_skin_id)
            if skin:
                return skin["image_path"]
        
        # بازگشت به تصویر پیش‌فرض
        card = self.db.get_card_by_id(card_id)
        return card.image_path if card else ""


# ==================== DATABASE OPERATIONS ====================

def create_skins_tables(db_path: str):
    """
    ایجاد جداول مورد نیاز برای Skins
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # جدول تعریف پوسته‌ها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS skins (
            skin_id TEXT PRIMARY KEY,
            card_id TEXT NOT NULL,
            name TEXT NOT NULL,
            skin_type TEXT NOT NULL,
            image_path TEXT NOT NULL,
            price INTEGER NOT NULL,
            is_seasonal BOOLEAN DEFAULT 0,
            season_end TEXT,
            description TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    
    # جدول پوسته‌های باز شده بازیکنان
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_skins (
            user_id INTEGER,
            skin_id TEXT,
            unlocked_at TEXT NOT NULL,
            PRIMARY KEY (user_id, skin_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id),
            FOREIGN KEY (skin_id) REFERENCES skins (skin_id)
        )
    ''')
    
    # جدول پوسته‌های فعال
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_skins (
            user_id INTEGER,
            card_id TEXT,
            skin_id TEXT NOT NULL,
            PRIMARY KEY (user_id, card_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id),
            FOREIGN KEY (card_id) REFERENCES cards (card_id),
            FOREIGN KEY (skin_id) REFERENCES skins (skin_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Skins tables created")


# ==================== HELPER FUNCTIONS ====================

def format_skin_info(skin: Dict, unlocked: bool = False) -> str:
    """
    فرمت کردن اطلاعات پوسته
    
    Args:
        skin: اطلاعات پوسته
        unlocked: آیا باز شده است
    
    Returns:
        پیام فرمت شده
    """
    type_info = SKIN_TYPES.get(skin["skin_type"], {})
    
    text = f"""
🎨 **{skin['name']}**

📦 نوع: {type_info.get('name_fa', skin['skin_type'])}
💰 قیمت: {skin['price']} سکه
📝 {skin.get('description', type_info.get('description', ''))}
"""
    
    if skin.get("is_seasonal"):
        text += f"\n🌸 فصلی - تا {skin.get('season_end', 'نامشخص')}"
    
    if unlocked:
        text += "\n\n✅ باز شده"
    else:
        text += "\n\n🔒 قفل"
    
    return text.strip()
