from io import BytesIO
import sqlite3
import pytest

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


def _family(**overrides):
    variants = {}
    for rarity, power in (("normal", 31), ("epic", 62), ("legend", 93)):
        variants[rarity] = {
            "power": power, "speed": power + 1, "iq": power + 2,
            "popularity": power + 3, "card_type": "POWER_TYPE",
            "abilities": [rarity], "card_effects": ["reflect"] if rarity == "legend" else [],
            "passive": {}, "image_path": f"assets/card_images/family_{rarity}.webp",
            "photo_file_id": f"photo-{rarity}", "sticker_file_id": f"sticker-{rarity}",
        }
    data = {"name": "Family Hero", "biography": "سه فرم", "dialogs": ["پیروزی"],
            "traits": ["hero"], "series": "Family", "hidden_stats": {"funny": 44},
            "variants": variants}
    data.update(overrides)
    return data


def test_card_admin_family_creates_and_updates_all_forms_atomically(tmp_path):
    db, client = _client(tmp_path)
    source = _family()
    source["variants"]["normal"]["passive"] = {
        "name": "Normal only", "condition": {"arena": "city"},
        "effect": {"stat": "power", "delta": 3},
    }
    created = client.post("/api/cards/family", json=source)
    assert created.status_code == 201, created.get_json()
    card = created.get_json()["card"]
    card_id = card["id"]
    assert card["rarity"] == "normal"
    assert card["power"] == 31
    variants = {form["rarity"]: form for form in card["variants"]}
    assert {rarity: form["power"] for rarity, form in variants.items()} == {
        "normal": 31, "epic": 62, "legend": 93}
    assert variants["legend"]["photo_file_id"] == "photo-legend"
    assert variants["epic"]["abilities"] == ["epic"]
    assert variants["legend"]["card_effects"] == ["reflect"]
    assert web_api_module.GameModeSystem(db).get_card_metadata(card_id, "normal")["passive"]["name"] == "Normal only"
    assert web_api_module.GameModeSystem(db).get_card_metadata(card_id, "epic")["passive"] == {}
    assert len({form["variant_id"] for form in variants.values()}) == 3

    db.get_or_create_player(7002, first_name="Family Tester")
    assert db.add_card_to_player(7002, card_id)
    assert db.set_player_card_rarity_override(7002, card_id, "legend")
    changed = _family(name="Family Hero Renamed")
    changed["variants"]["legend"]["power"] = 96
    changed["variants"]["normal"]["image_path"] = "assets/card_images/new_normal.webp"
    updated = client.put(f"/api/cards/{card_id}/family", json=changed)
    assert updated.status_code == 200, updated.get_json()
    after = {form["rarity"]: form for form in updated.get_json()["card"]["variants"]}
    assert after["legend"]["power"] == 96
    assert after["legend"]["variant_id"] == variants["legend"]["variant_id"]
    assert after["normal"]["photo_file_id"] == ""  # stale Telegram media is cleared
    assert after["epic"]["photo_file_id"] == "photo-epic"
    assert db.get_card_by_id_for_player(card_id, 7002).power == 96


