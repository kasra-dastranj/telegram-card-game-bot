import io
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from bot.handlers.battle import BattleHandlersMixin
from core.database import DatabaseManager
from migrations.migrate_arena_registry import migrate
from systems.arena_registry import ArenaRegistry, ArenaValidationError
from systems.battle_system_3rounds import BattleSystem3Rounds
from web.web_api import WebAPI


def quick_payload(*, miniapp=False, active_from=None, active_until=None):
    return {
        "name_fa": "زمین آزمایشی",
        "name_en": "Test Arena",
        "description_fa": "توضیح کامل زمین آزمایشی.",
        "emoji": "⚡",
        "tags": ["test"],
        "profiles": {
            "quick": {
                "enabled": True,
                "selection_weight": 100,
                "active_from": active_from,
                "active_until": active_until,
                "rules": {
                    "effects": [{"type": "stat_modifier", "condition": {"card_type": "power"}, "target_stat": "power", "delta": 2}],
                    "disabled_stats": [],
                    "abilities_enabled": True,
                    "passives_enabled": True,
                },
            }
        },
        "platform": {"telegram": {"enabled": True}, "miniapp": {"enabled": miniapp}},
    }


def test_migration_empty_repeat_and_dry_run_are_safe(tmp_path):
    empty = tmp_path / "empty.db"
    first = migrate(str(empty))
    second = migrate(str(empty))
    assert first["created"] == 10 and first["different"] == 0
    assert second["created"] == 0 and second["skipped"] == 10

    untouched = tmp_path / "dry.db"
    preview = migrate(str(untouched), dry_run=True)
    assert preview["dry_run"] and preview["created"] == 10
    assert not untouched.exists()


def test_publish_validation_rejects_empty_modes_bad_shape_and_naive_dates(tmp_path):
    registry = ArenaRegistry(DatabaseManager(str(tmp_path / "validation.db")))
    payload = quick_payload()
    payload["profiles"]["quick"]["enabled"] = False
    registry.create_draft("no_modes", payload, "test")
    with pytest.raises(ArenaValidationError) as error:
        registry.publish("no_modes", "test", 1)
    assert {item["code"] for item in error.value.issues} >= {"no_mode_enabled"}

    malformed = quick_payload()
    malformed["profiles"]["quick"]["rules"]["effects"] = ["not-an-object"]
    issues = registry.validate_payload("bad_effect", malformed)
    assert any(item["code"] == "invalid_quick_effect" for item in issues)

    dated = quick_payload(active_from="2026-01-01T10:00:00")
    assert any(item["code"] == "invalid_datetime" for item in registry.validate_payload("bad_date", dated))
    assert any(item["code"] == "arena_id_invalid" for item in registry.validate_payload("ab", quick_payload()))


def test_draft_never_enters_runtime_but_admin_preview_can_render_it(tmp_path):
    registry = ArenaRegistry(DatabaseManager(str(tmp_path / "draft.db")))
    draft = registry.create_draft("draft_preview", quick_payload(), "test")
    assert registry.runtime("draft_preview", "quick", "telegram", draft["version"]) is None
    preview = registry.preview("draft_preview", "quick", "telegram")
    assert preview["arena_id"] == "draft_preview"
    assert preview["version"] == draft["version"]


def test_time_windows_and_published_media_are_immutable(tmp_path):
    registry = ArenaRegistry(DatabaseManager(str(tmp_path / "media.db")))
    payload = quick_payload(active_from="2099-01-01T00:00:00+03:30")
    draft = registry.create_draft("future_arena", payload, "test")
    media = registry.add_media("future_arena", draft["version"], "miniapp", "background", "/future.webp", "image/webp", 100, "a" * 64, 720, 1280, "test")
    assert media["readiness_status"] == "ready"
    published = registry.publish("future_arena", "test", draft["draft_revision"])
    assert registry.list_active("quick", "telegram", "2028-01-01T00:00:00Z") == [] or all(item["arena_id"] != "future_arena" for item in registry.list_active("quick", "telegram", "2028-01-01T00:00:00Z"))
    with pytest.raises(ValueError, match="published_media_immutable"):
        registry.add_media("future_arena", published["version"], "miniapp", "background", "/other.webp", "image/webp", 100, "b" * 64, 720, 1280, "test")


def test_foreign_keys_and_dependency_json_parsing(tmp_path):
    db = DatabaseManager(str(tmp_path / "deps.db"))
    registry = ArenaRegistry(db)
    conn = registry._connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM arenas WHERE arena_id='city'")
            conn.commit()
        conn.rollback()
        conn.execute("CREATE TABLE IF NOT EXISTS card_mode_metadata(card_id TEXT PRIMARY KEY, passive TEXT)")
        conn.execute("INSERT OR REPLACE INTO card_mode_metadata(card_id,passive) VALUES (?,?)", ("x", '{"condition": true, "arena": "city"}'))
        conn.commit()
    finally:
        conn.close()
    assert registry.list_dependencies("city")["card_passives"] == 1


