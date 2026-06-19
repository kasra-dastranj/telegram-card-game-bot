#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: Card Stories System
اضافه کردن سیستم داستان سه‌مرحله‌ای برای کارت‌ها
"""

import sqlite3
import sys

def migrate_card_stories(db_path='game_bot.db'):
    """اضافه کردن ستون‌های story به جدول cards"""
    
    print("=" * 60)
    print("🔄 Migration: Card Stories System")
    print("=" * 60)
    print(f"📁 دیتابیس: {db_path}")
    print()
    print("این migration ستون‌های زیر را به جدول cards اضافه می‌کند:")
    print("1. story_normal - داستان مرحله Normal")
    print("2. story_epic - داستان مرحله Epic (باز می‌شود بعد از Fusion)")
    print("3. story_legend - داستان مرحله Legend (باز می‌شود بعد از Fusion)")
    print()
    
    input("Enter را بزنید تا ادامه دهید...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # بررسی وجود ستون‌ها
        cursor.execute("PRAGMA table_info(cards)")
        columns = [col[1] for col in cursor.fetchall()]
        
        migrations_needed = []
        
        if 'story_normal' not in columns:
            migrations_needed.append('story_normal')
        if 'story_epic' not in columns:
            migrations_needed.append('story_epic')
        if 'story_legend' not in columns:
            migrations_needed.append('story_legend')
        
        if not migrations_needed:
            print("✅ همه ستون‌های story از قبل وجود دارند!")
            conn.close()
            return True
        
        print(f"\n🔄 در حال اضافه کردن {len(migrations_needed)} ستون...")
        
        # اضافه کردن ستون‌ها
        for column in migrations_needed:
            try:
                cursor.execute(f'''
                    ALTER TABLE cards 
                    ADD COLUMN {column} TEXT DEFAULT NULL
                ''')
                print(f"✅ ستون {column} اضافه شد")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"⚠️ ستون {column} از قبل وجود دارد")
                else:
                    raise
        
        conn.commit()
        
        print("\n" + "=" * 60)
        print("✅ Migration با موفقیت انجام شد!")
        print("=" * 60)
        print()
        print("📝 نکات:")
        print("• هر کارت می‌تواند 3 بخش داستان داشته باشد")
        print("• story_normal: همیشه در دسترس است")
        print("• story_epic: بعد از Fusion به Epic باز می‌شود")
        print("• story_legend: بعد از Fusion به Legend باز می‌شود")
        print("• می‌توانید از Web Admin Panel داستان‌ها را مدیریت کنید")
        print()
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ خطا در migration: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'game_bot.db'
    success = migrate_card_stories(db_path)
    sys.exit(0 if success else 1)
