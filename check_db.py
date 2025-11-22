#!/usr/bin/env python3
import sqlite3

def check_database():
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    
    # بررسی جداول موجود
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables:", [t[0] for t in tables])
    
    # بررسی جدول card_cooldown_settings
    try:
        cursor.execute("SELECT * FROM card_cooldown_settings LIMIT 1")
        print("✅ card_cooldown_settings table exists")
    except sqlite3.OperationalError:
        print("❌ card_cooldown_settings table missing")
        
    # بررسی جدول card_wins
    try:
        cursor.execute("SELECT * FROM card_wins LIMIT 1")
        print("✅ card_wins table exists")
    except sqlite3.OperationalError:
        print("❌ card_wins table missing")
        
    # بررسی ستون hearts در جدول players
    try:
        cursor.execute("PRAGMA table_info(players)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        print("Players table columns:", column_names)
        if 'hearts' in column_names:
            print("✅ hearts column exists")
        else:
            print("❌ hearts column missing")
    except sqlite3.OperationalError as e:
        print("Error checking players table:", e)
    
    conn.close()

if __name__ == "__main__":
    check_database()