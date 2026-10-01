"""Preview or attach approved artwork to existing card forms."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RARITIES = {"normal", "epic", "legend"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def import_art(db_path: Path, manifest_path: Path, apply: bool = False,
               project_root: Path = ROOT) -> dict:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("images")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest needs a nonempty images array")
    changes = []
    seen = set()
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        for entry in entries:
            card_id, rarity, image_path = entry.get("card_id"), entry.get("rarity"), entry.get("image_path")
            if entry.get("approved") is not True or not isinstance(card_id, str) or rarity not in RARITIES:
                raise ValueError("each image needs approved=true, card_id and valid rarity")
            identity = (card_id, rarity)
            if identity in seen:
                raise ValueError(f"duplicate card form: {identity}")
            seen.add(identity)
            if not isinstance(image_path, str):
                raise ValueError(f"invalid image path: {identity}")
            path = Path(image_path)
            if (path.is_absolute() or ".." in path.parts or path.parts[:2] != ("assets", "card_images")
                    or path.suffix.lower() not in IMAGE_EXTENSIONS
                    or path.name == "card_needs_creation.png"):
                raise ValueError(f"image path must be a specific file in assets/card_images: {image_path}")
            resolved = (project_root / path).resolve()
            if not resolved.is_relative_to((project_root / "assets/card_images").resolve()) or not resolved.is_file():
                raise ValueError(f"image file missing or outside shared image folder: {image_path}")
            with Image.open(resolved) as picture:
                picture.verify()
            row = conn.execute(
                """SELECT v.variant_id,v.image_path,c.rarity FROM card_variants v
                   JOIN cards c ON c.card_id=v.card_id WHERE v.card_id=? AND v.rarity=?""",
                identity,
            ).fetchone()
            if not row:
                raise ValueError(f"unknown card form: {identity}")
            other = conn.execute(
                "SELECT rarity FROM card_variants WHERE card_id=? AND rarity!=? AND image_path=?",
                (card_id, rarity, image_path),
            ).fetchone()
            if other:
                raise ValueError(f"same artwork already assigned to {card_id}/{other[0]}")
            changes.append({"card_id": card_id, "rarity": rarity, "old": row[1],
                            "new": image_path, "changed": row[1] != image_path})
            if apply and row[1] != image_path:
                conn.execute("UPDATE card_variants SET image_path=?,updated_at=CURRENT_TIMESTAMP WHERE variant_id=?",
                             (image_path, row[0]))
                conn.execute("DELETE FROM card_variant_media_cache WHERE variant_id=?", (row[0],))
                if row[2] == rarity:
                    conn.execute("UPDATE cards SET image_path=? WHERE card_id=?", (image_path, card_id))
                    conn.execute("DELETE FROM card_media_cache WHERE card_id=?", (card_id,))
        if not apply:
            conn.rollback()
    return {"applied": apply, "changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(import_art(args.db, args.manifest, args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
