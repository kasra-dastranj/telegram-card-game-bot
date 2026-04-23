#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎮 TelBattle - Core System
فاز ۲: سیستم پایه کامل با پشتیبانی از Level/XP/Tier/Coins/Fusion/Arena
"""

import sqlite3
import json
import os
import random
import uuid
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from functools import lru_cache

# تنظیم لاگینگ
logger = logging.getLogger(__name__)

# ==================== SIMPLE CACHE ====================

class SimpleCache:
    """Cache ساده با TTL برای بهینه‌سازی"""
    def __init__(self, ttl_seconds=60):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())
    
    def clear(self):
        self.cache.clear()
    
    def invalidate(self, key):
        if key in self.cache:
            del self.cache[key]

# ==================== ENUMS ====================

class CardRarity(Enum):
    NORMAL = "normal"
    EPIC = "epic"
    LEGEND = "legend"
    RARE = "rare"

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
    card_type: str = "POWER_TYPE"   # POWER_TYPE / SPEED_TYPE / IQ_TYPE / POPULARITY_TYPE
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        
        # اعتبارسنجی آمار
        self.power = max(1, min(100, self.power))
        self.speed = max(1, min(100, self.speed))
        self.iq = max(1, min(100, self.iq))
        self.popularity = max(1, min(100, self.popularity))
        if self.dialogs is None:
            self.dialogs = []
        if not self.card_type:
            self.card_type = "POWER_TYPE"
    
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
            'card_type': self.card_type,
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
            card_type=data.get('card_type', 'POWER_TYPE'),
            created_at=datetime.fromisoformat(data['created_at'])
        )

@dataclass
class Player:
    user_id: int
    username: str
    first_name: str
    hearts: int = 10
    lives: int = 10
    total_score: int = 0
    last_heart_reset: datetime = None
    last_lives_reset: Optional[datetime] = None
    last_claim: Optional[datetime] = None
    created_at: datetime = None
    # فاز ۲
    coins: int = 0
    max_hearts: int = 10
    last_mining_claim: Optional[datetime] = None

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
            self.created_at = datetime.now()

# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    def __init__(self, db_path: str = "game_bot.db"):
        self.db_path = db_path
        # اضافه کردن cache برای بهینه‌سازی
        self.card_cache = SimpleCache(ttl_seconds=300)  # 5 دقیقه
        self.player_cache = SimpleCache(ttl_seconds=60)  # 1 دقیقه
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
                card_type TEXT DEFAULT 'POWER_TYPE',
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
                created_at TEXT NOT NULL,
                coins INTEGER DEFAULT 0,
                max_hearts INTEGER DEFAULT 10,
                last_mining_claim TEXT
            )
        ''')
        
        # جدول کارت‌های بازیکنان
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                card_id TEXT,
                obtained_at TEXT NOT NULL,
                usage_count INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
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
                arena_type TEXT,
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
                xp_gained INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES players (user_id)
            )
        ''')
        
        # جدول کولدان کارت‌ها
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
        
        # جدول تنظیمات Cooldown هر کارت
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_cooldown_settings (
                card_id TEXT PRIMARY KEY,
                win_limit INTEGER DEFAULT 10,
                cooldown_hours INTEGER DEFAULT 24,
                enabled BOOLEAN DEFAULT 1,
                FOREIGN KEY (card_id) REFERENCES cards (card_id)
            )
        ''')
        
        # ==================== جداول فاز ۲ ====================
        
        # جدول پیشرفت بازیکن (Level, XP, Tier)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_progression (
                user_id INTEGER PRIMARY KEY,
                level INTEGER DEFAULT 1,
                total_xp INTEGER DEFAULT 0,
                tier_points INTEGER DEFAULT 0,
                current_tier TEXT DEFAULT 'Bronze',
                last_played_at TEXT,
                FOREIGN KEY (user_id) REFERENCES players (user_id)
            )
        ''')
        
        # جدول لاگ Fusion
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fusion_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fusion_type TEXT NOT NULL,
                consumed_card_1 TEXT NOT NULL,
                consumed_card_2 TEXT NOT NULL,
                consumed_card_3 TEXT NOT NULL,
                upgraded_card_id TEXT NOT NULL,
                result_rarity TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES players (user_id)
            )
        ''')
        
        # جدول وضعیت بازی‌های ۳ راوندی
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS battle_states (
                fight_id TEXT PRIMARY KEY,
                challenger_id INTEGER NOT NULL,
                opponent_id INTEGER NOT NULL,
                challenger_card_id TEXT NOT NULL,
                opponent_card_id TEXT NOT NULL,
                arena TEXT NOT NULL,
                current_round INTEGER NOT NULL DEFAULT 1,
                challenger_rounds_won INTEGER NOT NULL DEFAULT 0,
                opponent_rounds_won INTEGER NOT NULL DEFAULT 0,
                challenger_used_stats TEXT NOT NULL DEFAULT '[]',
                opponent_used_stats TEXT NOT NULL DEFAULT '[]',
                challenger_current_stats TEXT NOT NULL,
                opponent_current_stats TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'round_1',
                created_at TEXT NOT NULL,
                FOREIGN KEY (fight_id) REFERENCES active_fights (fight_id)
            )
        ''')
        
        # جدول تاریخچه راوندها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS round_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fight_id TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                challenger_stat TEXT NOT NULL,
                opponent_stat TEXT NOT NULL,
                challenger_value INTEGER NOT NULL,
                opponent_value INTEGER NOT NULL,
                challenger_boost INTEGER NOT NULL DEFAULT 0,
                opponent_boost INTEGER NOT NULL DEFAULT 0,
                challenger_total INTEGER NOT NULL,
                opponent_total INTEGER NOT NULL,
                winner TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (fight_id) REFERENCES active_fights (fight_id)
            )
        ''')
        
        # جدول ماموریت‌های کارت
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_missions (
                card_id TEXT PRIMARY KEY,
                mission_type TEXT NOT NULL,
                target INTEGER NOT NULL,
                target_card TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # جدول پیشرفت ماموریت بازیکنان
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_card_missions (
                user_id INTEGER NOT NULL,
                card_id TEXT NOT NULL,
                current_progress INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                completed_at TEXT,
                reward_claimed INTEGER DEFAULT 0,
                reward_claimed_at TEXT,
                PRIMARY KEY (user_id, card_id)
            )
        ''')
        
        # جدول اسکین‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skins (
                skin_id TEXT PRIMARY KEY,
                card_id TEXT NOT NULL,
                name TEXT NOT NULL,
                skin_type TEXT NOT NULL,
                image_path TEXT,
                price INTEGER DEFAULT 50,
                is_seasonal INTEGER DEFAULT 0,
                season_end TEXT,
                description TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # جدول اسکین‌های باز شده بازیکنان
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_skins (
                user_id INTEGER NOT NULL,
                skin_id TEXT NOT NULL,
                unlocked_at TEXT NOT NULL,
                PRIMARY KEY (user_id, skin_id)
            )
        ''')
        
        # جدول اسکین فعال هر کارت
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_skins (
                user_id INTEGER NOT NULL,
                card_id TEXT NOT NULL,
                skin_id TEXT NOT NULL,
                PRIMARY KEY (user_id, card_id)
            )
        ''')
        
        # جدول بازی‌های Risk
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_matches (
                match_id TEXT PRIMARY KEY,
                challenger_id INTEGER NOT NULL,
                opponent_id INTEGER NOT NULL,
                table_value INTEGER NOT NULL,
                chat_id INTEGER,
                challenger_cards TEXT,
                opponent_cards TEXT,
                challenger_selected_card TEXT,
                opponent_selected_card TEXT,
                current_pot INTEGER DEFAULT 0,
                current_round INTEGER DEFAULT 1,
                challenger_rounds_won INTEGER DEFAULT 0,
                opponent_rounds_won INTEGER DEFAULT 0,
                winner_id INTEGER,
                status TEXT DEFAULT 'card_selection',
                bluff_phase TEXT DEFAULT 'none',
                challenger_bluff_action TEXT,
                opponent_bluff_action TEXT,
                raise_amount INTEGER DEFAULT 0,
                raise_by INTEGER,
                created_at TEXT NOT NULL
            )
        ''')
        
        # ==================== Migration: اضافه کردن ستون‌های جدید به جداول قدیمی ====================
        
        migrations = [
            ('player_cards', 'usage_count', 'INTEGER DEFAULT 0'),
            ('player_cards', 'is_favorite', 'INTEGER DEFAULT 0'),
            ('player_cards', 'rarity_override', 'TEXT'),
            ('cards', 'card_type', "TEXT DEFAULT 'POWER_TYPE'"),
            ('players', 'coins', 'INTEGER DEFAULT 0'),
            ('players', 'max_hearts', 'INTEGER DEFAULT 10'),
            ('players', 'last_mining_claim', 'TEXT'),
            ('players', 'lives', 'INTEGER DEFAULT 10'),
            ('players', 'last_lives_reset', 'TEXT'),
            ('active_fights', 'arena_type', 'TEXT'),
            ('fight_history', 'xp_gained', 'INTEGER DEFAULT 0'),
            ('risk_matches', 'bluff_phase', "TEXT DEFAULT 'none'"),
            ('risk_matches', 'challenger_bluff_action', 'TEXT'),
            ('risk_matches', 'opponent_bluff_action', 'TEXT'),
            ('risk_matches', 'raise_amount', 'INTEGER DEFAULT 0'),
            ('risk_matches', 'raise_by', 'INTEGER'),
        ]
        for table, column, col_def in migrations:
            try:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_def}')
            except sqlite3.OperationalError:
                pass  # ستون قبلاً وجود دارد
        
        # ==================== Indexes ====================
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_cards_user ON player_cards(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_cards_card ON player_cards(card_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fight_history_user ON fight_history(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fight_history_date ON fight_history(fought_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_active_fights_challenger ON active_fights(challenger_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_active_fights_opponent ON active_fights(opponent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_active_fights_status ON active_fights(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_active_fights_expires ON active_fights(expires_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_score ON players(total_score DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_progression_user ON player_progression(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_progression_last_played ON player_progression(last_played_at)')
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

# ==================== CARD OPERATIONS ====================
    
    def _get_connection(self) -> sqlite3.Connection:
        """دریافت connection به دیتابیس"""
        return sqlite3.connect(self.db_path)
    
    def add_card(self, card: Card) -> bool:
        """اضافه کردن کارت جدید"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            card_data = card.to_dict()
            cursor.execute('''
            INSERT INTO cards (card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, card_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                card_data['card_id'], card_data['name'], card_data['rarity'],
                card_data['power'], card_data['speed'], card_data['iq'], card_data['popularity'],
                card_data['abilities'], card_data['dialogs'], card_data['biography'],
                card_data['image_path'], card_data['card_type'], card_data['created_at']
            ))
            
            conn.commit()
            conn.close()
            self.card_cache.invalidate(f"card_{card.card_id}")
            return True
        except sqlite3.IntegrityError:
            try:
                conn.close()
            except Exception:
                pass
            return False
    
    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """دریافت کارت بر اساس ID با cache"""
        cached = self.card_cache.get(f"card_{card_id}")
        if cached:
            return cached
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, card_type, created_at
            FROM cards WHERE card_id = ?
        ''', (card_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
            card = Card.from_dict(dict(zip(columns, result)))
            self.card_cache.set(f"card_{card_id}", card)
            return card
        return None
    
    def get_card_by_id_for_player(self, card_id: str, user_id: int) -> Optional[Card]:
        """دریافت کارت با احتساب rarity_override بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.card_id, c.name, COALESCE(pc.rarity_override, c.rarity),
                   c.power, c.speed, c.iq, c.popularity,
                   c.abilities, c.dialogs, c.biography, c.image_path, c.card_type, c.created_at
            FROM cards c
            JOIN player_cards pc ON c.card_id = pc.card_id
            WHERE c.card_id = ? AND pc.user_id = ?
        ''', (card_id, user_id))
        result = cursor.fetchone()
        conn.close()
        if result:
            columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
            return Card.from_dict(dict(zip(columns, result)))
        return None
        """دریافت کارت بر اساس نام"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, card_type, created_at
            FROM cards WHERE lower(name) = lower(?) LIMIT 1
        ''', (name,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
            return Card.from_dict(dict(zip(columns, result)))
        return None
    
    def get_all_cards(self) -> List[Card]:
        """دریافت تمام کارت‌ها"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_id, name, rarity, power, speed, iq, popularity, abilities, dialogs, biography, image_path, card_type, created_at
            FROM cards ORDER BY created_at DESC
        ''')
        results = cursor.fetchall()
        conn.close()
        
        columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
        return [Card.from_dict(dict(zip(columns, r))) for r in results]
    
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
        
        cursor.execute('''
            SELECT user_id, username, first_name, hearts, COALESCE(lives, hearts, 10), total_score,
                   last_heart_reset, last_lives_reset, last_claim, created_at,
                   COALESCE(coins, 0), COALESCE(max_hearts, 10), last_mining_claim
            FROM players WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        
        def _to_dt(value, default=None):
            if value is None:
                return default
            if isinstance(value, datetime):
                return value
            try:
                return datetime.fromisoformat(str(value))
            except Exception:
                return default
        
        if result:
            player = Player(
                user_id=result[0],
                username=result[1] or "",
                first_name=result[2] or "بازیکن",
                hearts=int(result[3] or 10),
                lives=int(result[4] or 10),
                total_score=int(result[5] or 0),
                last_heart_reset=_to_dt(result[6], datetime.now()),
                last_lives_reset=_to_dt(result[7], datetime.now()),
                last_claim=_to_dt(result[8], None),
                created_at=_to_dt(result[9], datetime.now()),
                coins=int(result[10] or 0),
                max_hearts=int(result[11] or 10),
                last_mining_claim=_to_dt(result[12], None),
            )
        else:
            player = Player(
                user_id=user_id,
                username=username or "",
                first_name=first_name or "بازیکن"
            )
            cursor.execute('''
                INSERT INTO players (user_id, username, first_name, hearts, lives, total_score,
                                     last_heart_reset, last_lives_reset, last_claim, created_at,
                                     coins, max_hearts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                player.user_id, player.username, player.first_name,
                player.hearts, player.lives, player.total_score,
                player.last_heart_reset.isoformat(), player.last_lives_reset.isoformat(),
                None, player.created_at.isoformat(), 0, 10
            ))
            conn.commit()
            
            # ایجاد رکورد progression برای بازیکن جدید
            cursor.execute('''
                INSERT OR IGNORE INTO player_progression (user_id, level, total_xp, tier_points, current_tier, last_played_at)
                VALUES (?, 1, 0, 0, 'Bronze', ?)
            ''', (user_id, datetime.now().isoformat()))
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
                last_heart_reset = ?, last_lives_reset = ?, last_claim = ?,
                coins = ?, max_hearts = ?, last_mining_claim = ?
            WHERE user_id = ?
        ''', (
            player.username, player.first_name, player.hearts, player.lives, player.total_score,
            player.last_heart_reset.isoformat(),
            player.last_lives_reset.isoformat() if player.last_lives_reset else None,
            player.last_claim.isoformat() if player.last_claim else None,
            getattr(player, 'coins', 0),
            getattr(player, 'max_hearts', 10),
            player.last_mining_claim.isoformat() if getattr(player, 'last_mining_claim', None) else None,
            player.user_id
        ))
        
        conn.commit()
        conn.close()
    
    def get_player_cards(self, user_id: int) -> List[Card]:
        """دریافت کارت‌های بازیکن — با احتساب rarity_override از Fusion"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.card_id, c.name,
                   COALESCE(pc.rarity_override, c.rarity) as rarity,
                   c.power, c.speed, c.iq, c.popularity,
                   c.abilities, c.dialogs, c.biography, c.image_path, c.card_type, c.created_at
            FROM cards c
            JOIN player_cards pc ON c.card_id = pc.card_id
            WHERE pc.user_id = ?
            ORDER BY pc.obtained_at DESC
        ''', (user_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
        return [Card.from_dict(dict(zip(columns, r))) for r in results]
    
    def get_player_cards_by_rarity(self, user_id: int, rarity: CardRarity = None, page: int = 1, per_page: int = 6) -> Tuple[List[Card], int]:
        """دریافت کارت‌های بازیکن با فیلتر rarity و pagination"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        offset = (page - 1) * per_page
        columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
        
        if rarity:
            cursor.execute('''
                SELECT c.card_id, c.name, COALESCE(pc.rarity_override, c.rarity),
                       c.power, c.speed, c.iq, c.popularity,
                       c.abilities, c.dialogs, c.biography, c.image_path, c.card_type, c.created_at
                FROM cards c JOIN player_cards pc ON c.card_id = pc.card_id
                WHERE pc.user_id = ? AND COALESCE(pc.rarity_override, c.rarity) = ?
                ORDER BY pc.usage_count DESC, pc.obtained_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, rarity.value, per_page, offset))
            results = cursor.fetchall()
            cursor.execute('''
                SELECT COUNT(*) FROM cards c JOIN player_cards pc ON c.card_id = pc.card_id
                WHERE pc.user_id = ? AND COALESCE(pc.rarity_override, c.rarity) = ?
            ''', (user_id, rarity.value))
        else:
            cursor.execute('''
                SELECT c.card_id, c.name, COALESCE(pc.rarity_override, c.rarity),
                       c.power, c.speed, c.iq, c.popularity,
                       c.abilities, c.dialogs, c.biography, c.image_path, c.card_type, c.created_at
                FROM cards c JOIN player_cards pc ON c.card_id = pc.card_id
                WHERE pc.user_id = ?
                ORDER BY pc.usage_count DESC, pc.obtained_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, per_page, offset))
            results = cursor.fetchall()
            cursor.execute('SELECT COUNT(*) FROM player_cards WHERE user_id = ?', (user_id,))
        
        total_count = cursor.fetchone()[0]
        conn.close()
        return [Card.from_dict(dict(zip(columns, r))) for r in results], total_count
    
    def get_favorite_cards(self, user_id: int, page: int = 1, per_page: int = 6) -> Tuple[List[Card], int]:
        """دریافت کارت‌های مورد علاقه"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        offset = (page - 1) * per_page
        columns = ['card_id', 'name', 'rarity', 'power', 'speed', 'iq', 'popularity', 'abilities', 'dialogs', 'biography', 'image_path', 'card_type', 'created_at']
        
        cursor.execute('''
            SELECT c.card_id, c.name, c.rarity, c.power, c.speed, c.iq, c.popularity,
                   c.abilities, c.dialogs, c.biography, c.image_path, c.card_type, c.created_at
            FROM cards c JOIN player_cards pc ON c.card_id = pc.card_id
            WHERE pc.user_id = ? AND (pc.is_favorite = 1 OR pc.usage_count >= 5)
            ORDER BY pc.is_favorite DESC, pc.usage_count DESC
            LIMIT ? OFFSET ?
        ''', (user_id, per_page, offset))
        results = cursor.fetchall()
        
        cursor.execute('''
            SELECT COUNT(*) FROM player_cards
            WHERE user_id = ? AND (is_favorite = 1 OR usage_count >= 5)
        ''', (user_id,))
        total_count = cursor.fetchone()[0]
        conn.close()
        
        return [Card.from_dict(dict(zip(columns, r))) for r in results], total_count
    
    def toggle_favorite_card(self, user_id: int, card_id: str) -> bool:
        """تغییر وضعیت favorite کارت"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE player_cards
            SET is_favorite = CASE WHEN is_favorite = 1 THEN 0 ELSE 1 END
            WHERE user_id = ? AND card_id = ?
        ''', (user_id, card_id))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def increment_card_usage(self, user_id: int, card_id: str):
        """افزایش تعداد استفاده از کارت"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE player_cards
            SET usage_count = usage_count + 1
            WHERE user_id = ? AND card_id = ?
        ''', (user_id, card_id))
        
        conn.commit()
        conn.close()
    
    def get_rarity_counts(self, user_id: int) -> dict:
        """دریافت تعداد کارت‌های هر rarity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.rarity, COUNT(*)
            FROM cards c
            JOIN player_cards pc ON c.card_id = pc.card_id
            WHERE pc.user_id = ?
            GROUP BY c.rarity
        ''', (user_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        counts = {
            CardRarity.NORMAL.value: 0,
            CardRarity.EPIC.value: 0,
            CardRarity.LEGEND.value: 0
        }
        
        for rarity, count in results:
            counts[rarity] = count
        
        return counts
    # ==================== PHASE 2: PROGRESSION ====================
    
    def get_or_create_progression(self, user_id: int) -> Dict:
        """دریافت یا ایجاد رکورد progression بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT level, total_xp, tier_points, current_tier, last_played_at
            FROM player_progression WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.execute('''
                INSERT INTO player_progression (user_id, level, total_xp, tier_points, current_tier, last_played_at)
                VALUES (?, 1, 0, 0, 'Bronze', ?)
            ''', (user_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return {'level': 1, 'total_xp': 0, 'tier_points': 0, 'current_tier': 'Bronze', 'last_played_at': datetime.now()}
        
        conn.close()
        return {
            'level': result[0],
            'total_xp': result[1],
            'tier_points': result[2],
            'current_tier': result[3],
            'last_played_at': datetime.fromisoformat(result[4]) if result[4] else datetime.now()
        }
    
    def update_progression(self, user_id: int, level: int = None, total_xp: int = None,
                           tier_points: int = None, current_tier: str = None) -> bool:
        """بروزرسانی progression بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = ['last_played_at = ?']
        values = [datetime.now().isoformat()]
        
        if level is not None:
            updates.append('level = ?')
            values.append(level)
        if total_xp is not None:
            updates.append('total_xp = ?')
            values.append(total_xp)
        if tier_points is not None:
            updates.append('tier_points = ?')
            values.append(max(0, tier_points))
        if current_tier is not None:
            updates.append('current_tier = ?')
            values.append(current_tier)
        
        values.append(user_id)
        cursor.execute(f"UPDATE player_progression SET {', '.join(updates)} WHERE user_id = ?", values)
        conn.commit()
        conn.close()
        return True
    
    def add_xp(self, user_id: int, amount: int) -> Tuple[int, int]:
        """اضافه کردن XP و برگرداندن (old_level, new_level)"""
        from phase2_systems import LevelSystem
        prog = self.get_or_create_progression(user_id)
        old_level = prog['level']
        new_xp = prog['total_xp'] + amount
        new_level = LevelSystem.get_level_from_xp(new_xp)
        self.update_progression(user_id, level=new_level, total_xp=new_xp)
        return old_level, new_level
    
    def add_tier_points(self, user_id: int, amount: int) -> Tuple[str, str]:
        """اضافه/کم کردن TP و برگرداندن (old_tier, new_tier)"""
        from phase2_systems import TierSystem
        prog = self.get_or_create_progression(user_id)
        old_tier = prog['current_tier']
        new_tp = max(0, prog['tier_points'] + amount)
        new_tier = TierSystem.get_tier_from_tp(new_tp)
        self.update_progression(user_id, tier_points=new_tp, current_tier=new_tier)
        return old_tier, new_tier
    
    # ==================== PHASE 2: COINS ====================
    
    def add_coins(self, user_id: int, amount: int) -> bool:
        """اضافه کردن سکه به بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE players SET coins = coins + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        return True
    
    def spend_coins(self, user_id: int, amount: int) -> Tuple[bool, str]:
        """خرج کردن سکه — برمی‌گرداند (success, error_msg)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(coins, 0) FROM players WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if not row or row[0] < amount:
            conn.close()
            return False, f"سکه کافی نیست (موجودی: {row[0] if row else 0}، نیاز: {amount})"
        cursor.execute('UPDATE players SET coins = coins - ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        return True, ""
    
    # ==================== CARD COOLDOWN SETTINGS ====================
    
    def get_card_cooldown_settings(self, card_id: str) -> Dict:
        """دریافت تنظیمات cooldown کارت خاص"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT win_limit, cooldown_hours, is_enabled 
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
                    updates.append('is_enabled = ?')
                    values.append(enabled)
                
                if updates:
                    values.append(card_id)
                    query = f"UPDATE card_cooldown_settings SET {', '.join(updates)} WHERE card_id = ?"
                    cursor.execute(query, values)
            else:
                # ایجاد رکورد جدید
                cursor.execute('''
                    INSERT INTO card_cooldown_settings (card_id, win_limit, cooldown_hours, is_enabled)
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
                       COALESCE(ccs.is_enabled, 1) as enabled
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
    
    # ==================== PVP FIGHT OPERATIONS ====================
    
    def get_user_active_fights(self, user_id: int) -> List:
        """دریافت فایت‌های فعال بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fight_id FROM active_fights 
            WHERE (challenger_id = ? OR opponent_id = ?) 
            AND status != 'completed' AND status != 'cancelled'
        ''', (user_id, user_id))
        
        results = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in results]
    
    def create_fight(self, challenger_id: int, opponent_id: int, chat_id: int) -> str:
        """ایجاد فایت جدید"""
        fight_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now()
        expires_at = now + timedelta(minutes=15)
        
        cursor.execute('''
            INSERT INTO active_fights 
            (fight_id, challenger_id, opponent_id, status, chat_id, created_at, expires_at)
            VALUES (?, ?, ?, 'waiting_opponent', ?, ?, ?)
        ''', (fight_id, challenger_id, opponent_id, chat_id, now.isoformat(), expires_at.isoformat()))
        
        conn.commit()
        conn.close()
        
        return fight_id
    
    def get_active_fight_for_group(self, chat_id: int) -> Optional[str]:
        """دریافت فایت فعال برای گروه"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fight_id FROM active_fights 
            WHERE chat_id = ? AND status != 'completed' AND status != 'cancelled'
            ORDER BY created_at DESC LIMIT 1
        ''', (chat_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def cleanup_expired_fights(self, minutes: int = 15) -> int:
        """پاکسازی فایت‌های منقضی شده"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        cursor.execute('''
            UPDATE active_fights 
            SET status = 'cancelled'
            WHERE status != 'completed' AND status != 'cancelled'
            AND created_at < ?
        ''', (cutoff_time.isoformat(),))
        
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def get_fight_by_id(self, fight_id: str) -> Optional[PvPFight]:
        """دریافت فایت بر اساس ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fight_id, challenger_id, opponent_id, challenger_card_id, 
                   opponent_card_id, challenger_stat, opponent_stat, status, 
                   created_at, chat_id
            FROM active_fights WHERE fight_id = ?
        ''', (fight_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        return PvPFight(
            fight_id=result[0],
            challenger_id=result[1],
            opponent_id=result[2],
            challenger_card_id=result[3],
            opponent_card_id=result[4],
            challenger_stat=result[5],
            opponent_stat=result[6],
            status=FightStatus(result[7]) if result[7] else FightStatus.WAITING_FOR_OPPONENT,
            created_at=datetime.fromisoformat(result[8]) if result[8] else datetime.now(),
            chat_id=result[9]
        )
    
    def update_fight(self, fight_id: str, **kwargs) -> bool:
        """بروزرسانی فایت"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = []
        values = []
        
        for key, value in kwargs.items():
            updates.append(f"{key} = ?")
            # تبدیل Enum به string
            if isinstance(value, FightStatus):
                values.append(value.value)
            elif hasattr(value, 'value'):  # هر Enum دیگری
                values.append(value.value)
            else:
                values.append(value)
        
        if not updates:
            conn.close()
            return False
        
        values.append(fight_id)
        query = f"UPDATE active_fights SET {', '.join(updates)} WHERE fight_id = ?"
        
        cursor.execute(query, values)
        success = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return success
    
    def claim_opponent_if_waiting(self, fight_id: str, opponent_id: int) -> bool:
        """تنظیم حریف به صورت اتمی (برای جلوگیری از race condition)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE active_fights 
                SET opponent_id = ?
                WHERE fight_id = ? AND opponent_id = 0 AND status = 'waiting_opponent'
            ''', (opponent_id, fight_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return success
        except Exception as e:
            logger.error(f"Error claiming opponent: {e}")
            conn.close()
            return False
    
    def is_unclaimed(self, fight_or_id) -> bool:
        """بررسی اینکه آیا فایت هنوز claim نشده"""
        # اگر object باشد، fight_id را استخراج کن
        if isinstance(fight_or_id, PvPFight):
            fight_id = fight_or_id.fight_id
        else:
            fight_id = fight_or_id
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT opponent_id FROM active_fights 
            WHERE fight_id = ? AND status = 'waiting_opponent'
        ''', (fight_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result and result[0] == 0
    
    def delete_fight(self, fight_id: str) -> bool:
        """حذف فایت"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM active_fights WHERE fight_id = ?', (fight_id,))
        success = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return success
    
    def get_card_stats(self, card_id: str) -> Optional[Dict]:
        """دریافت آمار کارت"""
        card = self.get_card_by_id(card_id)
        if not card:
            return None
        
        return {
            'power': card.power,
            'speed': card.speed,
            'iq': card.iq,
            'popularity': card.popularity,
            'total': card.get_total_stats()
        }
    
    def get_player_card_stats(self, card_id: str, user_id: int) -> Dict:
        """دریافت آمار بازی‌های یک کارت برای یک بازیکن خاص"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # دریافت آمار از جدول fight_history
        cursor.execute('''
            SELECT 
                COUNT(*) as games_played,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'tie' THEN 1 ELSE 0 END) as ties
            FROM fight_history
            WHERE user_id = ? AND user_card_id = ?
        ''', (user_id, card_id))
        
        result = cursor.fetchone()
        conn.close()
        
        games_played = result[0] or 0
        wins = result[1] or 0
        losses = result[2] or 0
        ties = result[3] or 0
        
        win_rate = (wins / games_played * 100) if games_played > 0 else 0
        
        return {
            'games_played': games_played,
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'win_rate': win_rate
        }
    
    def reset_all_player_lives(self) -> int:
        """ریست جان همه بازیکنان (برای تست)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE players SET hearts = 10, last_heart_reset = ?', (datetime.now().isoformat(),))
        
        reset_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return reset_count
    
    def add_card_to_player(self, user_id: int, card_id: str) -> bool:
        """اضافه کردن کارت به بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO player_cards (user_id, card_id, obtained_at)
                VALUES (?, ?, ?)
            ''', (user_id, card_id, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def get_player_stats(self, user_id: int) -> Dict:
        """دریافت آمار بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # آمار کلی
        cursor.execute('''
            SELECT COUNT(*), 
                   SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN result = 'tie' THEN 1 ELSE 0 END)
            FROM fight_history WHERE user_id = ?
        ''', (user_id,))
        
        total_result = cursor.fetchone()
        total_games = total_result[0] or 0
        total_wins = total_result[1] or 0
        total_losses = total_result[2] or 0
        total_ties = total_result[3] or 0
        
        win_rate = (total_wins / total_games * 100) if total_games > 0 else 0
        
        conn.close()
        
        return {
            'total': {
                'games_played': total_games,
                'wins': total_wins,
                'losses': total_losses,
                'ties': total_ties,
                'win_rate': win_rate
            },
            'today': {'games_played': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'win_rate': 0},
            '7_days': {'games_played': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'win_rate': 0},
            '30_days': {'games_played': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'win_rate': 0}
        }
    
    def get_player_rank(self, user_id: int) -> Optional[int]:
        """دریافت رتبه بازیکن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) + 1 FROM players 
            WHERE total_score > (SELECT total_score FROM players WHERE user_id = ?)
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def get_player_card_counts(self, user_id: int) -> Dict:
        """دریافت تعداد کارت‌های بازیکن بر اساس کمیابی"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.rarity, COUNT(*) 
            FROM player_cards pc
            JOIN cards c ON pc.card_id = c.card_id
            WHERE pc.user_id = ?
            GROUP BY c.rarity
        ''', (user_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        counts = {'normal': 0, 'epic': 0, 'legend': 0, 'total': 0}
        for rarity, count in results:
            counts[rarity] = count
            counts['total'] += count
        
        return counts
    
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
        
        return leaderboard
    
    def get_leaderboard_by_timeframe(self, timeframe: str = "all", limit: int = 10, chat_id: int = None) -> List[Dict]:
        """دریافت لیدربورد با فیلتر زمانی و گروه
        
        Args:
            timeframe: "weekly", "monthly", "all"
            limit: تعداد نتایج (برای جهانی)
            chat_id: اگه مقدار داشته باشه، فقط اعضای این گروه رو نشون میده
        """
        from datetime import datetime, timedelta
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # محاسبه تاریخ شروع بر اساس timeframe
        now = datetime.now()
        if timeframe == "weekly":
            start_date = (now - timedelta(days=7)).isoformat()
        elif timeframe == "monthly":
            start_date = (now - timedelta(days=30)).isoformat()
        else:  # all
            start_date = "1970-01-01"
        
        if chat_id:
            # لیدربورد گروه - ساده‌تر: همه بازیکنان که امتیاز دارن
            # (فعلا group-specific tracking نداریم، پس همه رو نشون میدیم)
            if timeframe == "all":
                cursor.execute('''
                    SELECT 
                        p.user_id,
                        p.username,
                        p.first_name,
                        p.total_score,
                        COUNT(DISTINCT pc.card_id) as card_count,
                        p.total_score as period_score
                    FROM players p
                    LEFT JOIN player_cards pc ON p.user_id = pc.user_id
                    WHERE p.total_score > 0
                    GROUP BY p.user_id
                    ORDER BY p.total_score DESC
                ''')
            else:
                # برای گروه: محاسبه امتیاز دوره‌ای از fight_history
                cursor.execute('''
                    SELECT 
                        p.user_id,
                        p.username,
                        p.first_name,
                        p.total_score,
                        (SELECT COUNT(DISTINCT pc.card_id) FROM player_cards pc WHERE pc.user_id = p.user_id) as card_count,
                        (SELECT COALESCE(SUM(fh.score_gained), 0) FROM fight_history fh WHERE fh.user_id = p.user_id AND fh.fought_at >= ?) as period_score
                    FROM players p
                    WHERE p.user_id IN (SELECT DISTINCT user_id FROM fight_history WHERE fought_at >= ?)
                    AND (SELECT COALESCE(SUM(fh.score_gained), 0) FROM fight_history fh WHERE fh.user_id = p.user_id AND fh.fought_at >= ?) > 0
                    ORDER BY period_score DESC
                ''', (start_date, start_date, start_date))
        else:
            # لیدربورد جهانی
            if timeframe == "all":
                # برای "all" از total_score استفاده کن
                cursor.execute('''
                    SELECT 
                        p.user_id,
                        p.username,
                        p.first_name,
                        p.total_score,
                        COUNT(DISTINCT pc.card_id) as card_count,
                        p.total_score as period_score
                    FROM players p
                    LEFT JOIN player_cards pc ON p.user_id = pc.user_id
                    WHERE p.total_score > 0
                    GROUP BY p.user_id
                    ORDER BY p.total_score DESC
                    LIMIT ?
                ''', (limit,))
            else:
                # برای جهانی: محاسبه امتیاز دوره‌ای از fight_history
                cursor.execute('''
                    SELECT 
                        p.user_id,
                        p.username,
                        p.first_name,
                        p.total_score,
                        (SELECT COUNT(DISTINCT pc.card_id) FROM player_cards pc WHERE pc.user_id = p.user_id) as card_count,
                        (SELECT COALESCE(SUM(fh.score_gained), 0) FROM fight_history fh WHERE fh.user_id = p.user_id AND fh.fought_at >= ?) as period_score
                    FROM players p
                    WHERE p.user_id IN (SELECT DISTINCT user_id FROM fight_history WHERE fought_at >= ?)
                    AND (SELECT COALESCE(SUM(fh.score_gained), 0) FROM fight_history fh WHERE fh.user_id = p.user_id AND fh.fought_at >= ?) > 0
                    ORDER BY period_score DESC
                    LIMIT ?
                ''', (start_date, start_date, start_date, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        leaderboard = []
        for result in results:
            leaderboard.append({
                'user_id': result[0],
                'username': result[1],
                'first_name': result[2],
                'total_score': result[3],
                'card_count': result[4],
                'period_score': result[5]
            })
        
        return leaderboard
    
    def recalculate_all_total_scores(self):
        """محاسبه مجدد total_score همه بازیکنان از fight_history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # دریافت همه بازیکنان
        cursor.execute('SELECT user_id FROM players')
        players = cursor.fetchall()
        
        updated_count = 0
        for (user_id,) in players:
            # محاسبه total_score از fight_history
            cursor.execute('''
                SELECT COALESCE(SUM(score_gained), 0) 
                FROM fight_history 
                WHERE user_id = ?
            ''', (user_id,))
            
            total_score = cursor.fetchone()[0]
            
            # آپدیت total_score
            cursor.execute('''
                UPDATE players 
                SET total_score = ? 
                WHERE user_id = ?
            ''', (total_score, user_id))
            updated_count += 1
        
        conn.commit()
        conn.close()
        
        return updated_count
    
    def get_user_rank(self, user_id: int, timeframe: str = "all", chat_id: int = None) -> tuple:
        """دریافت رتبه کاربر در لیدربورد
        
        Returns:
            (rank, score) یا (None, None) اگه کاربر در لیست نباشه
        """
        leaderboard = self.get_leaderboard_by_timeframe(timeframe=timeframe, limit=1000, chat_id=chat_id)
        
        for i, player in enumerate(leaderboard):
            if player['user_id'] == user_id:
                return i + 1, player['period_score']
        
        return None, None
    
    def get_group_fighters(self, chat_id: int) -> List[Dict]:
        """دریافت لیست بازیکنانی که در این گروه fight کردن"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # دریافت user_id هایی که در این گروه fight شروع کردن یا قبول کردن
        cursor.execute('''
            SELECT DISTINCT p.user_id, p.username, p.first_name
            FROM players p
            WHERE p.user_id IN (
                SELECT DISTINCT challenger_id FROM active_fights WHERE chat_id = ?
                UNION
                SELECT DISTINCT opponent_id FROM active_fights WHERE chat_id = ? AND opponent_id != 0
            )
            OR p.user_id IN (
                SELECT DISTINCT fh.user_id 
                FROM fight_history fh
                JOIN active_fights af ON (fh.user_id = af.challenger_id OR fh.user_id = af.opponent_id)
                WHERE af.chat_id = ?
            )
        ''', (chat_id, chat_id, chat_id))
        
        results = cursor.fetchall()
        conn.close()
        
        fighters = []
        for result in results:
            fighters.append({
                'user_id': result[0],
                'username': result[1],
                'first_name': result[2]
            })
        
        return fighters

# ==================== GAME LOGIC ====================

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
    
    def claim_daily_card(self, user_id: int) -> Tuple[bool, Optional[Card], Optional[str]]:
        """دریافت کارت روزانه — سیستم pool فاز ۲ (احتمال برابر، همیشه Normal)"""
        player = self.db.get_or_create_player(user_id)
        
        # بررسی cooldown (ریست در ساعت 00:00 ایران)
        if player.last_claim and player.last_claim.year > 2000:
            try:
                from zoneinfo import ZoneInfo
                iran_tz = ZoneInfo("Asia/Tehran")
                now = datetime.now(iran_tz)
                lc = player.last_claim
                if lc.tzinfo is None:
                    lc = lc.replace(tzinfo=ZoneInfo("UTC")).astimezone(iran_tz)
                else:
                    lc = lc.astimezone(iran_tz)
                
                if lc.date() == now.date():
                    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).replace(tzinfo=iran_tz)
                    remaining = midnight - now
                    h = int(remaining.total_seconds() // 3600)
                    m = int((remaining.total_seconds() % 3600) // 60)
                    return False, None, f"شما امروز کارت دریافت کرده‌اید. کارت بعدی در {h} ساعت و {m} دقیقه دیگر (ساعت 00:00)"
            except Exception:
                # fallback به روش ساده
                if (datetime.now() - player.last_claim).total_seconds() < self.CLAIM_COOLDOWN_HOURS * 3600:
                    return False, None, "هنوز زمان کلیم نرسیده"
        
        # محاسبه pool: همه Normal هایی که بازیکن در Epic یا Legend ندارد
        all_cards = self.db.get_all_cards()
        normal_cards = [c for c in all_cards if c.rarity == CardRarity.NORMAL]
        
        if not normal_cards:
            return False, None, "هیچ کارت Normal در دیتابیس موجود نیست"
        
        player_cards = self.db.get_player_cards(user_id)
        excluded_ids = {c.card_id for c in player_cards if c.rarity in [CardRarity.EPIC, CardRarity.LEGEND, CardRarity.RARE]}
        
        pool = [c for c in normal_cards if c.card_id not in excluded_ids]
        
        # fallback اگر pool خالی شد
        if not pool:
            pool = normal_cards
        
        card = random.choice(pool)
        self.db.add_card_to_player(user_id, card.card_id)
        
        player.last_claim = datetime.now()
        self.db.update_player(player)
        
        return True, card, None
    
    def get_heart_reset_time_remaining(self, player: Player) -> Optional[timedelta]:
        """محاسبه زمان باقی‌مانده تا ریست جان‌ها"""
        if not player.last_heart_reset:
            return None
        
        next_reset = player.last_heart_reset + timedelta(hours=self.HEART_RESET_HOURS)
        now = datetime.now()
        
        if now >= next_reset:
            return None
        
        return next_reset - now
    
    def format_time_remaining(self, time_delta: timedelta) -> str:
        """فرمت کردن زمان باقی‌مانده"""
        total_seconds = int(time_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours} ساعت و {minutes} دقیقه"
        else:
            return f"{minutes} دقیقه"
    
    def resolve_pvp_fight(self, fight_id: str) -> Dict:
        """حل و فصل فایت PvP"""
        fight = self.db.get_fight_by_id(fight_id)
        
        if not fight:
            return {"success": False, "error": "فایت یافت نشد"}
        
        if not fight.challenger_card_id or not fight.opponent_card_id:
            return {"success": False, "error": "کارت‌ها انتخاب نشده‌اند"}
        
        if not fight.challenger_stat or not fight.opponent_stat:
            return {"success": False, "error": "ویژگی‌ها انتخاب نشده‌اند"}
        
        # دریافت کارت‌ها
        challenger_card = self.db.get_card_by_id(fight.challenger_card_id)
        opponent_card = self.db.get_card_by_id(fight.opponent_card_id)
        
        if not challenger_card or not opponent_card:
            return {"success": False, "error": "کارت‌ها یافت نشدند"}
        
        # محاسبه امتیازات - جمع دو ویژگی
        challenger_stat_value = challenger_card.get_stat_value(StatType(fight.challenger_stat))
        challenger_stat2 = challenger_card.get_stat_value(StatType(fight.opponent_stat))
        challenger_total = challenger_stat_value + challenger_stat2
        
        opponent_stat_value = opponent_card.get_stat_value(StatType(fight.opponent_stat))
        opponent_stat2 = opponent_card.get_stat_value(StatType(fight.challenger_stat))
        opponent_total = opponent_stat_value + opponent_stat2
        
        # تعیین برنده بر اساس جمع امتیازات
        if challenger_total > opponent_total:
            winner_id = fight.challenger_id
            loser_id = fight.opponent_id
            winner_card = challenger_card
            loser_card = opponent_card
            result = "win"
        elif opponent_total > challenger_total:
            winner_id = fight.opponent_id
            loser_id = fight.challenger_id
            winner_card = opponent_card
            loser_card = challenger_card
            result = "loss"
        else:
            winner_id = None
            loser_id = None
            winner_card = None
            loser_card = None
            result = "tie"
        
        # محاسبه امتیاز و جان بر اساس rarity
        def calculate_rewards(winner_rarity: CardRarity, loser_rarity: CardRarity):
            """محاسبه امتیاز برنده و جان از دست رفته بازنده"""
            # امتیاز برنده
            if winner_rarity == CardRarity.LEGEND:
                if loser_rarity == CardRarity.NORMAL:
                    score = 5  # انتظار میره ببره
                elif loser_rarity == CardRarity.EPIC:
                    score = 7
                else:  # Legend vs Legend
                    score = 10
            elif winner_rarity == CardRarity.EPIC:
                if loser_rarity == CardRarity.NORMAL:
                    score = 7
                elif loser_rarity == CardRarity.EPIC:
                    score = 10
                else:  # Epic beats Legend
                    score = 15  # upset!
            else:  # Normal wins
                if loser_rarity == CardRarity.NORMAL:
                    score = 10
                elif loser_rarity == CardRarity.EPIC:
                    score = 15  # upset!
                else:  # Normal beats Legend
                    score = 20  # huge upset!
            
            # جان از دست رفته بازنده
            if loser_rarity == CardRarity.NORMAL:
                if winner_rarity == CardRarity.LEGEND or winner_rarity == CardRarity.EPIC:
                    hearts_lost = 0  # انتظار میره ببازه
                else:  # Normal loses to Normal
                    hearts_lost = 1
            elif loser_rarity == CardRarity.EPIC:
                if winner_rarity == CardRarity.LEGEND:
                    hearts_lost = 0  # انتظار میره ببازه
                elif winner_rarity == CardRarity.EPIC:
                    hearts_lost = 1
                else:  # Epic loses to Normal
                    hearts_lost = 2  # upset!
            else:  # Legend loses
                if winner_rarity == CardRarity.LEGEND:
                    hearts_lost = 1
                elif winner_rarity == CardRarity.EPIC:
                    hearts_lost = 2  # upset!
                else:  # Legend loses to Normal
                    hearts_lost = 3  # huge upset!
            
            return score, hearts_lost
        
        # بروزرسانی امتیازات و جان‌ها
        challenger_player = self.db.get_or_create_player(fight.challenger_id)
        opponent_player = self.db.get_or_create_player(fight.opponent_id)
        
        if result == "win":
            score_gained, hearts_lost = calculate_rewards(challenger_card.rarity, opponent_card.rarity)
            challenger_player.total_score += score_gained
            challenger_player.hearts = max(0, challenger_player.hearts)
            opponent_player.hearts = max(0, opponent_player.hearts - hearts_lost)
            self.record_card_win(fight.challenger_id, fight.challenger_card_id)
        elif result == "loss":
            score_gained, hearts_lost = calculate_rewards(opponent_card.rarity, challenger_card.rarity)
            opponent_player.total_score += score_gained
            opponent_player.hearts = max(0, opponent_player.hearts)
            challenger_player.hearts = max(0, challenger_player.hearts - hearts_lost)
            self.record_card_win(fight.opponent_id, fight.opponent_card_id)
        else:  # tie
            # در مساوی، کارت ضعیف‌تر امتیاز میگیره
            challenger_rarity = challenger_card.rarity
            opponent_rarity = opponent_card.rarity
            
            # محاسبه امتیاز برای هر بازیکن
            def calculate_tie_score(my_rarity: CardRarity, opponent_rarity: CardRarity):
                if my_rarity == opponent_rarity:
                    return 0  # هم سطح = 0 امتیاز
                elif my_rarity == CardRarity.NORMAL:
                    if opponent_rarity == CardRarity.EPIC:
                        return 3
                    else:  # vs Legend
                        return 5
                elif my_rarity == CardRarity.EPIC:
                    if opponent_rarity == CardRarity.LEGEND:
                        return 3
                    else:  # vs Normal
                        return 0  # Epic قوی‌تره، امتیاز نمیگیره
                else:  # Legend
                    return 0  # Legend قوی‌تره، امتیاز نمیگیره
            
            challenger_tie_score = calculate_tie_score(challenger_rarity, opponent_rarity)
            opponent_tie_score = calculate_tie_score(opponent_rarity, challenger_rarity)
            
            challenger_player.total_score += challenger_tie_score
            opponent_player.total_score += opponent_tie_score
            
            # محاسبه جان از دست رفته در مساوی
            # فقط Legend در مساوی با Normal جان کم می‌کنه
            challenger_tie_hearts = 0
            opponent_tie_hearts = 0
            
            if challenger_rarity == CardRarity.LEGEND and opponent_rarity == CardRarity.NORMAL:
                challenger_tie_hearts = 1  # Legend باید جان کم کنه
            elif opponent_rarity == CardRarity.LEGEND and challenger_rarity == CardRarity.NORMAL:
                opponent_tie_hearts = 1  # Legend باید جان کم کنه
            
            challenger_player.hearts = max(0, challenger_player.hearts - challenger_tie_hearts)
            opponent_player.hearts = max(0, opponent_player.hearts - opponent_tie_hearts)
            
            score_gained = 0  # برای history
            hearts_lost = 0
        
        self.db.update_player(challenger_player)
        self.db.update_player(opponent_player)
        
        # ثبت در تاریخچه
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # محاسبه مقادیر برای ثبت تاریخچه
        if result == "win":
            challenger_score = score_gained
            challenger_hearts_lost = 0
            opponent_score = 0
            opponent_hearts_lost = hearts_lost
        elif result == "loss":
            challenger_score = 0
            challenger_hearts_lost = hearts_lost
            opponent_score = score_gained
            opponent_hearts_lost = 0
        else:  # tie
            challenger_score = challenger_tie_score
            challenger_hearts_lost = challenger_tie_hearts
            opponent_score = opponent_tie_score
            opponent_hearts_lost = opponent_tie_hearts
        
        # ثبت برای challenger
        cursor.execute('''
            INSERT INTO fight_history 
            (user_id, user_card_id, opponent_card_id, stat_used, result, score_gained, hearts_lost, fought_at, fight_type, opponent_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pvp', ?)
        ''', (
            fight.challenger_id, fight.challenger_card_id, fight.opponent_card_id,
            fight.challenger_stat, result, challenger_score,
            challenger_hearts_lost, now, fight.opponent_id
        ))
        
        # ثبت برای opponent
        opp_result = "win" if result == "loss" else ("loss" if result == "win" else "tie")
        cursor.execute('''
            INSERT INTO fight_history 
            (user_id, user_card_id, opponent_card_id, stat_used, result, score_gained, hearts_lost, fought_at, fight_type, opponent_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pvp', ?)
        ''', (
            fight.opponent_id, fight.opponent_card_id, fight.challenger_card_id,
            fight.opponent_stat, opp_result, opponent_score,
            opponent_hearts_lost, now, fight.challenger_id
        ))
        
        conn.commit()
        conn.close()
        
        # بروزرسانی وضعیت فایت
        self.db.update_fight(fight_id, status='completed')
        
        # تعیین result_type برای telegram_bot
        if result == "tie":
            result_type = "tie"
        elif result == "win":
            result_type = "challenger_wins"
        else:  # result == "loss"
            result_type = "opponent_wins"
        
        # ساخت winner و loser data برای telegram_bot
        # ساخت یه SimpleNamespace که مثل object رفتار می‌کنه
        from types import SimpleNamespace
        
        winner_data = None
        loser_data = None
        
        if result != "tie":
            if result == "win":
                # ساخت یه card object ساده که telegram_bot بتونه ازش استفاده کنه
                winner_card_obj = SimpleNamespace(
                    name=challenger_card.name,
                    power=challenger_card.power,
                    speed=challenger_card.speed,
                    iq=challenger_card.iq,
                    popularity=challenger_card.popularity,
                    rarity=challenger_card.rarity.value if hasattr(challenger_card.rarity, 'value') else str(challenger_card.rarity)
                )
                loser_card_obj = SimpleNamespace(
                    name=opponent_card.name,
                    power=opponent_card.power,
                    speed=opponent_card.speed,
                    iq=opponent_card.iq,
                    popularity=opponent_card.popularity,
                    rarity=opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else str(opponent_card.rarity)
                )
                
                winner_data = {
                    "user_id": fight.challenger_id,
                    "card": winner_card_obj,
                    "stat": fight.challenger_stat,
                    "stat_type": fight.challenger_stat,
                    "stat_value": challenger_stat_value,
                    "score_gained": challenger_score,
                    "hearts_lost": 0
                }
                loser_data = {
                    "user_id": fight.opponent_id,
                    "card": loser_card_obj,
                    "stat": fight.opponent_stat,
                    "stat_type": fight.opponent_stat,
                    "stat_value": opponent_stat_value,
                    "score_gained": 0,
                    "hearts_lost": opponent_hearts_lost
                }
            else:  # result == "loss"
                # ساخت یه card object ساده که telegram_bot بتونه ازش استفاده کنه
                winner_card_obj = SimpleNamespace(
                    name=opponent_card.name,
                    power=opponent_card.power,
                    speed=opponent_card.speed,
                    iq=opponent_card.iq,
                    popularity=opponent_card.popularity,
                    rarity=opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else str(opponent_card.rarity)
                )
                loser_card_obj = SimpleNamespace(
                    name=challenger_card.name,
                    power=challenger_card.power,
                    speed=challenger_card.speed,
                    iq=challenger_card.iq,
                    popularity=challenger_card.popularity,
                    rarity=challenger_card.rarity.value if hasattr(challenger_card.rarity, 'value') else str(challenger_card.rarity)
                )
                
                winner_data = {
                    "user_id": fight.opponent_id,
                    "card": winner_card_obj,
                    "stat": fight.opponent_stat,
                    "stat_type": fight.opponent_stat,
                    "stat_value": opponent_stat_value,
                    "score_gained": opponent_score,
                    "hearts_lost": 0
                }
                loser_data = {
                    "user_id": fight.challenger_id,
                    "card": loser_card_obj,
                    "stat": fight.challenger_stat,
                    "stat_type": fight.challenger_stat,
                    "stat_value": challenger_stat_value,
                    "score_gained": 0,
                    "hearts_lost": challenger_hearts_lost
                }
        
        # ساخت challenger و opponent data برای match_info_handler
        challenger_card_obj = SimpleNamespace(
            name=challenger_card.name,
            power=challenger_card.power,
            speed=challenger_card.speed,
            iq=challenger_card.iq,
            popularity=challenger_card.popularity,
            rarity=challenger_card.rarity.value if hasattr(challenger_card.rarity, 'value') else str(challenger_card.rarity)
        )
        opponent_card_obj = SimpleNamespace(
            name=opponent_card.name,
            power=opponent_card.power,
            speed=opponent_card.speed,
            iq=opponent_card.iq,
            popularity=opponent_card.popularity,
            rarity=opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else str(opponent_card.rarity)
        )
        
        challenger_data = {
            "user_id": fight.challenger_id,
            "card": challenger_card_obj,
            "stat": fight.challenger_stat,
            "stat_type": fight.challenger_stat,
            "stat_value": challenger_stat_value,
            "score_gained": challenger_score,
            "hearts_lost": challenger_hearts_lost
        }
        opponent_data = {
            "user_id": fight.opponent_id,
            "card": opponent_card_obj,
            "stat": fight.opponent_stat,
            "stat_type": fight.opponent_stat,
            "stat_value": opponent_stat_value,
            "score_gained": opponent_score,
            "hearts_lost": opponent_hearts_lost
        }
        
        # ==================== XP و Tier Points ====================
        from phase2_systems import LevelSystem, TierSystem, XP_SOURCES
        
        xp_sources = XP_SOURCES
        
        # XP برای challenger
        if result == "win":
            ch_xp = xp_sources.get("normal_win", 10)
            op_xp = xp_sources.get("normal_loss", 3)
        elif result == "loss":
            ch_xp = xp_sources.get("normal_loss", 3)
            op_xp = xp_sources.get("normal_win", 10)
        else:  # tie
            ch_xp = xp_sources.get("normal_loss", 3)
            op_xp = xp_sources.get("normal_loss", 3)
        
        ch_old_level, ch_new_level = self.db.add_xp(fight.challenger_id, ch_xp)
        op_old_level, op_new_level = self.db.add_xp(fight.opponent_id, op_xp)
        
        # TP برای challenger و opponent
        ch_prog = self.db.get_or_create_progression(fight.challenger_id)
        op_prog = self.db.get_or_create_progression(fight.opponent_id)
        
        if result != "tie":
            tp_gain, tp_loss = TierSystem.calculate_tp_change(
                ch_prog['current_tier'] if result == "win" else op_prog['current_tier'],
                op_prog['current_tier'] if result == "win" else ch_prog['current_tier']
            )
            if result == "win":
                ch_old_tier, ch_new_tier = self.db.add_tier_points(fight.challenger_id, tp_gain)
                op_old_tier, op_new_tier = self.db.add_tier_points(fight.opponent_id, -tp_loss)
            else:
                op_old_tier, op_new_tier = self.db.add_tier_points(fight.opponent_id, tp_gain)
                ch_old_tier, ch_new_tier = self.db.add_tier_points(fight.challenger_id, -tp_loss)
        else:
            ch_old_tier = ch_new_tier = ch_prog['current_tier']
            op_old_tier = op_new_tier = op_prog['current_tier']
            tp_gain = tp_loss = 0
        
        # اضافه کردن اطلاعات XP/Level به challenger_data و opponent_data
        challenger_data['xp_gained'] = ch_xp
        challenger_data['level_up'] = ch_new_level > ch_old_level
        challenger_data['new_level'] = ch_new_level
        challenger_data['tier_changed'] = ch_new_tier != ch_old_tier
        challenger_data['new_tier'] = ch_new_tier
        
        opponent_data['xp_gained'] = op_xp
        opponent_data['level_up'] = op_new_level > op_old_level
        opponent_data['new_level'] = op_new_level
        opponent_data['tier_changed'] = op_new_tier != op_old_tier
        opponent_data['new_tier'] = op_new_tier
        
        if winner_data:
            winner_data['xp_gained'] = ch_xp if result == "win" else op_xp
        if loser_data:
            loser_data['xp_gained'] = op_xp if result == "win" else ch_xp

        return {
            "success": True,
            "fight_id": fight_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "result": result,
            "result_type": result_type,
            "winner": winner_data,
            "loser": loser_data,
            "challenger": challenger_data,
            "opponent": opponent_data,
            "challenger_stat_value": challenger_stat_value,
            "opponent_stat_value": opponent_stat_value,
            "challenger_card": challenger_card,
            "opponent_card": opponent_card
        }

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