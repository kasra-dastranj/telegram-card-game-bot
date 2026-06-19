#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 Test Optional Features
تست سیستم‌های Tier Decay, Rare Cards, Card Missions
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_core import DatabaseManager, Card, CardRarity
from tier_decay_system import TierDecaySystem
from rare_cards_system import RareCardsSystem, create_rare_cards_tables
from card_missions_system import CardMissionsSystem, create_missions_tables


def test_tier_decay():
    """تست Tier Decay System"""
    print("🧪 Testing Tier Decay System...")
    
    db_path = "test_optional.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    decay_system = TierDecaySystem(db)
    
    # ایجاد جدول progression (ساده‌سازی شده)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_progression (
            user_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            total_xp INTEGER DEFAULT 0,
            tier_points INTEGER DEFAULT 500,
            current_tier TEXT DEFAULT 'Silver',
            last_played_at TEXT,
            created_at TEXT
        )
    ''')
    
    # اضافه کردن بازیکن تست
    cursor.execute('''
        INSERT INTO player_progression
        (user_id, tier_points, current_tier, last_played_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        123,
        1500,  # Diamond
        'Diamond',
        (datetime.now() - timedelta(days=10)).isoformat(),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    
    # تست محاسبه Decay
    print("  Testing decay calculation...")
    
    # Mock get_player_progression
    class MockProgression:
        def __init__(self):
            self.tier_points = 1500
            self.current_tier = 'Diamond'
            self.last_played_at = (datetime.now() - timedelta(days=10)).isoformat()
    
    db.get_player_progression = lambda user_id: MockProgression()
    db.update_player_progression = lambda *args, **kwargs: None
    
    result = decay_system.apply_decay_to_player(123)
    
    assert result["success"] == True
    assert result["decayed"] == True
    assert result["days_inactive"] == 10
    print(f"  ✅ Decay calculated: {result['old_tp']} → {result['new_tp']} (-{result['decay_amount']})")
    
    # پاکسازی
    os.remove(db_path)
    print("✅ Tier Decay tests passed!\n")


def test_rare_cards():
    """تست Rare Cards System"""
    print("🧪 Testing Rare Cards System...")
    
    db_path = "test_optional.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    create_rare_cards_tables(db_path)
    rare_system = RareCardsSystem(db)
    
    # ایجاد کارت Rare
    print("  Creating rare card...")
    success = rare_system.create_rare_card(
        card_id="rare_test_1",
        name="Test Rare Hero",
        power=10,
        speed=10,
        iq=10,
        popularity=10,
        abilities=["Special"],
        price_coins=1000,
        limited_quantity=50
    )
    assert success == True
    print("  ✅ Rare card created")
    
    # دریافت اطلاعات
    print("  Getting rare card info...")
    info = rare_system.get_rare_card_info("rare_test_1")
    assert info is not None
    assert info["limited_quantity"] == 50
    assert info["total_issued"] == 0
    assert info["remaining"] == 50
    print(f"  ✅ Info retrieved: {info['remaining']}/{info['limited_quantity']} remaining")
    
    # بررسی موجودی
    can_issue = rare_system.can_issue_rare_card("rare_test_1")
    assert can_issue == True
    print("  ✅ Can issue: True")
    
    # پاکسازی
    os.remove(db_path)
    print("✅ Rare Cards tests passed!\n")


def test_card_missions():
    """تست Card Missions System"""
    print("🧪 Testing Card Missions System...")
    
    db_path = "test_optional.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    create_missions_tables(db_path)
    missions_system = CardMissionsSystem(db)
    
    # ایجاد ماموریت
    print("  Creating mission...")
    success = missions_system.create_mission(
        card_id="test_card_1",
        mission_type="total_wins",
        target=20
    )
    assert success == True
    print("  ✅ Mission created")
    
    # دریافت ماموریت
    print("  Getting mission...")
    mission = missions_system.get_mission("test_card_1")
    assert mission is not None
    assert mission["mission_type"] == "total_wins"
    assert mission["target"] == 20
    print(f"  ✅ Mission retrieved: {mission['description']}")
    
    # ایجاد جدول players برای تست progress
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        INSERT INTO players (user_id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
    ''', (456, "test_user", "Test", datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # دریافت پیشرفت
    print("  Getting mission progress...")
    progress = missions_system.get_player_mission_progress(456, "test_card_1")
    assert progress is not None
    assert progress["current_progress"] == 0
    assert progress["completed"] == False
    print(f"  ✅ Progress: {progress['current_progress']}/{progress['target']}")
    
    # بروزرسانی پیشرفت
    print("  Updating progress...")
    result = missions_system.update_mission_progress(456, "test_card_1", increment=5)
    assert result["success"] == True
    assert result["current_progress"] == 5
    print(f"  ✅ Progress updated: {result['current_progress']}/{result['target']}")
    
    # پاکسازی
    os.remove(db_path)
    print("✅ Card Missions tests passed!\n")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Optional Features Tests")
    print("=" * 50)
    print()
    
    try:
        test_tier_decay()
        test_rare_cards()
        test_card_missions()
        
        print("=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
