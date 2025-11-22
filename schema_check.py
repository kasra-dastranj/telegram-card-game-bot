#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import json
import os

def main(db_path="game_bot.db"):
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    try:
        print("cards columns:")
        cur.execute("PRAGMA table_info(cards)")
        cols = [c[1] for c in cur.fetchall()]
        print(cols)
        print("has legacy dialog column:")
        print("dialog" in cols)
        print("sample rows (card_id,name,dialogs,biography):")
        cur.execute("SELECT card_id,name,dialogs,biography FROM cards LIMIT 5")
        rows = cur.fetchall()
        print(rows)
    finally:
        con.close()

if __name__ == "__main__":
    main()
