"""Preview or install versioned trial card missions without resetting progress."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_missions(db_path: Path, manifest_path: Path, apply: bool = False) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["missions"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("empty mission manifest")
    changes = []
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        seen = set()
        for entry in entries:
            name, mission_type, target = entry["card_name"], entry["mission_type"], entry["target"]
            if name in seen or mission_type != "total_wins" or type(target) is not int or not 1 <= target <= 100:
                raise ValueError(f"invalid or duplicate mission: {name}")
            seen.add(name)
            cards = conn.execute("SELECT card_id FROM cards WHERE name=?", (name,)).fetchall()
            if len(cards) != 1:
                raise ValueError(f"card name not unique or missing: {name}")
            card_id = cards[0][0]
            if not conn.execute("SELECT 1 FROM card_variants WHERE card_id=? AND rarity='legend'", (card_id,)).fetchone():
                raise ValueError(f"legend variant missing: {name}")
            existing = conn.execute(
                "SELECT mission_type,target,target_card FROM card_missions WHERE card_id=?", (card_id,)
            ).fetchone()
            if existing and tuple(existing) != (mission_type, target, None):
                raise ValueError(f"existing mission differs: {name}")
            changes.append({"card_id": card_id, "card_name": name,
                            "status": "unchanged" if existing else "add", "target": target})
            if apply and not existing:
                conn.execute(
                    """INSERT INTO card_missions(card_id,mission_type,target,target_card,created_at)
                       VALUES(?,?,?,NULL,CURRENT_TIMESTAMP)""",
                    (card_id, mission_type, target),
                )
        if not apply:
            conn.rollback()
    return {"version": manifest["version"], "applied": apply, "changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=ROOT / "content/trial_card_missions_v1.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(import_missions(args.db, args.manifest, args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
