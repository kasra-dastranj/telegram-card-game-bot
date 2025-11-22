#!/usr/bin/env python3
import sqlite3
import json

def migrate_database():
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    
    # ایجاد جدول card_cooldown_settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_cooldown_settings (
            card_id TEXT PRIMARY KEY,
            win_limit INTEGER DEFAULT 3,
            cooldown_hours INTEGER DEFAULT 24,
            is_enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # دریافت لیست کارت‌ها
    cursor.execute("SELECT card_id, rarity FROM cards")
    cards = cursor.fetchall()
    
    # تنظیم پیش‌فرض برای هر کارت
    for card_id, rarity in cards:
        # بررسی اینکه آیا تنظیمات قبلاً وجود دارد
        cursor.execute("SELECT card_id FROM card_cooldown_settings WHERE card_id = ?", (card_id,))
        if cursor.fetchone() is None:
            # تنظیم پیش‌فرض بر اساس rarity
            if rarity == 'legend':
                win_limit = 2
                cooldown_hours = 48
            elif rarity == 'epic':
                win_limit = 3
                cooldown_hours = 24
            else:  # normal
                win_limit = 5
                cooldown_hours = 12
                
            cursor.execute('''
                INSERT INTO card_cooldown_settings 
                (card_id, win_limit, cooldown_hours, is_enabled)
                VALUES (?, ?, ?, 1)
            ''', (card_id, win_limit, cooldown_hours))
    
    # ایجاد جدول card_wins
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
    
    # ایجاد index برای بهبود عملکرد
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_card_wins_user_card 
        ON card_wins(user_id, card_id)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_card_wins_date 
        ON card_wins(win_date)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Migration completed successfully!")
    print("✅ card_cooldown_settings table created")
    print("✅ card_wins table created")
    print(f"✅ Default settings added for {len(cards)} cards")

if __name__ == "__main__":
    migrate_database()