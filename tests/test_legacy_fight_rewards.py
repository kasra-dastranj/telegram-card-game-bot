"""Telegram three-round settlement must be atomic and replay-safe."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.legacy_fight_rewards_system import LegacyFightRewardsSystem


def _fight(tmp_path):
    db = DatabaseManager(str(tmp_path / "fight.db"))
    for user_id in (101, 202):
        db.get_or_create_player(user_id)
    blue = Card("blue", "Blue", CardRarity.NORMAL, 50, 50, 50, 50, [])
    red = Card("red", "Red", CardRarity.EPIC, 60, 60, 60, 60, [])
    assert db.add_card(blue) and db.add_card(red)
    assert db.add_card_to_player(101, "blue")
    assert db.add_card_to_player(202, "red")
    return db, db.create_fight(101, 202, -100), blue, red


def test_three_round_settles_all_resources_once_under_concurrent_retry(tmp_path):
    db, fight_id, blue, red = _fight(tmp_path)
    system = LegacyFightRewardsSystem(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: system.settle_three_round(fight_id, 101, 202, blue, red, "challenger_wins"),
            range(2),
        ))
    assert sorted(result["fresh"] for result in results) == [False, True]
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT total_score,hearts FROM players WHERE user_id=101").fetchone() == (20, 10)
        assert conn.execute("SELECT total_score,hearts FROM players WHERE user_id=202").fetchone() == (0, 9)
        assert conn.execute("SELECT total_xp FROM player_progression WHERE user_id=101").fetchone()[0] == 10
        assert conn.execute("SELECT total_xp FROM player_progression WHERE user_id=202").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM fight_history WHERE user_id IN (101,202)").fetchone()[0] == 2
        assert conn.execute("SELECT SUM(hearts_lost) FROM fight_history WHERE user_id IN (101,202)").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM match_reward_events WHERE request_id=?", (f"fight:{fight_id}",)).fetchone()[0] == 2
        assert conn.execute("SELECT status FROM active_fights WHERE fight_id=?", (fight_id,)).fetchone()[0] == "completed"


def test_history_failure_rolls_back_entire_fight_settlement(tmp_path):
    db, fight_id, blue, red = _fight(tmp_path)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("""CREATE TRIGGER reject_fight_history BEFORE INSERT ON fight_history
                        BEGIN SELECT RAISE(FAIL, 'history unavailable'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        LegacyFightRewardsSystem(db).settle_three_round(
            fight_id, 101, 202, blue, red, "challenger_wins"
        )
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT total_score,hearts FROM players WHERE user_id=101").fetchone() == (0, 10)
        assert conn.execute("SELECT total_score,hearts FROM players WHERE user_id=202").fetchone() == (0, 10)
        assert conn.execute("SELECT total_xp FROM player_progression WHERE user_id=101").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM fight_history").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM active_fights WHERE fight_id=?", (fight_id,)).fetchone()[0] == "waiting_opponent"
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE name='fight_reward_settlements'").fetchone()
        assert not table or conn.execute("SELECT COUNT(*) FROM fight_reward_settlements").fetchone()[0] == 0


def test_existing_reward_ledger_is_extended_without_losing_rows(tmp_path):
    db, fight_id, blue, red = _fight(tmp_path)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("""CREATE TABLE match_reward_events (
            request_id TEXT NOT NULL,user_id INTEGER NOT NULL,mode TEXT NOT NULL,
            xp INTEGER NOT NULL,score INTEGER NOT NULL,awarded_at TEXT NOT NULL,
            PRIMARY KEY(request_id,user_id))""")
        conn.execute("INSERT INTO match_reward_events VALUES('older',101,'quick',10,10,'2026-01-01')")
    LegacyFightRewardsSystem(db).settle_three_round(
        fight_id, 101, 202, blue, red, "challenger_wins"
    )
    with sqlite3.connect(db.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(match_reward_events)")}
        assert {"hearts_lost", "tp_delta"} <= columns
        assert conn.execute("SELECT xp,score FROM match_reward_events WHERE request_id='older'").fetchone() == (10, 10)
