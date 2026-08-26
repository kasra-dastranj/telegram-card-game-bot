import sqlite3

import pytest

from game_core import CardManager, DatabaseManager
from systems.card_upgrade_system import CardUpgradeSystem


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