def test_card_admin_family_rejects_incomplete_form_without_partial_write(tmp_path):
    _, client = _client(tmp_path)
    family = _family()
    family["variants"]["epic"]["iq"] = ""
    response = client.post("/api/cards/family", json=family)
    assert response.status_code == 400
    assert "epic" in response.get_json()["error"]
    assert client.get("/api/cards").get_json()["count"] == 0

    valid = client.post("/api/cards/family", json=_family()).get_json()["card"]
    before = valid["variants"]
    family = _family()
    family["variants"]["normal"]["power"] = 88
    family["variants"]["legend"]["passive"] = {
        "condition": {"arena": "unknown_arena"},
        "effect": {"stat": "power", "delta": 5},
    }
    response = client.put(f"/api/cards/{valid['id']}/family", json=family)
    assert response.status_code == 400
    after = client.get("/api/cards").get_json()["cards"][0]["variants"]
    assert [(form["rarity"], form["power"]) for form in after] == [
        (form["rarity"], form["power"]) for form in before]
    with sqlite3.connect(str(tmp_path / "admin.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM card_variants").fetchone()[0] == 3


def test_card_admin_editor_options_include_existing_content(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api_module, "PROJECT_ROOT", tmp_path)
    image_dir = tmp_path / "assets" / "card_images"
    image_dir.mkdir(parents=True)
    (image_dir / "family.webp").write_bytes(b"fake")
    _, client = _client(tmp_path)
    created = client.post("/api/cards/family", json=_family(traits=["hero", "شکارچی سایه‌ها"]))
    assert created.status_code == 201, created.get_json()
    assert created.get_json()["card"]["traits"] == ["hero", "شکارچی سایه‌ها"]
    response = client.get("/api/card-editor/options")
    assert response.status_code == 200, response.get_json()
    options = response.get_json()
    assert "hero" in options["traits"]
    assert "شکارچی سایه‌ها" in options["traits"]
    assert "Family" in options["series"]
    assert "Family Hero" in options["names"]
    assert "assets/card_images/family.webp" in options["images"]
    assert "city" in options["arenas"]


def test_trait_registration_persists_without_saving_a_card(tmp_path):
    db, client = _client(tmp_path)
    response = client.post('/api/card-editor/traits', json={'name': '  شکارچی سایه‌ها  '})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['trait'] == 'شکارچی سایه‌ها'
    assert client.get('/api/cards').get_json()['count'] == 0
    restarted = WebAPI(DatabaseManager(db.db_path)).app.test_client()
    assert 'شکارچی سایه‌ها' in restarted.get('/api/card-editor/options').get_json()['traits']
    first = restarted.post('/api/card-editor/traits', json={'name': 'Shadow Hunter'}).get_json()
    second = restarted.post('/api/card-editor/traits', json={'name': ' shadow HUNTER '}).get_json()
    assert second['trait'] == first['trait'] == 'Shadow Hunter'
    assert second['traits'].count('Shadow Hunter') == 1
    assert 'shadow HUNTER' not in second['traits']


@pytest.mark.parametrize('mode', ['family', 'card', 'variant'])
def test_trait_survives_removal_from_last_card_restart_and_card_deletion(tmp_path, mode):
    db, client = _client(tmp_path)
    trait = 'تریت دائمی مخصوص تست'
    payload = _family(traits=[trait]) if mode == 'family' else _payload(traits=[trait])
    created = client.post('/api/cards/family' if mode == 'family' else '/api/cards', json=payload)
    assert created.status_code == 201, created.get_json()
    card_id = created.get_json()['card']['id']
    endpoint = f'/api/cards/{card_id}'
    if mode == 'family':
        endpoint += '/family'
    elif mode == 'variant':
        endpoint += '/variants/legend'
    payload['traits'] = []
    removed = client.put(endpoint, json=payload)
    assert removed.status_code == 200, removed.get_json()
    if mode == 'variant':
        assert removed.get_json()['variant']['traits'] == []
        assert removed.get_json()['card']['traits'] == [trait]  # Epic was not edited.
    else:
        assert removed.get_json()['card']['traits'] == []
    restarted = WebAPI(DatabaseManager(db.db_path)).app.test_client()
    assert trait in restarted.get('/api/card-editor/options').get_json()['traits']
    another = restarted.post('/api/cards', json=_payload(name='Another Hero', traits=[trait]))
    assert another.status_code == 201, another.get_json()
    assert another.get_json()['card']['traits'] == [trait]
    assert restarted.delete(f"/api/cards/{another.get_json()['card']['id']}").status_code == 200
    assert restarted.delete(f'/api/cards/{card_id}').status_code == 200
    assert trait in WebAPI(db).app.test_client().get('/api/card-editor/options').get_json()['traits']


@pytest.mark.parametrize('body', [None, [], {}, {'name': ''}, {'name': '   '},
                                  {'name': 12}, {'name': ['wrong']},
                                  {'name': 'a' * 101}, {'name': 'bad\x00trait'}])
def test_trait_registration_rejects_invalid_name_without_changing_vocabulary(tmp_path, body):
    _, client = _client(tmp_path)
    before = client.get('/api/card-editor/options').get_json()['traits']
    response = client.post('/api/card-editor/traits', json=body)
    assert response.status_code == 400
    assert client.get('/api/card-editor/options').get_json()['traits'] == before


def test_trait_migration_backfills_legacy_database_on_copy_then_idempotently(tmp_path):
    from migrations.migrate_card_trait_registry import copy_database, apply_migration
    db, client = _client(tmp_path)
    created = client.post('/api/cards/family', json=_family(traits=['تریت قدیمی']))
    assert created.status_code == 201
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('DROP TABLE card_trait_registry')
        before_cards = conn.execute('SELECT * FROM cards').fetchall()
        before_metadata = conn.execute('SELECT * FROM card_mode_metadata').fetchall()
    preview = copy_database(db.db_path, tmp_path / 'preview.db')
    assert apply_migration(preview) == 11
    assert apply_migration(preview) == 11
    with sqlite3.connect(db.db_path) as original, sqlite3.connect(str(preview)) as copy:
        assert not original.execute("SELECT 1 FROM sqlite_master WHERE name='card_trait_registry'").fetchone()
        assert copy.execute('SELECT * FROM cards').fetchall() == before_cards
        assert copy.execute('SELECT * FROM card_mode_metadata').fetchall() == before_metadata
        assert copy.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    with pytest.raises(FileExistsError):
        copy_database(db.db_path, preview)
    backup = copy_database(db.db_path, tmp_path / 'backup.db')
    assert backup.is_file()
    assert apply_migration(db.db_path) == 11
    restarted = WebAPI(db).app.test_client()
    assert 'تریت قدیمی' in restarted.get('/api/card-editor/options').get_json()['traits']


def test_family_traits_are_independent_after_save_restart_and_removal(tmp_path):
    db, client = _client(tmp_path)
    family = _family()
    family.pop('traits')
    expected = {'normal': ['یخ'], 'epic': ['یخ', 'نینجا'], 'legend': ['یخ', 'نینجا', 'رهبر']}
    for rarity, traits in expected.items():
        family['variants'][rarity]['traits'] = traits
    created = client.post('/api/cards/family', json=family)
    assert created.status_code == 201, created.get_json()
    card_id = created.get_json()['card']['id']
    client = WebAPI(DatabaseManager(db.db_path)).app.test_client()
    stored = client.get('/api/cards').get_json()['cards'][0]
    assert {v['rarity']: v['traits'] for v in stored['variants']} == expected
    assert stored['traits'] == expected['normal']
    # Empty Normal is intentional; it must not inherit Epic or the legacy value.
    family['variants']['normal']['traits'] = []
    family['variants']['epic']['traits'] = ['نینجا']
    updated = client.put(f'/api/cards/{card_id}/family', json=family)
    assert updated.status_code == 200, updated.get_json()
    expected.update(normal=[], epic=['نینجا'])
    restarted = WebAPI(DatabaseManager(db.db_path)).app.test_client()
    assert {v['rarity']: v['traits'] for v in restarted.get('/api/cards').get_json()['cards'][0]['variants']} == expected
    assert set(sum(expected.values(), []) + ['یخ']) <= set(restarted.get('/api/card-editor/options').get_json()['traits'])
    # Invalid traits in one form must roll back the entire family edit.
    family['variants']['normal']['traits'] = ['must not be stored']
    family['variants']['legend']['traits'] = {'bad': True}
    assert restarted.put(f'/api/cards/{card_id}/family', json=family).status_code == 400
    assert {v['rarity']: v['traits'] for v in db.get_card_variants(card_id)} == expected


def test_single_form_edit_keeps_legacy_traits_on_other_forms(tmp_path):
    db, client = _client(tmp_path)
    card_id = client.post('/api/cards', json=_payload(traits=['legacy'])).get_json()['card']['id']
    expected = {rarity: ['legacy'] for rarity in ('normal', 'epic', 'legend')}
    for rarity in ('normal', 'epic', 'legend'):
        response = client.put(f'/api/cards/{card_id}/variants/{rarity}', json=_payload(traits=[rarity]))
        assert response.status_code == 200, response.get_json()
        expected[rarity] = [rarity]
        assert {v['rarity']: v['traits'] for v in db.get_card_variants(card_id)} == expected
    # Updating stats without traits must retain the explicit form traits.
    form = db.get_card_variant(card_id, 'epic')
    form.pop('traits')
    db.save_card_variant(card_id, 'epic', form)
    assert db.get_card_variant(card_id, 'epic')['traits'] == ['epic']


def test_legacy_card_edit_only_updates_traits_of_its_target_form(tmp_path):
    db, client = _client(tmp_path)
    card_id = client.post('/api/cards', json=_payload(traits=['legacy'])).get_json()['card']['id']
    updated = client.put(f'/api/cards/{card_id}', json=_payload(traits=['new epic']))
    assert updated.status_code == 200, updated.get_json()
    assert updated.get_json()['card']['traits'] == ['new epic']
    assert {v['rarity']: v['traits'] for v in db.get_card_variants(card_id)} == {
        'normal': ['legacy'], 'epic': ['new epic'], 'legend': ['legacy']}


def test_registry_backfill_includes_trait_only_stored_on_one_form(tmp_path):
    from migrations.migrate_card_variant_traits import apply_migration
    db, client = _client(tmp_path)
    family = _family(traits=[])
    family['variants']['legend']['traits'] = ['فقط لجند']
    card_id = client.post('/api/cards/family', json=family).get_json()['card']['id']
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT traits FROM card_mode_metadata WHERE card_id=?', (card_id,)).fetchone() == ('[]',)
        conn.execute('DROP TABLE card_trait_registry')
    apply_migration(db.db_path)
    assert 'فقط لجند' in WebAPI(db).app.test_client().get('/api/card-editor/options').get_json()['traits']
    form = db.get_card_variant(card_id, 'legend')
    db.save_card_variant(card_id, 'legend', dict(form, traits=[]))
    restarted = WebAPI(DatabaseManager(db.db_path)).app.test_client()
    assert 'فقط لجند' in restarted.get('/api/card-editor/options').get_json()['traits']


def test_form_traits_migration_preserves_legacy_rows_and_explicit_empty(tmp_path):
    from migrations.migrate_card_variant_traits import apply_migration, copy_database
    db, client = _client(tmp_path)
    card_id = client.post('/api/cards', json=_payload(traits=['قدیمی'])).get_json()['card']['id']
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('ALTER TABLE card_variants DROP COLUMN traits')
        before_metadata = conn.execute('SELECT * FROM card_mode_metadata').fetchall()
        before_cards = conn.execute('SELECT * FROM cards').fetchall()
        before_variants = conn.execute('SELECT * FROM card_variants').fetchall()
    preview = copy_database(db.db_path, tmp_path / 'preview.db')
    apply_migration(preview)
    apply_migration(preview)
    with sqlite3.connect(db.db_path) as original, sqlite3.connect(str(preview)) as copy:
        assert 'traits' not in {row[1] for row in original.execute('PRAGMA table_info(card_variants)')}
        assert copy.execute('SELECT * FROM cards').fetchall() == before_cards
        assert copy.execute('SELECT * FROM card_mode_metadata').fetchall() == before_metadata
        assert [row[:-1] for row in copy.execute('SELECT * FROM card_variants')] == before_variants
        assert copy.execute('SELECT traits FROM card_variants').fetchall() == [(None,)] * 3
        assert copy.execute('PRAGMA quick_check').fetchall() == [('ok',)]
    prepared = DatabaseManager(str(preview))
    assert all(v['traits'] == ['قدیمی'] for v in prepared.get_card_variants(card_id))
    form = prepared.get_card_variant(card_id, 'normal')
    prepared.save_card_variant(card_id, 'normal', dict(form, traits=[]))
    apply_migration(preview)
    assert prepared.get_card_variant(card_id, 'normal')['traits'] == []
    assert prepared.get_card_variant(card_id, 'epic')['traits'] == ['قدیمی']
