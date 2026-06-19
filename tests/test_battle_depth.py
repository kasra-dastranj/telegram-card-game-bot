#!/usr/bin/env python3
"""
تست سیستم عمق بازی — فاز ۱
تست‌ها: Type Counter, Arena Boost, Stat Reduction, Abilities
"""

import sys
sys.path.insert(0, '.')

from game_core import Card, CardRarity
from battle_system_3rounds import (
    BattleSystem3Rounds, BattleState, ARENAS,
    TYPE_COUNTER, TYPE_COUNTER_BONUS, ABILITIES,
    get_card_ability
)

# ==================== ساخت کارت‌های تست ====================

card_power = Card(
    card_id="test_power",
    name="Heisenberg",
    rarity=CardRarity.EPIC,
    power=85, speed=40, iq=70, popularity=50,
    abilities=["boost_15"],
    card_type="POWER_TYPE"
)

card_speed = Card(
    card_id="test_speed",
    name="Flash",
    rarity=CardRarity.LEGEND,
    power=30, speed=95, iq=45, popularity=60,
    abilities=["sabotage_10"],
    card_type="SPEED_TYPE"
)

card_iq = Card(
    card_id="test_iq",
    name="Sherlock",
    rarity=CardRarity.RARE,
    power=35, speed=50, iq=92, popularity=55,
    abilities=["copy"],
    card_type="IQ_TYPE"
)

card_popularity = Card(
    card_id="test_pop",
    name="Ronaldo",
    rarity=CardRarity.NORMAL,
    power=60, speed=70, iq=40, popularity=98,
    abilities=[],
    card_type="POPULARITY_TYPE"
)


def test_type_counter():
    """تست سیستم برتری تایپ"""
    print("\n" + "="*50)
    print("🔺 تست Type Counter")
    print("="*50)
    
    # POWER > SPEED
    assert TYPE_COUNTER["POWER_TYPE"] == "SPEED_TYPE", "POWER should counter SPEED"
    print("✅ POWER > SPEED")
    
    # SPEED > IQ
    assert TYPE_COUNTER["SPEED_TYPE"] == "IQ_TYPE", "SPEED should counter IQ"
    print("✅ SPEED > IQ")
    
    # IQ > POPULARITY
    assert TYPE_COUNTER["IQ_TYPE"] == "POPULARITY_TYPE", "IQ should counter POPULARITY"
    print("✅ IQ > POPULARITY")
    
    # POPULARITY > POWER
    assert TYPE_COUNTER["POPULARITY_TYPE"] == "POWER_TYPE", "POPULARITY should counter POWER"
    print("✅ POPULARITY > POWER")
    
    # بونوس = 10
    assert TYPE_COUNTER_BONUS == 10
    print(f"✅ بونوس برتری: +{TYPE_COUNTER_BONUS}")
    
    print("\n📊 مثال: Heisenberg (POWER) vs Flash (SPEED)")
    print(f"   Heisenberg counter Flash = True → +{TYPE_COUNTER_BONUS}")
    print(f"   Flash counter Heisenberg = False → +0")


def test_arena_boost():
    """تست بوست زمین"""
    print("\n" + "="*50)
    print("🔥 تست Arena Boost (+8)")
    print("="*50)
    
    # چک کنیم همه arena‌ها boost_amount=8 دارن
    for arena_id, info in ARENAS.items():
        assert info["boost_amount"] == 8, f"{arena_id} boost should be 8"
        print(f"✅ {info['emoji']} {info['name_fa']}: boost_stat={info['boost_stat']}, amount=+{info['boost_amount']}")
    
    # تست calculate_boost
    class FakeDB:
        pass
    
    battle = BattleSystem3Rounds(FakeDB())
    
    # Heisenberg (POWER_TYPE) در power_arena با stat power → باید +8 بگیره
    boost = battle.calculate_boost(card_power, "power_arena", "power")
    assert boost == 8, f"Expected 8, got {boost}"
    print(f"\n✅ Heisenberg (POWER) در عرصه قدرت + stat power = +{boost}")
    
    # Heisenberg (POWER_TYPE) در power_arena با stat speed → 0
    boost = battle.calculate_boost(card_power, "power_arena", "speed")
    assert boost == 0, f"Expected 0, got {boost}"
    print(f"✅ Heisenberg (POWER) در عرصه قدرت + stat speed = +{boost}")
    
    # Flash (SPEED_TYPE) در speed_track با stat speed → +8
    boost = battle.calculate_boost(card_speed, "speed_track", "speed")
    assert boost == 8, f"Expected 8, got {boost}"
    print(f"✅ Flash (SPEED) در پیست سرعت + stat speed = +{boost}")
    
    # Flash (SPEED_TYPE) در power_arena → 0
    boost = battle.calculate_boost(card_speed, "power_arena", "power")
    assert boost == 0
    print(f"✅ Flash (SPEED) در عرصه قدرت + stat power = +{boost}")


