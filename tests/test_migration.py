#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 تست Migration فاز ۲ - بدون تغییر دیتابیس اصلی
"""

import sqlite3
import shutil
from phase2_migration import Phase2Migration

def test_migration_dry_run():
    """تست migration روی یک کپی از دیتابیس"""
    
    print("=" * 60)
    print("🧪 تست Migration (Dry Run)")
    print("=" * 60)
    
    # ایجاد کپی موقت
    test_db = "game_bot_test.db"
    try:
        shutil.copy2("game_bot.db", test_db)
        print(f"✅ کپی موقت ایجاد شد: {test_db}\n")
    except FileNotFoundError:
        print("❌ فایل game_bot.db یافت نشد!")
        return False
    
    # نمایش وضعیت قبل از migration
    print("📊 وضعیت قبل از Migration:")
    print("-" * 60)
    
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    
    # تعداد کارت‌ها
    cursor.execute("SELECT COUNT(*) FROM cards")
    card_count = cursor.fetchone()[0]
    print(f"  کارت‌ها: {card_count} عدد")
    
    # نمونه آمار کارت
    cursor.execute("SELECT name, power, speed, iq, popularity FROM cards LIMIT 3")
    sample_cards = cursor.fetchall()
    print(f"\n  نمونه آمار کارت‌ها (قبل):")
    for card in sample_cards:
        print(f"    - {card[0]}: power={card[1]}, speed={card[2]}, iq={card[3]}, pop={card[4]}")
    
    # تعداد بازیکنان
    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]
    print(f"\n  بازیکنان: {player_count} نفر")
    
    # تعداد کارت‌های بازیکنان
    cursor.execute("SELECT COUNT(*) FROM player_cards")
    player_card_count = cursor.fetchone()[0]
    print(f"  کارت‌های بازیکنان: {player_card_count} عدد")
    
    conn.close()
    
    # اجرای migration روی کپی
    print("\n" + "=" * 60)
    print("🔄 اجرای Migration...")
    print("=" * 60 + "\n")
    
    migration = Phase2Migration(db_path=test_db)
    success = migration.run()
    
    # نمایش وضعیت بعد از migration
    if success:
        print("\n" + "=" * 60)
        print("📊 وضعیت بعد از Migration:")
        print("-" * 60)
        
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        # نمونه آمار کارت بعد از migration
        cursor.execute("SELECT name, power, speed, iq, popularity, card_type FROM cards LIMIT 3")
        sample_cards_after = cursor.fetchall()
        print(f"  نمونه آمار کارت‌ها (بعد):")
        for card in sample_cards_after:
            print(f"    - {card[0]}: power={card[1]}, speed={card[2]}, iq={card[3]}, pop={card[4]} ({card[5]})")
        
        # بررسی player_progression
        cursor.execute("SELECT COUNT(*) FROM player_progression")
        progression_count = cursor.fetchone()[0]
        print(f"\n  بازیکنان با progression: {progression_count} نفر")
        
        # نمونه progression
        cursor.execute("""
            SELECT p.username, pp.level, pp.total_xp, pp.tier_points, pp.current_tier
            FROM player_progression pp
            JOIN players p ON pp.user_id = p.user_id
            LIMIT 3
        """)
        sample_progression = cursor.fetchall()
        print(f"\n  نمونه progression:")
        for prog in sample_progression:
            print(f"    - {prog[0]}: Level {prog[1]}, {prog[2]} XP, {prog[3]} TP ({prog[4]})")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ تست موفق بود!")
        print("=" * 60)
        print("\n💡 برای اجرای واقعی:")
        print("   python phase2_migration.py")
    else:
        print("\n❌ تست ناموفق بود")
    
    # پاک کردن فایل موقت
    import os
    try:
        os.remove(test_db)
        if os.path.exists(test_db + ".backup_phase2_" + "*"):
            os.remove(test_db + ".backup_phase2_*")
        print(f"\n🗑️  فایل‌های موقت پاک شدند")
    except:
        pass
    
    return success


if __name__ == "__main__":
    test_migration_dry_run()
