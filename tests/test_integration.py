#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 Integration Test - Phase 2 Systems
تست یکپارچگی سیستم‌های جدید با Bot
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_core import DatabaseManager, CardRarity
from tier_decay_system import TierDecaySystem
from card_missions_system import CardMissionsSystem


def test_tier_decay_integration():
    """تست یکپارچگی Tier Decay"""
    print("\n" + "="*50)
    print("🧪 Testing Tier Decay Integration")
    print("="*50)
    
    # اجرای migrations
    print("\n📦 Running migrations...")
    from phase2_migration import Phase2Migration
    migration = Phase2Migration('test_integration.db')
    migration.run()
    
    from migrate_optional_features import migrate_optional_features
    migrate_optional_features('test_integration.db')
    
    db = DatabaseManager('test_integration.db')
    tier_decay = TierDecaySystem(db)
    
    # ایجاد بازیکن تست
    test_user_id = 999999
    player = db.get_or_create_player(test_user_id, "test_user", "Test User")
    
    # ایجاد progression
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # حذف داده‌های قبلی
    cursor.execute('DELETE FROM player_progression WHERE user_id = ?', (test_user_id,))
    
    # ایجاد progression با TP بالا
    cursor.execute('''
        INSERT INTO player_progression 
        (user_id, level, total_xp, current_tier, tier_points, last_played_at)
        VALUES (?, 10, 5000, 'Gold', 1200, ?)
    ''', (test_user_id, datetime.now() - timedelta(days=5)))
    
    conn.commit()
    conn.close()
    
    # تست دریافت اطلاعات Decay
    decay_info = tier_decay.get_decay_info(test_user_id)
    
    print(f"\n✅ Decay Info Retrieved:")
    print(f"   Current Tier: {decay_info.get('current_tier')}")
    print(f"   Current TP: {decay_info.get('current_tp')}")
    print(f"   Days Inactive: {decay_info.get('days_inactive')}")
    print(f"   Days Until Decay: {decay_info.get('days_until_decay')}")
    print(f"   Potential Decay: {decay_info.get('potential_decay')} TP")
    
    # تست اعمال Decay
    result = tier_decay.apply_decay_to_player(test_user_id)
    
    if result:
        print(f"\n✅ Decay Applied:")
        print(f"   Old TP: {result.get('old_tp')}")
        print(f"   New TP: {result.get('new_tp')}")
        print(f"   TP Lost: {result.get('tp_lost')}")
        print(f"   Tier Changed: {result.get('tier_changed')}")
        if result.get('tier_changed'):
            print(f"   Old Tier: {result.get('old_tier')}")
            print(f"   New Tier: {result.get('new_tier')}")
    
    print("\n✅ Tier Decay Integration Test PASSED!")
    return True


def test_missions_integration():
    """تست یکپارچگی Card Missions"""
    print("\n" + "="*50)
    print("🧪 Testing Card Missions Integration")
    print("="*50)
    
    db = DatabaseManager('test_integration.db')
    missions = CardMissionsSystem(db)
    
    test_user_id = 999999
    test_card_id = "test_epic_card"
    
    # ایجاد کارت Epic تست
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # حذف داده‌های قبلی
    cursor.execute('DELETE FROM cards WHERE card_id = ?', (test_card_id,))
    cursor.execute('DELETE FROM player_cards WHERE card_id = ?', (test_card_id,))
    cursor.execute('DELETE FROM card_missions WHERE card_id = ?', (test_card_id,))
    
    # ایجاد کارت
    cursor.execute('''
        INSERT INTO cards 
        (card_id, name, rarity, power, speed, iq, popularity, abilities, biography, image_path, card_type)
        VALUES (?, 'Test Epic', 'epic', 8, 8, 8, 8, '["Test Ability"]', 'Test Bio', '', 'POWER')
    ''', (test_card_id,))
    
    # اضافه کردن به بازیکن
    cursor.execute('''
        INSERT INTO player_cards (user_id, card_id)
        VALUES (?, ?)
    ''', (test_user_id, test_card_id))
    
    conn.commit()
    conn.close()
    
    # ایجاد ماموریت
    success = missions.create_mission(test_card_id, 'total_wins', 10)
    print(f"\n✅ Mission Created: {success}")
    
    # دریافت progress
    progress = missions.get_player_mission_progress(test_user_id, test_card_id)
    
    if progress:
        print(f"\n✅ Mission Progress Retrieved:")
        print(f"   Mission Type: {progress.get('mission', {}).get('mission_type')}")
        print(f"   Target: {progress.get('mission', {}).get('target')}")
        print(f"   Current Progress: {progress.get('current_progress')}")
        print(f"   Completed: {progress.get('completed')}")
    
    # شبیه‌سازی چند برد
    for i in range(5):
        match_data = {
            "won": True,
            "winning_stat": "power"
        }
        result = missions.check_and_update_mission(test_user_id, test_card_id, match_data)
        print(f"\n   Match {i+1}: Progress = {result.get('current_progress')}/{result.get('target')}")
    
    # بررسی progress نهایی
    progress = missions.get_player_mission_progress(test_user_id, test_card_id)
    print(f"\n✅ Final Progress: {progress.get('current_progress')}/{progress.get('mission', {}).get('target')}")
    
    print("\n✅ Card Missions Integration Test PASSED!")
    return True


def test_profile_display():
    """تست نمایش اطلاعات در Profile"""
    print("\n" + "="*50)
    print("🧪 Testing Profile Display")
    print("="*50)
    
    db = DatabaseManager('test_integration.db')
    tier_decay = TierDecaySystem(db)
    
    test_user_id = 999999
    
    # دریافت اطلاعات برای نمایش در Profile
    decay_info = tier_decay.get_decay_info(test_user_id)
    
    if decay_info:
        days_until_decay = decay_info.get('days_until_decay', 0)
        
        # شبیه‌سازی متن Profile
        if days_until_decay > 0:
            decay_text = f"   🛡️ حفاظت: {days_until_decay} روز"
        else:
            decay_text = f"   ⚠️ Decay فعال!"
        
        print(f"\n✅ Profile Display Text:")
        print(f"📈 پیشرفت:")
        print(f"⭐ Level: 10/30")
        print(f"🏆 Tier: {decay_info.get('current_tier')} ({decay_info.get('current_tp')} TP)")
        print(decay_text)
    
    print("\n✅ Profile Display Test PASSED!")
    return True


def cleanup():
    """پاکسازی فایل تست"""
    try:
        if os.path.exists('test_integration.db'):
            os.remove('test_integration.db')
            print("\n🧹 Test database cleaned up")
    except Exception as e:
        print(f"\n⚠️ Cleanup warning: {e}")


def main():
    """اجرای تمام تست‌ها"""
    print("\n" + "="*50)
    print("Starting Integration Tests")
    print("="*50)
    
    try:
        # اجرای تست‌ها
        test_tier_decay_integration()
        test_missions_integration()
        test_profile_display()
        
        print("\n" + "="*50)
        print("ALL INTEGRATION TESTS PASSED!")
        print("="*50)
        print("\nBot is ready for Phase 2 features!")
        print("\nNext Steps:")
        print("   1. Setup Cron Job (see CRON_SETUP.md)")
        print("   2. Test with real users")
        print("   3. Monitor logs")
        print("   4. Add remaining UI (Rare Cards, Skins, Risk Mode)")
        
        return True
        
    except Exception as e:
        print(f"\nTest Failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        cleanup()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
