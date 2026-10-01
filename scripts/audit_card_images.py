#!/usr/bin/env python3
"""Read-only inventory of missing and shared images by character/form."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def audit(db_path: str | Path, image_root: str | Path = ROOT) -> dict:
    missing = []
    placeholder = []
    shared = []
    by_card = defaultdict(list)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""SELECT c.card_id,c.name,v.rarity,v.image_path
                              FROM card_variants v JOIN cards c ON c.card_id=v.card_id
                              ORDER BY c.card_id,v.rarity""").fetchall()
    for card_id, name, rarity, image in rows:
        path = Path(image or "")
        valid = bool(image) and not path.is_absolute() and ".." not in path.parts
        valid = valid and (Path(image_root) / path).resolve().is_file()
        if path.name == "card_needs_creation.png":
            placeholder.append({"card_id": card_id, "name": name, "rarity": rarity})
        if not valid:
            missing.append({"card_id": card_id, "name": name, "rarity": rarity, "image_path": image or ""})
        elif image:
            by_card[card_id].append((rarity, image))
    for card_id, forms in sorted(by_card.items()):
        by_image = defaultdict(list)
        for rarity, image in forms:
            by_image[image].append(rarity)
        for image, rarities in sorted(by_image.items()):
            if len(rarities) > 1:
                shared.append({"card_id": card_id, "rarities": rarities, "image_path": image})
    return {"forms_checked": len(rows), "missing": missing,
            "placeholder": placeholder, "shared_within_character": shared}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "game_bot.db")
    parser.add_argument("--image-root", type=Path, default=ROOT,
                        help="Project root containing assets/card_images (defaults to checkout)")
    args = parser.parse_args()
    print(json.dumps(audit(args.db, args.image_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
