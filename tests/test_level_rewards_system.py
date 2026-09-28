"""Coin rules are configurable and crossing a level pays only once."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from core.database import DatabaseManager
from systems.level_rewards_system import LevelRewardsSystem
from systems.phase2_systems import ProgressionDB


def _db(tmp_path):
    db = DatabaseManager(str(tmp_path / "level.db"))
    db.get_or_create_player(101)
    db.get_or_create_progression(101)
    return db


def test_no_coin_award_without_configured_rules(tmp_path):
    db = _db(tmp_path)
    assert db.add_xp(101, 100) == (1, 2)
    assert db.get_or_create_player(101).coins == 0


def test_multi_level_coin_rules_pay_once_even_on_concurrent_xp(tmp_path):
    db = _db(tmp_path)
    rules = LevelRewardsSystem(db)
    rules.set_coin_rule(2, 12)
    rules.set_coin_rule(3, 18)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: db.add_xp(101, 125), range(2)))
    assert db.get_or_create_progression(101)["level"] == 3
    assert db.get_or_create_player(101).coins == 30
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM player_level_coin_awards WHERE user_id=101").fetchone()[0] == 2
    assert db.add_xp(101, 10) == (3, 3)
    assert db.get_or_create_player(101).coins == 30


def test_legacy_progression_helper_uses_same_level_rules(tmp_path):
    db = _db(tmp_path)
    LevelRewardsSystem(db).set_coin_rule(2, 9)
    assert ProgressionDB(db.db_path).add_xp(101, 100, "test") == (True, 1, 2)
    assert db.get_or_create_player(101).coins == 9
