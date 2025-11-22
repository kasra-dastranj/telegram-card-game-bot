#!/usr/bin/env python3
import sqlite3

def simple_fix():
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    
    try:
        # حذف جداول موقت اگر وجود دارن
        cursor.execute("DROP TABLE IF EXISTS card_cooldown_settings_new")
        cursor.execute("DROP TABLE IF EXISTS card_cooldown_settings_backup")
        
        # تغییر نام ستون enabled به is_enabled
        cursor.execute("ALTER TABLE card_cooldown_settings RENAME COLUMN enabled TO is_enabled")
        
        # ایجاد جدول card_wins
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_wins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_id TEXT NOT NULL,
                win_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        print("✅ Database fixed successfully!")
        
        # بررسی نتیجه
        cursor.execute("PRAGMA table_info(card_cooldown_settings)")
        columns = cursor.fetchall()
        print("New columns:", [col[1] for col in columns])
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    simple_fix()