def test_ability_mapping():
    """تست نگاشت ابیلیتی به کارت"""
    print("\n" + "="*50)
    print("🪄 تست Ability Mapping")
    print("="*50)
    
    # Epic → boost_15
    ab = get_card_ability(card_power)
    assert ab == "boost_15", f"Epic card should get boost_15, got {ab}"
    print(f"✅ {card_power.name} (Epic) → {ab} ({ABILITIES[ab]['name_fa']})")
    
    # Legend → sabotage_10
    ab = get_card_ability(card_speed)
    assert ab == "sabotage_10", f"Legend card should get sabotage_10, got {ab}"
    print(f"✅ {card_speed.name} (Legend) → {ab} ({ABILITIES[ab]['name_fa']})")
    
    # Rare → copy
    ab = get_card_ability(card_iq)
    assert ab == "copy", f"Rare card should get copy, got {ab}"
    print(f"✅ {card_iq.name} (Rare) → {ab} ({ABILITIES[ab]['name_fa']})")
    
    # Normal → None (ابیلیتی نداره) — ولی fallback به card_type
    ab = get_card_ability(card_popularity)
    print(f"✅ {card_popularity.name} (Normal, POPULARITY_TYPE) → {ab} ({ABILITIES[ab]['name_fa'] if ab else 'None'})")


def test_apply_ability():
    """تست اعمال اثر ابیلیتی"""
    print("\n" + "="*50)
    print("💥 تست Apply Ability")
    print("="*50)
    
    class FakeDB:
        pass
    
    battle = BattleSystem3Rounds(FakeDB())
    
    # boost_15: challenger +15
    ch_total, op_total, text = battle.apply_ability(
        "boost_15", "challenger", 70, 65, 60, 55, 5, 5)
    assert ch_total == 85, f"Expected 85, got {ch_total}"
    assert op_total == 65
    print(f"✅ boost_15 (challenger): 70 → {ch_total} | {text}")
    
    # sabotage_10: opponent -10
    ch_total, op_total, text = battle.apply_ability(
        "sabotage_10", "challenger", 70, 65, 60, 55, 5, 5)
    assert op_total == 55, f"Expected 55, got {op_total}"
    print(f"✅ sabotage_10 (challenger): opponent 65 → {op_total} | {text}")
    
    # copy: opponent total = challenger total
    ch_total, op_total, text = battle.apply_ability(
        "copy", "challenger", 70, 90, 60, 80, 5, 5)
    assert op_total == 70, f"Expected 70, got {op_total}"
    print(f"✅ copy (challenger): opponent 90 → {op_total} (= challenger) | {text}")
    
    # shield: just returns text, effect is in reduction
    ch_total, op_total, text = battle.apply_ability(
        "shield", "challenger", 70, 65, 60, 55, 5, 5)
    assert ch_total == 70 and op_total == 65  # no change to totals
    print(f"✅ shield (challenger): totals unchanged | {text}")


