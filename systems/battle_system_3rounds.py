#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚔️ TelBattle Phase 2 - 3-Round Battle System
سیستم مبارزه ۳ راوندی با Stat Locking و زمین‌های بازی
"""

import sqlite3
import logging
import random
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass

from game_core import Card, CardRarity, StatType

logger = logging.getLogger(__name__)

# ==================== ARENA TYPES ====================

ARENAS = {
    "power_arena": {
        "name_fa": "عرصه قدرت",
        "name_en": "Power Arena",
        "boost_stat": "power",
        "boost_amount": 8,
        "emoji": "⚡"
    },
    "speed_track": {
        "name_fa": "پیست سرعت",
        "name_en": "Speed Track",
        "boost_stat": "speed",
        "boost_amount": 8,
        "emoji": "🏃"
    },
    "thinking_room": {
        "name_fa": "اتاق فکر",
        "name_en": "Thinking Room",
        "boost_stat": "iq",
        "boost_amount": 8,
        "emoji": "🧠"
    },
    "stage": {
        "name_fa": "صحنه",
        "name_en": "Stage",
        "boost_stat": "popularity",
        "boost_amount": 8,
        "emoji": "⭐"
    }
}

# ==================== TYPE COUNTER SYSTEM ====================

# چرخه برتری: POWER > SPEED > IQ > POPULARITY > POWER
TYPE_COUNTER = {
    "POWER_TYPE": "SPEED_TYPE",      # قدرت سرعت رو می‌زنه
    "SPEED_TYPE": "IQ_TYPE",         # سرعت هوش رو می‌زنه
    "IQ_TYPE": "POPULARITY_TYPE",    # هوش شهرت رو می‌زنه
    "POPULARITY_TYPE": "POWER_TYPE", # شهرت قدرت رو می‌زنه
}

TYPE_COUNTER_BONUS = 10  # بونوس برتری تایپ

# ==================== ABILITY SYSTEM ====================

ABILITIES = {
    "boost_15": {
        "name_fa": "تقویت",
        "emoji": "💥",
        "description": "استت این راوندِ خودت +15",
        "effect": "self_boost",
        "value": 15,
    },
    "sabotage_10": {
        "name_fa": "خرابکاری",
        "emoji": "🔧",
        "description": "استت حریف در این راوند -10",
        "effect": "opponent_debuff",
        "value": 10,
    },
    "copy": {
        "name_fa": "تقلید",
        "emoji": "🪞",
        "description": "مقدار total حریف را برابر total خودت کن",
        "effect": "copy_opponent",
        "value": 0,
    },
    "peek": {
        "name_fa": "شنود",
        "emoji": "👁️",
        "description": "یک stat تصادفی حریف را قبل از انتخاب ببین",
        "effect": "reveal_stat",
        "value": 0,
    },
    "shield": {
        "name_fa": "سپر",
        "emoji": "🛡️",
        "description": "اگر این راوند باختی، کاهش stat نصف شود",
        "effect": "reduce_penalty",
        "value": 0,
    },
}

# نگاشت ابیلیتی بر اساس rarity
RARITY_ABILITY_MAP = {
    "normal": None,              # بدون ابیلیتی
    "epic": "boost_15",          # حماسی: تقویت
    "legend": "sabotage_10",     # افسانه‌ای: خرابکاری
    "rare": "copy",              # کمیاب: تقلید
}

# نگاشت ابیلیتی بر اساس card_type (override اگه rarity ابیلیتی نداد)
TYPE_ABILITY_MAP = {
    "POWER_TYPE": "boost_15",
    "SPEED_TYPE": "peek",
    "IQ_TYPE": "sabotage_10",
    "POPULARITY_TYPE": "shield",
}


def get_card_ability(card) -> Optional[str]:
    """
    تعیین ابیلیتی فعال یک کارت.
    اولویت: rarity → card_type → None
    """
    rarity_val = card.rarity.value if hasattr(card.rarity, 'value') else card.rarity
    ability = RARITY_ABILITY_MAP.get(rarity_val)
    if ability:
        return ability
    # fallback به card_type
    card_type = getattr(card, 'card_type', None)
    if card_type:
        return TYPE_ABILITY_MAP.get(card_type)
    return None

# ==================== MODELS ====================

@dataclass
class RoundResult:
    """نتیجه یک راوند"""
    round_number: int
    challenger_stat: str
    opponent_stat: str
    challenger_value: int
    opponent_value: int
    challenger_boost: int
    opponent_boost: int
    challenger_total: int
    opponent_total: int
    winner: Optional[str]  # 'challenger', 'opponent', or None (tie)
    challenger_reduction: int
    opponent_reduction: int
    timestamp: str

@dataclass
class BattleState:
    """وضعیت کامل یک بازی ۳ راوندی"""
    fight_id: str
    challenger_id: int
    opponent_id: int
    challenger_card_id: str
    opponent_card_id: str
    arena: str
    current_round: int
    challenger_rounds_won: int
    opponent_rounds_won: int
    challenger_used_stats: List[str]
    opponent_used_stats: List[str]
    rounds_history: List[RoundResult]
    status: str  # 'round_1', 'round_2', 'round_3', 'completed'
    
    # آمار کارت‌ها (کاهش یافته در طول بازی)
    challenger_current_stats: Dict[str, int]
    opponent_current_stats: Dict[str, int]

# ==================== BATTLE SYSTEM ====================

class BattleSystem3Rounds:
    """سیستم مبارزه ۳ راوندی"""
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def select_arena(self, challenger_card: Card, opponent_card: Card) -> str:
        """
        انتخاب زمین بازی بر اساس rarity کارت‌ها
        
        قانون:
        - اگر یکی rarity پایین‌تر دارد، او انتخاب می‌کند
        - اگر برابر باشند، random انتخاب می‌شود
        
        Args:
            challenger_card: کارت challenger
            opponent_card: کارت opponent
            
        Returns:
            arena_id (e.g., "power_arena")
        """
        rarity_order = {
            CardRarity.NORMAL: 1,
            CardRarity.EPIC: 2,
            CardRarity.LEGEND: 3,
            CardRarity.RARE: 4
        }
        
        challenger_rarity_value = rarity_order.get(challenger_card.rarity, 1)
        opponent_rarity_value = rarity_order.get(opponent_card.rarity, 1)
        
        if challenger_rarity_value < opponent_rarity_value:
            selector = "challenger"
        elif opponent_rarity_value < challenger_rarity_value:
            selector = "opponent"
        else:
            selector = "random"
        
        # اگه random باشه، همین‌جا انتخاب کن
        # اگه یکی باید انتخاب کنه، None برگردون تا UI نشون داده بشه
        if selector == "random":
            arena_id = random.choice(list(ARENAS.keys()))
            logger.info(f"Arena randomly selected: {arena_id}")
            return arena_id, None  # (arena_id, selector_role)
        else:
            logger.info(f"Arena selector: {selector}")
            return None, selector  # بازیکن باید انتخاب کنه
    
    def calculate_boost(self, card: Card, arena: str, selected_stat: str) -> int:
        """
        محاسبه boost زمین برای یک کارت
        
        Boost فقط زمانی اعمال می‌شود که:
        1. تایپ کارت با نوع زمین یکسان باشد
        2. بازیکن همان stat متناظر را انتخاب کرده باشد
        
        Args:
            card: کارت بازیکن
            arena: شناسه زمین
            selected_stat: ویژگی انتخاب شده توسط بازیکن
            
        Returns:
            مقدار boost (معمولاً 0 یا 1)
        """
        arena_info = ARENAS.get(arena)
        if not arena_info:
            return 0
        
        boost_stat = arena_info["boost_stat"]
        boost_amount = arena_info["boost_amount"]
        
        # بررسی اینکه stat انتخاب شده با boost stat زمین یکسان است
        if selected_stat != boost_stat:
            return 0
        
        # بررسی اینکه تایپ کارت با زمین match می‌کند
        card_type = getattr(card, 'card_type', None)
        if not card_type:
            return 0
        
        # تبدیل card_type به stat name
        type_to_stat = {
            "POWER_TYPE": "power",
            "SPEED_TYPE": "speed",
            "IQ_TYPE": "iq",
            "POPULARITY_TYPE": "popularity"
        }
        
        card_main_stat = type_to_stat.get(card_type)
        
        if card_main_stat == boost_stat:
            return boost_amount
        
        return 0
    
    def apply_ability(self, ability_key: str, role: str,
                      challenger_total: int, opponent_total: int,
                      challenger_base: int, opponent_base: int,
                      challenger_boost: int, opponent_boost: int) -> Tuple[int, int, str]:
        """
        اعمال اثر ابیلیتی فعال‌شده روی total‌های راوند.
        
        Args:
            ability_key: کلید ابیلیتی (مثل 'boost_15')
            role: 'challenger' یا 'opponent' (کی ابیلیتی زده)
            challenger_total: مجموع فعلی challenger
            opponent_total: مجموع فعلی opponent
            و بقیه مقادیر پایه
            
        Returns:
            (new_challenger_total, new_opponent_total, effect_text)
        """
        ability = ABILITIES.get(ability_key)
        if not ability:
            return challenger_total, opponent_total, ""
        
        effect = ability["effect"]
        emoji = ability["emoji"]
        name = ability["name_fa"]
        
        if effect == "self_boost":
            # +15 به خودش
            if role == "challenger":
                challenger_total += ability["value"]
            else:
                opponent_total += ability["value"]
            effect_text = f"{emoji} {name}: +{ability['value']}"
            
        elif effect == "opponent_debuff":
            # -10 از حریف
            if role == "challenger":
                opponent_total = max(0, opponent_total - ability["value"])
            else:
                challenger_total = max(0, challenger_total - ability["value"])
            effect_text = f"{emoji} {name}: -{ability['value']} حریف"
            
        elif effect == "copy_opponent":
            # total حریف = total خودت
            if role == "challenger":
                opponent_total = challenger_total
            else:
                challenger_total = opponent_total
            effect_text = f"{emoji} {name}: مقدار حریف = مقدار تو"
            
        elif effect == "reduce_penalty":
            # اثرش بعد از resolve اعمال میشه (در reduction)
            effect_text = f"{emoji} {name}: کاهش stat نصف شد"
            
        else:
            effect_text = ""
        
        return challenger_total, opponent_total, effect_text

    def get_available_stats(self, used_stats: List[str]) -> List[str]:
        """
        دریافت ویژگی‌های قابل انتخاب
        
        Args:
            used_stats: لیست ویژگی‌های استفاده شده
            
        Returns:
            لیست ویژگی‌های قابل انتخاب
        """
        all_stats = ["power", "speed", "iq", "popularity"]
        available = [s for s in all_stats if s not in used_stats]
        return available
    
    def resolve_round(
        self,
        battle_state: BattleState,
        challenger_card: Card,
        opponent_card: Card,
        challenger_stat: str,
        opponent_stat: str
    ) -> RoundResult:
        """
        حل و فصل یک راوند
        
        Args:
            battle_state: وضعیت فعلی بازی
            challenger_card: کارت challenger
            opponent_card: کارت opponent
            challenger_stat: ویژگی انتخاب شده توسط challenger
            opponent_stat: ویژگی انتخاب شده توسط opponent
            
        Returns:
            RoundResult
        """
        # دریافت آمار فعلی (کاهش یافته)
        challenger_base = battle_state.challenger_current_stats[challenger_stat]
        opponent_base = battle_state.opponent_current_stats[opponent_stat]
        
        # محاسبه boost
        challenger_boost = self.calculate_boost(challenger_card, battle_state.arena, challenger_stat)
        opponent_boost = self.calculate_boost(opponent_card, battle_state.arena, opponent_stat)
        
        # محاسبه بونوس برتری تایپ (Type Counter)
        challenger_type = getattr(challenger_card, 'card_type', '') or ''
        opponent_type = getattr(opponent_card, 'card_type', '') or ''
        
        challenger_counter_bonus = 0
        opponent_counter_bonus = 0
        if TYPE_COUNTER.get(challenger_type) == opponent_type:
            challenger_counter_bonus = TYPE_COUNTER_BONUS
        if TYPE_COUNTER.get(opponent_type) == challenger_type:
            opponent_counter_bonus = TYPE_COUNTER_BONUS
        
        # محاسبه مجموع
        challenger_total = challenger_base + challenger_boost + challenger_counter_bonus
        opponent_total = opponent_base + opponent_boost + opponent_counter_bonus
        
        # تعیین برنده
        if challenger_total > opponent_total:
            winner = "challenger"
            win_margin = challenger_total - opponent_total
        elif opponent_total > challenger_total:
            winner = "opponent"
            win_margin = opponent_total - challenger_total
        else:
            winner = None  # tie
            win_margin = 0
        
        # محاسبه کاهش آمار (پررنگ‌تر شده برای عمق استراتژیک)
        challenger_reduction = 0
        opponent_reduction = 0
        
        if winner == "challenger":
            # بازنده کاهش می‌یابد
            if win_margin >= 15:
                opponent_reduction = 8
            else:
                opponent_reduction = 5
        elif winner == "opponent":
            # بازنده کاهش می‌یابد
            if win_margin >= 15:
                challenger_reduction = 8
            else:
                challenger_reduction = 5
        else:
            # تساوی: هر دو 3 واحد کم می‌شوند
            challenger_reduction = 3
            opponent_reduction = 3
        
        # اعمال کاهش
        battle_state.challenger_current_stats[challenger_stat] = max(
            0,
            battle_state.challenger_current_stats[challenger_stat] - challenger_reduction
        )
        battle_state.opponent_current_stats[opponent_stat] = max(
            0,
            battle_state.opponent_current_stats[opponent_stat] - opponent_reduction
        )
        
        # ساخت نتیجه
        result = RoundResult(
            round_number=battle_state.current_round,
            challenger_stat=challenger_stat,
            opponent_stat=opponent_stat,
            challenger_value=challenger_base,
            opponent_value=opponent_base,
            challenger_boost=challenger_boost,
            opponent_boost=opponent_boost,
            challenger_total=challenger_total,
            opponent_total=opponent_total,
            winner=winner,
            challenger_reduction=challenger_reduction,
            opponent_reduction=opponent_reduction,
            timestamp=datetime.now().isoformat()
        )
        
        # بروزرسانی امتیاز راوندها
        if winner == "challenger":
            battle_state.challenger_rounds_won += 1
        elif winner == "opponent":
            battle_state.opponent_rounds_won += 1
        
        # اضافه کردن به تاریخچه
        battle_state.rounds_history.append(result)
        
        # اضافه کردن به used_stats
        battle_state.challenger_used_stats.append(challenger_stat)
        battle_state.opponent_used_stats.append(opponent_stat)
        
        logger.info(
            f"Round {result.round_number} resolved: "
            f"Challenger {challenger_total} vs Opponent {opponent_total} "
            f"(Winner: {winner})"
        )
        
        return result
    
    def is_battle_finished(self, battle_state: BattleState) -> bool:
        """
        بررسی اینکه آیا بازی تمام شده است
        
        بازی تمام می‌شود اگر:
        - یکی از بازیکنان 2 راوند برده باشد
        - 3 راوند کامل شده باشد
        
        Args:
            battle_state: وضعیت فعلی بازی
            
        Returns:
            True اگر بازی تمام شده باشد
        """
        if battle_state.challenger_rounds_won >= 2:
            return True
        if battle_state.opponent_rounds_won >= 2:
            return True
        if battle_state.current_round > 3:
            return True
        return False
    
    def get_final_winner(self, battle_state: BattleState) -> Optional[str]:
        """
        تعیین برنده نهایی
        
        Args:
            battle_state: وضعیت نهایی بازی
            
        Returns:
            'challenger', 'opponent', or None (tie)
        """
        if battle_state.challenger_rounds_won > battle_state.opponent_rounds_won:
            return "challenger"
        elif battle_state.opponent_rounds_won > battle_state.challenger_rounds_won:
            return "opponent"
        else:
            return None  # tie (نباید اتفاق بیفتد در best of 3)


# ==================== DATABASE OPERATIONS ====================

def create_battle_tables(db_path: str):
    """
    ایجاد جداول مورد نیاز برای سیستم ۳ راوندی
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
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
            challenger_reduction INTEGER NOT NULL DEFAULT 0,
            opponent_reduction INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (fight_id) REFERENCES active_fights (fight_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Battle tables created successfully")


# ==================== HELPER FUNCTIONS ====================

def format_round_result(
    round_result: RoundResult,
    challenger_card: Card,
    opponent_card: Card,
    arena: str,
    for_user: str  # 'challenger' or 'opponent'
) -> str:
    """
    فرمت کردن نتیجه راوند برای نمایش به بازیکن
    
    Args:
        round_result: نتیجه راوند
        challenger_card: کارت challenger
        opponent_card: کارت opponent
        arena: شناسه زمین
        for_user: برای کدام بازیکن (challenger یا opponent)
        
    Returns:
        متن فرمت شده
    """
    arena_info = ARENAS.get(arena, {})
    arena_name = arena_info.get("name_fa", "نامشخص")
    arena_emoji = arena_info.get("emoji", "🏟️")
    
    # تعیین "شما" و "حریف"
    if for_user == "challenger":
        your_card = challenger_card
        opponent_card_display = opponent_card
        your_stat = round_result.challenger_stat
        opponent_stat = round_result.opponent_stat
        your_value = round_result.challenger_value
        opponent_value = round_result.opponent_value
        your_boost = round_result.challenger_boost
        opponent_boost = round_result.opponent_boost
        your_total = round_result.challenger_total
        opponent_total = round_result.opponent_total
        your_reduction = round_result.challenger_reduction
        opponent_reduction = round_result.opponent_reduction
        you_won = round_result.winner == "challenger"
    else:
        your_card = opponent_card
        opponent_card_display = challenger_card
        your_stat = round_result.opponent_stat
        opponent_stat = round_result.challenger_stat
        your_value = round_result.opponent_value
        opponent_value = round_result.challenger_value
        your_boost = round_result.opponent_boost
        opponent_boost = round_result.challenger_boost
        your_total = round_result.opponent_total
        opponent_total = round_result.challenger_total
        your_reduction = round_result.opponent_reduction
        opponent_reduction = round_result.challenger_reduction
        you_won = round_result.winner == "opponent"
    
    # نام ویژگی‌ها به فارسی
    stat_names = {
        "power": "⚡ قدرت",
        "speed": "🏃 سرعت",
        "iq": "🧠 هوش",
        "popularity": "⭐ محبوبیت"
    }
    
    your_stat_name = stat_names.get(your_stat, your_stat)
    opponent_stat_name = stat_names.get(opponent_stat, opponent_stat)
    
    # رریتی کارت حریف (نام مخفی است)
    opponent_rarity = opponent_card_display.rarity.value if hasattr(opponent_card_display.rarity, 'value') else str(opponent_card_display.rarity)
    
    # تعیین نتیجه
    if round_result.winner is None:
        result_text = "🤝 مساوی!"
        result_detail = f"💥 هر دو {your_reduction} واحد کم شدند"
    elif you_won:
        result_text = "🏆 شما برنده!"
        result_detail = f"💥 {your_stat_name} شما: {your_value + your_boost} → {your_value + your_boost - your_reduction}"
    else:
        result_text = "💀 حریف برنده!"
        result_detail = f"💥 {opponent_stat_name} حریف: {opponent_value + opponent_boost} → {opponent_value + opponent_boost - opponent_reduction}"
    
    text = f"""
━━━━━━━━━━━━━━━━━━━━━━
     📊 راوند {round_result.round_number}
━━━━━━━━━━━━━━━━━━━━━━

🏟️ زمین: {arena_emoji} {arena_name}

🎴 کارت شما: {your_card.name} ({your_card.rarity.value if hasattr(your_card.rarity, 'value') else str(your_card.rarity)})
🎴 کارت حریف: ??? ({opponent_rarity})

⚔️ ویژگی انتخابی:
  شما: {your_stat_name}
  حریف: {opponent_stat_name}

📈 آمار:
  شما: {your_value} + {your_boost} (زمین) = {your_total}
  حریف: {opponent_value} + {opponent_boost} = {opponent_total}

{result_text}
{result_detail}
"""
    
    return text.strip()

