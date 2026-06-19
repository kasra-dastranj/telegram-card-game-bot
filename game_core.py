#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎮 TelBattle - Core System (Compatibility Wrapper)

این فایل یه wrapper هست که backward compatibility رو حفظ می‌کنه.
کد اصلی در پوشه core/ قرار داره:
  - core/models.py     → مدل‌ها و Enum ها
  - core/database.py   → DatabaseManager
  - core/game_logic.py → GameLogic و CardManager
"""

# Re-export everything for backward compatibility
from core.models import (
    SimpleCache,
    CardRarity,
    StatType,
    FightStatus,
    Card,
    Player,
    PvPFight,
)

from core.database import DatabaseManager

from core.game_logic import GameLogic, CardManager

__all__ = [
    'SimpleCache',
    'CardRarity',
    'StatType',
    'FightStatus',
    'Card',
    'Player',
    'PvPFight',
    'DatabaseManager',
    'GameLogic',
    'CardManager',
]
