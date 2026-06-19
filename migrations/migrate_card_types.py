#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration برای Card Types & Arenas
"""

import sqlite3
import os
from datetime import datetime

def migrate_card_types(db_path: str = 'game_bot.db'):
    """اضافه کردن card_type به کارت‌ها و تخصیص خودکار"""
    
    print(f"🔄 شروع Migration Card Types...")
    print(f"📁 دیتابیس: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ دیتابیس پیدا نشد: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. اضافه کردن ستون card_type
        print("\n1️⃣ اضافه کردن ستون card_type...")
        try:
            cursor.execute('''
                ALTER TABLE cards 
                ADD COLUMN card_type TEXT
            ''')
            print("   ✅ ستون card_type اضافه شد")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("   ℹ️ ستون card_type از قبل وجود دارد")
            else:
                raise
        
        # 2. تخصیص card_type به کارت‌های موجود
        print("\n2️⃣ تخصیص card_type به کارت‌های موجود...")
        
        # دریافت همه کارت‌ها
        cursor.execute('''
            SELECT card_id, name, power, speed, iq, popularity 
            FROM cards
        ''')
        
        cards = cursor.fetchall()
        print(f"   • تعداد کارت‌ها: {len(cards)}")
        
        updated = 0
        for card in cards:
            card_id, name, power, speed, iq, popularity = card
            
            # محاسبه بالاترین stat
            stats = {
                'power': power,
                'speed': speed,
                'iq': iq,
                'popularity': popularity
            }
            
            max_stat = max(stats, key=stats.get)
            
            # تعیین card_type
            type_mapping = {
                'power': 'POWER_TYPE',
                'speed': 'SPEED_TYPE',
                'iq': 'IQ_TYPE',
                'popularity': 'POPULARITY_TYPE'
            }
            
            card_type = type_mapping[max_stat]
            
            # بروزرسانی
            cursor.execute('''
                UPDATE cards 
                SET card_type = ?
                WHERE card_id = ?
            ''', (card_type, card_id))
            
            updated += 1
            
            if updated <= 5:  # نمایش 5 کارت اول
                print(f"   • {name}: {max_stat.upper()} → {card_type}")
        
        print(f"   ✅ {updated} کارت بروزرسانی شد")
        
        conn.commit()
        
        # 3. بررسی نتیجه
        print("\n3️⃣ بررسی توزیع card_type...")
        cursor.execute('''
            SELECT card_type, COUNT(*) 
            FROM cards 
            GROUP BY card_type
        ''')
        
        distribution = cursor.fetchall()
        for card_type, count in distribution:
            print(f"   • {card_type}: {count} کارت")
        
        print("\n" + "="*50)
        print("✅ Migration Card Types موفق بود!")
        print("="*50)
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ خطا در Migration: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    # دیتابیس تست
    print("🧪 Migration روی دیتابیس تست...")
    success_test = migrate_card_types('game_bot_test.db')
    
    if success_test:
        print("\n" + "="*50)
        print("✅ Migration تست موفق بود!")
        print("="*50)
    
    # دیتابیس اصلی (با تایید)
    print("\n" + "="*50)
    response = input("آیا می‌خواهید Migration را روی دیتابیس اصلی اجرا کنید؟ (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        print("\n🔄 Migration روی دیتابیس اصلی...")
        success_main = migrate_card_types('game_bot.db')
        
        if success_main:
            print("\n" + "="*50)
            print("✅ Migration اصلی موفق بود!")
            print("="*50)
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("\n⏭️ Migration اصلی لغو شد")
        sys.exit(0 if success_test else 1)
