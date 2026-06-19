#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Migration: Tier Decay System
اضافه کردن ستون last_played_at
"""

import sqlite3
import sys
from datetime import datetime


def migrate_tier_decay(db_path: str = "game_bot.db"):
    """
    Migration برای Tier Decay
    
    اضافه می‌کند:
    - last_played_at به player_progression
    """
    print(f"🔄 Starting Tier Decay migration on {db_path}...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # اضافه کردن ستون last_played_at
        print("📝 Adding last_played_at column...")
        cursor.execute('''
            ALTER TABLE player_progression
            ADD COLUMN last_played_at TEXT
        ''')
        print("✅ Column added")
        
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  Column already exists")
        else:
            raise
    
    # تنظیم last_played_at برای بازیکنان موجود
    print("📝 Setting last_played_at for existing players...")
    cursor.execute('''
        UPDATE player_progression
        SET last_played_at = ?
        WHERE last_played_at IS NULL
    ''', (datetime.now().isoformat(),))
    
    updated = cursor.rowcount
    print(f"✅ Updated {updated} players")
    
    conn.commit()
    conn.close()
    
    print("✅ Tier Decay migration completed!")
    return True


if __name__ == "__main__":
    # دریافت مسیر دیتابیس از آرگومان یا استفاده از پیش‌فرض
    db_path = sys.argv[1] if len(sys.argv) > 1 else "game_bot.db"
    
    try:
        migrate_tier_decay(db_path)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
