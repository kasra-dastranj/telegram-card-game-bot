"""
TelBattle Core Package
Re-exports all public classes for backward compatibility
"""

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
