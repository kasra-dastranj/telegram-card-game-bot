#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration برای Economy System
"""

import sqlite3
import os
from datetime import datetime

def migrate_economy(db_path: str = 'game_bot.db'):
    """اضافه کردن ستون‌های Economy به دیتابیس"""
    
    print(f"🔄 شروع Migration Economy System...")
    print(f"📁 دیتابیس: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ دیتابیس پیدا نشد: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. اضافه کردن last_mining_claim
        print("\n1️⃣ اضافه کردن ستون last_mining_claim...")
        try:
            cursor.execute('''
                ALTER TABLE players 
                ADD COLUMN last_mining_claim DATETIME
            ''')
            print("   ✅ ستون last_mining_claim اضافه شد")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("   ℹ️ ستون last_mining_claim از قبل وجود دارد")
            else:
                raise
        
        # 2. اضافه کردن max_hearts
        print("\n2️⃣ اضافه کردن ستون max_hearts...")
        try:
            cursor.execute('''
                ALTER TABLE players 
                ADD COLUMN max_hearts INTEGER DEFAULT 10
            ''')
            print("   ✅ ستون max_hearts اضافه شد")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("   ℹ️ ستون max_hearts از قبل وجود دارد")
            else:
                raise
        
        # 3. بروزرسانی max_hearts برای بازیکنان موجود (اگر NULL است)
        print("\n3️⃣ بروزرسانی max_hearts برای بازیکنان موجود...")
        cursor.execute('''
            UPDATE players 
            SET max_hearts = 10 
            WHERE max_hearts IS NULL
        ''')
        updated = cursor.rowcount
        print(f"   ✅ {updated} بازیکن بروزرسانی شد")
        
        # 4. بررسی ستون coins
        print("\n4️⃣ بررسی ستون coins...")
        cursor.execute("PRAGMA table_info(players)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'coins' not in columns:
            print("   ⚠️ ستون coins وجود ندارد! اضافه می‌شود...")
            cursor.execute('''
                ALTER TABLE players 
                ADD COLUMN coins INTEGER DEFAULT 0
            ''')
            print("   ✅ ستون coins اضافه شد")
        else:
            print("   ✅ ستون coins موجود است")
        
        conn.commit()
        
        print("\n" + "="*50)
        print("✅ Migration Economy System موفق بود!")
        print("="*50)
        
        # نمایش ساختار جدول
        print("\n📊 ساختار جدول players:")
        cursor.execute("PRAGMA table_info(players)")
        for row in cursor.fetchall():
            print(f"   • {row[1]} ({row[2]})")
        
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
    success_test = migrate_economy('game_bot_test.db')
    
    if success_test:
        print("\n" + "="*50)
        print("✅ Migration تست موفق بود!")
        print("="*50)
    
    # دیتابیس اصلی (با تایید)
    print("\n" + "="*50)
    response = input("آیا می‌خواهید Migration را روی دیتابیس اصلی اجرا کنید؟ (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        print("\n🔄 Migration روی دیتابیس اصلی...")
        success_main = migrate_economy('game_bot.db')
        
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
