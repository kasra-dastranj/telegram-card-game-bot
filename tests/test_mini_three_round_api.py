"""Two-player Mini App three-round flow and its player-scoped state."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from core.models import Card, CardRarity
from game_core import DatabaseManager
from systems.arena_registry import ArenaRegistry
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.game_mode_system import GameModeSystem
from systems.mini_three_round_system import MiniThreeRoundSystem
import web.miniapp_api as miniapp


def headers(user_id):
    return {"X-Debug-User-Id": str(user_id)}


@pytest.fixture()
def client_and_modes(tmp_path, monkeypatch):
    database = DatabaseManager(str(tmp_path / "three.db"))
    modes = GameModeSystem(database)
    arena_registry = ArenaRegistry(database)
    engine = MiniThreeRoundSystem(database, modes, arena_registry, BattleSystem3Rounds(database))
    monkeypatch.setattr(miniapp, "db", database)
    monkeypatch.setattr(miniapp, "quick_modes", modes)
    monkeypatch.setattr(miniapp, "mini_three_round", engine)
    miniapp.app.config.update(TESTING=True, DEBUG=True)
    for user_id, card_id, power in ((101, "three-a", 80), (202, "three-b", 80)):
        card = Card(card_id=card_id, name=f"Hero {user_id}", rarity=CardRarity.NORMAL,
                    power=power, speed=70, iq=60, popularity=50, abilities=[],
                    card_type="POWER_TYPE")
        assert database.add_card(card)
        database.get_or_create_player(user_id)
        assert database.add_card_to_player(user_id, card_id)
    return miniapp.app.test_client(), modes


def post(client, path, user_id, payload=None):
    return client.post(path, json=payload or {}, headers=headers(user_id))


def test_random_match_is_separate_from_quick_and_hides_cards(client_and_modes):
    client, _ = client_and_modes
    quick = post(client, "/api/v1/quick/matchmaking", 101, {"variant": "normal"}).get_json()
    first = post(client, "/api/v1/three-round/matchmaking", 101)
    assert first.status_code == 201
    assert first.get_json()["request_id"] != quick["request_id"]
    assert client.get(f"/api/v1/three-round/requests/{quick['request_id']}", headers=headers(101)).status_code == 404
    second = post(client, "/api/v1/three-round/matchmaking", 202)
    assert second.status_code == 200
    match = second.get_json()
    assert match["phase"] == "card_selection"
    assert match["opponent_card"] is None
    request_id = match["request_id"]
    assert client.get(f"/api/v1/quick/requests/{request_id}", headers=headers(101)).status_code == 404
    assert client.get(f"/api/v1/three-round/requests/{request_id}", headers=headers(303)).status_code == 404
    assert post(client, f"/api/v1/three-round/matches/{request_id}/card", 101, {"card_id": "three-b"}).status_code == 409
    selected = post(client, f"/api/v1/three-round/matches/{request_id}/card", 101, {"card_id": "three-a"})
    assert selected.status_code == 200
    assert selected.get_json()["opponent_card"] is None
    assert post(client, f"/api/v1/three-round/matches/{request_id}/card", 202, {"card_id": "three-b"}).status_code == 200
    revealed = client.get(f"/api/v1/three-round/requests/{request_id}", headers=headers(101)).get_json()
    assert revealed["opponent_card"]["card_id"] == "three-b"
    assert revealed["arena"]["arena_id"] == match["arena"]["arena_id"]


def test_invite_three_tie_and_unique_stats(client_and_modes):
    client, _ = client_and_modes
    invite = post(client, "/api/v1/three-round/invites", 101).get_json()
    assert "?three_invite=" in invite["invite_url"]
    token = invite["invite_token"]
    assert post(client, f"/api/v1/quick/invites/{token}/accept", 202).status_code == 404
    accepted = post(client, f"/api/v1/three-round/invites/{token}/accept", 202)
    assert accepted.status_code == 200
    request_id = invite["request_id"]
    for user_id, card_id in ((101, "three-a"), (202, "three-b")):
        assert post(client, f"/api/v1/three-round/matches/{request_id}/card", user_id, {"card_id": card_id}).status_code == 200
    for round_index, stat in enumerate(("power", "speed", "iq"), start=1):
        first = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 101, {"stat": stat})
        assert first.status_code == 200
        assert first.get_json()["last_round"] is None if round_index == 1 else first.get_json()["last_round"]["round"] == round_index - 1
        if round_index == 2:
            assert post(client, f"/api/v1/three-round/matches/{request_id}/stat", 101, {"stat": "power"}).status_code == 409
        second = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 202, {"stat": stat})
        assert second.status_code == 200
        assert second.get_json()["last_round"]["winner_id"] is None
    final = second.get_json()
    assert final["status"] == "completed"
    assert final["report"]["is_tie"] is True
    assert len(final["report"]["rounds"]) == 3


def test_two_round_wins_finish_early_and_preserve_calculation(client_and_modes):
    client, _ = client_and_modes
    first = post(client, "/api/v1/three-round/matchmaking", 101).get_json()
    post(client, "/api/v1/three-round/matchmaking", 202)
    request_id = first["request_id"]
    for user_id, card_id in ((101, "three-a"), (202, "three-b")):
        post(client, f"/api/v1/three-round/matches/{request_id}/card", user_id, {"card_id": card_id})
    for mine, rival in (("power", "popularity"), ("speed", "iq")):
        hidden = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 101, {"stat": mine}).get_json()
        assert hidden["opponent_stat_selected"] is False
        final = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 202, {"stat": rival}).get_json()
        last = final["last_round"]
        assert last["winner_id"] == 101
        assert last["values"]["101"]["total"] == last["values"]["101"]["base"] + last["values"]["101"]["boost"]
    assert final["status"] == "completed"
    assert final["report"]["winner_id"] == 101
    assert len(final["report"]["rounds"]) == 2


def test_deadline_forfeits_to_player_who_chose(client_and_modes):
    client, modes = client_and_modes
    first = post(client, "/api/v1/three-round/matchmaking", 101).get_json()
    post(client, "/api/v1/three-round/matchmaking", 202)
    request_id = first["request_id"]
    post(client, f"/api/v1/three-round/matches/{request_id}/card", 101, {"card_id": "three-a"})
    state = modes.get_state(request_id)
    state["deadline"] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)).isoformat()
    with modes._connect() as conn:
        modes._save_state(conn, request_id, state)
    final = client.get(f"/api/v1/three-round/requests/{request_id}", headers=headers(101)).get_json()
    assert final["status"] == "completed"
    assert final["report"]["winner_id"] == 101
    assert final["report"]["forfeit"] is True
