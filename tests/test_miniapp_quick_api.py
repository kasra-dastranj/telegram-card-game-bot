from datetime import datetime, timedelta, timezone
import json

import pytest

from game_core import DatabaseManager
from core.models import Card, CardRarity
from systems.game_mode_system import GameModeSystem
import web.miniapp_api as miniapp


@pytest.fixture()
def quick_client(tmp_path, monkeypatch):
    test_db = DatabaseManager(str(tmp_path / "quick-api.db"))
    monkeypatch.setattr(miniapp, "db", test_db)
    monkeypatch.setattr(miniapp, "quick_modes", GameModeSystem(test_db))
    miniapp.app.config.update(TESTING=True, DEBUG=True)
    return miniapp.app.test_client(), miniapp.quick_modes


def _headers(user_id):
    return {"X-Debug-User-Id": str(user_id)}


def test_random_matchmaking_is_idempotent_and_connects_two_players(quick_client):
    client, _ = quick_client
    first = client.post(
        "/api/v1/quick/matchmaking",
        json={"variant": "normal"},
        headers=_headers(101),
    )
    retry = client.post(
        "/api/v1/quick/matchmaking",
        json={"variant": "normal"},
        headers=_headers(101),
    )
    assert first.status_code == retry.status_code == 201
    assert first.get_json()["request_id"] == retry.get_json()["request_id"]
    not_started = client.get(
        f"/api/v1/quick/matches/{first.get_json()['request_id']}",
        headers=_headers(101),
    )
    assert not_started.status_code == 409

    matched = client.post(
        "/api/v1/quick/matchmaking",
        json={"variant": "normal"},
        headers=_headers(202),
    )
    payload = matched.get_json()
    assert matched.status_code == 200
    assert payload["status"] == "active"
    assert payload["phase"] == "card_selection"
    assert payload["user_id"] == 202
    assert payload["opponent_id"] == 101
    assert "cards" not in payload
    assert "ability_choices" not in payload
    assert payload["opponent_card"] is None

    creator_view = client.get(
        f"/api/v1/quick/requests/{payload['request_id']}",
        headers=_headers(101),
    ).get_json()
    assert creator_view["opponent_id"] == 202
    assert creator_view["phase"] == "card_selection"


def test_invite_acceptance_and_non_participant_access_are_protected(quick_client):
    client, _ = quick_client
    created = client.post(
        "/api/v1/quick/invites",
        json={"variant": "normal"},
        headers=_headers(1),
    )
    invite = created.get_json()
    assert created.status_code == 201
    assert "?invite=" in invite["invite_url"]

    accepted = client.post(
        f"/api/v1/quick/invites/{invite['invite_token']}/accept",
        headers=_headers(2),
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["phase"] == "card_selection"

    outsider = client.get(
        f"/api/v1/quick/requests/{invite['request_id']}",
        headers=_headers(3),
    )
    assert outsider.status_code == 404


def test_polling_marks_expired_request_with_localized_message(quick_client):
    client, modes = quick_client
    waiting = client.post(
        "/api/v1/quick/matchmaking",
        json={"variant": "normal"},
        headers=_headers(7),
    ).get_json()
    expired_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    ).replace(microsecond=0).isoformat()
    conn = modes._connect()
    conn.execute(
        "UPDATE game_requests SET expires_at=? WHERE request_id=?",
        (expired_at, waiting["request_id"]),
    )
    conn.commit()
    conn.close()

    response = client.get(
        f"/api/v1/quick/requests/{waiting['request_id']}",
        headers=_headers(7),
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "expired"
    assert "منقضی" in payload["message"]


def test_polling_settles_an_expired_choice_phase(quick_client):
    client, modes = quick_client
    first = client.post(
        "/api/v1/quick/matchmaking", json={"variant": "normal"}, headers=_headers(31)
    ).get_json()
    client.post(
        "/api/v1/quick/matchmaking", json={"variant": "normal"}, headers=_headers(32)
    )
    state = modes.get_state(first["request_id"])
    state["deadline"] = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    ).replace(microsecond=0).isoformat()
    conn = modes._connect()
    conn.execute(
        "UPDATE game_match_states SET state_json=? WHERE request_id=?",
        (json.dumps(state), first["request_id"]),
    )
    conn.commit()
    conn.close()

    settled = client.get(
        f"/api/v1/quick/requests/{first['request_id']}", headers=_headers(31)
    ).get_json()
    assert settled["status"] == "completed"
    assert settled["phase"] == "completed"
    assert settled["report"]["forfeit"] is True
    assert settled["report"]["reason"] == "card_selection_timeout"


def test_quick_snapshot_exposes_conditional_arena_values(quick_client):
    client, modes = quick_client
    power_card = Card(
        card_id="power-card",
        name="Power Card",
        rarity=CardRarity.NORMAL,
        power=80,
        speed=50,
        iq=40,
        popularity=30,
        abilities=[],
        card_type="POWER_TYPE",
    )
    speed_card = Card(
        card_id="speed-card",
        name="Speed Card",
        rarity=CardRarity.NORMAL,
        power=60,
        speed=70,
        iq=50,
        popularity=40,
        abilities=[],
        card_type="SPEED_TYPE",
    )
    for card in (power_card, speed_card):
        assert modes.db.add_card(card)
    for user_id, card in ((41, speed_card), (42, power_card)):
        modes.db.get_or_create_player(user_id)
        assert modes.db.add_card_to_player(user_id, card.card_id)

    first = client.post(
        "/api/v1/quick/matchmaking", json={"variant": "normal"}, headers=_headers(41)
    ).get_json()
    client.post(
        "/api/v1/quick/matchmaking", json={"variant": "normal"}, headers=_headers(42)
    )
    request_id = first["request_id"]
    assert client.post(
        f"/api/v1/quick/matches/{request_id}/card",
        json={"card_id": speed_card.card_id},
        headers=_headers(41),
    ).status_code == 200
    assert client.post(
        f"/api/v1/quick/matches/{request_id}/card",
        json={"card_id": power_card.card_id},
        headers=_headers(42),
    ).status_code == 200

    state = modes.get_state(request_id)
    state["initial_arena"] = "desert"
    state["arena"] = "desert"
    conn = modes._connect()
    modes._save_state(conn, request_id, state)
    conn.commit()
    conn.close()

    snapshot = client.get(
        f"/api/v1/quick/requests/{request_id}", headers=_headers(41)
    ).get_json()

    assert snapshot["my_final_values"] == {
        "power": 60,
        "speed": 69,
        "iq": 50,
        "popularity": 40,
    }
    assert snapshot["my_arena_effects"] == [
        {"card_type": "speed", "stat": "speed", "delta": -1}
    ]
