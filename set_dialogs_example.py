#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick helper to set/append dialogs for a sample card to demonstrate JSON storage in SQLite.

Usage (Windows PowerShell):
    python .\set_dialogs_example.py
    # or choose a different card and lines
    python .\set_dialogs_example.py --name "Spongebob" --lines "I'm ready!" "Best day ever!"

Behavior:
- Looks up the card by name in the 'cards' table.
- Parses existing dialogs JSON (if any), merges with provided lines, deduplicates, and updates the row.
- Prints before/after dialogs for verification.
"""

import argparse
import json
import os
import sqlite3
from typing import List

DEFAULT_DB = "game_bot.db"
DEFAULT_CARD = "Heisenberg"
DEFAULT_LINES = [
    "I am the one who knocks!",
    "Say my name!",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set dialogs for a sample card")
    parser.add_argument("--db", dest="db_path", default=DEFAULT_DB, help="Path to SQLite database file")
    parser.add_argument("--name", dest="card_name", default=DEFAULT_CARD, help="Card name to update")
    parser.add_argument("--lines", nargs="*", dest="lines", default=DEFAULT_LINES, help="Dialog lines to add")
    return parser.parse_args()


def get_existing_dialogs(row_value) -> List[str]:
    if row_value is None:
        return []
    if isinstance(row_value, str) and row_value.strip():
        try:
            parsed = json.loads(row_value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def main():
    args = parse_args()
    db_path = args.db_path
    card_name = args.card_name
    new_lines = [s for s in (args.lines or []) if isinstance(s, str) and s.strip()]

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    try:
        cur.execute("SELECT card_id, dialogs FROM cards WHERE name = ?", (card_name,))
        row = cur.fetchone()
        if not row:
            print(f"Card not found by name: {card_name}")
            return
        card_id, dialogs_text = row
        before_list = get_existing_dialogs(dialogs_text)
        # Merge and deduplicate while preserving order
        merged = list(dict.fromkeys([*before_list, *new_lines]))
        cur.execute(
            "UPDATE cards SET dialogs = ? WHERE card_id = ?",
            (json.dumps(merged, ensure_ascii=False), card_id),
        )
        con.commit()
        print("Updated dialogs for:", card_name)
        print("Before:", before_list)
        print("After:", merged)
    finally:
        con.close()


if __name__ == "__main__":
    main()
