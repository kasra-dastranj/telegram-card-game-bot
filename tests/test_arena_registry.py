import copy

import pytest

from core.database import DatabaseManager
from systems.arena_registry import ArenaRegistry, ArenaValidationError
from systems.game_mode_system import GameModeSystem
from web.web_api import WebAPI


def _quick_payload(name="شهر طوفانی", miniapp=False):
    return {
        "name_fa": name,
        "name_en": "Storm City",
        "description_fa": "رعد و برق میدان را روشن می‌کند.",
        "emoji": "⚡",
        "profiles": {
            "quick": {
                "enabled": True,
                "selection_weight": 25,
                "rules": {
                    "effects": [{"type": "stat_modifier", "condition": {"card_type": "power"}, "target_stat": "power", "delta": 2, "priority": 0}],
                    "disabled_stats": [], "abilities_enabled": True, "passives_enabled": True,
                },
            },
        },
        "platform": {"telegram": {"enabled": True}, "miniapp": {"enabled": miniapp}},
    }


def test_seed_is_idempotent_and_preserves_legacy_pools(tmp_path):
    registry = ArenaRegistry(DatabaseManager(str(tmp_path / "arena.db")))
    assert registry.seed_legacy_arenas()["created"] == 0
    assert {item["arena_id"] for item in registry.list_active("quick", "telegram")} == {
        "city", "desert", "ice", "forest", "silent_temple", "null_zone"
    }
    power = registry.runtime("power_arena", "three_round", "telegram")
    assert power["boost_stat"] == "power"
    assert power["boost_amount"] == 8


def test_publish_is_versioned_and_existing_snapshot_is_stable(tmp_path):
    registry = ArenaRegistry(DatabaseManager(str(tmp_path / "arena.db")))
    registry.create_draft("storm_city", _quick_payload(), "test")
    version_one = registry.publish("storm_city", "test", 1)
    snapshot_one = registry.snapshot_for_match("storm_city", "quick")
    draft = registry.create_next_draft("storm_city", "test")
    payload = _quick_payload("شهر طوفانی نسخه دو")
    payload["profiles"]["quick"]["rules"]["effects"][0]["delta"] = 3
    registry.update_draft("storm_city", payload, "test", draft["draft_revision"])
    version_two = registry.publish("storm_city", "test", 2)
    assert version_one["version"] == 1 and version_two["version"] == 2
    assert snapshot_one["version"] == 1
    assert snapshot_one["rules"]["effects"][0]["delta"] == 2
    assert registry.snapshot_for_match("storm_city", "quick")["rules"]["effects"][0]["delta"] == 3


def test_miniapp_publish_requires_ready_background(tmp_path):
    registry = ArenaRegistry(DatabaseManager(str(tmp_path / "arena.db")))
    registry.create_draft("media_gate", _quick_payload(miniapp=True), "test")
    with pytest.raises(ArenaValidationError) as error:
        registry.publish("media_gate", "test", 1)
    assert any(issue["code"] == "miniapp_media_not_ready" for issue in error.value.issues)


def test_quick_match_records_immutable_arena_snapshot(tmp_path):
    db = DatabaseManager(str(tmp_path / "arena.db"))
    modes = GameModeSystem(db)
    request = modes.create_invite(1, "quick", "normal")
    assert modes.accept_invite(request["invite_token"], 2)[0]
    state = modes.start_quick_match(request["request_id"])
    modes._advance_quick_after_cards(state)
    assert state["arena_snapshot"]["version"] == 1
    assert state["arena_snapshot"]["arena_id"] == state["arena"]
    before = copy.deepcopy(state["arena_snapshot"])
    modes._store_arena_snapshot(state, modes._random_arena(exclude=state["arena"]), replaced=True)
    assert state["arena_history"] == [before]


def test_arena_admin_endpoints_create_preview_and_publish(tmp_path, monkeypatch):
    monkeypatch.delenv("ARENA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    monkeypatch.setenv("ARENA_ADMIN_LOCAL_DEV", "1")
    api = WebAPI(DatabaseManager(str(tmp_path / "admin-arena.db")))
    api.app.config.update(TESTING=True)
    client = api.app.test_client()

    arena_page = client.get("/arenas")
    assert arena_page.status_code == 200
    arena_page.close()
    payload = _quick_payload()
    payload["arena_id"] = "storm_city"
    created = client.post("/api/arenas", json=payload)
    assert created.status_code == 201, created.get_json()
    draft = created.get_json()["arena"]
    published = client.post("/api/arenas/storm_city/publish", json={"draft_revision": draft["draft_revision"]})
    assert published.status_code == 200, published.get_json()
    preview = client.get("/api/arenas/storm_city/preview?mode=quick&platform=telegram")
    assert preview.status_code == 200
    assert preview.get_json()["arena"]["arena_id"] == "storm_city"
    remote_write = client.post("/api/arenas", json=payload, environ_base={"REMOTE_ADDR": "10.0.0.7"})
    assert remote_write.status_code == 403
