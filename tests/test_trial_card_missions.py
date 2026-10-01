"""Trial mission content and match-driven progress on disposable databases."""

import sqlite3

from core.database import DatabaseManager
from core.models import Card, CardRarity
from scripts.import_card_missions import import_missions
from systems.card_missions_system import CardMissionsSystem
from systems.match_rewards_system import MatchRewardsSystem


def test_win_progress_is_atomic_and_retry_does_not_advance_again(tmp_path):
    db = DatabaseManager(str(tmp_path / "missions.db"))
    db.get_or_create_player(101)
    db.add_card(Card("hero", "Hero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    db.add_card_to_player(101, "hero")
    assert CardMissionsSystem(db).create_mission("hero", "total_wins", 2)
    awards = {101: {"result": "win", "xp": 10, "score": 10, "card_id": "hero"}}
    with sqlite3.connect(db.db_path) as conn:
        MatchRewardsSystem.award(conn, "mission-match-1", "quick", awards)
        MatchRewardsSystem.award(conn, "mission-match-1", "quick", awards)
        assert conn.execute("SELECT current_progress FROM player_card_missions WHERE user_id=101 AND card_id='hero'").fetchone()[0] == 1
        MatchRewardsSystem.award(conn, "mission-match-2", "quick", awards)
        assert conn.execute("SELECT current_progress,completed FROM player_card_missions WHERE user_id=101 AND card_id='hero'").fetchone() == (2, 1)


def test_mission_import_is_repeatable_and_does_not_replace_existing(tmp_path):
    db = DatabaseManager(str(tmp_path / "missions.db"))
    db.add_card(Card("hero", "Hero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    manifest = tmp_path / "missions.json"
    manifest.write_text('{"version":"test","missions":[{"card_name":"Hero","mission_type":"total_wins","target":3}]}', encoding="utf-8")
    assert import_missions(tmp_path / "missions.db", manifest)["changes"][0]["status"] == "add"
    assert import_missions(tmp_path / "missions.db", manifest, True)["applied"]
    assert import_missions(tmp_path / "missions.db", manifest, True)["changes"][0]["status"] == "unchanged"
