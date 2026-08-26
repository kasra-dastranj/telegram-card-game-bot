import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from game_core import CardManager, DatabaseManager
import web.miniapp_api as miniapp
from systems.card_missions_system import CardMissionsSystem
from systems.skins_system import SkinsSystem


@pytest.fixture()
def hub_client(tmp_path, monkeypatch):
    test_db = DatabaseManager(str(tmp_path / "player-hub.db"))
    CardManager(test_db).create_sample_cards()
    player = test_db.get_or_create_player(101, "commander", "فرمانده")
    player.hearts = 3
    player.max_hearts = 5
    player.coins = 1250
    test_db.update_player(player)
    for card in test_db.get_all_cards():
        test_db.add_card_to_player(101, card.card_id)

    monkeypatch.setattr(miniapp, "db", test_db)
    miniapp.app.config.update(TESTING=True, DEBUG=True)
    return miniapp.app.test_client(), test_db


def _headers(user_id):
    return {"X-Debug-User-Id": str(user_id)}


def _signed_init_data(bot_token, user, *, auth_date=None):
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAExampleQuery",
        "signature": "telegram-signature-placeholder",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_telegram_init_data_keeps_encoded_photo_url_intact(monkeypatch):
    bot_token = "123456:test-token"
    user = {
        "id": 101,
        "first_name": "فرمانده",
        "photo_url": "https://cdn.example/avatar.svg?file=one&size=small+large",
    }
    monkeypatch.setattr(miniapp, "BOT_TOKEN", bot_token)

    verified = miniapp.verify_telegram_init_data(_signed_init_data(bot_token, user))

    assert verified == user


def test_telegram_init_data_rejects_stale_payload(monkeypatch):
    bot_token = "123456:test-token"
    monkeypatch.setattr(miniapp, "BOT_TOKEN", bot_token)

    verified = miniapp.verify_telegram_init_data(
        _signed_init_data(bot_token, {"id": 101}, auth_date=int(time.time()) - 172800)
    )

    assert verified is None


def test_overview_exposes_resources_progress_and_collection_counts(hub_client):
    client, _ = hub_client
    response = client.get("/api/v1/player-hub/overview", headers=_headers(101))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["hearts"] == 3
    assert payload["max_hearts"] == 5
    assert payload["coins"] == 1250
    assert payload["heart_reset_seconds"] > 0
    assert payload["xp_to_next_level"] > 0
    assert payload["counts"]["cards"] == 4
    assert payload["best_card"]["card_id"]
    assert "can_claim" in payload["claim"]


def test_cards_support_pagination_filtering_search_and_sort(hub_client):
    client, _ = hub_client
    first_page = client.get(
        "/api/v1/cards?limit=2&page=1&sort=power",
        headers=_headers(101),
    )
    payload = first_page.get_json()
    assert first_page.status_code == 200
    assert payload["total"] == 4
    assert payload["page_count"] == 2
    assert len(payload["cards"]) == 2
    assert payload["cards"][0]["power"] >= payload["cards"][1]["power"]

    search = client.get(
        "/api/v1/cards?query=heisen&rarity=normal",
        headers=_headers(101),
    ).get_json()
    assert search["total"] == 1
    assert search["cards"][0]["name"] == "Heisenberg"


def test_card_detail_requires_ownership(hub_client):
    client, db = hub_client
    card_id = next(card.card_id for card in db.get_player_cards(101) if card.name == "Spongebob")

    owned = client.get(f"/api/v1/cards/{card_id}", headers=_headers(101))
    outsider = client.get(f"/api/v1/cards/{card_id}", headers=_headers(202))

    assert owned.status_code == 200
    assert owned.get_json()["card_id"] == card_id
    assert outsider.status_code == 404
    assert outsider.get_json()["error_code"] == "card_not_owned"


def test_cards_reject_invalid_pagination(hub_client):
    client, _ = hub_client
    response = client.get("/api/v1/cards?page=nope", headers=_headers(101))
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_pagination"


