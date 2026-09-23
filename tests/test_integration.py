"""Isolated integration tests for the current Phase 2 systems."""

import sqlite3
from datetime import datetime, timedelta

from game_core import Card, CardRarity, DatabaseManager
from systems.card_missions_system import CardMissionsSystem
from systems.tier_decay_system import TierDecaySystem


def _database(tmp_path, name):
    return DatabaseManager(str(tmp_path / name))


def _inactive_gold_player(db, user_id=999999):
    db.get_or_create_player(user_id, "test_user", "Test User")
    db.get_or_create_progression(user_id)
    last_played = (datetime.now() - timedelta(days=5)).isoformat()
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            """
            UPDATE player_progression
            SET level=10, total_xp=5000, current_tier='Gold',
                tier_points=1200, last_played_at=?
            WHERE user_id=?
            """,
            (last_played, user_id),
        )
    return user_id


def test_tier_decay_integration(tmp_path):
    db = _database(tmp_path, "tier-decay.db")
    user_id = _inactive_gold_player(db)
    tier_decay = TierDecaySystem(db)

    info = tier_decay.get_decay_info(user_id)
    assert info["in_protection"] is False
    assert info["days_inactive"] >= 5
    assert info["estimated_decay"] == 60

    result = tier_decay.apply_decay_to_player(user_id)
    assert result["success"] is True
    assert result["decayed"] is True
    assert result["old_tp"] == 1200
    assert result["new_tp"] == 1140
    assert result["decay_amount"] == 60


def test_missions_integration(tmp_path):
    db = _database(tmp_path, "missions.db")
    user_id = 999999
    card_id = "test_epic_card"
    db.get_or_create_player(user_id, "mission_user", "Mission User")
    assert db.add_card(
        Card(
            card_id=card_id,
            name="Test Epic",
            rarity=CardRarity.EPIC,
            power=80,
            speed=70,
            iq=60,
            popularity=50,
            abilities=["Test Ability"],
        )
    )
    assert db.add_card_to_player(user_id, card_id)

    missions = CardMissionsSystem(db)
    assert missions.create_mission(card_id, "total_wins", 10)
    initial = missions.get_player_mission_progress(user_id, card_id)
    assert initial["current_progress"] == 0
    assert initial["completed"] is False

    update = None
    for _ in range(5):
        update = missions.check_and_update_mission(
            user_id, card_id, {"won": True, "winning_stat": "power"}
        )

    assert update["current_progress"] == 5
    final = missions.get_player_mission_progress(user_id, card_id)
    assert final["current_progress"] == 5
    assert final["target"] == 10
    assert final["completed"] is False


def test_profile_decay_display_contract(tmp_path):
    db = _database(tmp_path, "profile.db")
    user_id = _inactive_gold_player(db)
    info = TierDecaySystem(db).get_decay_info(user_id)

    if info["in_protection"]:
        text = f"حفاظت: {info['days_remaining']} روز"
    else:
        text = f"Decay فعال: {info['estimated_decay']} TP"

    assert text == "Decay فعال: 60 TP"
