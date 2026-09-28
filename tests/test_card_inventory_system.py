"""Quantity migration and same-character fusion on disposable databases."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.card_upgrade_system import CardUpgradeSystem
from systems.economy_system import EconomySystem
from systems.fusion_system import FusionSystem, format_fusion_result
import web.miniapp_api as miniapp


def _db(tmp_path):
    db = DatabaseManager(str(tmp_path / "inventory.db"))
    db.get_or_create_player(101)
    assert db.add_card(Card("sub-zero", "Sub-Zero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    assert db.add_card_to_player(101, "sub-zero")
    return db


def _grant_more(db, count):
    with sqlite3.connect(db.db_path) as conn:
        for _ in range(count):
            CardInventorySystem.grant_in(conn, 101, "sub-zero", "normal")


def test_identical_fusion_consumes_three_copies_and_keeps_character(tmp_path):
    db = _db(tmp_path)
    _grant_more(db, 2)
    result = FusionSystem(db).fuse_identical(101, "sub-zero", "epic")
    assert result.success and result.xp_gained == 15
    assert "سه نسخهٔ یکسان" in format_fusion_result(result)
    assert CardInventorySystem(db).counts(101, "sub-zero") == {"epic": 1}
    assert db.get_card_by_id_for_player("sub-zero", 101).rarity == CardRarity.EPIC
    assert db.get_or_create_progression(101)["total_xp"] == 15
    assert not FusionSystem(db).fuse_identical(101, "sub-zero", "epic").success


def test_active_form_is_player_selected_when_both_forms_exist(tmp_path):
    db = _db(tmp_path)
    _grant_more(db, 3)
    inventory = CardInventorySystem(db)
    assert FusionSystem(db).fuse_identical(101, "sub-zero", "epic").success
    assert inventory.counts(101, "sub-zero") == {"normal": 1, "epic": 1}
    assert db.get_card_by_id_for_player("sub-zero", 101).rarity == CardRarity.NORMAL

    assert inventory.activate(101, "sub-zero", "epic")["ok"]
    assert db.get_card_by_id_for_player("sub-zero", 101).rarity == CardRarity.EPIC

    assert inventory.activate(101, "sub-zero", "normal")["ok"]
    assert db.get_card_by_id_for_player("sub-zero", 101).rarity == CardRarity.NORMAL

def test_duplicate_copies_count_for_daily_mining(tmp_path):
    db = _db(tmp_path)
    _grant_more(db, 4)
    economy = EconomySystem(db)
    assert economy.calculate_daily_mining(101) == 1
    assert economy.get_economy_stats(101)["mineable_cards"] == 5
    assert economy.claim_daily_mining(101)[:2] == (True, 1)
    assert economy.claim_daily_mining(101)[0] is False


def test_coin_grant_rejects_missing_player(tmp_path):
    db = _db(tmp_path)
    economy = EconomySystem(db)
    assert not economy.add_coins(999, 5)
    assert not economy.add_coins(101, True)
    assert economy.add_coins(101, 5)
    assert economy.get_coins(101) == 5


def test_coin_upgrade_moves_one_copy_and_preserves_other_normal(tmp_path):
    db = _db(tmp_path)
    _grant_more(db, 1)
    player = db.get_or_create_player(101)
    player.coins = 100
    db.update_player(player)
    result = CardUpgradeSystem(db).upgrade(101, "sub-zero", "normal_to_epic")
    assert result["ok"]
    assert CardInventorySystem(db).counts(101, "sub-zero") == {"normal": 1, "epic": 1}
    assert db.get_or_create_player(101).coins == 0
    assert db.get_card_by_id_for_player("sub-zero", 101).rarity == CardRarity.NORMAL


def test_existing_ownership_migrates_once_without_creating_extra_copies(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("DROP TABLE player_card_stacks")
        conn.execute("DELETE FROM inventory_migrations")
    migrated = DatabaseManager(db.db_path)
    assert CardInventorySystem(migrated).counts(101, "sub-zero") == {"normal": 1}
    reopened = DatabaseManager(db.db_path)
    assert CardInventorySystem(reopened).counts(101, "sub-zero") == {"normal": 1}


def test_concurrent_identical_fusion_only_consumes_once(tmp_path):
    db = _db(tmp_path)
    _grant_more(db, 2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: FusionSystem(db).fuse_identical(101, "sub-zero", "epic").success,
            range(2),
        ))
    assert sum(results) == 1
    assert CardInventorySystem(db).counts(101, "sub-zero") == {"epic": 1}
    assert db.get_or_create_progression(101)["total_xp"] == 15


def test_mini_app_shows_copy_counts_and_switches_active_form(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _grant_more(db, 3)
    monkeypatch.setattr(miniapp, "db", db)
    miniapp.app.config.update(TESTING=True, DEBUG=True)
    client = miniapp.app.test_client()
    headers = {"X-Debug-User-Id": "101"}
    detail = client.get("/api/v1/cards/sub-zero", headers=headers).get_json()
    assert detail["inventory"] == {"normal": 4}
    response = client.post("/api/v1/cards/sub-zero/fuse-copies", json={"target": "epic"}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["card"]["inventory"] == {"normal": 1, "epic": 1}
    selected = client.post("/api/v1/cards/sub-zero/active-form", json={"rarity": "epic"}, headers=headers)
    assert selected.status_code == 200
    assert selected.get_json()["card"]["rarity"] == "epic"
    assert client.get("/api/v1/cards/sub-zero", headers=headers).get_json()["rarity"] == "epic"
