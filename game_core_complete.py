#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎮 Telegram Card Game - Core System with Individual Card Cooldown
سیستم‌های پایه بازی کارت تلگرام - فاز ۱ + PvP + Cooldown جداگانه
"""

import sqlite3
import json
import os
import random
import uuid
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

# تنظیم لاگینگ
logger = logging.getLogger(__name__)

# ==================== ENUMS ====================

class CardRarity(Enum):
    NORMAL = "normal"
    EPIC = "epic" 
    LEGEND = "legend"

class StatType(Enum):
    POWER = "power"
    SPEED = "speed"
    IQ = "iq"
    POPULARITY = "popularity"

class FightStatus(Enum):
    WAITING_FOR_OPPONENT = "waiting_opponent"
    CHALLENGER_CARD_SELECTED = "challenger_card_selected"
    OPPONENT_CARD_SELECTED = "opponent_card_selected"
    BOTH_CARDS_SELECTED = "both_cards_selected"
    CHALLENGER_STAT_SELECTED = "challenger_stat_selected"
    OPPONENT_STAT_SELECTED = "opponent_stat_selected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# ==================== MODELS ====================

@dataclass
class Card:
    card_id: str
    name: str
    rarity: CardRarity
    power: int  # 1-100
    speed: int  # 1-100
    iq: int     # 1-100
    popularity: int  # 1-100
    abilities: List[str]
    dialogs: List[str] = None
    biography: str = "Biography not available."
    image_path: str = ""
    created_at: datetime = None    def __p
ost_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        
        # اعتبارسنجی آمار
        self.power = max(1, min(100, self.power))
        self.speed = max(1, min(100, self.speed))
        self.iq = max(1, min(100, self.iq))
        self.popularity = max(1, min(100, self.popularity))
        if self.dialogs is None:
            self.dialogs = []
    
    def get_ability_count(self) -> int:
        """تعداد ابیلیتی مجاز بر اساس کمیابی"""
        ability_counts = {
            CardRarity.NORMAL: 1,
            CardRarity.EPIC: 2,
            CardRarity.LEGEND: 3
        }
        return ability_counts[self.rarity]
    
    def get_total_stats(self) -> int:
        """مجموع کل آمار"""
        return self.power + self.speed + self.iq + self.popularity
    
    def get_stat_value(self, stat_type: StatType) -> int:
        """دریافت مقدار ویژگی خاص"""
        return getattr(self, stat_type.value)
    
    def to_dict(self) -> Dict:
        """تبدیل به دیکشنری برای ذخیره"""
        return {
            'card_id': self.card_id,
            'name': self.name,
            'rarity': self.rarity.value,
            'power': self.power,
            'speed': self.speed,
            'iq': self.iq,
            'popularity': self.popularity,
            'abilities': json.dumps(self.abilities, ensure_ascii=False),
            'dialogs': json.dumps(self.dialogs or [], ensure_ascii=False),
            'biography': self.biography,
            'image_path': self.image_path,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        """ایجاد از دیکشنری"""
        abilities = []
        try:
            abilities_raw = data.get('abilities')
            if isinstance(abilities_raw, str):
                abilities = json.loads(abilities_raw) if abilities_raw else []
            elif isinstance(abilities_raw, list):
                abilities = abilities_raw
        except Exception:
            abilities = []
        
        dialogs_list = []
        dialogs_raw = data.get('dialogs')
        try:
            if isinstance(dialogs_raw, str):
                dialogs_list = json.loads(dialogs_raw) if dialogs_raw else []
            elif isinstance(dialogs_raw, list):
                dialogs_list = dialogs_raw
        except Exception:
            dialogs_list = []
        
        return cls(
            card_id=data['card_id'],
            name=data['name'],
            rarity=CardRarity(data['rarity']),
            power=data['power'],
            speed=data['speed'],
            iq=data['iq'],
            popularity=data['popularity'],
            abilities=abilities,
            dialogs=dialogs_list,
            biography=data.get('biography', 'Biography not available.'),
            image_path=data.get('image_path', ''),
            created_at=datetime.fromisoformat(data['created_at'])
        )

@dataclass
class Player:
    user_id: int
    username: str
    first_name: str
    hearts: int = 10  # تغییر از 5 به 10
    lives: int = 10
    total_score: int = 0
    last_heart_reset: datetime = None
    last_lives_reset: Optional[datetime] = None
    last_claim: Optional[datetime] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_heart_reset is None:
            self.last_heart_reset = datetime.now()
        if self.last_lives_reset is None:
            self.last_lives_reset = datetime.now()

@dataclass
class PvPFight:
    fight_id: str
    challenger_id: int
    opponent_id: int
    challenger_card_id: Optional[str] = None
    opponent_card_id: Optional[str] = None
    challenger_stat: Optional[str] = None
    opponent_stat: Optional[str] = None
    status: FightStatus = FightStatus.WAITING_FOR_OPPONENT
    created_at: datetime = None
    chat_id: Optional[int] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()# =====
=============== DATABASE MANAGER ====================

class DatabaseManager:
    def __init__(self, db_path: str = "game_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """ایجاد جداول دیتابیس"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # جدول کارت‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                card_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                rarity TEXT NOT NULL,
                power INTEGER NOT NULL,
                speed INTEGER NOT NULL,
                iq INTEGER NOT NULL,
                popularity INTEGER NOT NULL,
                abilities TEXT NOT NULL,
                dialogs TEXT,
                biography TEXT,
                image_path TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # جدول بازیکنان
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                hearts INTEGER DEFAULT 10,
                lives INTEGER DEFAULT 10,
                total_score INTEGER DEFAULT 0,
                last_heart_reset TEXT,
                last_lives_reset TEXT,
                last_claim TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # جدول کارت‌های بازیکنان
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                card_id TEXT,
                obtained_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES players (user_id),
                FOREIGN KEY (card_id) REFERENCES cards (card_id),
                UNIQUE(user_id, card_id)
            )
        ''')
        
        # جدول فایت‌های فعال PvP
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_fights (
                fight_id TEXT PRIMARY KEY,
                challenger_id INTEGER NOT NULL,
                opponent_id INTEGER NOT NULL,
                challenger_card_id TEXT,
                opponent_card_id TEXT,
                challenger_stat TEXT,
                opponent_stat TEXT,
                status TEXT NOT NULL DEFAULT 'waiting_opponent',
                chat_id INTEGER,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (challenger_id) REFERENCES players (user_id),
                FOREIGN KEY (opponent_id) REFERENCES players (user_id)
            )
        ''')
        
        # جدول تاریخچه فایت‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fight_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_card_id TEXT,
                opponent_card_id TEXT,
                stat_used TEXT,
                result TEXT,
                score_gained INTEGER,
                hearts_lost INTEGER,
                fought_at TEXT,
                fight_type TEXT DEFAULT 'pvp',
                opponent_user_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES players (user_id)
            )
        ''')
        
        # جدول کولدان کارت‌ها (سیستم قدیمی)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_cooldowns (
                user_id INTEGER,
                card_id TEXT,
                wins_count INTEGER DEFAULT 0,
                last_win_time TEXT,
                cooldown_until TEXT,
                is_in_cooldown BOOLEAN DEFAULT 0,
                PRIMARY KEY (user_id, card_id),
                FOREIGN KEY (user_id) REFERENCES players (user_id),
                FOREIGN KEY (card_id) REFERENCES cards (card_id)
            )
        ''')
        
        # جدول تنظیمات Cooldown هر کارت - NEW
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_cooldown_settings (
                card_id TEXT PRIMARY KEY,
                win_limit INTEGER DEFAULT 10,
                cooldown_hours INTEGER DEFAULT 24,
                enabled BOOLEAN DEFAULT 1,
                FOREIGN KEY (card_id) REFERENCES cards (card_id)
            )
        ''')
        
        conn.commit()
        conn.close()    # ====
================ CARD OPERATIONS ====================
    
    def add_card(self, card: Card) -> bool:
        """اضافه کردن کارت جدید"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            card_data = card.to_dict()
            cursor.execute('''
            INSERT INTO cards (card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                card_data['card_id'], card_data['name'], card_data['rarity'],
                card_data['power'], card_data['speed'], card_data['iq'], card_data['popularity'],
                card_data['abilities'], card_data['dialogs'], card_data['biography'], 
                card_data['image_path'], card_data['created_at']
            ))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            if conn:
                conn.close()
            return False
    
    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """دریافت کارت بر اساس ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, created_at
            FROM cards
            WHERE card_id = ?
        ''', (card_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'created_at']
            card_data = dict(zip(columns, result))
            return Card.from_dict(card_data)
        return None
    
    def get_card_by_name(self, name: str) -> Optional[Card]:
        """دریافت کارت بر اساس نام"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, created_at
            FROM cards
            WHERE lower(name) = lower(?)
            LIMIT 1
        ''', (name,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'created_at']
            card_data = dict(zip(columns, result))
            return Card.from_dict(card_data)
        return None
    
    def get_all_cards(self) -> List[Card]:
        """دریافت تمام کارت‌ها"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, created_at
            FROM cards
            ORDER BY created_at DESC
        ''')
        results = cursor.fetchall()
        conn.close()
        
        cards = []
        columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'created_at']
        for result in results:
            card_data = dict(zip(columns, result))
            cards.append(Card.from_dict(card_data))
        
        return cards
    
    def delete_card(self, card_id: str) -> bool:
        """حذف کارت"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM cards WHERE card_id = ?', (card_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        return deleted   
 # ==================== PLAYER OPERATIONS ====================
    
    def get_or_create_player(self, user_id: int, username: str = None, first_name: str = None) -> Player:
        """دریافت یا ایجاد بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            columns = ['user_id', 'username', 'first_name', 'hearts', 'lives', 'total_score', 'last_heart_reset', 'last_lives_reset', 'last_claim', 'created_at']
            player_data = dict(zip(columns, result))
            
            # تبدیل تاریخ‌ها
            def _to_dt(value, default=None):
                if value is None:
                    return default
                if isinstance(value, datetime):
                    return value
                try:
                    if not isinstance(value, str):
                        value = str(value)
                    try:
                        return datetime.fromisoformat(value)
                    except Exception:
                        try:
                            ts = float(value)
                            return datetime.fromtimestamp(ts)
                        except Exception:
                            try:
                                if value.endswith('Z'):
                                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                            except Exception:
                                pass
                            return default
                except Exception:
                    return default

            player_data['last_heart_reset'] = _to_dt(player_data.get('last_heart_reset'), datetime.now())
            player_data['last_lives_reset'] = _to_dt(player_data.get('last_lives_reset'), datetime.now())
            player_data['last_claim'] = _to_dt(player_data.get('last_claim'), None)
            player_data['created_at'] = _to_dt(player_data.get('created_at'), datetime.now())

            # اطمینان از عددی بودن فیلدها
            for num_field in ['hearts', 'lives', 'total_score']:
                try:
                    player_data[num_field] = int(player_data.get(num_field) or 0)
                except Exception:
                    player_data[num_field] = 0

            player = Player(**player_data)
        else:
            # ایجاد بازیکن جدید
            player = Player(
                user_id=user_id,
                username=username or "",
                first_name=first_name or "بازیکن"
            )
            
            cursor.execute('''
                INSERT INTO players (user_id, username, first_name, hearts, lives, total_score, last_heart_reset, last_lives_reset, last_claim, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                player.user_id, player.username, player.first_name,
                player.hearts, player.lives, player.total_score,
                player.last_heart_reset.isoformat(), player.last_lives_reset.isoformat(),
                player.last_claim.isoformat() if player.last_claim else None,
                player.created_at.isoformat()
            ))
            
            conn.commit()
        
        conn.close()
        return player
    
    def update_player(self, player: Player) -> None:
        """بروزرسانی اطلاعات بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE players 
            SET username = ?, first_name = ?, hearts = ?, lives = ?, total_score = ?, 
                last_heart_reset = ?, last_lives_reset = ?, last_claim = ?
            WHERE user_id = ?
        ''', (
            player.username, player.first_name, player.hearts, player.lives, player.total_score,
            player.last_heart_reset.isoformat(),
            player.last_lives_reset.isoformat() if player.last_lives_reset else None,
            player.last_claim.isoformat() if player.last_claim else None,
            player.user_id
        ))
        
        conn.commit()
        conn.close()
    
    def get_player_cards(self, user_id: int) -> List[Card]:
        """دریافت کارت‌های بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.card_id, c.name, c.rarity, c.power, c.speed, c.iq, c.popularity, c.abilities, c.dialogs, c.biography, c.image_path, c.created_at
            FROM cards c
            JOIN player_cards pc ON c.card_id = pc.card_id
            WHERE pc.user_id = ?
            ORDER BY pc.obtained_at DESC
        ''', (user_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        cards = []
        columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'created_at']
        for result in results:
            card_data = dict(zip(columns, result))
            cards.append(Card.from_dict(card_data))
        
        return cards 
   # ==================== CARD COOLDOWN SETTINGS - NEW ====================
    
    def get_card_cooldown_settings(self, card_id: str) -> Dict:
        """دریافت تنظیمات cooldown کارت خاص"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT win_limit, cooldown_hours, enabled 
                FROM card_cooldown_settings 
                WHERE card_id = ?
            ''', (card_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'win_limit': result[0],
                    'cooldown_hours': result[1],
                    'enabled': bool(result[2])
                }
            else:
                # اگر تنظیمات وجود ندارد، مقادیر پیش‌فرض برگردان
                return {
                    'win_limit': 10,
                    'cooldown_hours': 24,
                    'enabled': True
                }
        finally:
            conn.close()
    
    def set_card_cooldown_settings(self, card_id: str, win_limit: int = None, 
                                 cooldown_hours: int = None, enabled: bool = None) -> bool:
        """تنظیم cooldown کارت خاص"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # بررسی وجود رکورد
            cursor.execute('SELECT card_id FROM card_cooldown_settings WHERE card_id = ?', (card_id,))
            exists = cursor.fetchone()
            
            if exists:
                # بروزرسانی رکورد موجود
                updates = []
                values = []
                
                if win_limit is not None:
                    updates.append('win_limit = ?')
                    values.append(win_limit)
                if cooldown_hours is not None:
                    updates.append('cooldown_hours = ?')
                    values.append(cooldown_hours)
                if enabled is not None:
                    updates.append('enabled = ?')
                    values.append(enabled)
                
                if updates:
                    values.append(card_id)
                    query = f"UPDATE card_cooldown_settings SET {', '.join(updates)} WHERE card_id = ?"
                    cursor.execute(query, values)
            else:
                # ایجاد رکورد جدید
                cursor.execute('''
                    INSERT INTO card_cooldown_settings (card_id, win_limit, cooldown_hours, enabled)
                    VALUES (?, ?, ?, ?)
                ''', (
                    card_id,
                    win_limit if win_limit is not None else 10,
                    cooldown_hours if cooldown_hours is not None else 24,
                    enabled if enabled is not None else True
                ))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting card cooldown settings: {e}")
            return False
        finally:
            conn.close()
    
    def get_all_card_cooldown_settings(self) -> Dict[str, Dict]:
        """دریافت تنظیمات cooldown همه کارت‌ها"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT c.card_id, c.name, c.rarity,
                       COALESCE(ccs.win_limit, 10) as win_limit,
                       COALESCE(ccs.cooldown_hours, 24) as cooldown_hours,
                       COALESCE(ccs.enabled, 1) as enabled
                FROM cards c
                LEFT JOIN card_cooldown_settings ccs ON c.card_id = ccs.card_id
                WHERE c.rarity IN ('epic', 'legend')
                ORDER BY c.rarity DESC, c.name
            ''')
            
            results = cursor.fetchall()
            settings = {}
            
            for result in results:
                card_id, name, rarity, win_limit, cooldown_hours, enabled = result
                settings[card_id] = {
                    'name': name,
                    'rarity': rarity,
                    'win_limit': win_limit,
                    'cooldown_hours': cooldown_hours,
                    'enabled': bool(enabled)
                }
            
            return settings
        finally:
            conn.close()
    
    # ==================== LEADERBOARD & STATS ====================
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """دریافت لیدربورد"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.user_id, p.username, p.first_name, p.total_score,
                   COUNT(pc.card_id) as card_count
            FROM players p
            LEFT JOIN player_cards pc ON p.user_id = pc.user_id
            GROUP BY p.user_id
            ORDER BY p.total_score DESC
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        leaderboard = []
        for result in results:
            leaderboard.append({
                'user_id': result[0],
                'username': result[1],
                'first_name': result[2],
                'total_score': result[3],
                'card_count': result[4]
            })
        
        return leaderboard# =======
============= GAME LOGIC ====================

class GameLogic:
    def __init__(self, db: DatabaseManager, config: Optional[dict] = None):
        self.db = db
        cfg = config or {}
        game_cfg = cfg.get('game_settings', cfg) if isinstance(cfg, dict) else {}

        # تنظیمات پیش‌فرض بازی (قابل پیکربندی)
        self.DAILY_HEARTS = int(game_cfg.get('daily_hearts', 10))  # تغییر از 5 به 10
        self.HEART_RESET_HOURS = int(game_cfg.get('heart_reset_hours', 24))
        self.CLAIM_COOLDOWN_HOURS = int(game_cfg.get('claim_cooldown_hours', 24))
        
        # تنظیمات Cooldown کارت‌ها
        cooldown_cfg = game_cfg.get('card_cooldown', {}) if isinstance(game_cfg, dict) else {}
        self.CARD_COOLDOWN_ENABLED = bool(cooldown_cfg.get('enabled', True))
        self.CARD_COOLDOWN_WIN_LIMIT = int(cooldown_cfg.get('win_limit', 10))
        self.CARD_COOLDOWN_HOURS = int(cooldown_cfg.get('cooldown_hours', 24))

        # نرخ ظهور کارت‌ها
        rates = game_cfg.get('card_drop_rates', {}) if isinstance(game_cfg, dict) else {}
        normal = int(rates.get('normal', 65))
        epic = int(rates.get('epic', 25))
        legend = int(rates.get('legend', 10))
        total = normal + epic + legend
        if total != 100 and total > 0:
            normal = round((normal / total) * 100)
            epic = round((epic / total) * 100)
            legend = 100 - (normal + epic)

        self.CARD_DROP_RATES = {
            CardRarity.NORMAL: normal,
            CardRarity.EPIC: epic,
            CardRarity.LEGEND: legend
        }

    def check_and_reset_hearts(self, player: Player) -> Player:
        """بررسی و ریست قلب‌ها در صورت نیاز"""
        now = datetime.now()
        time_diff = now - player.last_heart_reset
        
        if time_diff.total_seconds() >= self.HEART_RESET_HOURS * 3600:
            player.hearts = self.DAILY_HEARTS
            player.last_heart_reset = now
            self.db.update_player(player)
        
        return player
    
    def is_card_eligible_for_cooldown(self, card: Card) -> bool:
        """بررسی اینکه آیا کارت مشمول سیستم cooldown است یا نه"""
        if not self.CARD_COOLDOWN_ENABLED:
            return False
        return card.rarity in [CardRarity.EPIC, CardRarity.LEGEND]
    
    def is_card_in_cooldown(self, user_id: int, card_id: str) -> Tuple[bool, Optional[datetime]]:
        """بررسی cooldown کارت با تنظیمات جداگانه"""
        card = self.db.get_card_by_id(card_id)
        if not card or not self.is_card_eligible_for_cooldown(card):
            return False, None
        
        # دریافت تنظیمات خاص این کارت
        card_settings = self.db.get_card_cooldown_settings(card_id)
        if not card_settings['enabled']:
            return False, None
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT is_in_cooldown, cooldown_until 
                FROM card_cooldowns 
                WHERE user_id = ? AND card_id = ?
            ''', (user_id, card_id))
            
            result = cursor.fetchone()
            if not result:
                return False, None
            
            is_in_cooldown, cooldown_until_str = result
            
            if not is_in_cooldown or not cooldown_until_str:
                return False, None
            
            cooldown_until = datetime.fromisoformat(cooldown_until_str)
            now = datetime.now()
            
            # اگر cooldown گذشته باشد، آن را ریست کن
            if now >= cooldown_until:
                cursor.execute('''
                    UPDATE card_cooldowns 
                    SET is_in_cooldown = 0, cooldown_until = NULL 
                    WHERE user_id = ? AND card_id = ?
                ''', (user_id, card_id))
                conn.commit()
                return False, None
            
            return True, cooldown_until
            
        except Exception as e:
            logger.error(f"Error checking card cooldown for user {user_id}, card {card_id}: {e}")
            return False, None
        finally:
            conn.close()
    
    def record_card_win(self, user_id: int, card_id: str) -> None:
        """ثبت برد کارت با تنظیمات جداگانه"""
        card = self.db.get_card_by_id(card_id)
        if not card or not self.is_card_eligible_for_cooldown(card):
            return
        
        # دریافت تنظیمات خاص این کارت
        card_settings = self.db.get_card_cooldown_settings(card_id)
        if not card_settings['enabled']:
            return
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            now = datetime.now()
            
            # دریافت یا ایجاد رکورد cooldown
            cursor.execute('''
                SELECT wins_count, last_win_time, is_in_cooldown 
                FROM card_cooldowns 
                WHERE user_id = ? AND card_id = ?
            ''', (user_id, card_id))
            
            result = cursor.fetchone()
            
            if result:
                wins_count, last_win_time, is_in_cooldown = result
                wins_count += 1
            else:
                wins_count = 1
                is_in_cooldown = False
            
            # بررسی اینکه آیا باید وارد cooldown شود (با تنظیمات خاص کارت)
            cooldown_until = None
            if wins_count >= card_settings['win_limit']:
                is_in_cooldown = True
                cooldown_until = now + timedelta(hours=card_settings['cooldown_hours'])
                wins_count = 0  # ریست شمارنده
            
            # بروزرسانی یا درج رکورد
            cursor.execute('''
                INSERT OR REPLACE INTO card_cooldowns 
                (user_id, card_id, wins_count, last_win_time, cooldown_until, is_in_cooldown)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id, card_id, wins_count, 
                now.isoformat(), 
                cooldown_until.isoformat() if cooldown_until else None,
                is_in_cooldown
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error recording card win for user {user_id}, card {card_id}: {e}")
        finally:
            conn.close()

# ==================== CARD MANAGER ====================

class CardManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def create_sample_cards(self) -> int:
        """ایجاد کارت‌های نمونه"""
        sample_cards = [
            # Normal Cards
            {
                'name': 'Heisenberg',
                'rarity': CardRarity.NORMAL,
                'power': 75, 'speed': 60, 'iq': 95, 'popularity': 80,
                'abilities': ['Chemistry Master'],
                'biography': 'شیمیدان نابغه که به مسیر تاریک قدم گذاشت.'
            },
            {
                'name': 'Spongebob',
                'rarity': CardRarity.NORMAL,
                'power': 40, 'speed': 70, 'iq': 50, 'popularity': 90,
                'abilities': ['Optimism'],
                'biography': 'اسفنج پرانرژی از زیر آب که همیشه آماده است.'
            },
            # Epic Cards
            {
                'name': 'Homelander',
                'rarity': CardRarity.EPIC,
                'power': 95, 'speed': 85, 'iq': 70, 'popularity': 60,
                'abilities': ['Laser Eyes', 'Flight'],
                'biography': 'قهرمان قدرتمند با چهره‌ای پیچیده.'
            },
            # Legend Cards
            {
                'name': 'Thanos',
                'rarity': CardRarity.LEGEND,
                'power': 100, 'speed': 75, 'iq': 90, 'popularity': 85,
                'abilities': ['Infinity Stones', 'Reality Manipulation', 'Time Control'],
                'biography': 'تایتان جنون‌زده که به دنبال تعادل کیهان است.'
            }
        ]
        
        added_count = 0
        for card_data in sample_cards:
            card = Card(
                card_id=str(uuid.uuid4()),
                name=card_data['name'],
                rarity=card_data['rarity'],
                power=card_data['power'],
                speed=card_data['speed'],
                iq=card_data['iq'],
                popularity=card_data['popularity'],
                abilities=card_data['abilities'],
                biography=card_data['biography']
            )
            
            if self.db.add_card(card):
                added_count += 1
        
        return added_count