#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست Fusion UI
"""

import os
import sys

# تنظیم ENV_FILE برای تست
os.environ['ENV_FILE'] = '.env.test'

from game_core import DatabaseManager, CardRarity
from fusion_system import FusionSystem

def test_fusion_ui():
    """تست سیستم Fusion"""
    print("🧪 شروع تست Fusion UI...")
    
    # اتصال به دیتابیس تست
    db = DatabaseManager(db_path='game_bot_test.db')
    fusion = FusionSystem(db)
    
    # ایجاد یک بازیکن تست
    test_user_id = 999999
    
    # پاک کردن کارت‌های قبلی
    import sqlite3
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM player_cards WHERE user_id = ?', (test_user_id,))
    conn.commit()
    conn.close()
    
    print(f"\n1️⃣ ایجاد بازیکن تست (user_id={test_user_id})...")
    player = db.get_or_create_player(test_user_id, "test_user", "Test User")
    print(f"   ✅ بازیکن ایجاد شد")
    
    # اضافه کردن 3 کارت Normal
    print("\n2️⃣ اضافه کردن 3 کارت Normal...")
    all_cards = db.get_all_cards()
    normal_cards = [c for c in all_cards if c.rarity == CardRarity.NORMAL][:3]
    
    if len(normal_cards) < 3:
        print("   ❌ کارت Normal کافی در دیتابیس وجود ندارد!")
        return False
    
    for card in normal_cards:
        db.add_card_to_player(test_user_id, card.card_id)
        print(f"   ✅ {card.name} اضافه شد")
    
    # بررسی امکان Fusion
    print("\n3️⃣ بررسی امکان Fusion...")
    can_fuse, available_cards = fusion.can_fuse_to_epic(test_user_id)
    print(f"   • امکان Fusion: {can_fuse}")
    print(f"   • تعداد کارت‌های Normal: {len(available_cards)}")
    
    if not can_fuse:
        print("   ❌ امکان Fusion وجود ندارد!")
        return False
    
    print("   ✅ امکان Fusion وجود دارد")
    
    # انتخاب 3 کارت برای Fusion
    print("\n4️⃣ انتخاب 3 کارت برای Fusion...")
    selected_cards = [c.card_id for c in available_cards[:3]]
    selected_card_id = selected_cards[0]  # کارت اول ارتقا می‌یابد
    
    print(f"   • کارت‌های انتخاب شده: {[c.name for c in available_cards[:3]]}")
    print(f"   • کارت ارتقا یافته: {available_cards[0].name}")
    
    # اعتبارسنجی
    print("\n5️⃣ اعتبارسنجی...")
    is_valid, error = fusion.validate_fusion_cards(
        test_user_id, 
        selected_cards, 
        selected_card_id, 
        CardRarity.NORMAL
    )
    
    if not is_valid:
        print(f"   ❌ اعتبارسنجی ناموفق: {error}")
        return False
    
    print("   ✅ اعتبارسنجی موفق")
    
    # انجام Fusion
    print("\n6️⃣ انجام Fusion...")
    result = fusion.fuse_to_epic(test_user_id, selected_cards, selected_card_id)
    
    if not result.success:
        print(f"   ❌ Fusion ناموفق: {result.error}")
        return False
    
    print("   ✅ Fusion موفق!")
    print(f"   • کارت ارتقا یافته: {result.upgraded_card.name} ({result.upgraded_card.rarity.value})")
    print(f"   • کارت‌های مصرف شده: {[c.name for c in result.consumed_cards]}")
    
    # بررسی نتیجه
    print("\n7️⃣ بررسی نتیجه...")
    player_cards = db.get_player_cards(test_user_id)
    epic_cards = [c for c in player_cards if c.rarity == CardRarity.EPIC]
    
    print(f"   • تعداد کارت‌های Epic: {len(epic_cards)}")
    
    if len(epic_cards) != 1:
        print(f"   ❌ تعداد کارت‌های Epic اشتباه است! (انتظار: 1, واقعی: {len(epic_cards)})")
        return False
    
    if epic_cards[0].card_id != selected_card_id:
        print(f"   ❌ کارت Epic اشتباه است!")
        return False
    
    print("   ✅ نتیجه صحیح است")
    
    # بررسی fusion_log
    print("\n8️⃣ بررسی fusion_log...")
    history = fusion.get_fusion_history(test_user_id, limit=1)
    
    if len(history) == 0:
        print("   ❌ هیچ رکوردی در fusion_log ثبت نشده!")
        return False
    
    log = history[0]
    print(f"   • نوع Fusion: {log['fusion_type']}")
    print(f"   • کارت ارتقا یافته: {log['upgraded_card_id']}")
    print(f"   • نتیجه: {log['result_rarity']}")
    print("   ✅ لاگ صحیح ثبت شده")
    
    # آمار Fusion
    print("\n9️⃣ بررسی آمار Fusion...")
    stats = fusion.get_fusion_stats(test_user_id)
    print(f"   • تعداد کل Fusion: {stats['total_fusions']}")
    print(f"   • Normal→Epic: {stats['normal_to_epic']}")
    print(f"   • Epic→Legend: {stats['epic_to_legend']}")
    
    if stats['total_fusions'] != 1 or stats['normal_to_epic'] != 1:
        print("   ❌ آمار اشتباه است!")
        return False
    
    print("   ✅ آمار صحیح است")
    
    print("\n" + "="*50)
    print("✅ همه تست‌ها موفق بودند!")
    print("="*50)
    
    return True

if __name__ == "__main__":
    try:
        success = test_fusion_ui()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ خطا در تست: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
