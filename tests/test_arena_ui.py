#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 Test Arena UI Integration
تست یکپارچگی Arena در UI
"""

import os
import sys
import sqlite3
from datetime import datetime

# تنظیم مسیر برای import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_core import DatabaseManager, GameLogic, Card, CardRarity
from arena_system import ArenaSystem, ArenaType, ARENAS


def test_arena_system():
    """تست سیستم Arena"""
    print("🧪 Testing Arena System...")
    
    # تست انتخاب رندوم Arena
    arena = ArenaSystem.select_random_arena()
    print(f"✅ Random arena selected: {arena.value}")
    
    # تست دریافت اطلاعات Arena
    info = ArenaSystem.get_arena_info(arena)
    print(f"✅ Arena info: {info['name']} - {info['description']}")
    
    # تست محاسبه Boost
    # کارت POWER_TYPE در Power Arena با انتخاب power
    final_value, has_boost = ArenaSystem.calculate_boost(
        card_type="POWER_TYPE",
        arena=ArenaType.POWER_ARENA,
        selected_stat="power",
        base_value=50
    )
    assert final_value == 51, f"Expected 51, got {final_value}"
    assert has_boost == True, "Expected boost to be True"
    print(f"✅ Boost calculation correct: 50 + 1 = {final_value}")
    
    # تست بدون Boost (stat اشتباه)
    final_value, has_boost = ArenaSystem.calculate_boost(
        card_type="POWER_TYPE",
        arena=ArenaType.POWER_ARENA,
        selected_stat="speed",  # stat اشتباه
        base_value=50
    )
    assert final_value == 50, f"Expected 50, got {final_value}"
    assert has_boost == False, "Expected boost to be False"
    print(f"✅ No boost when stat mismatch: {final_value}")
    
    # تست بدون Boost (arena اشتباه)
    final_value, has_boost = ArenaSystem.calculate_boost(
        card_type="POWER_TYPE",
        arena=ArenaType.SPEED_TRACK,  # arena اشتباه
        selected_stat="power",
        base_value=50
    )
    assert final_value == 50, f"Expected 50, got {final_value}"
    assert has_boost == False, "Expected boost to be False"
    print(f"✅ No boost when arena mismatch: {final_value}")
    
    print("✅ Arena System tests passed!\n")


def test_arena_in_battle():
    """تست Arena در سیستم نبرد"""
    print("🧪 Testing Arena in Battle System...")
    
    # استفاده از دیتابیس تست
    db_path = "test_arena.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DatabaseManager(db_path)
    
    # ایجاد جداول battle_states
    from battle_system_3rounds import create_battle_tables
    create_battle_tables(db_path)
    
    # اضافه کردن ستون card_type
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE cards ADD COLUMN card_type TEXT')
        conn.commit()
    except:
        pass
    conn.close()
    
    game = GameLogic(db, {
        'game_settings': {'daily_hearts': 5},
        'database': {'path': db_path}
    })
    
    # ایجاد کارت‌های تست با card_type
    card1 = Card(
        card_id="test_power_1",
        name="Power Hero",
        rarity=CardRarity.NORMAL,
        power=60,
        speed=40,
        iq=30,
        popularity=35,
        abilities=["Strong"],
        card_type="POWER_TYPE"
    )
    
    card2 = Card(
        card_id="test_speed_1",
        name="Speed Hero",
        rarity=CardRarity.NORMAL,
        power=35,
        speed=65,
        iq=40,
        popularity=30,
        abilities=["Fast"],
        card_type="SPEED_TYPE"
    )
    
    db.add_card(card1)
    db.add_card(card2)
    
    # ایجاد بازیکنان
    player1 = db.get_or_create_player(111, "player1", "Player One")
    player2 = db.get_or_create_player(222, "player2", "Player Two")
    
    # اضافه کردن کارت‌ها به بازیکنان
    db.add_card_to_player(111, "test_power_1")
    db.add_card_to_player(222, "test_speed_1")
    
    # ایجاد فایت
    fight_id = db.create_fight(111, 222, chat_id=None)
    
    # انتخاب کارت‌ها
    db.update_fight(fight_id, challenger_card_id="test_power_1")
    db.update_fight(fight_id, opponent_card_id="test_speed_1")
    
    # اولین resolve برای ایجاد battle_state
    result = game.resolve_pvp_fight(fight_id)
    assert result["success"] == True
    assert result["action"] == "waiting_for_stats"
    assert "arena" in result
    print(f"✅ Battle state created with arena: {result['arena']}")
    
    # انتخاب stats برای راوند 1
    db.update_fight(fight_id, challenger_stat="power", opponent_stat="speed")
    
    # حل راوند 1
    result = game.resolve_pvp_fight(fight_id)
    assert result["success"] == True
    assert "round_result" in result
    assert "arena" in result
    
    round_result = result["round_result"]
    print(f"✅ Round 1 resolved:")
    print(f"   Arena: {result['arena']}")
    print(f"   Challenger: {round_result['challenger_value']} + {round_result['challenger_boost']} = {round_result['challenger_total']}")
    print(f"   Opponent: {round_result['opponent_value']} + {round_result['opponent_boost']} = {round_result['opponent_total']}")
    print(f"   Winner: {round_result['winner']}")
    
    # پاکسازی
    os.remove(db_path)
    print("✅ Arena in Battle tests passed!\n")


def test_card_type_display():
    """تست نمایش Card Type"""
    print("🧪 Testing Card Type Display...")
    
    from arena_system import get_card_type_emoji, get_card_type_name
    
    # تست emoji
    assert get_card_type_emoji("POWER_TYPE") == "💪"
    assert get_card_type_emoji("SPEED_TYPE") == "⚡"
    assert get_card_type_emoji("IQ_TYPE") == "🧠"
    assert get_card_type_emoji("POPULARITY_TYPE") == "⭐"
    print("✅ Card type emojis correct")
    
    # تست نام فارسی
    assert get_card_type_name("POWER_TYPE") == "قدرت"
    assert get_card_type_name("SPEED_TYPE") == "سرعت"
    assert get_card_type_name("IQ_TYPE") == "هوش"
    assert get_card_type_name("POPULARITY_TYPE") == "محبوبیت"
    print("✅ Card type names correct")
    
    print("✅ Card Type Display tests passed!\n")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Arena UI Integration Tests")
    print("=" * 50)
    print()
    
    try:
        test_arena_system()
        test_arena_in_battle()
        test_card_type_display()
        
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
