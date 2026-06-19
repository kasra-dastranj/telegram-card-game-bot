#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import json

conn = sqlite3.connect('game_bot.db')
cursor = conn.cursor()

print("🎴 تحلیل کارت‌های بازی")
print("=" * 60)

# Get rarity distribution
cursor.execute("""
    SELECT rarity, COUNT(*) 
    FROM cards 
    GROUP BY rarity
""")
rarity_dist = cursor.fetchall()

print("\n📊 توزیع بر اساس Rarity:")
for rarity, count in rarity_dist:
    print(f"  {rarity.upper()}: {count} کارت")

# Get card types distribution
cursor.execute("""
    SELECT card_type, COUNT(*) 
    FROM cards 
    WHERE card_type IS NOT NULL
    GROUP BY card_type
""")
type_dist = cursor.fetchall()

print("\n🎯 توزیع بر اساس Card Type:")
for card_type, count in type_dist:
    if card_type:
        print(f"  {card_type}: {count} کارت")

# Get sample cards
cursor.execute("""
    SELECT name, rarity, power, speed, iq, popularity, card_type
    FROM cards
    LIMIT 5
""")
samples = cursor.fetchall()

print("\n📋 نمونه کارت‌ها:")
for card in samples:
    name, rarity, power, speed, iq, pop, ctype = card
    total = power + speed + iq + pop
    print(f"\n  • {name} ({rarity})")
    print(f"    Type: {ctype or 'N/A'}")
    print(f"    Stats: Power={power}, Speed={speed}, IQ={iq}, Pop={pop}")
    print(f"    Total: {total}")

# Check for phase 2 tables
print("\n\n🔍 بررسی جداول Phase 2:")
phase2_tables = [
    'player_progression',
    'fusion_log',
    'battle_states',
    'round_history'
]

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
existing_tables = [t[0] for t in cursor.fetchall()]

for table in phase2_tables:
    exists = table in existing_tables
    status = "✅" if exists else "❌"
    print(f"  {status} {table}")

# Check for phase 2 columns in players
cursor.execute("PRAGMA table_info(players)")
player_columns = [col[1] for col in cursor.fetchall()]

print("\n🔍 بررسی ستون‌های Phase 2 در players:")
phase2_columns = ['coins', 'max_hearts', 'last_mining_claim', 'weekly_score']
for col in phase2_columns:
    exists = col in player_columns
    status = "✅" if exists else "❌"
    print(f"  {status} {col}")

conn.close()
