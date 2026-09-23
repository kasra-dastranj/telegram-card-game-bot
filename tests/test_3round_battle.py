"""Database contract checks for the three-round battle engine."""

import sqlite3

from game_core import DatabaseManager, GameLogic


def test_3round_battle_tables_are_created(tmp_path):
    db_path = tmp_path / "three-round.db"
    db = DatabaseManager(str(db_path))

    # Construction verifies that the engine accepts a freshly initialized DB.
    assert GameLogic(db).db is db

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert {"active_fights", "battle_states", "round_history"} <= tables
