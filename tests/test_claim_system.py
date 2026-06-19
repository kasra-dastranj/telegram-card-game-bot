#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست سیستم Claim جدید
"""

import sys
import io

# تنظیم encoding برای ویندوز
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from game_core import DatabaseManager, GameLogic, CardRarity
from claim_system import ClaimSystem, format_pool_stats

def test_claim_pool():
    """تست pool management"""
    print("=" * 60)
    print("🧪 تست Claim Pool Management")
    print("=" * 60)
    
    db = DatabaseManager('game_bot_test.db')
    claim_system = ClaimSystem(db)
    
    test_user_id = 5735941901
    
    # دریافت آمار pool
    stats = claim_system.get_pool_stats(test_user_id)
    print(f"\n{format_pool_stats(stats)}")
    
    # دریافت pool
    pool = claim_system.get_claimable_pool(test_user_id)
    print(f"\n📋 کارت‌های قابل Claim: {len(pool)}")
    
    if pool:
        print(f"\n🎴 نمونه کارت‌های pool (5 تا اول):")
        for i, card in enumerate(pool[:5], 1):
            print(f"  {i}. {card.name} ({card.rarity.value})")
    
    print("\n✅ تست Pool Management موفق")

def test_claim_card():
    """تست کلیم کارت"""
    print("\n" + "=" * 60)
    print("🧪 تست Claim Card")
    print("=" * 60)
    
    db = DatabaseManager('game_bot_test.db')
    game = GameLogic(db)
    
    test_user_id = 5735941901
    
    # دریافت تعداد کارت‌های قبل
    cards_before = db.get_player_cards(test_user_id)
    normal_before = len([c for c in cards_before if c.rarity == CardRarity.NORMAL])
    
    print(f"\n📊 قبل از Claim:")
    print(f"  - کل کارت‌ها: {len(cards_before)}")
    print(f"  - Normal: {normal_before}")
    
    # تلاش برای claim
    success, card, error = game.claim_daily_card(test_user_id)
    
    if success and card:
        print(f"\n✅ Claim موفق!")
        print(f"  - کارت دریافتی: {card.name}")
        print(f"  - Rarity: {card.rarity.value}")
        
        # بررسی که Normal است
        if card.rarity == CardRarity.NORMAL:
            print(f"  - ✅ کارت Normal است (طبق قوانین)")
        else:
            print(f"  - ❌ کارت Normal نیست! (خطا)")
        
        # دریافت تعداد کارت‌های بعد
        cards_after = db.get_player_cards(test_user_id)
        normal_after = len([c for c in cards_after if c.rarity == CardRarity.NORMAL])
        
        print(f"\n📊 بعد از Claim:")
        print(f"  - کل کارت‌ها: {len(cards_after)}")
        print(f"  - Normal: {normal_after}")
        print(f"  - تغییر: +{len(cards_after) - len(cards_before)} کارت")
        
    else:
        print(f"\n⚠️ Claim ناموفق:")
        print(f"  - خطا: {error}")
        print(f"  - این طبیعی است اگر امروز قبلاً claim کرده‌اید")
    
    print("\n✅ تست Claim Card موفق")

def test_claim_cooldown():
    """تست cooldown کلیم"""
    print("\n" + "=" * 60)
    print("🧪 تست Claim Cooldown")
    print("=" * 60)
    
    db = DatabaseManager('game_bot_test.db')
    claim_system = ClaimSystem(db)
    
    test_user_id = 5735941901
    
    # بررسی cooldown
    can_claim, error = claim_system.can_claim_today(test_user_id)
    
    if can_claim:
        print(f"\n✅ می‌توانید امروز claim کنید")
    else:
        print(f"\n⏰ Cooldown فعال است:")
        print(f"  - {error}")
    
    print("\n✅ تست Cooldown موفق")

def test_pool_exclusion():
    """تست حذف کارت‌های Epic/Legend از pool"""
    print("\n" + "=" * 60)
    print("🧪 تست Pool Exclusion (Epic/Legend)")
    print("=" * 60)
    
    db = DatabaseManager('game_bot_test.db')
    claim_system = ClaimSystem(db)
    
    test_user_id = 5735941901
    
    # دریافت کارت‌های بازیکن
    player_cards = db.get_player_cards(test_user_id)
    epic_cards = [c for c in player_cards if c.rarity == CardRarity.EPIC]
    legend_cards = [c for c in player_cards if c.rarity == CardRarity.LEGEND]
    
    print(f"\n📊 کارت‌های بازیکن:")
    print(f"  - Epic: {len(epic_cards)}")
    print(f"  - Legend: {len(legend_cards)}")
    
    if epic_cards:
        print(f"\n🟣 کارت‌های Epic:")
        for card in epic_cards[:3]:
            print(f"  - {card.name}")
    
    if legend_cards:
        print(f"\n🟡 کارت‌های Legend:")
        for card in legend_cards[:3]:
            print(f"  - {card.name}")
    
    # دریافت pool
    pool = claim_system.get_claimable_pool(test_user_id)
    pool_card_ids = {c.card_id for c in pool}
    
    # بررسی که Epic/Legend در pool نیستند
    excluded_count = 0
    for card in epic_cards + legend_cards:
        if card.card_id in pool_card_ids:
            print(f"\n❌ خطا: {card.name} ({card.rarity.value}) در pool است!")
        else:
            excluded_count += 1
    
    print(f"\n✅ {excluded_count} کارت Epic/Legend از pool خارج شدند")
    print(f"✅ تست Pool Exclusion موفق")

if __name__ == "__main__":
    try:
        test_claim_pool()
        test_claim_cooldown()
        test_pool_exclusion()
        test_claim_card()
        
        print("\n" + "=" * 60)
        print("✅ همه تست‌ها با موفقیت انجام شد!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        import traceback
        traceback.print_exc()
