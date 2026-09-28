"""The original Telegram PvP path must use the active form and settle once."""

import sqlite3

from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity


def _fight(tmp_path):
    db = DatabaseManager(str(tmp_path / "single.db"))
    for uid in (101, 202):
        db.get_or_create_player(uid)
    for cid, name in (("blue", "Blue"), ("red", "Red")):
        assert db.add_card(Card(cid, name, CardRarity.NORMAL, 50, 50, 50, 50, []))
    assert db.add_card_to_player(101, "blue")
    assert db.add_card_to_player(202, "red")
    assert db.set_player_card_rarity_override(101, "blue", "epic")
    fight_id = db.create_fight(101, 202, -100)
    assert db.update_fight(
        fight_id, challenger_card_id="blue", opponent_card_id="red",
        challenger_stat="power", opponent_stat="speed", status="both_cards_selected",
    )
    return db, fight_id


def test_active_form_decides_result_and_retry_does_not_reaward(tmp_path):
    db, fight_id = _fight(tmp_path)
    game = GameLogic(db)
    result = game.resolve_pvp_fight(fight_id)
    assert result["success"] and result["winner_id"] == 101
    assert result["challenger_stat_value"] == 58
    with sqlite3.connect(db.db_path) as conn:
        before = conn.execute("SELECT total_score,hearts FROM players WHERE user_id=101").fetchone()
        assert before == (7, 10)
        assert conn.execute("SELECT total_xp FROM player_progression WHERE user_id=101").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM fight_history WHERE user_id IN (101,202)").fetchone()[0] == 2
    retry = game.resolve_pvp_fight(fight_id)
    assert not retry["success"] and retry.get("already_settled")
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT total_score,hearts FROM players WHERE user_id=101").fetchone() == before
        assert conn.execute("SELECT COUNT(*) FROM fight_history WHERE user_id IN (101,202)").fetchone()[0] == 2


def test_history_error_rolls_back_single_round_awards(tmp_path):
    db, fight_id = _fight(tmp_path)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("""CREATE TRIGGER reject_single_history BEFORE INSERT ON fight_history
                        BEGIN SELECT RAISE(FAIL, 'history unavailable'); END""")
    result = GameLogic(db).resolve_pvp_fight(fight_id)
    assert not result["success"]
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT total_score,hearts FROM players WHERE user_id=101").fetchone() == (0, 10)
        assert conn.execute("SELECT total_xp FROM player_progression WHERE user_id=101").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM fight_history").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM active_fights WHERE fight_id=?", (fight_id,)).fetchone()[0] == "both_cards_selected"
