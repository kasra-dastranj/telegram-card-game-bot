#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🃏 TelBattle - Deck System
سیستم ساخت، ذخیره و مدیریت دک‌های بازیکن
"""

import logging
from typing import List, Dict, Optional, Tuple

from core.models import Card, CardRarity

logger = logging.getLogger(__name__)

DECK_SELECTION_TTL_SECONDS = 60

# امتیاز هر rarity برای محدودیت دک
RARITY_POINTS = {
    'normal': 1,
    'epic':   2,
    'legend': 3,
    'rare':   2,  # rare مثل epic حساب می‌شود
}
MAX_DECK_POINTS = 5

# پیام‌های خطا
ERR_MAX_DECKS       = "حداکثر ۵۰ دک مجاز است. یک دک را حذف کنید."
ERR_CARD_COUNT      = "دک باید دقیقاً ۳ کارت داشته باشد."
ERR_DUPLICATE_CARD  = "کارت‌های تکراری در دک مجاز نیست."
ERR_NOT_OWNED       = "کارت «{name}» در کلکسیون شما نیست."
ERR_NAME_TOO_LONG   = "نام دک حداکثر ۲۰ کاراکتر می‌تواند باشد."
ERR_POINTS_EXCEEDED = "امتیاز دک بیش از حد مجاز ({max}) است. ترکیب انتخاب‌شده {pts} امتیاز دارد."
ERR_DECK_NOT_FOUND  = "دک یافت نشد."
ERR_NOT_OWNER       = "این دک متعلق به شما نیست."


class DeckSystem:
    """سیستم مدیریت دک‌های بازیکنان"""

    MAX_DECKS         = 50
    MAX_CARDS_PER_DECK = 3
    MAX_NAME_LENGTH   = 20

    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db

    # ==================== VALIDATION ====================

    def _validate(
        self,
        player_id: int,
        card_ids: List[str],
        name: Optional[str],
        is_edit: bool = False
    ) -> Tuple[bool, str]:
        """اعتبارسنجی کامل برای ساخت یا ویرایش دک.
        Returns: (ok, error_message)
        """
        # تعداد دک (فقط در ساخت، نه ویرایش)
        if not is_edit:
            if self.db.count_player_decks(player_id) >= self.MAX_DECKS:
                return False, ERR_MAX_DECKS

        # تعداد کارت
        if len(card_ids) != self.MAX_CARDS_PER_DECK:
            return False, ERR_CARD_COUNT

        # تکراری نبودن
        if len(set(card_ids)) != self.MAX_CARDS_PER_DECK:
            return False, ERR_DUPLICATE_CARD

        # عضویت در کلکسیون. طبق قوانین جدید Deck Mode، rarity دیگر
        # محدودیت ساخت دک نیست و فقط برای نمایش خلاصه نگه داشته می‌شود.
        player_cards = {c.card_id: c for c in self.db.get_player_cards(player_id)}
        for cid in card_ids:
            if cid not in player_cards:
                return False, ERR_NOT_OWNED.format(name=cid)

        # طول نام
        if name and len(name) > self.MAX_NAME_LENGTH:
            return False, ERR_NAME_TOO_LONG

        return True, ""

    # ==================== NAME ====================

    def _generate_default_name(self, player_id: int) -> str:
        """نام پیش‌فرض بر اساس تعداد دک‌های فعلی"""
        existing = self.db.get_player_decks(player_id)
        used_names = {d['deck_name'] for d in existing}
        for i in range(1, self.MAX_DECKS + 2):
            candidate = f"دک {i}"
            if candidate not in used_names:
                return candidate
        return f"دک {len(existing) + 1}"

    # ==================== DECK CRUD ====================

    def create_deck(
        self,
        player_id: int,
        card_ids: List[str],
        name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """ساخت دک جدید.
        Returns: (True, deck_id) در صورت موفقیت
                 (False, error_message) در صورت خطا
        """
        ok, err = self._validate(player_id, card_ids, name, is_edit=False)
        if not ok:
            return False, err

        if not name:
            name = self._generate_default_name(player_id)

        deck_id = self.db.create_deck(
            player_id, name,
            card_ids[0], card_ids[1], card_ids[2]
        )
        logger.info(f"Deck created: {deck_id} for player {player_id}")
        return True, deck_id

    def update_deck(
        self,
        player_id: int,
        deck_id: str,
        card_ids: Optional[List[str]] = None,
        name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """ویرایش دک موجود.
        Returns: (True, "") یا (False, error_message)
        """
        deck = self.db.get_deck_by_id(deck_id)
        if not deck:
            return False, ERR_DECK_NOT_FOUND
        if deck['player_id'] != player_id:
            return False, ERR_NOT_OWNER

        # اگر card_ids جدید داده شده، اعتبارسنجی کن
        if card_ids is not None:
            ok, err = self._validate(player_id, card_ids, name, is_edit=True)
            if not ok:
                return False, err
            self.db.update_deck(
                deck_id,
                deck_name=name,
                card_id_1=card_ids[0],
                card_id_2=card_ids[1],
                card_id_3=card_ids[2],
                is_valid=1
            )
        else:
            # فقط نام عوض می‌شود
            if name and len(name) > self.MAX_NAME_LENGTH:
                return False, ERR_NAME_TOO_LONG
            self.db.update_deck(deck_id, deck_name=name)

        logger.info(f"Deck updated: {deck_id}")
        return True, ""

    def delete_deck(self, player_id: int, deck_id: str) -> Tuple[bool, str]:
        """حذف دک.
        Returns: (True, "") یا (False, error_message)
        """
        deck = self.db.get_deck_by_id(deck_id)
        if not deck:
            return False, ERR_DECK_NOT_FOUND
        if deck['player_id'] != player_id:
            return False, ERR_NOT_OWNER
        self.db.delete_deck(deck_id)
        logger.info(f"Deck deleted: {deck_id}")
        return True, ""

    # ==================== QUERIES ====================

    def get_player_decks(self, player_id: int) -> List[Dict]:
        """همه دک‌های یک بازیکن با اطلاعات کامل کارت‌ها.
        Returns: لیست dict با کلیدهای:
          deck_id, deck_name, is_valid, total_points, cards: [Card, Card, Card]
        """
        raw_decks = self.db.get_player_decks(player_id)
        result = []
        for d in raw_decks:
            cards = self._load_deck_cards(player_id, d)
            total_pts = self._calc_points(cards)
            result.append({
                'deck_id':     d['deck_id'],
                'deck_name':   d['deck_name'],
                'is_valid':    bool(d['is_valid']),
                'total_points': total_pts,
                'cards':       cards,
            })
        return result

    def get_valid_decks(self, player_id: int) -> List[Dict]:
        """فقط دک‌های کامل و معتبر (is_valid=1)"""
        # قبل از برگشت، integrity چک می‌کنیم
        self._refresh_deck_validity(player_id)
        all_decks = self.get_player_decks(player_id)
        return [d for d in all_decks if d['is_valid']]

    def get_deck_cards(self, deck_id: str, player_id: int) -> List[Card]:
        """کارت‌های یک دک به صورت List[Card]"""
        deck = self.db.get_deck_by_id(deck_id)
        if not deck:
            return []
        if deck['player_id'] != player_id:
            return []
        return self._load_deck_cards(player_id, deck)

    def validate_deck_integrity(self, player_id: int, deck_id: str) -> bool:
        """بررسی اینکه هر ۳ کارت هنوز در کلکسیون هستند.
        اگر ناقص باشد is_valid=0 می‌کند و False برمی‌گرداند.
        """
        deck = self.db.get_deck_by_id(deck_id)
        if not deck:
            return False
        if deck['player_id'] != player_id:
            return False

        owned_ids = {c.card_id for c in self.db.get_player_cards(player_id)}
        card_ids = [deck['card_id_1'], deck['card_id_2'], deck['card_id_3']]

        if all(cid in owned_ids for cid in card_ids):
            return True

        # دک ناقص — علامت‌گذاری
        self.db.update_deck(deck_id, is_valid=0)
        logger.info(f"Deck {deck_id} marked invalid (card removed from collection)")
        return False

    # ==================== HELPERS ====================

    def _load_deck_cards(self, player_id: int, deck_row: Dict) -> List[Card]:
        """بارگذاری Card objects از card_id های دک"""
        cards = []
        for key in ('card_id_1', 'card_id_2', 'card_id_3'):
            cid = deck_row.get(key)
            if cid:
                card = (
                    self.db.get_card_by_id_for_player(cid, player_id)
                    or self.db.get_card_by_id(cid)
                )
                if card:
                    cards.append(card)
        return cards

    def _calc_points(self, cards: List[Card]) -> int:
        """محاسبه مجموع امتیاز rarity یک دک"""
        total = 0
        for card in cards:
            rarity_val = card.rarity.value if hasattr(card.rarity, 'value') else card.rarity
            total += RARITY_POINTS.get(rarity_val, 1)
        return total

    def _refresh_deck_validity(self, player_id: int) -> None:
        """بررسی و به‌روزرسانی validity همه دک‌های یک بازیکن"""
        raw_decks = self.db.get_player_decks(player_id)
        owned_ids = {c.card_id for c in self.db.get_player_cards(player_id)}
        for d in raw_decks:
            if not d['is_valid']:
                continue  # قبلاً ناقص شناخته شده
            card_ids = [d['card_id_1'], d['card_id_2'], d['card_id_3']]
            if not all(cid in owned_ids for cid in card_ids):
                self.db.update_deck(d['deck_id'], is_valid=0)
                logger.info(f"Deck {d['deck_id']} invalidated during refresh")

    @staticmethod
    def format_deck_summary(deck: Dict) -> str:
        """متن خلاصه یک دک برای نمایش در UI"""
        rarity_emoji = {'normal': '🟢', 'epic': '🟣', 'legend': '🟡', 'rare': '🔵'}
        status = "✅" if deck['is_valid'] else "⚠️"
        cards_text = " · ".join(
            f"{rarity_emoji.get(c.rarity.value if hasattr(c.rarity,'value') else c.rarity, '⚪')} {c.name}"
            for c in deck['cards']
        )
        return (
            f"{status} **{deck['deck_name']}** — {deck['total_points']}pt\n"
            f"└ {cards_text}"
        )