def test_deck_crud_uses_owned_cards_and_returns_synergy(hub_client):
    client, db = hub_client
    card_ids = [card.card_id for card in db.get_player_cards(101)]
    created = client.post(
        "/api/v1/decks",
        json={"name": "تیم اصلی", "card_ids": card_ids[:3]},
        headers=_headers(101),
    )
    assert created.status_code == 201
    deck = created.get_json()["data"]
    assert deck["deck_name"] == "تیم اصلی"
    assert len(deck["cards"]) == 3
    assert "score" in deck["synergy"]

    updated = client.put(
        f"/api/v1/decks/{deck['deck_id']}",
        json={"name": "تیم دوم", "card_ids": card_ids[1:4]},
        headers=_headers(101),
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["deck_name"] == "تیم دوم"

    outsider_delete = client.delete(f"/api/v1/decks/{deck['deck_id']}", headers=_headers(202))
    assert outsider_delete.status_code == 403
    deleted = client.delete(f"/api/v1/decks/{deck['deck_id']}", headers=_headers(101))
    assert deleted.status_code == 200
    assert client.get("/api/v1/decks", headers=_headers(101)).get_json()["decks"] == []


def test_deck_creation_rejects_duplicate_and_foreign_cards(hub_client):
    client, db = hub_client
    owned = [card.card_id for card in db.get_player_cards(101)]
    duplicate = client.post(
        "/api/v1/decks",
        json={"card_ids": [owned[0], owned[0], owned[1]]},
        headers=_headers(101),
    )
    assert duplicate.status_code == 400

    foreign = client.post(
        "/api/v1/decks",
        json={"card_ids": owned[:3]},
        headers=_headers(202),
    )
    assert foreign.status_code == 400


def test_daily_claim_is_idempotent_for_the_same_day(hub_client):
    client, _ = hub_client
    first = client.post("/api/v1/claim", headers=_headers(101))
    second = client.post("/api/v1/claim", headers=_headers(101))

    assert first.status_code == 200
    assert first.get_json()["data"]["card"]["rarity"] == "normal"
    assert second.status_code == 409
    assert second.get_json()["error_code"] == "already_claimed"


def test_mission_reward_is_claimed_once_and_upgrades_owned_epic(hub_client):
    client, db = hub_client
    card = next(card for card in db.get_player_cards(101) if card.rarity.value == "normal")
    db.set_player_card_rarity_override(101, card.card_id, "epic")
    missions = CardMissionsSystem(db)
    assert missions.create_mission(card.card_id, "total_wins", 1)
    assert missions.update_mission_progress(101, card.card_id)["completed"] is True

    first = client.post(f"/api/v1/missions/{card.card_id}/claim", headers=_headers(101))
    second = client.post(f"/api/v1/missions/{card.card_id}/claim", headers=_headers(101))

    assert first.status_code == 200
    assert first.get_json()["data"]["card"]["rarity"] == "legend"
    assert second.status_code == 409
    assert second.get_json()["error_code"] == "reward_claimed"


def test_skin_purchase_and_activation_verify_card_binding(hub_client):
    client, db = hub_client
    cards = db.get_player_cards(101)
    card, other = cards[0], cards[1]
    skins = SkinsSystem(db)
    assert skins.create_skin("skin-test", card.card_id, "Night", "special", "night.png", price=150)

    purchase = client.post(f"/api/v1/cards/{card.card_id}/skins/skin-test/purchase", headers=_headers(101))
    wrong_card = client.post(
        f"/api/v1/cards/{other.card_id}/skins/activate",
        json={"skin_id": "skin-test"},
        headers=_headers(101),
    )
    activate = client.post(
        f"/api/v1/cards/{card.card_id}/skins/activate",
        json={"skin_id": "skin-test"},
        headers=_headers(101),
    )

    assert purchase.status_code == 200
    assert wrong_card.status_code == 409
    assert wrong_card.get_json()["error_code"] == "skin_not_owned"
    assert activate.status_code == 200
    assert client.get(f"/api/v1/cards/{card.card_id}/skins", headers=_headers(101)).get_json()["active_skin_id"] == "skin-test"


def test_fusion_preview_and_execute_consume_two_cards_atomically(hub_client):
    client, db = hub_client
    cards = db.get_player_cards(101)[:3]
    card_ids = [card.card_id for card in cards]
    for card_id in card_ids:
        db.set_player_card_rarity_override(101, card_id, "normal")
    ok, deck_id = miniapp.DeckSystem(db).create_deck(101, card_ids, "Fusion Deck")
    assert ok

    preview = client.post(
        "/api/v1/fusions/preview",
        json={"card_ids": card_ids, "retained_card_id": card_ids[0], "target_rarity": "epic"},
        headers=_headers(101),
    )
    executed = client.post(
        "/api/v1/fusions",
        json={"card_ids": card_ids, "retained_card_id": card_ids[0], "target_rarity": "epic"},
        headers=_headers(101),
    )

    assert preview.status_code == 200
    assert len(preview.get_json()["consumed_card_ids"]) == 2
    assert executed.status_code == 200
    assert executed.get_json()["data"]["card"]["rarity"] == "epic"
    assert len(db.get_player_cards(101)) == 2
    assert db.get_deck_by_id(deck_id)["is_valid"] == 0


def test_fusion_rejects_foreign_or_mixed_cards_without_consuming(hub_client):
    client, db = hub_client
    cards = db.get_player_cards(101)[:3]
    card_ids = [card.card_id for card in cards]
    before = len(db.get_player_cards(101))

    response = client.post(
        "/api/v1/fusions",
        json={"card_ids": card_ids, "retained_card_id": card_ids[0], "target_rarity": "legend"},
        headers=_headers(101),
    )

    assert response.status_code == 409
    assert len(db.get_player_cards(101)) == before
