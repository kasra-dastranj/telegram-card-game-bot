"""Phase 2 migration checks that never touch the developer database."""

import sqlite3
from pathlib import Path

from game_core import DatabaseManager
from migrations.phase2_migration import Phase2Migration


def test_migration_isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "phase2-source.db"
    DatabaseManager(str(db_path))

    migration = Phase2Migration(str(db_path))
    assert migration.run() is True
    assert migration.backup_path is not None
    assert Path(migration.backup_path).exists()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        card_columns = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}

    assert {"player_progression", "fusion_log", "card_missions"} <= tables
    assert "card_type" in card_columns
