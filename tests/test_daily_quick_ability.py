"""Daily card claims award one Quick consumable across both entry points."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems.game_mode_system import ABILITY_DEFINITIONS, GameModeSystem
from systems.player_rewards_system import PlayerRewardsSystem


def _daily_db(tmp_path):
    db = DatabaseManager(str(tmp_path / "daily.db"))
    db.get_or_create_player(101)
    assert db.add_card(Card(
        card_id="daily-card", name="Daily Card", rarity=CardRarity.NORMAL,
        power=50, speed=50, iq=50, popularity=50, abilities=[],
    ))
    GameModeSystem(db)
    return db


def _ability_total(db):
    with sqlite3.connect(db.db_path) as conn:
        return conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM player_ability_inventory WHERE user_id=101"
        ).fetchone()[0]


def test_daily_claim_awards_one_quick_ability_and_cross_client_retry_does_not(tmp_path):
    db = _daily_db(tmp_path)
    result = PlayerRewardsSystem(db).claim_daily(101)
    assert result["ok"]
    assert result["ability"]["key"] in ABILITY_DEFINITIONS
    assert _ability_total(db) == 1
    success, card, error, ability = GameLogic(db).claim_daily_card_with_ability(101)
    assert not success and card is None and ability is None
    assert error
    assert _ability_total(db) == 1


def test_simultaneous_claims_commit_card_and_ability_once(tmp_path):
    db = _daily_db(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: PlayerRewardsSystem(db).claim_daily(101), range(2)))
    assert sum(bool(result["ok"]) for result in results) == 1
    assert _ability_total(db) == 1
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM player_cards WHERE user_id=101"
        ).fetchone()[0] == 1


def test_bot_claim_uses_shared_reward_path(tmp_path):
    db = _daily_db(tmp_path)
    success, card, error, ability = GameLogic(db).claim_daily_card_with_ability(101)
    assert success and error is None
    assert card.card_id == "daily-card"
    assert ability["key"] in ABILITY_DEFINITIONS
    assert _ability_total(db) == 1
