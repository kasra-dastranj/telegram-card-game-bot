#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 تست سیستم مبارزه ۳ راوندی
"""

import sys
import sqlite3
from game_core import DatabaseManager, GameLogic

def test_3round_battle():
    """تست سریع سیستم ۳ راوندی"""
    
    print("🧪 تست سیستم مبارزه ۳ راوندی\n")
    
    # استفاده از دیتابیس تست
    db = DatabaseManager("game_bot_test.db")
    game = GameLogic(db)
    
    # بررسی وجود جداول
    conn = sqlite3.connect("game_bot_test.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='battle_states'")
    if cursor.fetchone():
        print("✅ جدول battle_states وجود دارد")
    else:
        print("❌ جدول battle_states وجود ندارد")
        return False
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='round_history'")
    if cursor.fetchone():
        print("✅ جدول round_history وجود دارد")
    else:
        print("❌ جدول round_history وجود ندارد")
        return False
    
    conn.close()
    
    print("\n✅ همه جداول موجود هستند!")
    print("\n📝 برای تست کامل، باید از ربات تلگرام استفاده کنید.")
    
    return True

if __name__ == "__main__":
    success = test_3round_battle()
    sys.exit(0 if success else 1)
