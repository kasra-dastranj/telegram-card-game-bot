"""Regression tests for lossless rewards and one-time weekly payouts."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.economy_system import EconomySystem
from systems.match_rewards_system import MatchRewardsSystem
from systems.player_rewards_system import PlayerRewardsSystem
from systems.weekly_rewards_system import WeeklyRewardsSystem


@pytest.fixture
def db(tmp_path):
    database = DatabaseManager(str(tmp_path / "progression.db"))
    database.get_or_create_player(101)
    database.get_or_create_player(202)
    return database


def test_score_conversion_keeps_remainder(db):
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE players SET total_score=150 WHERE user_id=101")

    economy = EconomySystem(db)
    assert economy.convert_score_to_coins(101, 150)[0] is False
    assert (db.get_or_create_player(101).total_score, economy.get_coins(101)) == (150, 0)

    assert economy.convert_score_to_coins(101, 100)[:2] == (True, 1)
    assert (db.get_or_create_player(101).total_score, economy.get_coins(101)) == (50, 1)


def test_daily_claim_adds_a_real_duplicate_copy(db):
    first = Card("first", "First", CardRarity.NORMAL, 10, 10, 10, 10, [])
    assert db.add_card(first)
    assert db.add_card_to_player(101, first.card_id)

    rewards = PlayerRewardsSystem(db)
    assert rewards.claim_status(101)["pool_count"] == 1
    assert rewards.claim_status(101)["can_claim"]
    result = rewards.claim_daily(101)
    assert result["ok"] and result["card_id"] == first.card_id
    assert result["quantity"] == 2
    assert not rewards.claim_status(101)["can_claim"]
    assert CardInventorySystem(db).counts(101, first.card_id) == {"normal": 2}
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_cards WHERE user_id=101 AND card_id='first'"
        ).fetchone()[0] == 1


def test_daily_claim_without_any_normal_card_does_not_consume_turn(db):
    rewards = PlayerRewardsSystem(db)
    assert rewards.claim_status(101)["pool_exhausted"]
    result = rewards.claim_daily(101)
    assert not result["ok"] and result["error_code"] == "empty_pool"
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT last_claim FROM players WHERE user_id=101").fetchone()[0] is None


def test_weekly_rewards_are_atomic_and_idempotent(db):
    weekly = WeeklyRewardsSystem(db)
    leaderboard = [{"user_id": 101}, {"user_id": 202}]
    assert weekly.distribute("2026-09-21", leaderboard) == [(1, 101, 100), (2, 202, 50)]
    assert weekly.distribute("2026-09-21", leaderboard) == []
    assert db.get_or_create_player(101).coins == 100
    assert db.get_or_create_player(202).coins == 50
    assert db.get_or_create_progression(101)["total_xp"] == 100
    assert db.get_or_create_progression(101)["level"] == 2
    assert db.get_or_create_progression(202)["total_xp"] == 50


def test_weekly_leaderboard_uses_closed_period_and_stable_ties(db):
    with sqlite3.connect(db.db_path) as conn:
        conn.executemany(
            "INSERT INTO fight_history(user_id,score_gained,fought_at) VALUES(?,?,?)",
            [
                (101, 50, "2026-09-20T20:29:59+00:00"),  # Before Tehran Monday.
                (101, 10, "2026-09-20T20:30:00+00:00"),
                (202, 10, "2026-09-21T12:00:00+00:00"),
                (202, 90, "2026-09-27T20:30:00+00:00"),  # Next period.
            ],
        )
    weekly = WeeklyRewardsSystem(db)
    results = weekly.leaderboard_for_period(
        datetime(2026, 9, 20, 20, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 27, 20, 30, tzinfo=timezone.utc),
    )
    assert results == [
        {"user_id": 101, "period_score": 10},
        {"user_id": 202, "period_score": 10},
    ]


def test_weekly_rewards_roll_back_entire_batch_on_missing_player(db):
    weekly = WeeklyRewardsSystem(db)
    with pytest.raises(ValueError, match="no player record"):
        weekly.distribute("2026-09-21", [{"user_id": 101}, {"user_id": 999}])
    assert db.get_or_create_player(101).coins == 0
    assert weekly.distribute("2026-09-21", [{"user_id": 101}]) == [(1, 101, 100)]


def test_concurrent_weekly_runs_only_pay_once(db):
    weekly = WeeklyRewardsSystem(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: weekly.distribute("2026-09-21", [{"user_id": 101}]), range(2)
        ))
    assert sorted(len(result) for result in results) == [0, 1]
    assert db.get_or_create_player(101).coins == 100


def test_match_reward_history_failure_rolls_back_xp_and_score(db):
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_match_history BEFORE INSERT ON fight_history BEGIN SELECT RAISE(ABORT, 'history failed'); END")

    awards = {101: {"result": "win", "xp": 10, "score": 10}}
    with pytest.raises(sqlite3.IntegrityError, match="history failed"):
        with sqlite3.connect(db.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            MatchRewardsSystem.award(conn, "match-1", "quick", awards)

    assert db.get_or_create_player(101).total_score == 0
    assert db.get_or_create_progression(101)["total_xp"] == 0
