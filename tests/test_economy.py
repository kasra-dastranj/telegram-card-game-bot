#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست Economy System
"""

import os
import sys

# تنظیم ENV_FILE برای تست
os.environ['ENV_FILE'] = '.env.test'

from game_core import DatabaseManager, CardRarity
from economy_system import EconomySystem

def test_economy():
    """تست سیستم Economy"""
    print("🧪 شروع تست Economy System...")
    
    # اتصال به دیتابیس تست
    db = DatabaseManager(db_path='game_bot_test.db')
    economy = EconomySystem(db)
    
    # ایجاد یک بازیکن تست
    test_user_id = 888888
    
    print(f"\n1️⃣ ایجاد بازیکن تست (user_id={test_user_id})...")
    player = db.get_or_create_player(test_user_id, "test_economy", "Test Economy")
    print(f"   ✅ بازیکن ایجاد شد")
    
    # تست 1: دریافت موجودی سکه
    print("\n2️⃣ تست دریافت موجودی سکه...")
    coins = economy.get_coins(test_user_id)
    print(f"   • موجودی فعلی: {coins} سکه")
    print("   ✅ تست موفق")
    
    # تست 2: اضافه کردن سکه
    print("\n3️⃣ تست اضافه کردن سکه...")
    success = economy.add_coins(test_user_id, 100, "test")
    new_coins = economy.get_coins(test_user_id)
    print(f"   • موجودی جدید: {new_coins} سکه")
    
    if not success or new_coins != coins + 100:
        print("   ❌ تست ناموفق!")
        return False
    
    print("   ✅ تست موفق")
    
    # تست 3: خرج کردن سکه
    print("\n4️⃣ تست خرج کردن سکه...")
    success, error = economy.spend_coins(test_user_id, 50, "test")
    new_coins = economy.get_coins(test_user_id)
    print(f"   • موجودی جدید: {new_coins} سکه")
    
    if not success:
        print(f"   ❌ تست ناموفق: {error}")
        return False
    
    print("   ✅ تست موفق")
    
    # تست 4: خرج کردن بیش از موجودی
    print("\n5️⃣ تست خرج کردن بیش از موجودی...")
    success, error = economy.spend_coins(test_user_id, 10000, "test")
    
    if success:
        print("   ❌ تست ناموفق: باید ناموفق باشد!")
        return False
    
    print(f"   • خطا: {error}")
    print("   ✅ تست موفق (خطا مورد انتظار)")
    
    # تست 5: محاسبه ماینینگ
    print("\n6️⃣ تست محاسبه ماینینگ...")
    
    # اضافه کردن 10 کارت Normal
    all_cards = db.get_all_cards()
    normal_cards = [c for c in all_cards if c.rarity == CardRarity.NORMAL][:10]
    
    import sqlite3
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM player_cards WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    for card in normal_cards:
        db.add_card_to_player(test_user_id, card.card_id)
    
    mining = economy.calculate_daily_mining(test_user_id)
    expected = 10 // 5  # 2 سکه
    
    print(f"   • تعداد کارت: 10")
    print(f"   • ماینینگ محاسبه شده: {mining} سکه")
    print(f"   • ماینینگ مورد انتظار: {expected} سکه")
    
    if mining != expected:
        print("   ❌ تست ناموفق!")
        return False
    
    print("   ✅ تست موفق")
    
    # تست 6: دریافت ماینینگ
    print("\n7️⃣ تست دریافت ماینینگ...")
    
    # پاک کردن last_mining_claim
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET last_mining_claim = NULL WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    coins_before = economy.get_coins(test_user_id)
    success, coins_earned, error = economy.claim_daily_mining(test_user_id)
    coins_after = economy.get_coins(test_user_id)
    
    if not success:
        print(f"   ❌ تست ناموفق: {error}")
        return False
    
    print(f"   • سکه دریافتی: {coins_earned}")
    print(f"   • موجودی قبل: {coins_before}")
    print(f"   • موجودی بعد: {coins_after}")
    
    if coins_after != coins_before + coins_earned:
        print("   ❌ موجودی اشتباه است!")
        return False
    
    print("   ✅ تست موفق")
    
    # تست 7: دریافت مجدد ماینینگ (باید ناموفق باشد)
    print("\n8️⃣ تست دریافت مجدد ماینینگ...")
    success, coins_earned, error = economy.claim_daily_mining(test_user_id)
    
    if success:
        print("   ❌ تست ناموفق: باید ناموفق باشد!")
        return False
    
    print(f"   • خطا: {error}")
    print("   ✅ تست موفق (خطا مورد انتظار)")
    
    # تست 8: تبدیل امتیاز به سکه
    print("\n9️⃣ تست تبدیل امتیاز به سکه...")
    
    # اضافه کردن امتیاز
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET total_score = 500 WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    coins_before = economy.get_coins(test_user_id)
    success, coins_earned, error = economy.convert_score_to_coins(test_user_id, 200)
    coins_after = economy.get_coins(test_user_id)
    
    if not success:
        print(f"   ❌ تست ناموفق: {error}")
        return False
    
    expected_coins = 200 // 100  # 2 سکه
    
    print(f"   • امتیاز مصرف شده: 200")
    print(f"   • سکه دریافتی: {coins_earned}")
    print(f"   • سکه مورد انتظار: {expected_coins}")
    
    if coins_earned != expected_coins:
        print("   ❌ سکه اشتباه است!")
        return False
    
    print("   ✅ تست موفق")
    
    # تست 9: خرید قلب
    print("\n🔟 تست خرید قلب...")
    
    # اضافه کردن سکه کافی
    economy.add_coins(test_user_id, 300, "test")
    
    success, error = economy.buy_heart_increase(test_user_id)
    
    if not success:
        print(f"   ❌ تست ناموفق: {error}")
        return False
    
    stats = economy.get_economy_stats(test_user_id)
    print(f"   • قلب جدید: {stats['max_hearts']}")
    
    if stats['max_hearts'] != 11:  # 10 + 1
        print("   ❌ قلب اشتباه است!")
        return False
    
    print("   ✅ تست موفق")
    
    # تست 10: آمار اقتصادی
    print("\n1️⃣1️⃣ تست آمار اقتصادی...")
    stats = economy.get_economy_stats(test_user_id)
    
    print(f"   • سکه: {stats['coins']}")
    print(f"   • امتیاز: {stats['score']}")
    print(f"   • قلب: {stats['max_hearts']}")
    print(f"   • کارت‌های قابل ماینینگ: {stats['mineable_cards']}")
    print(f"   • ماینینگ روزانه: {stats['daily_mining']}")
    print("   ✅ تست موفق")
    
    print("\n" + "="*50)
    print("✅ همه تست‌ها موفق بودند!")
    print("="*50)
    
    return True

if __name__ == "__main__":
    try:
        success = test_economy()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ خطا در تست: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
