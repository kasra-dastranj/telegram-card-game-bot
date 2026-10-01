import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from game_core import CardManager, DatabaseManager
from systems.card_upgrade_system import CardUpgradeSystem
from systems.game_mode_system import GameModeSystem
from systems.level_rewards_system import LevelRewardsSystem
import web.miniapp_api as miniapp


@pytest.fixture()
def upgrade_db(tmp_path):
    database = DatabaseManager(str(tmp_path / "upgrades.db"))
    CardManager(database).create_sample_cards()
    player = database.get_or_create_player(501, "owner", "Owner")
    player.coins = 1000
    database.update_player(player)
    normal = next(card for card in database.get_all_cards() if card.rarity.value == "normal")
    database.add_card_to_player(501, normal.card_id)
    return database, normal.card_id


def _snapshot(database, user_id, card_id):
    conn = sqlite3.connect(database.db_path)
    try:
        coins = conn.execute("SELECT coins FROM players WHERE user_id=?", (user_id,)).fetchone()[0]
        rarity = conn.execute(
            "SELECT rarity_override FROM player_cards WHERE user_id=? AND card_id=?",
            (user_id, card_id),
        ).fetchone()[0]
        xp = conn.execute("SELECT total_xp FROM player_progression WHERE user_id=?", (user_id,)).fetchone()
        return coins, rarity, xp[0] if xp else 0
    finally:
        conn.close()


def test_upgrade_changes_coin_rarity_and_xp_together(upgrade_db):
    database, card_id = upgrade_db
    result = CardUpgradeSystem(database).upgrade(501, card_id, "normal_to_epic")

    assert result["ok"] is True
    assert _snapshot(database, 501, card_id) == (900, "epic", 15)


def test_upgrade_retry_reuses_receipt_without_second_charge(upgrade_db):
    database, card_id = upgrade_db
    system = CardUpgradeSystem(database)
    first = system.upgrade(501, card_id, "normal_to_epic", "upgrade-retry-001")
    retry = system.upgrade(501, card_id, "normal_to_epic", "upgrade-retry-001")
    conflict = system.upgrade(501, card_id, "epic_to_legend", "upgrade-retry-001")
    assert first["ok"] and retry["ok"] and retry["replayed"]
    assert conflict["error_code"] == "idempotency_conflict"
    assert _snapshot(database, 501, card_id) == (900, "epic", 15)


def test_mini_app_upgrade_retry_is_one_charge(upgrade_db, monkeypatch):
    database, card_id = upgrade_db
    monkeypatch.setattr(miniapp, "db", database)
    miniapp.app.config.update(TESTING=True, DEBUG=True)
    client = miniapp.app.test_client()
    headers = {"X-Debug-User-Id": "501"}
    path = f"/api/v1/cards/{card_id}/upgrade"
    body = {"upgrade_key": "normal_to_epic", "request_key": "api-upgrade-retry-001"}
    first = client.post(path, json=body, headers=headers)
    again = client.post(path, json=body, headers=headers)
    assert first.status_code == again.status_code == 200
    assert again.get_json()["data"]["upgrade"]["replayed"] is True
    assert _snapshot(database, 501, card_id) == (900, "epic", 15)


def test_upgrade_response_includes_level_coin_reward(upgrade_db):
    database, card_id = upgrade_db
    database.update_progression(501, total_xp=95)
    player = database.get_or_create_player(501)
    player.coins = 100
    database.update_player(player)
    LevelRewardsSystem(database).set_coin_rule(2, 9)

    result = CardUpgradeSystem(database).upgrade(501, card_id, "normal_to_epic")

    assert result["ok"] is True
    assert result["new_level"] == 2
    assert result["coins"] == 9
    assert _snapshot(database, 501, card_id) == (9, "epic", 110)


def test_upgrade_rejects_foreign_card_without_charging(upgrade_db):
    database, card_id = upgrade_db
    outsider = database.get_or_create_player(502, "outsider", "Outsider")
    outsider.coins = 1000
    database.update_player(outsider)

    result = CardUpgradeSystem(database).upgrade(502, card_id, "normal_to_epic")

    assert result["error_code"] == "card_not_owned"
    assert database.get_or_create_player(502).coins == 1000


def test_upgrade_rejects_insufficient_funds_without_partial_change(upgrade_db):
    database, card_id = upgrade_db
    player = database.get_or_create_player(501)
    player.coins = 99
    database.update_player(player)

    result = CardUpgradeSystem(database).upgrade(501, card_id, "normal_to_epic")

    assert result["error_code"] == "insufficient_coins"
    assert _snapshot(database, 501, card_id) == (99, None, 0)


def test_upgrade_rejects_while_a_match_is_active(upgrade_db):
    database, card_id = upgrade_db
    conn = sqlite3.connect(database.db_path)
    conn.execute(
        """
        INSERT INTO solo_fights
            (fight_id, player_id, difficulty, status, created_at)
        VALUES ('active-test', 501, 'easy', 'round_1', CURRENT_TIMESTAMP)
        """
    )
    conn.commit()
    conn.close()

    result = CardUpgradeSystem(database).upgrade(501, card_id, "normal_to_epic")

    assert result["error_code"] == "active_match"
    assert _snapshot(database, 501, card_id) == (1000, None, 0)


def test_accepted_deck_request_uses_actual_fight_to_lock_collection(upgrade_db):
    database, _ = upgrade_db
    modes = GameModeSystem(database)
    request = modes.create_invite(501, "deck", "normal")
    accepted, _, _ = modes.accept_request(request["request_id"], 502)
    assert accepted
    upgrades = CardUpgradeSystem(database)
    assert not upgrades.is_management_locked(501)
    fight_id = database.create_fight(501, 502, -100)
    assert upgrades.is_management_locked(501)
    with sqlite3.connect(database.db_path) as conn:
        conn.execute("UPDATE active_fights SET status='completed' WHERE fight_id=?", (fight_id,))
    assert not upgrades.is_management_locked(501)
    assert not upgrades.is_management_locked(502)


def test_expired_accepted_quick_request_does_not_lock_collection(upgrade_db):
    database, _ = upgrade_db
    modes = GameModeSystem(database)
    request = modes.create_invite(501, "quick", "normal")
    accepted, _, _ = modes.accept_request(request["request_id"], 502)
    assert accepted
    upgrades = CardUpgradeSystem(database)
    assert upgrades.is_management_locked(501)
    with sqlite3.connect(database.db_path) as conn:
        conn.execute(
            "UPDATE game_requests SET expires_at=? WHERE request_id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(), request["request_id"]),
        )
    assert not upgrades.is_management_locked(501)


def test_expired_quick_choice_does_not_lock_collection(upgrade_db):
    database, _ = upgrade_db
    modes = GameModeSystem(database)
    request = modes.create_invite(501, "quick", "normal")
    accepted, _, _ = modes.accept_request(request["request_id"], 502)
    assert accepted
    modes.start_quick_match(request["request_id"])
    upgrades = CardUpgradeSystem(database)
    assert upgrades.is_management_locked(501)
    with sqlite3.connect(database.db_path) as conn:
        state = json.loads(conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?",
            (request["request_id"],),
        ).fetchone()[0])
        state["deadline"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        conn.execute(
            "UPDATE game_match_states SET state_json=? WHERE request_id=?",
            (json.dumps(state), request["request_id"]),
        )
    assert not upgrades.is_management_locked(501)
    assert not upgrades.is_management_locked(502)
