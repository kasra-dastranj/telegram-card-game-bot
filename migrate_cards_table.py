#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone migration script for the 'cards' table.

- Ensures the columns 'biography' (TEXT) and 'dialogs' (TEXT) exist.
- If a legacy 'dialog' TEXT column exists, migrates its values into 'dialogs' as a JSON array
  when 'dialogs' is NULL or empty.

Usage (Windows PowerShell):
    python migrate_cards_table.py

You can optionally pass a custom database path:
    python migrate_cards_table.py --db game_bot.db

This script is idempotent: running it multiple times is safe.
"""

import argparse
import json
import os
import sqlite3
from typing import List


def get_table_columns(cursor: sqlite3.Cursor, table: str) -> List[str]:
    cursor.execute("PRAGMA table_info(%s)" % table)
    return [row[1] for row in cursor.fetchall()]


def ensure_columns(conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
    columns = get_table_columns(cursor, "cards")

    if "biography" not in columns:
        cursor.execute("ALTER TABLE cards ADD COLUMN biography TEXT")
        print("Added column: biography")
    if "dialogs" not in columns:
        cursor.execute("ALTER TABLE cards ADD COLUMN dialogs TEXT")
        print("Added column: dialogs")

    conn.commit()


def migrate_legacy_dialog(conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> int:
    columns = get_table_columns(cursor, "cards")
    if "dialog" not in columns:
        return 0

    # Find rows where legacy dialog has content and dialogs is NULL or empty
    cursor.execute(
        """
        SELECT card_id, dialog, COALESCE(dialogs, '') as dialogs
        FROM cards
        WHERE dialog IS NOT NULL AND TRIM(dialog) <> ''
        """
    )
    rows = cursor.fetchall()

    migrated = 0
    for card_id, legacy_dialog, dialogs_text in rows:
        try:
            existing_list = []
            if dialogs_text and dialogs_text.strip():
                try:
                    existing_list = json.loads(dialogs_text)
                    if not isinstance(existing_list, list):
                        existing_list = []
                except Exception:
                    existing_list = []
            legacy_dialog = legacy_dialog.strip()
            if legacy_dialog and legacy_dialog not in existing_list:
                new_list = [*existing_list, legacy_dialog]
                cursor.execute(
                    "UPDATE cards SET dialogs = ? WHERE card_id = ?",
                    (json.dumps(new_list, ensure_ascii=False), card_id),
                )
                migrated += 1
        except Exception as e:
            print(f"Could not migrate dialog for {card_id}: {e}")

    conn.commit()
    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migrate 'cards' table to support biography and dialogs fields.")
    parser.add_argument("--db", dest="db_path", default="game_bot.db", help="Path to SQLite database file")
    args = parser.parse_args()

    db_path = args.db_path
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        ensure_columns(conn, cursor)
        migrated = migrate_legacy_dialog(conn, cursor)
        if migrated:
            print(f"Migrated legacy 'dialog' to 'dialogs' for {migrated} card(s).")
        else:
            print("No legacy 'dialog' values found to migrate or migration not needed.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
