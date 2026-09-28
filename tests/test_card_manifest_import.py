"""The content importer must never create random or duplicate card definitions."""

import sqlite3

import pytest

from core.database import DatabaseManager
from scripts.audit_card_images import audit
from scripts.import_card_manifest import import_manifest, validate
import scripts.import_card_manifest as card_import


def _manifest():
    form = {
        "power": 42, "speed": 51, "iq": 63, "popularity": 74,
        "abilities": [], "card_effects": [], "passive": {},
        "card_type": "IQ_TYPE", "image_path": "assets/card_images/shrek.png",
    }
    return {"cards": [{
        "approved": True, "card_id": "manifest_test_card", "name": "Manifest Test Card",
        "rarity": "normal", "biography": "Authored test biography", "dialogs": [],
        "variants": {rarity: dict(form) for rarity in ("normal", "epic", "legend")},
    }]}


def test_manifest_dry_run_apply_and_repeat_are_idempotent(tmp_path):
    db = DatabaseManager(str(tmp_path / "cards.db"))
    cards = validate(_manifest())
    preview = import_manifest(db.db_path, cards)
    assert len(preview) == 4
    with sqlite3.connect(db.db_path) as conn:
        assert not conn.execute("SELECT 1 FROM cards WHERE card_id='manifest_test_card'").fetchone()
    assert import_manifest(db.db_path, cards, apply=True) == preview
    assert import_manifest(db.db_path, cards) == []
    assert import_manifest(db.db_path, cards, apply=True) == []
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cards WHERE card_id='manifest_test_card'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM card_variants WHERE card_id='manifest_test_card'").fetchone()[0] == 3
    image_report = audit(db.db_path)
    assert image_report["missing"] == []
    assert image_report["shared_within_character"] == [{
        "card_id": "manifest_test_card",
        "rarities": ["epic", "legend", "normal"],
        "image_path": "assets/card_images/shrek.png",
    }]


def test_manifest_requires_approval_real_image_and_explicit_stats():
    manifest = _manifest()
    manifest["cards"][0]["approved"] = False
    with pytest.raises(ValueError, match="approved"):
        validate(manifest)
    manifest = _manifest()
    manifest["cards"][0]["variants"]["epic"]["image_path"] = "assets/card_images/missing.png"
    with pytest.raises(ValueError, match="image missing"):
        validate(manifest)
    manifest = _manifest()
    manifest["cards"][0]["variants"]["normal"]["power"] = None
    with pytest.raises(ValueError, match="stats"):
        validate(manifest)


def test_manifest_accepts_only_the_configured_shared_image_symlink(tmp_path, monkeypatch):
    project = tmp_path / "release"
    project.mkdir()
    shared = tmp_path / "shared_images"
    shared.mkdir()
    (project / "assets").mkdir()
    (shared / "shrek.png").write_bytes(b"test image")
    try:
        (project / "assets/card_images").symlink_to(shared, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    monkeypatch.setattr(card_import, "ROOT", project)
    assert validate(_manifest())

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "not-allowed.png").write_bytes(b"test image")
    (project / "untrusted").symlink_to(outside, target_is_directory=True)
    manifest = _manifest()
    manifest["cards"][0]["variants"]["normal"]["image_path"] = "untrusted/not-allowed.png"
    with pytest.raises(ValueError, match="outside project"):
        validate(manifest)


def test_changed_image_invalidates_telegram_media_cache(tmp_path):
    db = DatabaseManager(str(tmp_path / "cards.db"))
    cards = validate(_manifest())
    import_manifest(db.db_path, cards, apply=True)
    with sqlite3.connect(db.db_path) as conn:
        variant_id = conn.execute(
            "SELECT variant_id FROM card_variants WHERE card_id='manifest_test_card' AND rarity='normal'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO card_media_cache(card_id,media_kind,file_id,updated_at) VALUES(?,?,?,?)",
            ("manifest_test_card", "photo", "old-photo", "2026-01-01"),
        )
        conn.execute(
            "INSERT INTO card_variant_media_cache(variant_id,media_kind,file_id,updated_at) VALUES(?,?,?,?)",
            (variant_id, "photo", "old-variant-photo", "2026-01-01"),
        )
    cards[0]["variants"]["normal"]["image_path"] = "assets/card_images/john_wick.png"
    import_manifest(db.db_path, cards, apply=True)
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM card_media_cache WHERE card_id='manifest_test_card'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM card_variant_media_cache WHERE variant_id=?", (variant_id,)).fetchone()[0] == 0