def test_resolve_round_full():
    """تست کامل یک راوند با همه سیستم‌ها"""
    print("\n" + "="*50)
    print("⚔️ تست Resolve Round کامل")
    print("="*50)
    
    class FakeDB:
        pass
    
    battle = BattleSystem3Rounds(FakeDB())
    
    # Heisenberg (POWER, Epic) vs Flash (SPEED, Legend)
    # Arena: power_arena
    # Heisenberg plays "power", Flash plays "speed"
    # Type counter: POWER > SPEED → Heisenberg +10
    # Arena boost: Heisenberg POWER_TYPE in power_arena + power stat → +8
    # Flash SPEED_TYPE in power_arena + speed stat → 0
    
    state = BattleState(
        fight_id="test1234",
        challenger_id=1,
        opponent_id=2,
        challenger_card_id="test_power",
        opponent_card_id="test_speed",
        arena="power_arena",
        current_round=1,
        challenger_rounds_won=0,
        opponent_rounds_won=0,
        challenger_used_stats=[],
        opponent_used_stats=[],
        rounds_history=[],
        status="round_1",
        challenger_current_stats={"power": 85, "speed": 40, "iq": 70, "popularity": 50},
        opponent_current_stats={"power": 30, "speed": 95, "iq": 45, "popularity": 60},
    )
    
    result = battle.resolve_round(state, card_power, card_speed, "power", "speed")
    
    print(f"\n🎴 Heisenberg (POWER) vs Flash (SPEED)")
    print(f"🏟️ Arena: عرصه قدرت (boost: power +8)")
    print(f"\n📊 محاسبه:")
    print(f"   Heisenberg: power={85} + arena_boost=8 + type_counter=10 = {result.challenger_total}")
    print(f"   Flash:      speed={95} + arena_boost=0 + type_counter=0 = {result.opponent_total}")
    print(f"\n🏆 برنده: {'Challenger (Heisenberg)' if result.winner == 'challenger' else 'Opponent (Flash)' if result.winner == 'opponent' else 'مساوی'}")
    print(f"📉 کاهش stat بازنده: challenger=-{result.challenger_reduction}, opponent=-{result.opponent_reduction}")
    
    # بررسی: Heisenberg = 85 + 8 + 10 = 103, Flash = 95 + 0 + 0 = 95
    assert result.challenger_total == 103, f"Expected 103, got {result.challenger_total}"
    assert result.opponent_total == 95, f"Expected 95, got {result.opponent_total}"
    assert result.winner == "challenger"
    
    # margin = 103 - 95 = 8, < 15 → reduction = 5 (بازنده)
    assert result.opponent_reduction == 5, f"Expected opponent_reduction=5, got {result.opponent_reduction}"
    print(f"\n✅ همه مقادیر درسته!")
    
    # بررسی stat کاهش‌یافته
    new_speed = state.opponent_current_stats["speed"]
    print(f"   Flash speed بعد از باخت: 95 → {new_speed}")
    assert new_speed == 90, f"Expected 90, got {new_speed}"
    print(f"✅ کاهش stat بازنده صحیح (95 - 5 = 90)")


def test_scenario_weak_beats_strong():
    """تست سناریو: کارت ضعیف‌تر با استراتژی می‌بره"""
    print("\n" + "="*50)
    print("🧠 سناریو: کارت ضعیف‌تر با Type Counter + Arena می‌بره")
    print("="*50)
    
    # Sherlock (IQ, Rare, iq=92) vs Ronaldo (POPULARITY, Normal, popularity=98)
    # Arena: thinking_room (boost iq)
    # IQ counters POPULARITY → +10
    # Sherlock IQ_TYPE in thinking_room + iq → +8
    # Total Sherlock: 92 + 8 + 10 = 110
    # Total Ronaldo: 98 + 0 + 0 = 98
    # Sherlock wins despite Ronaldo having higher raw stat!
    
    class FakeDB:
        pass
    
    battle = BattleSystem3Rounds(FakeDB())
    
    state = BattleState(
        fight_id="test5678",
        challenger_id=3,
        opponent_id=4,
        challenger_card_id="test_iq",
        opponent_card_id="test_pop",
        arena="thinking_room",
        current_round=1,
        challenger_rounds_won=0,
        opponent_rounds_won=0,
        challenger_used_stats=[],
        opponent_used_stats=[],
        rounds_history=[],
        status="round_1",
        challenger_current_stats={"power": 35, "speed": 50, "iq": 92, "popularity": 55},
        opponent_current_stats={"power": 60, "speed": 70, "iq": 40, "popularity": 98},
    )
    
    result = battle.resolve_round(state, card_iq, card_popularity, "iq", "popularity")
    
    print(f"\n🎴 Sherlock (IQ, raw=92) vs Ronaldo (POPULARITY, raw=98)")
    print(f"🏟️ Arena: اتاق فکر (boost: iq +8)")
    print(f"\n📊 Sherlock: 92 + 8(arena) + 10(counter) = {result.challenger_total}")
    print(f"📊 Ronaldo:  98 + 0 + 0 = {result.opponent_total}")
    print(f"\n🏆 برنده: {'Sherlock! 🎉' if result.winner == 'challenger' else 'Ronaldo'}")
    
    assert result.winner == "challenger", "Sherlock should win with type counter + arena!"
    print(f"\n✅ کارت ضعیف‌تر (92 vs 98) با استراتژی درست برنده شد!")
    print(f"   → اصل طلایی: «بازیکن باهوش‌تر باید بتواند ببرد» ✅")


# ==================== اجرا ====================

if __name__ == "__main__":
    print("🎮 TelBattle — تست سیستم عمق بازی فاز ۱")
    print("=" * 50)
    
    test_type_counter()
    test_arena_boost()
    test_ability_mapping()
    test_apply_ability()
    test_resolve_round_full()
    test_scenario_weak_beats_strong()
    
    print("\n" + "=" * 50)
    print("🎉 همه تست‌ها پاس شدن!")
    print("=" * 50)
