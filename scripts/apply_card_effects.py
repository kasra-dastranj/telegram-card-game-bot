#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply Phase 3 card effect assignments from data/card_effects.json."""

import json
import sqlite3
from pathlib import Path


VALID_EFFECTS = {"reflect", "drain", "arena_shift"}


def apply_card_effects(db_path: str = "game_bot.db", effects_path: str = "data/card_effects.json") -> int:
    effects_file = Path(effects_path)
    assignments = json.loads(effects_file.read_text(encoding="utf-8"))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE cards ADD COLUMN card_effects TEXT DEFAULT '[]'")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            conn.close()
            raise

    cursor.execute("UPDATE cards SET card_effects = '[]'")

    updated = 0
    missing = []
    invalid = []

    for card_key, effects in assignments.items():
        clean_effects = []
        for effect in effects:
            if effect in VALID_EFFECTS:
                clean_effects.append(effect)
            else:
                invalid.append((card_key, effect))

        cursor.execute(
            "UPDATE cards SET card_effects = ? WHERE card_id = ? OR lower(name) = lower(?)",
            (json.dumps(clean_effects, ensure_ascii=False), card_key, card_key),
        )
        if cursor.rowcount == 0:
            missing.append(card_key)
        else:
            updated += cursor.rowcount

    if invalid:
        conn.rollback()
        conn.close()
        raise ValueError(f"Invalid effects: {invalid}")

    if missing:
        conn.rollback()
        conn.close()
        raise ValueError(f"Cards not found: {missing}")

    conn.commit()
    conn.close()
    return updated


if __name__ == "__main__":
    count = apply_card_effects()
    print(f"Applied card effects to {count} cards")
