#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migration script — لود کارت‌ها از cards_export.json به DB
اجرا روی Railway Console:
  python migrate_cards.py
"""

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DATABASE_PATH", "game_bot.db")

def migrate():
    # بارگذاری کارت‌ها از JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards_export.json")
    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found")
        return

    with open(json_path, encoding="utf-8") as f:
        cards = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    added = 0
    skipped = 0
    for card in cards:
        abilities = card.get("abilities", [])
        if isinstance(abilities, list):
            abilities = json.dumps(abilities, ensure_ascii=False)

        try:
            cursor.execute('''
                INSERT OR IGNORE INTO cards
                (card_id, name, rarity, power, speed, iq, popularity,
                 abilities, biography, card_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                card["card_id"], card["name"], card["rarity"],
                card["power"], card["speed"], card["iq"], card["popularity"],
                abilities, card.get("biography", ""),
                card.get("card_type", "POWER_TYPE"),
                datetime.now().isoformat()
            ))
            if cursor.rowcount > 0:
                added += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Error adding {card['name']}: {e}")

    conn.commit()
    conn.close()
    print(f"✅ Migration done: {added} added, {skipped} skipped (already exist)")
    print(f"Total cards in DB: {added + skipped}")

if __name__ == "__main__":
    migrate()
