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

