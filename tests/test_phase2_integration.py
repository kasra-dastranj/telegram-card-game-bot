#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست یکپارچه Phase 2
تست کامل همه سیستم‌های Phase 2 با هم
"""

import os
import sys
from datetime import datetime

# تنظیم ENV_FILE برای تست
os.environ['ENV_FILE'] = '.env.test'

from game_core import DatabaseManager, CardRarity
from phase2_systems import LevelSystem, TierSystem, DecaySystem, ProgressionDB
from fusion_system import FusionSystem
from economy_system import EconomySystem
from claim_system import ClaimSystem

def test_phase2_integration():
    """تست یکپارچه Phase 2"""
    print("🧪 شروع تست یکپارچه Phase 2...")
    print("="*60)
    
    # اتصال به دیتابیس تست
    db = DatabaseManager(db_path='game_bot_test.db')
    
    # راه‌اندازی سیستم‌ها
    level_sys = LevelSystem()
    tier_sys = TierSystem()
    decay_sys = DecaySystem()
    prog_db = ProgressionDB(db)
    fusion = FusionSystem(db)
    economy = EconomySystem(db)
    claim = ClaimSystem(db)
    
    # ایجاد بازیکن تست
    test_user_id = 777777
    
    print(f"\n📋 سناریو: بازیکن جدید تا Legend")
    print("="*60)
    
    # پاک کردن داده‌های قبلی
    import sqlite3
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM player_cards WHERE user_id = ?', (test_user_id,))
    cursor.execute('DELETE FROM player_progression WHERE user_id = ?', (test_user_id,))
    cursor.execute('DELETE FROM fusion_log WHERE user_id = ?', (test_user_id,))
    cursor.execute('DELETE FROM players WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    # مرحله 1: ایجاد بازیکن
    print("\n1️⃣ ایجاد بازیکن و Initialize...")
    player = db.get_or_create_player(test_user_id, "test_integration", "Test Integration")
    
    # Initialize Phase 2
    prog_db.initialize_player(test_user_id)
    
    progression = prog_db.get_player_progression(test_user_id)
    print(f"   ✅ Level: {progression.level}")
    print(f"   ✅ Tier: {progression.current_tier}")
    print(f"   ✅ XP: {progression.total_xp}")
    print(f"   ✅ TP: {progression.tier_points}")
    
    # مرحله 2: Claim کارت‌ها
    print("\n2️⃣ Claim کارت‌های Normal...")
    
    for i in range(10):
        success, card, error = claim.claim_card(test_user_id)
        if success:
            print(f"   ✅ Claim {i+1}: {card.name}")
        else:
            print(f"   ❌ Claim {i+1} ناموفق: {error}")
            # Reset cooldown برای تست
            conn = sqlite3.connect('game_bot_test.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE players SET last_claim = NULL WHERE user_id = ?', (test_user_id,))
            conn.commit()
            conn.close()
    
    cards = db.get_player_cards(test_user_id)
    print(f"   📊 تعداد کل کارت‌ها: {len(cards)}")
    
    # مرحله 3: Fusion Normal → Epic
    print("\n3️⃣ Fusion: Normal → Epic...")
    
    can_fuse, normal_cards = fusion.can_fuse_to_epic(test_user_id)
    
    if can_fuse:
        selected_cards = [c.card_id for c in normal_cards[:3]]
        selected_card_id = selected_cards[0]
        
        result = fusion.fuse_to_epic(test_user_id, selected_cards, selected_card_id)
        
        if result.success:
            print(f"   ✅ Fusion موفق: {result.upgraded_card.name} → Epic")
            
            # اضافه XP برای Fusion
            prog_db.add_xp(test_user_id, 15)
            progression = prog_db.get_player_progression(test_user_id)
            print(f"   ✅ XP جدید: {progression.total_xp} (Level {progression.level})")
        else:
            print(f"   ❌ Fusion ناموفق: {result.error}")
    else:
        print(f"   ⚠️ کارت کافی برای Fusion نیست")
    
    # مرحله 4: ماینینگ
    print("\n4️⃣ ماینینگ روزانه...")
    
    # Reset mining cooldown
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET last_mining_claim = NULL WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    success, coins, error = economy.claim_daily_mining(test_user_id)
    
    if success:
        print(f"   ✅ ماینینگ موفق: {coins} سکه")
        print(f"   💰 موجودی: {economy.get_coins(test_user_id)} سکه")
    else:
        print(f"   ❌ ماینینگ ناموفق: {error}")
    
    # مرحله 5: شبیه‌سازی بازی‌ها
    print("\n5️⃣ شبیه‌سازی بازی‌ها (10 برد)...")
    
    for i in range(10):
        # اضافه XP برای برد
        prog_db.add_xp(test_user_id, 10)
        
        # اضافه TP برای برد
        prog_db.add_tier_points(test_user_id, 15)
    
    progression = prog_db.get_player_progression(test_user_id)
    print(f"   ✅ Level: {progression.level}")
    print(f"   ✅ Tier: {progression.current_tier}")
    print(f"   ✅ XP: {progression.total_xp}")
    print(f"   ✅ TP: {progression.tier_points}")
    
    # مرحله 6: تبدیل امتیاز به سکه
    print("\n6️⃣ تبدیل امتیاز به سکه...")
    
    # اضافه امتیاز
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET total_score = 500 WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    success, coins, error = economy.convert_score_to_coins(test_user_id, 200)
    
    if success:
        print(f"   ✅ تبدیل موفق: 200 امتیاز → {coins} سکه")
        print(f"   💰 موجودی: {economy.get_coins(test_user_id)} سکه")
    else:
        print(f"   ❌ تبدیل ناموفق: {error}")
    
    # مرحله 7: خرید قلب
    print("\n7️⃣ خرید قلب از شاپ...")
    
    # اضافه سکه کافی
    economy.add_coins(test_user_id, 300, "test")
    
    success, error = economy.buy_heart_increase(test_user_id)
    
    if success:
        stats = economy.get_economy_stats(test_user_id)
        print(f"   ✅ خرید موفق: قلب جدید = {stats['max_hearts']}")
        print(f"   💰 موجودی: {stats['coins']} سکه")
    else:
        print(f"   ❌ خرید ناموفق: {error}")
    
    # مرحله 8: Claim بیشتر و Fusion به Legend
    print("\n8️⃣ Claim بیشتر برای Fusion به Legend...")
    
    # Claim کارت‌های بیشتر
    for i in range(15):
        conn = sqlite3.connect('game_bot_test.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE players SET last_claim = NULL WHERE user_id = ?', (test_user_id,))
        conn.commit()
        conn.close()
        
        success, card, error = claim.claim_card(test_user_id)
        if success and i < 3:  # فقط 3 تا اول رو نمایش بده
            print(f"   ✅ Claim: {card.name}")
    
    # Fusion به Epic (برای داشتن 3 Epic)
    print("\n   🔮 Fusion های بیشتر برای داشتن 3 Epic...")
    
    for fusion_num in range(2):
        can_fuse, normal_cards = fusion.can_fuse_to_epic(test_user_id)
        
        if can_fuse:
            selected_cards = [c.card_id for c in normal_cards[:3]]
            selected_card_id = selected_cards[0]
            
            result = fusion.fuse_to_epic(test_user_id, selected_cards, selected_card_id)
            
            if result.success:
                print(f"   ✅ Fusion {fusion_num+1}: {result.upgraded_card.name} → Epic")
    
    # Fusion به Legend
    print("\n   🌟 Fusion: Epic → Legend...")
    
    can_fuse, epic_cards = fusion.can_fuse_to_legend(test_user_id)
    
    if can_fuse:
        selected_cards = [c.card_id for c in epic_cards[:3]]
        selected_card_id = selected_cards[0]
        
        result = fusion.fuse_to_legend(test_user_id, selected_cards, selected_card_id)
        
        if result.success:
            print(f"   ✅ Fusion موفق: {result.upgraded_card.name} → Legend!")
            
            # اضافه XP برای Fusion
            prog_db.add_xp(test_user_id, 30)
            progression = prog_db.get_player_progression(test_user_id)
            print(f"   ✅ XP جدید: {progression.total_xp} (Level {progression.level})")
        else:
            print(f"   ❌ Fusion ناموفق: {result.error}")
    else:
        print(f"   ⚠️ کارت Epic کافی نیست ({len(epic_cards)}/3)")
    
    # مرحله 9: خلاصه نهایی
    print("\n" + "="*60)
    print("📊 خلاصه نهایی")
    print("="*60)
    
    # Progression
    progression = prog_db.get_player_progression(test_user_id)
    print(f"\n🎯 پیشرفت:")
    print(f"   • Level: {progression.level}")
    print(f"   • XP: {progression.total_xp}")
    print(f"   • Tier: {progression.current_tier}")
    print(f"   • TP: {progression.tier_points}")
    
    # کارت‌ها
    cards = db.get_player_cards(test_user_id)
    normal_count = len([c for c in cards if c.rarity == CardRarity.NORMAL])
    epic_count = len([c for c in cards if c.rarity == CardRarity.EPIC])
    legend_count = len([c for c in cards if c.rarity == CardRarity.LEGEND])
    
    print(f"\n🎴 کارت‌ها:")
    print(f"   • تعداد کل: {len(cards)}")
    print(f"   • Normal: {normal_count}")
    print(f"   • Epic: {epic_count}")
    print(f"   • Legend: {legend_count}")
    
    # اقتصاد
    stats = economy.get_economy_stats(test_user_id)
    print(f"\n💰 اقتصاد:")
    print(f"   • سکه: {stats['coins']}")
    print(f"   • امتیاز: {stats['score']}")
    print(f"   • قلب: {stats['max_hearts']}")
    print(f"   • ماینینگ روزانه: {stats['daily_mining']} سکه")
    
    # Fusion
    fusion_stats = fusion.get_fusion_stats(test_user_id)
    print(f"\n🔮 Fusion:")
    print(f"   • تعداد کل: {fusion_stats['total_fusions']}")
    print(f"   • Normal→Epic: {fusion_stats['normal_to_epic']}")
    print(f"   • Epic→Legend: {fusion_stats['epic_to_legend']}")
    
    # بررسی موفقیت
    print("\n" + "="*60)
    
    success = True
    
    if progression.level < 2:
        print("❌ Level کمتر از 2 است!")
        success = False
    
    if legend_count < 1:
        print("❌ هیچ کارت Legend ندارد!")
        success = False
    
    if stats['coins'] < 1:
        print("❌ سکه ندارد!")
        success = False
    
    if fusion_stats['total_fusions'] < 1:
        print("❌ هیچ Fusion انجام نشده!")
        success = False
    
    if success:
        print("✅ همه سیستم‌های Phase 2 به درستی کار می‌کنند!")
        print("✅ تست یکپارچه موفق بود!")
    else:
        print("❌ برخی سیستم‌ها مشکل دارند!")
    
    print("="*60)
    
    return success

if __name__ == "__main__":
    try:
        success = test_phase2_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ خطا در تست: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
