#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏟️ TelBattle Phase 2 - Arena System
سیستم زمین‌های بازی با Boost
"""

import random
import logging
from typing import Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class CardType(Enum):
    """تایپ کارت‌ها"""
    POWER_TYPE = "POWER_TYPE"
    SPEED_TYPE = "SPEED_TYPE"
    IQ_TYPE = "IQ_TYPE"
    POPULARITY_TYPE = "POPULARITY_TYPE"


class ArenaType(Enum):
    """انواع زمین بازی"""
    POWER_ARENA = "power_arena"
    SPEED_TRACK = "speed_track"
    THINKING_ROOM = "thinking_room"
    STAGE = "stage"


# تعریف زمین‌ها
ARENAS = {
    ArenaType.POWER_ARENA: {
        "name": "🏟️ میدان قدرت",
        "name_en": "Power Arena",
        "description": "زمینی برای نمایش قدرت خام",
        "boost_stat": "power",
        "boost_type": CardType.POWER_TYPE,
        "emoji": "💪"
    },
    ArenaType.SPEED_TRACK: {
        "name": "🏁 پیست سرعت",
        "name_en": "Speed Track",
        "description": "مسیری برای سریع‌ترین‌ها",
        "boost_stat": "speed",
        "boost_type": CardType.SPEED_TYPE,
        "emoji": "⚡"
    },
    ArenaType.THINKING_ROOM: {
        "name": "🧠 اتاق فکر",
        "name_en": "Thinking Room",
        "description": "فضایی برای نبوغ ذهنی",
        "boost_stat": "iq",
        "boost_type": CardType.IQ_TYPE,
        "emoji": "🎓"
    },
    ArenaType.STAGE: {
        "name": "🎭 صحنه",
        "name_en": "Stage",
        "description": "جایی برای درخشش ستاره‌ها",
        "boost_stat": "popularity",
        "boost_type": CardType.POPULARITY_TYPE,
        "emoji": "⭐"
    }
}


class ArenaSystem:
    """
    سیستم Arena
    
    ویژگی‌ها:
    - انتخاب رندوم Arena برای هر بازی
    - محاسبه Boost (+1) برای کارت‌های مناسب
    - نمایش اطلاعات Arena
    """
    
    @staticmethod
    def select_random_arena() -> ArenaType:
        """
        انتخاب رندوم یک Arena
        
        Returns:
            ArenaType
        """
        arena = random.choice(list(ArenaType))
        logger.info(f"Selected arena: {arena.value}")
        return arena
    
    @staticmethod
    def get_arena_info(arena: ArenaType) -> Dict:
        """
        دریافت اطلاعات Arena
        
        Args:
            arena: نوع Arena
        
        Returns:
            اطلاعات Arena
        """
        return ARENAS[arena]
    
    @staticmethod
    def calculate_boost(
        card_type: str,
        arena: ArenaType,
        selected_stat: str,
        base_value: int
    ) -> Tuple[int, bool]:
        """
        محاسبه Boost برای stat انتخاب شده
        
        قوانین Boost:
        - کارت باید تایپ مناسب داشته باشد
        - Arena باید مناسب باشد
        - Stat انتخاب شده باید با Arena match کند
        
        Args:
            card_type: تایپ کارت (POWER_TYPE, SPEED_TYPE, ...)
            arena: نوع Arena
            selected_stat: stat انتخاب شده (power, speed, iq, popularity)
            base_value: مقدار پایه stat
        
        Returns:
            (final_value, has_boost)
        """
        arena_info = ARENAS[arena]
        boost_stat = arena_info['boost_stat']
        boost_type = arena_info['boost_type'].value
        
        # بررسی شرایط Boost
        has_boost = (
            card_type == boost_type and
            selected_stat == boost_stat
        )
        
        final_value = base_value + 1 if has_boost else base_value
        
        if has_boost:
            logger.info(
                f"Boost applied: {card_type} in {arena.value} "
                f"with {selected_stat} → {base_value} + 1 = {final_value}"
            )
        
        return final_value, has_boost
    
    @staticmethod
    def format_arena_message(arena: ArenaType) -> str:
        """
        فرمت کردن پیام Arena برای نمایش
        
        Args:
            arena: نوع Arena
        
        Returns:
            پیام فرمت شده
        """
        info = ARENAS[arena]
        
        text = (
            f"{info['emoji']} **{info['name']}**\n"
            f"_{info['description']}_\n\n"
            f"💡 Boost: کارت‌های {info['boost_type'].value} "
            f"با انتخاب {info['boost_stat']} → +1"
        )
        
        return text
    
    @staticmethod
    def get_boost_emoji(has_boost: bool) -> str:
        """دریافت emoji برای نمایش Boost"""
        return "🔥" if has_boost else ""


# ==================== HELPER FUNCTIONS ====================

def format_stat_with_boost(stat_name: str, base_value: int, final_value: int) -> str:
    """
    فرمت کردن stat با نمایش Boost
    
    Args:
        stat_name: نام stat
        base_value: مقدار پایه
        final_value: مقدار نهایی
    
    Returns:
        رشته فرمت شده
    """
    if final_value > base_value:
        return f"{stat_name}: {base_value} → {final_value} 🔥"
    else:
        return f"{stat_name}: {final_value}"


def get_card_type_emoji(card_type: str) -> str:
    """دریافت emoji برای تایپ کارت"""
    emojis = {
        'POWER_TYPE': '💪',
        'SPEED_TYPE': '⚡',
        'IQ_TYPE': '🧠',
        'POPULARITY_TYPE': '⭐'
    }
    return emojis.get(card_type, '❓')


def get_card_type_name(card_type: str) -> str:
    """دریافت نام فارسی تایپ کارت"""
    names = {
        'POWER_TYPE': 'قدرت',
        'SPEED_TYPE': 'سرعت',
        'IQ_TYPE': 'هوش',
        'POPULARITY_TYPE': 'محبوبیت'
    }
    return names.get(card_type, 'نامشخص')
