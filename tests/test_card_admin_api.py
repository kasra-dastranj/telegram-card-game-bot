from io import BytesIO

from core.database import DatabaseManager
import web.web_api as web_api_module
from web.web_api import WebAPI


def _payload(**overrides):
    data = {
        "name": "Admin Test Hero",
        "rarity": "epic",
        "card_type": "IQ_TYPE",
        "power": 64,
        "speed": 72,
        "iq": 91,
        "popularity": 58,
        "abilities": ["تمرکز", "تحلیل"],
        "card_effects": ["drain"],
        "dialogs": ["شروع کنیم", "تمام شد"],
        "biography": "کارت تست پنل مدیریت",
        "image_path": "assets/card_images/admin-test.webp",
        "traits": ["hero", "smart"],
        "series": "Admin Suite",
        "hidden_stats": {"funny": 33, "leadership": 88},
        "passive": {
            "name": "تمرکز شهری",
            "condition": {"arena": "city"},
            "effect": {"stat": "iq", "delta": 7},
        },
        "photo_file_id": "telegram-photo-id",
        "sticker_file_id": "telegram-sticker-id",
    }
    data.update(overrides)
    return data


def _client(tmp_path):
    db = DatabaseManager(str(tmp_path / "admin.db"))
    api = WebAPI(db)
    api.app.config.update(TESTING=True)
    return db, api.app.test_client()


def test_card_admin_create_read_and_update_current_schema(tmp_path):
    db, client = _client(tmp_path)

    home = client.get("/")
    assert home.status_code == 200
    assert b"<!doctype html>" in home.data.lower()
    home.close()

    created = client.post("/api/cards", json=_payload())
    assert created.status_code == 201, created.get_json()
    created_card = created.get_json()["card"]
    card_id = created_card["id"]
    assert created_card["traits"] == ["hero", "smart"]
    assert created_card["hidden_stats"]["leadership"] == 88
    assert created_card["passive"]["condition"] == {"arena": "city"}
    assert created_card["photo_file_id"] == "telegram-photo-id"

    stored = db.get_card_by_name("admin test hero")
    assert stored is not None
    assert stored.card_id == card_id
    assert stored.card_effects == ["drain"]

    updated_payload = _payload(
        name="Admin Test Hero Updated",
        rarity="legend",
        power=79,
        traits=["hero", "leader"],
        series="Current Version",
        hidden_stats={"charisma": 93},
        passive={
            "name": "رهبری",
            "condition": {"opponent_trait": "villain"},
            "effect": {"stat": "popularity", "delta": 9},
        },
        photo_file_id="",
    )
    updated = client.put(f"/api/cards/{card_id}", json=updated_payload)
    assert updated.status_code == 200, updated.get_json()
    updated_card = updated.get_json()["card"]
    assert updated_card["name"] == "Admin Test Hero Updated"
    assert updated_card["power"] == 79
    assert updated_card["traits"] == ["hero", "leader"]
    assert updated_card["series"] == "Current Version"
    assert updated_card["photo_file_id"] == ""
    assert updated_card["sticker_file_id"] == "telegram-sticker-id"

    listing = client.get("/api/cards")
    assert listing.status_code == 200
    assert listing.get_json()["cards"][0] == updated_card


def test_card_admin_rejects_invalid_current_mode_metadata(tmp_path):
    _, client = _client(tmp_path)

    bad_hidden = client.post(
        "/api/cards",
        json=_payload(name="Bad Hidden", hidden_stats={"funny": 101}),
    )
    assert bad_hidden.status_code == 400

    bad_passive = client.post(
        "/api/cards",
        json=_payload(
            name="Bad Passive",
            passive={
                "condition": {"arena": "not-an-arena"},
                "effect": {"stat": "iq", "delta": 5},
            },
        ),
    )
    assert bad_passive.status_code == 400

    multiple_conditions = client.post(
        "/api/cards",
        json=_payload(
            name="Too Many Conditions",
            passive={
                "condition": {"arena": "city", "opponent_trait": "villain"},
                "effect": {"stat": "iq", "delta": 5},
            },
        ),
    )
    assert multiple_conditions.status_code == 400


def test_card_admin_media_uploads_use_current_asset_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api_module, "PROJECT_ROOT", tmp_path)
    _, client = _client(tmp_path)

    image = client.post(
        "/api/upload_image",
        data={"card_name": "Media Hero", "image": (BytesIO(b"fake-image"), "hero.webp")},
        content_type="multipart/form-data",
    )
    assert image.status_code == 200, image.get_json()
    assert (tmp_path / image.get_json()["image_path"]).is_file()

    sticker = client.post(
        "/api/upload_sticker",
        data={"card_name": "قهرمان شب", "sticker": (BytesIO(b"fake-webp"), "sticker.webp")},
        content_type="multipart/form-data",
    )
    assert sticker.status_code == 200, sticker.get_json()
    assert sticker.get_json()["filename"] == "قهرمان_شب.webp"
    assert (tmp_path / sticker.get_json()["sticker_path"]).is_file()

    wrong_sticker = client.post(
        "/api/upload_sticker",
        data={"card_name": "Wrong", "sticker": (BytesIO(b"png"), "sticker.png")},
        content_type="multipart/form-data",
    )
    assert wrong_sticker.status_code == 400


def test_card_admin_keeps_three_independent_forms_per_character(tmp_path):
    db, client = _client(tmp_path)
    created = client.post("/api/cards", json=_payload(name="Variant Hero", rarity="epic"))
    assert created.status_code == 201, created.get_json()
    card = created.get_json()["card"]
    card_id = card["id"]
    assert [variant["rarity"] for variant in card["variants"]] == ["normal", "epic", "legend"]

    legend_payload = _payload(
        name="Variant Hero", rarity="legend", power=99, speed=89, iq=96,
        popularity=94, image_path="assets/card_images/variant-hero_legend.webp",
        photo_file_id="legend-photo", sticker_file_id="legend-sticker",
        passive={
            "name": "اوج قهرمانی",
            "condition": {"arena": "city"},
            "effect": {"stat": "popularity", "delta": 1},
        },
    )
    updated = client.put(f"/api/cards/{card_id}/variants/legend", json=legend_payload)
    assert updated.status_code == 200, updated.get_json()
    variants = {variant["rarity"]: variant for variant in updated.get_json()["card"]["variants"]}
    assert variants["legend"]["power"] == 99
    assert variants["legend"]["image_path"].endswith("_legend.webp")
    assert variants["legend"]["photo_file_id"] == "legend-photo"
    assert variants["epic"]["power"] == 64  # original form did not change

    db.get_or_create_player(7001, first_name="Variant Tester")
    assert db.add_card_to_player(7001, card_id)
    assert db.set_player_card_rarity_override(7001, card_id, "legend")
    owned = db.get_card_by_id_for_player(card_id, 7001)
    assert owned.rarity.value == "legend"
    assert owned.power == 99
