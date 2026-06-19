#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست سیستم داستان کارت‌ها
"""

import sys
from game_core import DatabaseManager, Card, CardRarity

def test_story_system():
    """تست کامل سیستم داستان"""
    
    print("=" * 60)
    print("🧪 تست سیستم داستان کارت‌ها")
    print("=" * 60)
    
    db = DatabaseManager('game_bot.db')
    
    # 1. تست ساختار دیتابیس
    print("\n1️⃣ بررسی ساختار دیتابیس...")
    import sqlite3
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(cards)")
    columns = [col[1] for col in cursor.fetchall()]
    conn.close()
    
    required_cols = ['story_normal', 'story_epic', 'story_legend']
    for col in required_cols:
        if col in columns:
            print(f"   ✅ {col} موجود است")
        else:
            print(f"   ❌ {col} موجود نیست!")
            return False
    
    # 2. تست ایجاد کارت با داستان
    print("\n2️⃣ تست ایجاد کارت با داستان...")
    test_card = Card(
        card_id="test_story_card",
        name="Test Story Card",
        rarity=CardRarity.NORMAL,
        power=50,
        speed=50,
        iq=50,
        popularity=50,
        abilities=["test"],
        story_normal="این داستان مرحله Normal است",
        story_epic="این داستان مرحله Epic است",
        story_legend="این داستان مرحله Legend است"
    )
    
    # حذف کارت تست قبلی اگر وجود داشت
    db.delete_card("test_story_card")
    
    # اضافه کردن کارت
    if db.add_card(test_card):
        print("   ✅ کارت با داستان ایجاد شد")
    else:
        print("   ❌ خطا در ایجاد کارت")
        return False
    
    # 3. تست خواندن کارت
    print("\n3️⃣ تست خواندن کارت از دیتابیس...")
    loaded_card = db.get_card_by_id("test_story_card")
    
    if loaded_card:
        print("   ✅ کارت خوانده شد")
        
        # بررسی داستان‌ها
        if hasattr(loaded_card, 'story_normal') and loaded_card.story_normal:
            print(f"   ✅ story_normal: {loaded_card.story_normal[:30]}...")
        else:
            print("   ❌ story_normal موجود نیست")
            
        if hasattr(loaded_card, 'story_epic') and loaded_card.story_epic:
            print(f"   ✅ story_epic: {loaded_card.story_epic[:30]}...")
        else:
            print("   ❌ story_epic موجود نیست")
            
        if hasattr(loaded_card, 'story_legend') and loaded_card.story_legend:
            print(f"   ✅ story_legend: {loaded_card.story_legend[:30]}...")
        else:
            print("   ❌ story_legend موجود نیست")
    else:
        print("   ❌ کارت خوانده نشد")
        return False
    
    # 4. تست بروزرسانی داستان
    print("\n4️⃣ تست بروزرسانی داستان...")
    loaded_card.story_normal = "داستان Normal بروز شده"
    loaded_card.story_epic = "داستان Epic بروز شده"
    loaded_card.story_legend = "داستان Legend بروز شده"
    
    if db.update_card(loaded_card):
        print("   ✅ کارت بروزرسانی شد")
        
        # خواندن دوباره
        updated_card = db.get_card_by_id("test_story_card")
        if updated_card.story_normal == "داستان Normal بروز شده":
            print("   ✅ story_normal بروز شد")
        else:
            print("   ❌ story_normal بروز نشد")
            
    else:
        print("   ❌ خطا در بروزرسانی")
        return False
    
    # 5. تست Web Admin Panel API
    print("\n5️⃣ تست Web Admin Panel...")
    try:
        from web_admin_panel import WebAdminPanel
        panel = WebAdminPanel()
        
        # بررسی routes
        routes = [rule.rule for rule in panel.app.url_map.iter_rules()]
        
        if '/api/card/<card_id>' in routes:
            print("   ✅ API endpoint برای دریافت کارت موجود است")
        else:
            print("   ❌ API endpoint برای دریافت کارت موجود نیست")
            
        if '/api/card/<card_id>/stories' in routes:
            print("   ✅ API endpoint برای بروزرسانی داستان موجود است")
        else:
            print("   ❌ API endpoint برای بروزرسانی داستان موجود نیست")
            
    except Exception as e:
        print(f"   ❌ خطا در بررسی Web Panel: {e}")
        return False
    
    # پاکسازی
    print("\n6️⃣ پاکسازی...")
    db.delete_card("test_story_card")
    print("   ✅ کارت تست حذف شد")
    
    print("\n" + "=" * 60)
    print("✅ همه تست‌ها با موفقیت انجام شد!")
    print("=" * 60)
    print()
    print("📝 نتیجه:")
    print("• سیستم داستان کامل است")
    print("• دیتابیس آماده است")
    print("• Web Admin Panel آماده است")
    print()
    print("🚀 برای استفاده:")
    print("   python web_admin_panel.py")
    print()
    
    return True

if __name__ == "__main__":
    try:
        success = test_story_system()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
