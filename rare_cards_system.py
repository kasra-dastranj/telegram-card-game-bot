#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌟 TelBattle Phase 2 - Rare Cards System
سیستم کارت‌های نایاب (Rare)
"""

import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime

from game_core import Card, CardRarity

logger = logging.getLogger(__name__)


# ==================== RARE CARDS SYSTEM ====================

class RareCardsSystem:
    """
    سیستم Rare Cards
    
    ویژگی‌ها:
    - کارت‌های منحصربفرد و محدود
    - فقط از لیدربرد هفتگی یا خرید
    - آمار خاص و طراحی دستی
    - بدون سهم در ماینینگ روزانه
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def create_rare_card(
        self,
        card_id: str,
        name: str,
        power: int,
        speed: int,
        iq: int,
        popularity: int,
        abilities: List[str],
        biography: str = "",
        image_path: str = "",
        price_coins: int = 1000,
        limited_quantity: int = 100
    ) -> bool:
        """
        ایجاد یک کارت Rare
        
        Args:
            card_id: شناسه کارت
            name: نام کارت
            power, speed, iq, popularity: آمار (می‌تواند خارج از محدودیت باشد)
            abilities: لیست توانایی‌ها
            biography: بیوگرافی
            image_path: مسیر تصویر
            price_coins: قیمت خرید (اگر قابل خرید باشد)
            limited_quantity: تعداد محدود در کل بازی
        
        Returns:
            موفقیت
        """
        card = Card(
            card_id=card_id,
            name=name,
            rarity=CardRarity.RARE,
            power=power,
            speed=speed,
            iq=iq,
            popularity=popularity,
            abilities=abilities,
            biography=biography,
            image_path=image_path,
            card_type=None  # Rare cards don't have type
        )
        
        # اضافه کردن کارت به دیتابیس
        success = self.db.add_card(card)
        
        if success:
            # ذخیره اطلاعات اضافی Rare
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO rare_cards_info
                (card_id, price_coins, limited_quantity, total_issued)
                VALUES (?, ?, ?, 0)
            ''', (card_id, price_coins, limited_quantity))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Rare card created: {name}")
        
        return success
    
    def get_rare_card_info(self, card_id: str) -> Optional[Dict]:
        """
        دریافت اطلاعات Rare card
        
        Args:
            card_id: شناسه کارت
        
        Returns:
            اطلاعات کارت
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_id, price_coins, limited_quantity, total_issued
            FROM rare_cards_info
            WHERE card_id = ?
        ''', (card_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "card_id": result[0],
                "price_coins": result[1],
                "limited_quantity": result[2],
                "total_issued": result[3],
                "remaining": result[2] - result[3]
            }
        
        return None
    
    def can_issue_rare_card(self, card_id: str) -> bool:
        """
        بررسی اینکه آیا می‌توان کارت Rare را صادر کرد
        
        Args:
            card_id: شناسه کارت
        
        Returns:
            True اگر موجودی باقی مانده باشد
        """
        info = self.get_rare_card_info(card_id)
        if not info:
            return False
        
        return info["remaining"] > 0
    
    def issue_rare_card(self, user_id: int, card_id: str, source: str = "leaderboard") -> Dict:
        """
        صدور کارت Rare به بازیکن
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
            source: منبع دریافت (leaderboard, purchase, event)
        
        Returns:
            نتیجه
        """
        # بررسی موجودی
        if not self.can_issue_rare_card(card_id):
            return {
                "success": False,
                "error": "این کارت Rare تمام شده است!"
            }
        
        # بررسی اینکه بازیکن قبلاً این کارت را ندارد
        player_cards = self.db.get_player_cards(user_id)
        if any(c.card_id == card_id for c in player_cards):
            return {
                "success": False,
                "error": "شما قبلاً این کارت Rare را دارید!"
            }
        
        # اضافه کردن کارت به بازیکن
        success = self.db.add_card_to_player(user_id, card_id)
        
        if success:
            # بروزرسانی تعداد صادر شده
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE rare_cards_info
                SET total_issued = total_issued + 1
                WHERE card_id = ?
            ''', (card_id,))
            
            # لاگ صدور
            cursor.execute('''
                INSERT INTO rare_cards_log
                (user_id, card_id, source, issued_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, card_id, source, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Rare card issued: {card_id} to user {user_id} from {source}")
            
            return {
                "success": True,
                "card_id": card_id
            }
        
        return {
            "success": False,
            "error": "خطا در صدور کارت"
        }
    
    def get_available_rare_cards(self) -> List[Dict]:
        """
        دریافت لیست کارت‌های Rare موجود
        
        Returns:
            لیست کارت‌ها با اطلاعات موجودی
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.card_id, c.name, c.power, c.speed, c.iq, c.popularity,
                   r.price_coins, r.limited_quantity, r.total_issued
            FROM cards c
            JOIN rare_cards_info r ON c.card_id = r.card_id
            WHERE c.rarity = 'rare'
            ORDER BY c.name
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        cards = []
        for row in results:
            cards.append({
                "card_id": row[0],
                "name": row[1],
                "power": row[2],
                "speed": row[3],
                "iq": row[4],
                "popularity": row[5],
                "price_coins": row[6],
                "limited_quantity": row[7],
                "total_issued": row[8],
                "remaining": row[7] - row[8],
                "available": (row[7] - row[8]) > 0
            })
        
        return cards
    
    def purchase_rare_card(self, user_id: int, card_id: str) -> Dict:
        """
        خرید کارت Rare با سکه
        
        Args:
            user_id: شناسه بازیکن
            card_id: شناسه کارت
        
        Returns:
            نتیجه
        """
        # دریافت اطلاعات کارت
        info = self.get_rare_card_info(card_id)
        if not info:
            return {"success": False, "error": "کارت یافت نشد"}
        
        # بررسی موجودی
        if info["remaining"] <= 0:
            return {"success": False, "error": "این کارت تمام شده است"}
        
        # بررسی سکه بازیکن
        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)
        
        if coins < info["price_coins"]:
            return {
                "success": False,
                "error": f"سکه کافی ندارید! نیاز: {info['price_coins']}, دارید: {coins}"
            }
        
        # کسر سکه
        new_coins = coins - info["price_coins"]
        self.db.update_player(user_id, coins=new_coins)
        
        # صدور کارت
        result = self.issue_rare_card(user_id, card_id, source="purchase")
        
        if result["success"]:
            result["coins_spent"] = info["price_coins"]
            result["remaining_coins"] = new_coins
        else:
            # برگشت سکه در صورت خطا
            self.db.update_player(user_id, coins=coins)
        
        return result


# ==================== DATABASE OPERATIONS ====================

def create_rare_cards_tables(db_path: str):
    """
    ایجاد جداول مورد نیاز برای Rare Cards
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # جدول اطلاعات Rare Cards
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rare_cards_info (
            card_id TEXT PRIMARY KEY,
            price_coins INTEGER NOT NULL,
            limited_quantity INTEGER NOT NULL,
            total_issued INTEGER DEFAULT 0,
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    
    # جدول لاگ صدور Rare Cards
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rare_cards_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card_id TEXT NOT NULL,
            source TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id),
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Rare cards tables created")


# ==================== HELPER FUNCTIONS ====================

def format_rare_card_info(card_info: Dict) -> str:
    """
    فرمت کردن اطلاعات کارت Rare
    
    Args:
        card_info: اطلاعات کارت
    
    Returns:
        پیام فرمت شده
    """
    text = f"""
🌟 **{card_info['name']}** (Rare)

📊 آمار:
  ⚡ قدرت: {card_info['power']}
  🏃 سرعت: {card_info['speed']}
  🧠 هوش: {card_info['iq']}
  ⭐ محبوبیت: {card_info['popularity']}

💰 قیمت: {card_info['price_coins']} سکه
📦 موجودی: {card_info['remaining']}/{card_info['limited_quantity']}
"""
    
    if card_info['remaining'] <= 0:
        text += "\n❌ تمام شده!"
    elif card_info['remaining'] <= 10:
        text += "\n⚠️ تعداد محدود باقی مانده!"
    
    return text.strip()
