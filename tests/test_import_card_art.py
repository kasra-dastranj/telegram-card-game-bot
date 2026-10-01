"""Art-only imports must target an existing form and be repeatable."""

import json
import sqlite3

import pytest
from PIL import Image

from core.database import DatabaseManager
from core.models import Card, CardRarity
from scripts.import_card_art import import_art


def test_art_import_previews_and_updates_only_selected_form(tmp_path):
    db = DatabaseManager(str(tmp_path / "art.db"))
    db.add_card(Card("hero", "Hero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    folder = tmp_path / "assets/card_images"
    folder.mkdir(parents=True)
    Image.new("RGB", (32, 48), "purple").save(folder / "hero_epic.png")
    manifest = tmp_path / "art.json"
    manifest.write_text(json.dumps({"images": [{"card_id": "hero", "rarity": "epic",
        "image_path": "assets/card_images/hero_epic.png", "approved": True}]}), encoding="utf-8")
    with sqlite3.connect(db.db_path) as conn:
        original = conn.execute("SELECT image_path FROM card_variants WHERE card_id='hero' AND rarity='epic'").fetchone()[0]
    assert import_art(tmp_path / "art.db", manifest, project_root=tmp_path)["changes"][0]["changed"]
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT image_path FROM card_variants WHERE card_id='hero' AND rarity='epic'").fetchone()[0] == original
    assert import_art(tmp_path / "art.db", manifest, True, tmp_path)["applied"]
    assert not import_art(tmp_path / "art.db", manifest, True, tmp_path)["changes"][0]["changed"]
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT image_path FROM card_variants WHERE card_id='hero' AND rarity='epic'").fetchone()[0] == "assets/card_images/hero_epic.png"
        assert conn.execute("SELECT image_path FROM cards WHERE card_id='hero'").fetchone()[0] != "assets/card_images/hero_epic.png"


def test_art_import_rejects_placeholder_and_unapproved(tmp_path):
    db = DatabaseManager(str(tmp_path / "art.db"))
    db.add_card(Card("hero", "Hero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    manifest = tmp_path / "art.json"
    manifest.write_text(json.dumps({"images": [{"card_id": "hero", "rarity": "epic",
        "image_path": "assets/card_images/card_needs_creation.png", "approved": True}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        import_art(tmp_path / "art.db", manifest, project_root=tmp_path)
