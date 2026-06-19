#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Migration: Optional Features (Tier Decay, Rare Cards, Missions)
"""

import sqlite3
import sys
from datetime import datetime


def migrate_optional_features(db_path: str = "game_bot.db"):
    """
    Migration کامل برای ویژگی‌های اختیاری
    
    شامل:
    1. Tier Decay (last_played_at)
    2. Rare Cards (tables)
    3. Card Missions (tables)
    """
    print(f"🔄 Starting Optional Features migration on {db_path}...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # ==================== TIER DECAY ====================
    print("\n📝 Tier Decay Migration...")
    
    try:
        cursor.execute('''
            ALTER TABLE player_progression
            ADD COLUMN last_played_at TEXT
        ''')
        print("✅ Added last_played_at column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  last_played_at already exists")
        elif "no such table" in str(e).lower():
            print("⚠️  player_progression table doesn't exist yet - will be created by phase2_migration")
        else:
            raise
    
    # تنظیم last_played_at برای بازیکنان موجود
    try:
        cursor.execute('''
            UPDATE player_progression
            SET last_played_at = ?
            WHERE last_played_at IS NULL
        ''', (datetime.now().isoformat(),))
        updated = cursor.rowcount
        if updated > 0:
            print(f"✅ Set last_played_at for {updated} players")
    except sqlite3.OperationalError:
        print("ℹ️  Skipping last_played_at update (table not ready)")
    
    # ==================== RARE CARDS ====================
    print("\n📝 Rare Cards Migration...")
    
    # جدول اطلاعات Rare Cards
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rare_cards_info (
            card_id TEXT PRIMARY KEY,
            price_coins INTEGER NOT NULL,
            limited_quantity INTEGER NOT NULL,
            total_issued INTEGER DEFAULT 0,
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    print("✅ Created rare_cards_info table")
    
    # جدول لاگ صدور
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rare_cards_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card_id TEXT NOT NULL,
            source TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id),
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    print("✅ Created rare_cards_log table")
    
    # ==================== CARD MISSIONS ====================
    print("\n📝 Card Missions Migration...")
    
    # جدول تعریف ماموریت‌ها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_missions (
            card_id TEXT PRIMARY KEY,
            mission_type TEXT NOT NULL,
            target INTEGER NOT NULL,
            target_card TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (card_id) REFERENCES cards (card_id)
        )
    ''')
    print("✅ Created card_missions table")
    
    # جدول پیشرفت بازیکنان
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_card_missions (
            user_id INTEGER,
            card_id TEXT,
            current_progress INTEGER DEFAULT 0,
            completed BOOLEAN DEFAULT 0,
            completed_at TEXT,
            reward_claimed BOOLEAN DEFAULT 0,
            reward_claimed_at TEXT,
            PRIMARY KEY (user_id, card_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id),
            FOREIGN KEY (card_id) REFERENCES card_missions (card_id)
        )
    ''')
    print("✅ Created player_card_missions table")
    
    # ==================== INDEXES ====================
    print("\n📝 Creating indexes...")
    
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rare_cards_log_user ON rare_cards_log(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rare_cards_log_card ON rare_cards_log(card_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_missions_user ON player_card_missions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_missions_completed ON player_card_missions(completed)')
        print("✅ Indexes created")
    except Exception as e:
        print(f"⚠️  Index creation warning: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Optional Features migration completed!")
    print("\n📊 Summary:")
    print("  ✅ Tier Decay: last_played_at column")
    print("  ✅ Rare Cards: 2 tables (info, log)")
    print("  ✅ Card Missions: 2 tables (missions, progress)")
    
    return True


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "game_bot.db"
    
    try:
        migrate_optional_features(db_path)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
