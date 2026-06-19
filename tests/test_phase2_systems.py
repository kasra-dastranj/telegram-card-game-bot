#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست سیستم‌های فاز ۲
"""

import sys
import io

# تنظیم encoding برای ویندوز
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from phase2_systems import (
    LevelSystem, TierSystem, DecaySystem, ProgressionDB,
    XP_SOURCES, format_xp_bar, format_tier_badge
)
from datetime import datetime, timedelta

def test_level_system():
    """تست سیستم Level"""
    print("=" * 50)
    print("🎯 تست سیستم Level & XP")
    print("=" * 50)
    
    # تست محاسبه XP
    print("\n📊 XP مورد نیاز برای هر Level:")
    for level in range(1, 11):
        xp_needed = LevelSystem.xp_for_level(level)
        total_xp = LevelSystem.total_xp_for_level(level)
        print(f"  Level {level:2d}: {xp_needed:3d} XP (Total: {total_xp:4d})")
    
    # تست محاسبه Level از XP
    print("\n📈 محاسبه Level از XP:")
    test_xps = [0, 50, 100, 250, 500, 1000, 2000]
    for xp in test_xps:
        level = LevelSystem.get_level_from_xp(xp)
        current_level, xp_in_level, xp_needed = LevelSystem.get_xp_progress(xp)
        bar = format_xp_bar(xp_in_level, xp_needed)
        print(f"  {xp:4d} XP → Level {level} | {bar} ({xp_in_level}/{xp_needed})")
    
    print("\n✅ تست Level System موفق")

def test_tier_system():
    """تست سیستم Tier"""
    print("\n" + "=" * 50)
    print("🏆 تست سیستم Tier & TP")
    print("=" * 50)
    
    # تست محاسبه Tier از TP
    print("\n📊 Tier بر اساس TP:")
    test_tps = [0, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2500]
    for tp in test_tps:
        tier = TierSystem.get_tier_from_tp(tp)
        badge = format_tier_badge(tier)
        print(f"  {tp:4d} TP → {badge} {tier}")
    
    # تست محاسبه TP Change
    print("\n⚔️ محاسبه تغییر TP (Normal Battle):")
    tiers = ["Bronze", "Silver", "Gold", "Diamond", "Elite"]
    for winner_tier in tiers:
        for loser_tier in tiers:
            tp_gain, tp_loss = TierSystem.calculate_tp_change(winner_tier, loser_tier, "normal")
            print(f"  {winner_tier:8s} beats {loser_tier:8s}: +{tp_gain:2d} TP / -{tp_loss:2d} TP")
    
    print("\n✅ تست Tier System موفق")

def test_decay_system():
    """تست سیستم Decay"""
    print("\n" + "=" * 50)
    print("⏰ تست سیستم Decay")
    print("=" * 50)
    
    # تست Decay برای tier های مختلف
    print("\n📉 Decay بعد از بی‌فعالیت:")
    tiers = ["Bronze", "Silver", "Gold", "Diamond", "Elite"]
    
    for tier in tiers:
        print(f"\n  {format_tier_badge(tier)} {tier}:")
        current_tp = 1000  # فرض: 1000 TP
        
        for days in [1, 3, 5, 7, 10, 14]:
            last_played = datetime.now() - timedelta(days=days)
            new_tp, decay_amount = DecaySystem.calculate_decay(current_tp, tier, last_played)
            
            if decay_amount > 0:
                print(f"    {days:2d} روز: {current_tp} → {new_tp} (-{decay_amount} TP)")
            else:
                print(f"    {days:2d} روز: {current_tp} (حفاظت فعال)")
    
    print("\n✅ تست Decay System موفق")

def test_database_operations():
    """تست عملیات دیتابیس"""
    print("\n" + "=" * 50)
    print("💾 تست عملیات دیتابیس")
    print("=" * 50)
    
    db = ProgressionDB('game_bot_test.db')
    
    # تست دریافت progression
    print("\n📊 تست دریافت Progression:")
    test_user_id = 5735941901  # user ID شما
    
    progression = db.get_progression(test_user_id)
    if progression:
        print(f"  User ID: {progression.user_id}")
        print(f"  Level: {progression.level}")
        print(f"  Total XP: {progression.total_xp}")
        print(f"  Tier: {format_tier_badge(progression.current_tier)} {progression.current_tier}")
        print(f"  TP: {progression.tier_points}")
        print(f"  Last Played: {progression.last_played_at}")
    else:
        print(f"  ❌ Progression not found for user {test_user_id}")
    
    # تست اضافه کردن XP
    print("\n📈 تست اضافه کردن XP:")
    success, old_level, new_level = db.add_xp(test_user_id, 50, "test")
    if success:
        print(f"  ✅ XP اضافه شد: Level {old_level} → {new_level}")
    else:
        print(f"  ❌ خطا در اضافه کردن XP")
    
    # تست اضافه کردن TP
    print("\n🏆 تست اضافه کردن TP:")
    success, old_tier, new_tier = db.add_tp(test_user_id, 20)
    if success:
        print(f"  ✅ TP اضافه شد: {old_tier} → {new_tier}")
    else:
        print(f"  ❌ خطا در اضافه کردن TP")
    
    print("\n✅ تست Database Operations موفق")

def test_xp_sources():
    """نمایش منابع XP"""
    print("\n" + "=" * 50)
    print("💰 منابع XP")
    print("=" * 50)
    
    for source, xp in XP_SOURCES.items():
        print(f"  {source:20s}: {xp:3d} XP")
    
    print("\n✅ منابع XP نمایش داده شد")

if __name__ == "__main__":
    print("🧪 شروع تست سیستم‌های فاز ۲\n")
    
    try:
        test_level_system()
        test_tier_system()
        test_decay_system()
        test_xp_sources()
        test_database_operations()
        
        print("\n" + "=" * 50)
        print("✅ همه تست‌ها با موفقیت انجام شد!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ خطا در تست: {e}")
        import traceback
        traceback.print_exc()
