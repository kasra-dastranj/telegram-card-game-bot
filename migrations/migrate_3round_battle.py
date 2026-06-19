#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 Migration Script: 3-Round Battle System
اضافه کردن جداول مورد نیاز برای سیستم ۳ راوندی
"""

import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_3round_battle(db_path: str = "game_bot.db"):
    """
    اضافه کردن جداول سیستم ۳ راوندی
    
    Args:
        db_path: مسیر دیتابیس
    """
    logger.info(f"🔄 شروع Migration: 3-Round Battle System")
    logger.info(f"📁 دیتابیس: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # ۱. ایجاد جدول battle_states
        logger.info("🏗️ ایجاد جدول battle_states...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS battle_states (
                fight_id TEXT PRIMARY KEY,
                challenger_id INTEGER NOT NULL,
                opponent_id INTEGER NOT NULL,
                challenger_card_id TEXT NOT NULL,
                opponent_card_id TEXT NOT NULL,
                arena TEXT NOT NULL,
                current_round INTEGER NOT NULL DEFAULT 1,
                challenger_rounds_won INTEGER NOT NULL DEFAULT 0,
                opponent_rounds_won INTEGER NOT NULL DEFAULT 0,
                challenger_used_stats TEXT NOT NULL DEFAULT '[]',
                opponent_used_stats TEXT NOT NULL DEFAULT '[]',
                challenger_current_stats TEXT NOT NULL,
                opponent_current_stats TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'round_1',
                created_at TEXT NOT NULL,
                FOREIGN KEY (fight_id) REFERENCES active_fights (fight_id)
            )
        ''')
        logger.info("✅ جدول battle_states ایجاد شد")
        
        # ۲. ایجاد جدول round_history
        logger.info("🏗️ ایجاد جدول round_history...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS round_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fight_id TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                challenger_stat TEXT NOT NULL,
                opponent_stat TEXT NOT NULL,
                challenger_value INTEGER NOT NULL,
                opponent_value INTEGER NOT NULL,
                challenger_boost INTEGER NOT NULL DEFAULT 0,
                opponent_boost INTEGER NOT NULL DEFAULT 0,
                challenger_total INTEGER NOT NULL,
                opponent_total INTEGER NOT NULL,
                winner TEXT,
                challenger_reduction INTEGER NOT NULL DEFAULT 0,
                opponent_reduction INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (fight_id) REFERENCES active_fights (fight_id)
            )
        ''')
        logger.info("✅ جدول round_history ایجاد شد")
        
        # ۳. بررسی وجود ستون arena در active_fights
        logger.info("🔍 بررسی ستون arena در active_fights...")
        cursor.execute("PRAGMA table_info(active_fights)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'arena' not in columns:
            logger.info("➕ اضافه کردن ستون arena به active_fights...")
            cursor.execute('''
                ALTER TABLE active_fights
                ADD COLUMN arena TEXT DEFAULT NULL
            ''')
            logger.info("✅ ستون arena اضافه شد")
        else:
            logger.info("ℹ️ ستون arena از قبل وجود دارد")
        
        # ۴. Commit تغییرات
        conn.commit()
        logger.info("✅ Migration با موفقیت کامل شد!")
        
        # ۵. نمایش آمار
        cursor.execute("SELECT COUNT(*) FROM battle_states")
        battle_states_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM round_history")
        round_history_count = cursor.fetchone()[0]
        
        logger.info(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 آمار Migration:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ جدول battle_states: {battle_states_count} رکورد
✅ جدول round_history: {round_history_count} رکورد
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """)
        
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ خطا در Migration: {e}", exc_info=True)
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else "game_bot.db"
    
    print(f"""
╔══════════════════════════════════════════╗
║  🔄 Migration: 3-Round Battle System    ║
╚══════════════════════════════════════════╝

دیتابیس: {db_path}

این اسکریپت جداول زیر را اضافه می‌کند:
  1. battle_states - وضعیت بازی‌های ۳ راوندی
  2. round_history - تاریخچه راوندها
  3. ستون arena در active_fights

آماده برای شروع؟
    """)
    
    input("Enter را بزنید تا ادامه دهید...")
    
    success = migrate_3round_battle(db_path)
    
    if success:
        print("\n✅ Migration موفقیت‌آمیز بود!")
        print("\n🎮 حالا می‌توانید سیستم ۳ راوندی را استفاده کنید.")
    else:
        print("\n❌ Migration ناموفق بود. لطفاً لاگ‌ها را بررسی کنید.")
        sys.exit(1)
