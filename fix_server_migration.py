#!/usr/bin/env python3
import sqlite3

def fix_database():
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    
    try:
        # بررسی ستون‌های موجود
        cursor.execute("PRAGMA table_info(card_cooldown_settings)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        print("Current columns:", column_names)
        
        # اگر enabled وجود داره ولی is_enabled نداره، تغییر نام بده
        if 'enabled' in column_names and 'is_enabled' not in column_names:
            print("Renaming 'enabled' to 'is_enabled'...")
            
            # ایجاد جدول جدید با ستون درست
            cursor.execute('''
                CREATE TABLE card_cooldown_settings_new (
                    card_id TEXT PRIMARY KEY,
                    win_limit INTEGER DEFAULT 3,
                    cooldown_hours INTEGER DEFAULT 24,
                    is_enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # کپی کردن داده‌ها
            cursor.execute('''
                INSERT INTO card_cooldown_settings_new 
                (card_id, win_limit, cooldown_hours, is_enabled, created_at, updated_at)
                SELECT card_id, win_limit, cooldown_hours, enabled, created_at, updated_at
                FROM card_cooldown_settings
            ''')
            
            # حذف جدول قدیمی و تغییر نام جدول جدید
            cursor.execute('DROP TABLE card_cooldown_settings')
            cursor.execute('ALTER TABLE card_cooldown_settings_new RENAME TO card_cooldown_settings')
            
            print("✅ Column renamed successfully!")
        
        # ایجاد جدول card_wins اگر وجود نداره
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_wins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_id TEXT NOT NULL,
                win_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES players(user_id),
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            )
        ''')
        
        # ایجاد index ها
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_card_wins_user_card 
            ON card_wins(user_id, card_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_card_wins_date 
            ON card_wins(win_date)
        ''')
        
        print("✅ card_wins table created!")
        
        conn.commit()
        print("✅ Database fixed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()