def test_admin_auth_is_fail_closed_and_draft_preview_is_authenticated(tmp_path, monkeypatch):
    monkeypatch.delenv("ARENA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    monkeypatch.delenv("ARENA_ADMIN_LOCAL_DEV", raising=False)
    api = WebAPI(DatabaseManager(str(tmp_path / "admin.db")))
    api.app.config.update(TESTING=True)
    client = api.app.test_client()
    assert client.get("/api/arenas").status_code == 403

    monkeypatch.setenv("ARENA_ADMIN_TOKEN", "write-secret")
    monkeypatch.setenv("ARENA_ADMIN_PUBLISH_TOKEN", "publish-secret")
    api = WebAPI(DatabaseManager(str(tmp_path / "admin-secure.db")))
    api.app.config.update(TESTING=True)
    client = api.app.test_client()
    headers = {"X-Admin-Token": "write-secret"}
    body = {"arena_id": "draft_api", **quick_payload()}
    created = client.post("/api/arenas", json=body, headers=headers)
    assert created.status_code == 201
    preview = client.get("/api/arenas/draft_api/preview?mode=quick&platform=telegram", headers=headers)
    assert preview.status_code == 200
    revision = created.get_json()["arena"]["draft_revision"]
    assert client.post("/api/arenas/draft_api/publish", json={"draft_revision": revision}, headers=headers).status_code == 403
    assert client.post("/api/arenas/draft_api/publish", json={"draft_revision": revision}, headers={"X-Admin-Token": "publish-secret"}).status_code == 200


def test_arena_upload_decodes_webp_and_rejects_wrong_dimensions(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_ADMIN_TOKEN", "secret")
    monkeypatch.setenv("MINIAPP_ARENA_MEDIA_DIR", str(tmp_path / "media"))
    api = WebAPI(DatabaseManager(str(tmp_path / "upload.db")))
    api.app.config.update(TESTING=True)
    client = api.app.test_client()
    headers = {"X-Admin-Token": "secret"}
    created = client.post("/api/arenas", json={"arena_id": "media_api", **quick_payload()}, headers=headers).get_json()["arena"]

    def webp(width, height):
        stream = io.BytesIO()
        Image.new("RGB", (width, height), "#123456").save(stream, format="WEBP")
        stream.seek(0)
        return stream

    bad = client.post("/api/arenas/media_api/media", data={"version": str(created["version"]), "background": (webp(300, 300), "bad.webp")}, headers=headers)
    assert bad.status_code == 400 and bad.get_json()["error"] == "invalid_media_dimensions"
    good = client.post("/api/arenas/media_api/media", data={"version": str(created["version"]), "background": (webp(720, 1280), "good.webp")}, headers=headers)
    assert good.status_code == 201
    assert good.get_json()["media"]["width"] == 720


def test_classic_cards_do_not_trigger_deck_resolver_and_rule_flags_work(tmp_path):
    handler = BattleHandlersMixin()
    handler._fight_arena_mode = lambda _fight_id: "three_round"
    card = SimpleNamespace(card_id="c", power=10, speed=10, iq=10, popularity=10, card_type="SPEED_TYPE")
    assert not handler._should_use_deck_resolver("fight", card, card)
    handler._fight_arena_mode = lambda _fight_id: "deck"
    assert handler._should_use_deck_resolver("fight", card, card)

    battle = BattleSystem3Rounds(DatabaseManager(str(tmp_path / "battle.db")))
    snapshot = {"boost_stat": "power", "boost_amount": 7, "requires_card_type_match": False}
    assert battle.calculate_boost(card, "power_arena", "power", snapshot) == 7
    deck_snapshot = {"compare_stat": "power", "trait_ranks": [], "stat_tiebreak_enabled": False}
    opponent = SimpleNamespace(card_id="o", power=1, speed=1, iq=1, popularity=1)
    result = battle.resolve_deck_cards(card, opponent, "power_arena", deck_snapshot)
    assert result["winner"] is None and result["reason"] == "tie"


def test_miniapp_keeps_versioned_arena_media_while_placing_cards():
    source = (Path(__file__).parents[1] / "frontend" / "game" / "src" / "BattleScene.ts").read_text(encoding="utf-8")
    place_cards = source.split("private placeCards", 1)[1].split("private placeQuickCards", 1)[0]
    assert "this.setArena(fight.arena);" in place_cards
    assert "fight.arena.arena_id" not in place_cards
