#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎴 TelBattle Phase 2 - Claim System
سیستم کلیم جدید با Pool Management
"""

import random
import logging
from typing import List, Tuple, Optional, Set
from datetime import datetime, timedelta

from game_core import Card, CardRarity

logger = logging.getLogger(__name__)

class ClaimSystem:
    """
    سیستم کلیم جدید فاز ۲
    
    قوانین:
    - همیشه Normal می‌دهد
    - احتمال برابر برای همه کارت‌های pool
    - کارت‌های Epic/Legend از pool خارج می‌شوند
    - هرگز ناموفق نمی‌شود
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def get_claimable_pool(self, user_id: int) -> List[Card]:
        """
        دریافت pool کارت‌های قابل claim
        
        قوانین pool:
        1. کارت در pool است اگر:
           - بازیکن آن را در حالت EPIC یا LEGEND ندارد
        
        2. کارت از pool خارج است اگر:
           - بازیکن همان کارت را در حالت EPIC دارد
           - بازیکن همان کارت را در حالت LEGEND دارد
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            لیست کارت‌های قابل claim
        """
        # دریافت همه کارت‌های Normal
        all_cards = self.db.get_all_cards()
        normal_cards = [c for c in all_cards if c.rarity == CardRarity.NORMAL]
        
        if not normal_cards:
            logger.warning("No Normal cards found in database!")
            return []
        
        # دریافت کارت‌های Epic و Legend بازیکن
        player_cards = self.db.get_player_cards(user_id)
        
        # ساخت set از card_id های Epic و Legend
        excluded_card_ids: Set[str] = set()
        for card in player_cards:
            if card.rarity in [CardRarity.EPIC, CardRarity.LEGEND]:
                excluded_card_ids.add(card.card_id)
        
        # فیلتر کردن pool
        claimable = [c for c in normal_cards if c.card_id not in excluded_card_ids]
        
        # Fallback: اگر pool خالی شد (همه کارت‌ها Epic/Legend هستند)
        if not claimable:
            logger.warning(f"User {user_id} has all cards in Epic/Legend! Using fallback.")
            # در این حالت، کارت‌های Normal موجود در موجودی هم مجاز هستند
            player_normal_cards = [c for c in player_cards if c.rarity == CardRarity.NORMAL]
            if player_normal_cards:
                claimable = player_normal_cards
            else:
                # اگر هیچ Normal نداره، از همه Normal cards استفاده کن
                claimable = normal_cards
        
        logger.info(f"User {user_id} claimable pool size: {len(claimable)}")
        return claimable
    
    def can_claim_today(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        بررسی اینکه آیا بازیکن امروز می‌تواند claim کند
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            (can_claim, error_message)
        """
        player = self.db.get_or_create_player(user_id)
        
        # بررسی آیا امروز قبلاً claim کرده
        if player.last_claim and player.last_claim.year > 2000:
            now = datetime.now()
            
            last_claim_date = player.last_claim.date()
            today = now.date()
            
            # اگر امروز claim کرده
            if last_claim_date == today:
                # محاسبه زمان تا نیمه شب
                midnight = datetime.combine(today + timedelta(days=1), datetime.min.time())
                remaining = midnight - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                
                error_msg = f"شما امروز کارت دریافت کرده‌اید. کارت بعدی در {hours} ساعت و {minutes} دقیقه دیگر (ساعت 00:00)"
                return False, error_msg
        
        return True, None
    
    def claim_card(self, user_id: int) -> Tuple[bool, Optional[Card], Optional[str]]:
        """
        کلیم کارت روزانه
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            (success, card, error_message)
        """
        # بررسی cooldown
        can_claim, error_msg = self.can_claim_today(user_id)
        if not can_claim:
            return False, None, error_msg
        
        # دریافت pool
        claimable_pool = self.get_claimable_pool(user_id)
        
        if not claimable_pool:
            return False, None, "هیچ کارتی برای claim موجود نیست"
        
        # انتخاب با احتمال برابر
        selected_card = random.choice(claimable_pool)
        
        logger.info(f"User {user_id} claimed card: {selected_card.name} (Normal)")
        
        # اضافه کردن کارت به موجودی (همیشه Normal)
        added = self.db.add_card_to_player(user_id, selected_card.card_id)
        
        if not added:
            logger.warning(f"Failed to add card {selected_card.card_id} to user {user_id}")
        
        # بروزرسانی last_claim
        player = self.db.get_or_create_player(user_id)
        player.last_claim = datetime.now()
        self.db.update_player(player)
        
        logger.info(f"User {user_id} claim successful. Next claim: tomorrow 00:00")
        
        return True, selected_card, None
    
    def get_pool_stats(self, user_id: int) -> dict:
        """
        دریافت آمار pool برای نمایش
        
        Args:
            user_id: شناسه بازیکن
            
        Returns:
            آمار pool
        """
        all_cards = self.db.get_all_cards()
        normal_cards = [c for c in all_cards if c.rarity == CardRarity.NORMAL]
        
        player_cards = self.db.get_player_cards(user_id)
        
        # تعداد کارت‌های Epic/Legend
        epic_count = len([c for c in player_cards if c.rarity == CardRarity.EPIC])
        legend_count = len([c for c in player_cards if c.rarity == CardRarity.LEGEND])
        
        # تعداد کارت‌های قابل claim
        claimable = self.get_claimable_pool(user_id)
        
        return {
            "total_normal_cards": len(normal_cards),
            "claimable_count": len(claimable),
            "excluded_count": len(normal_cards) - len(claimable),
            "player_epic_count": epic_count,
            "player_legend_count": legend_count
        }


# ==================== HELPER FUNCTIONS ====================

def format_pool_stats(stats: dict) -> str:
    """فرمت کردن آمار pool برای نمایش"""
    return (
        f"📊 آمار Pool:\n"
        f"  - کل کارت‌های Normal: {stats['total_normal_cards']}\n"
        f"  - قابل Claim: {stats['claimable_count']}\n"
        f"  - خارج از Pool: {stats['excluded_count']}\n"
        f"  - Epic شما: {stats['player_epic_count']}\n"
        f"  - Legend شما: {stats['player_legend_count']}"
    )
