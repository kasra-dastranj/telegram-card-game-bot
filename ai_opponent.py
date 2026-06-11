#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آسو — خدای TelBattle
منطق هوش مصنوعی حریف Solo
"""

import random
from typing import List, Dict, Optional
from game_core import Card, CardRarity

# ==================== شخصیت آسو ====================

ASO_DIALOGS = {
    "greeting": [
        "«می‌دونم اومدی. انتخاب کن.»",
        "«دوباره اومدی؟ جالبه.»",
        "«قدمت رو چشم... اگه جرأت داری.»",
    ],
    "round_win": [
        "«این همه توانت بود؟»",
        "«ضعیف‌تر از چیزی بودی که فکر می‌کردم.»",
        "«راوند بعد سخت‌تره.»",
    ],
    "round_lose": [
        "«جالبه... ادامه بده.»",
        "«شانس داشتی. هنوز.»",
        "«خوب بود. اما کافی نیست.»",
    ],
    "game_win": [
        "«امروز رحم کردم.»",
        "«برگرد وقتی قوی‌تر شدی.»",
        "«این یک استثناست.»",
    ],
    "game_lose": [
        "«ضعیف بودی.»",
        "«دوباره تلاش کن. شاید.»",
        "«دنیای من جای ضعیفا نیست.»",
    ],
}

ASO_MODES = {
    "easy": {
        "name": "آسو رحیم",
        "subtitle": "سطح آسان",
        "rarity": "normal",
        "score": 3,
        "xp": 5,
        "tier_points": 10,
        "hearts_lost_on_defeat": 1,
    },
    "medium": {
        "name": "آسو خشمگین",
        "subtitle": "سطح متوسط",
        "rarity": "epic",
        "score": 5,
        "xp": 8,
        "tier_points": 15,
        "hearts_lost_on_defeat": 1,
    },
    "hard": {
        "name": "آسو نابودگر",
        "subtitle": "سطح سخت",
        "rarity": "legend",
        "score": 8,
        "xp": 10,
        "tier_points": 20,
        "hearts_lost_on_defeat": 1,
    },
}

DAILY_SOLO_LIMIT = 10


class AsoAI:
    """هوش مصنوعی آسو"""

    def __init__(self, difficulty: str):
        self.difficulty = difficulty
        self.mode = ASO_MODES.get(difficulty, ASO_MODES["medium"])

    def get_greeting(self) -> str:
        return random.choice(ASO_DIALOGS["greeting"])

    def get_round_dialog(self, aso_won_round: bool) -> str:
        key = "round_win" if aso_won_round else "round_lose"
        return random.choice(ASO_DIALOGS[key])

    def get_result_dialog(self, aso_won_game: bool) -> str:
        key = "game_lose" if aso_won_game else "game_win"
        return random.choice(ASO_DIALOGS[key])

    def select_card(self, db) -> Optional[Card]:
        """انتخاب تصادفی کارت از pool مربوط به سختی"""
        rarity = self.mode["rarity"]
        pool = db.get_cards_by_rarity_pool(rarity)
        if not pool:
            # fallback به normal
            pool = db.get_cards_by_rarity_pool("normal")
        if not pool:
            return None
        return random.choice(pool)

    def select_stat(
        self,
        available_stats: List[str],
        ai_card: Card,
        player_card: Card,
        round_num: int
    ) -> str:
        """
        انتخاب stat بر اساس سختی:
        - easy:   کاملاً رندوم
        - medium: راوند اول رندوم، بعد بهترین stat خودش
        - hard:   statی که player ضعیف‌تره
        """
        if not available_stats:
            return "power"

        if self.difficulty == "easy":
            return random.choice(available_stats)

        elif self.difficulty == "medium":
            if round_num == 1:
                return random.choice(available_stats)
            # بهترین stat آسو از میان available
            return max(available_stats, key=lambda s: getattr(ai_card, s, 0))

        else:  # hard
            # statی که player در آن ضعیف‌تر است
            return min(available_stats, key=lambda s: getattr(player_card, s, 0))

    def calculate_rewards(self) -> Dict:
        """جوایز بر اساس سختی"""
        return {
            "score": self.mode["score"],
            "xp": self.mode["xp"],
            "tier_points": self.mode["tier_points"],
        }

    def calculate_defeat_penalty(self) -> Dict:
        """جریمه باخت"""
        return {
            "hearts_lost": self.mode["hearts_lost_on_defeat"],
            "xp": 3,  # XP تسلی
        }
