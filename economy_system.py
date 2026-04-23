#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
💰 TelBattle Phase 2 - Economy System
سیستم اقتصاد: سکه، ماینینگ، شاپ
"""

import sqlite3
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

from game_core import CardRarity

logger = logging.getLogger(__name__)


class EconomySystem:
    """
    سیستم اقتصاد فاز ۲
    
    ویژگی‌ها:
    - ماینینگ روزانه (هر 5 کارت = 1 سکه)
    - تبدیل امتیاز به سکه (هر 100 امتیاز = 1 سکه)
    - شاپ (ارتقا، قلب، اسکین)
    """
    
    # قیمت‌ها
    PRICES = {
        'upgrade_normal_to_epic': 100,
        'upgrade_epic_to_legend': 500,
        'heart_increase': 200,  # +1 قلب دائمی
        'skin_normal': 50,
        'skin_special': 150,
        'skin_seasonal': 100,
    }
    
    # نرخ تبدیل
    SCORE_TO_COIN_RATE = 100  # هر 100 امتیاز = 1 سکه
    MINING_RATE = 5  # هر 5 کارت = 1 سکه
    
    # محدودیت‌ها
    MAX_HEARTS = 15  # حداکثر قلب
    DEFAULT_HEARTS = 10  # قلب پیش‌فرض
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    # ==================== COIN MANAGEMENT ====================
    
    def get_coins(self, user_id: int) -> int:
        """دریافت موجودی سکه"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT coins FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    
    def add_coins(self, user_id: int, amount: int, reason: str = "") -> bool:
        """
        اضافه کردن سکه
        
        Args:
            user_id: شناسه بازیکن
            amount: مقدار سکه
            reason: دلیل (برای لاگ)
        
        Returns:
            موفقیت
        """
        if amount <= 0:
            return False
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE players 
                SET coins = coins + ?
                WHERE user_id = ?
            ''', (amount, user_id))
            
            conn.commit()
            
            logger.info(f"User {user_id} received {amount} coins. Reason: {reason}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add coins: {e}")
            return False
        finally:
            conn.close()
    
    def spend_coins(self, user_id: int, amount: int, reason: str = "") -> Tuple[bool, Optional[str]]:
        """
        خرج کردن سکه
        
        Args:
            user_id: شناسه بازیکن
            amount: مقدار سکه
            reason: دلیل (برای لاگ)
        
        Returns:
            (success, error_message)
        """
        if amount <= 0:
            return False, "مقدار نامعتبر"
        
        current_coins = self.get_coins(user_id)
        
        if current_coins < amount:
            return False, f"سکه کافی نیست! (موجودی: {current_coins}, نیاز: {amount})"
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE players 
                SET coins = coins - ?
                WHERE user_id = ?
            ''', (amount, user_id))
            
            conn.commit()
            
            logger.info(f"User {user_id} spent {amount} coins. Reason: {reason}")
            return True, None
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to spend coins: {e}")
            return False, f"خطا: {str(e)}"
        finally:
            conn.close()
    
    # ==================== MINING ====================
    
    def calculate_daily_mining(self, user_id: int) -> int:
        """
        محاسبه ماینینگ روزانه
        
        فرمول: floor(تعداد_کارت_های_Normal_Epic_Legend / 5)
        
        Args:
            user_id: شناسه بازیکن
        
        Returns:
            تعداد سکه قابل ماینینگ
        """
        player_cards = self.db.get_player_cards(user_id)
        
        # فقط Normal, Epic, Legend (Rare حساب نمی‌شود)
        mineable_cards = [
            c for c in player_cards 
            if c.rarity in [CardRarity.NORMAL, CardRarity.EPIC, CardRarity.LEGEND]
        ]
        
        coins = len(mineable_cards) // self.MINING_RATE
        
        logger.info(f"User {user_id} mining: {len(mineable_cards)} cards → {coins} coins")
        
        return coins
    
    def can_claim_mining(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        بررسی امکان دریافت ماینینگ روزانه
        
        Returns:
            (can_claim, error_message)
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT last_mining_claim 
                FROM players 
                WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row or not row[0]:
                return True, None
            
            last_claim = datetime.fromisoformat(row[0])
            now = datetime.now()
            time_diff = now - last_claim
            
            if time_diff < timedelta(hours=24):
                remaining = timedelta(hours=24) - time_diff
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                
                return False, f"تا ماینینگ بعدی {hours} ساعت و {minutes} دقیقه مانده"
            
            return True, None
            
        finally:
            conn.close()
    
    def claim_daily_mining(self, user_id: int) -> Tuple[bool, int, Optional[str]]:
        """
        دریافت ماینینگ روزانه
        
        Returns:
            (success, coins_earned, error_message)
        """
        # بررسی امکان
        can_claim, error = self.can_claim_mining(user_id)
        if not can_claim:
            return False, 0, error
        
        # محاسبه ماینینگ
        coins = self.calculate_daily_mining(user_id)
        
        if coins == 0:
            return False, 0, "شما کارت کافی برای ماینینگ ندارید! (حداقل 5 کارت)"
        
        # اضافه کردن سکه
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE players 
                SET coins = coins + ?,
                    last_mining_claim = ?
                WHERE user_id = ?
            ''', (coins, datetime.now().isoformat(), user_id))
            
            conn.commit()
            
            logger.info(f"User {user_id} claimed mining: {coins} coins")
            return True, coins, None
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to claim mining: {e}")
            return False, 0, f"خطا: {str(e)}"
        finally:
            conn.close()
    
    # ==================== SCORE CONVERSION ====================
    
    def convert_score_to_coins(self, user_id: int, score_amount: int) -> Tuple[bool, int, Optional[str]]:
        """
        تبدیل امتیاز به سکه
        
        نرخ: هر 100 امتیاز = 1 سکه
        
        Args:
            user_id: شناسه بازیکن
            score_amount: مقدار امتیاز برای تبدیل
        
        Returns:
            (success, coins_earned, error_message)
        """
        if score_amount < self.SCORE_TO_COIN_RATE:
            return False, 0, f"حداقل {self.SCORE_TO_COIN_RATE} امتیاز نیاز است!"
        
        # دریافت امتیاز فعلی
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT total_score FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return False, 0, "بازیکن پیدا نشد!"
            
            current_score = row[0]
            
            if current_score < score_amount:
                return False, 0, f"امتیاز کافی نیست! (موجودی: {current_score})"
            
            # محاسبه سکه
            coins = score_amount // self.SCORE_TO_COIN_RATE
            
            # کم کردن امتیاز و اضافه کردن سکه
            cursor.execute('''
                UPDATE players 
                SET total_score = total_score - ?,
                    coins = coins + ?
                WHERE user_id = ?
            ''', (score_amount, coins, user_id))
            
            conn.commit()
            
            logger.info(f"User {user_id} converted {score_amount} score to {coins} coins")
            return True, coins, None
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to convert score: {e}")
            return False, 0, f"خطا: {str(e)}"
        finally:
            conn.close()
    
    # ==================== SHOP ====================
    
    def buy_heart_increase(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        خرید افزایش قلب دائمی (+1 قلب)
        
        قیمت: 200 سکه
        حداکثر: 15 قلب
        
        Returns:
            (success, error_message)
        """
        price = self.PRICES['heart_increase']
        
        # بررسی موجودی
        success, error = self.spend_coins(user_id, price, "buy_heart_increase")
        if not success:
            return False, error
        
        # دریافت قلب فعلی
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT max_hearts FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            
            if not row:
                # بازگشت سکه
                self.add_coins(user_id, price, "refund_heart_increase")
                return False, "بازیکن پیدا نشد!"
            
            current_hearts = row[0] if row[0] else self.DEFAULT_HEARTS
            
            if current_hearts >= self.MAX_HEARTS:
                # بازگشت سکه
                self.add_coins(user_id, price, "refund_heart_increase")
                return False, f"حداکثر قلب ({self.MAX_HEARTS}) است!"
            
            # افزایش قلب
            new_hearts = current_hearts + 1
            
            cursor.execute('''
                UPDATE players 
                SET max_hearts = ?
                WHERE user_id = ?
            ''', (new_hearts, user_id))
            
            conn.commit()
            
            logger.info(f"User {user_id} bought heart increase: {current_hearts} → {new_hearts}")
            return True, None
            
        except Exception as e:
            conn.rollback()
            # بازگشت سکه
            self.add_coins(user_id, price, "refund_heart_increase")
            logger.error(f"Failed to buy heart increase: {e}")
            return False, f"خطا: {str(e)}"
        finally:
            conn.close()
    
    def buy_card_upgrade(self, user_id: int, upgrade_type: str) -> Tuple[bool, Optional[str]]:
        """
        خرید ارتقای کارت با سکه
        
        Args:
            user_id: شناسه بازیکن
            upgrade_type: 'normal_to_epic' یا 'epic_to_legend'
        
        Returns:
            (success, error_message)
        """
        if upgrade_type == 'normal_to_epic':
            price = self.PRICES['upgrade_normal_to_epic']
        elif upgrade_type == 'epic_to_legend':
            price = self.PRICES['upgrade_epic_to_legend']
        else:
            return False, "نوع ارتقا نامعتبر!"
        
        # بررسی موجودی
        success, error = self.spend_coins(user_id, price, f"buy_{upgrade_type}")
        if not success:
            return False, error
        
        logger.info(f"User {user_id} bought {upgrade_type} for {price} coins")
        return True, None
    
    # ==================== STATS ====================
    
    def get_economy_stats(self, user_id: int) -> Dict:
        """دریافت آمار اقتصادی بازیکن"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT coins, total_score, max_hearts, last_mining_claim
                FROM players 
                WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return {
                    'coins': 0,
                    'score': 0,
                    'max_hearts': self.DEFAULT_HEARTS,
                    'last_mining_claim': None,
                    'mineable_cards': 0,
                    'daily_mining': 0
                }
            
            # محاسبه ماینینگ روزانه
            daily_mining = self.calculate_daily_mining(user_id)
            
            # تعداد کارت‌های قابل ماینینگ
            player_cards = self.db.get_player_cards(user_id)
            mineable_cards = len([
                c for c in player_cards 
                if c.rarity in [CardRarity.NORMAL, CardRarity.EPIC, CardRarity.LEGEND]
            ])
            
            return {
                'coins': row[0] if row[0] else 0,
                'score': row[1] if row[1] else 0,
                'max_hearts': row[2] if row[2] else self.DEFAULT_HEARTS,
                'last_mining_claim': row[3],
                'mineable_cards': mineable_cards,
                'daily_mining': daily_mining
            }
            
        finally:
            conn.close()


# ==================== HELPER FUNCTIONS ====================

def format_coins(amount: int) -> str:
    """فرمت کردن سکه برای نمایش"""
    return f"💰 {amount:,} سکه"


def format_economy_stats(stats: Dict) -> str:
    """فرمت کردن آمار اقتصادی برای نمایش"""
    text = (
        f"💰 **آمار اقتصادی**\n\n"
        f"💵 موجودی سکه: {stats['coins']:,}\n"
        f"⭐ امتیاز: {stats['score']:,}\n"
        f"❤️ قلب: {stats['max_hearts']}\n\n"
        f"⛏️ **ماینینگ روزانه**\n"
        f"  • کارت‌های قابل ماینینگ: {stats['mineable_cards']}\n"
        f"  • درآمد روزانه: {stats['daily_mining']} سکه\n"
    )
    
    if stats['last_mining_claim']:
        last_claim = datetime.fromisoformat(stats['last_mining_claim'])
        text += f"  • آخرین دریافت: {last_claim.strftime('%Y-%m-%d %H:%M')}\n"
    
    return text
