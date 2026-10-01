"""Preview or canonicalize legacy card_images/ paths to shipped assets."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize(db_path: Path, apply: bool = False) -> dict:
    changes = []
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        for table, key_columns in (("cards", ("card_id",)),
                                   ("card_variants", ("card_id", "rarity"))):
            rows = conn.execute(
                f"SELECT {','.join(key_columns)},image_path FROM {table} WHERE image_path LIKE 'card_images/%'"
            ).fetchall()
            for row in rows:
                old = row[-1]
                path = Path(old)
                if len(path.parts) != 2 or path.parts[0] != "card_images":
                    raise ValueError(f"unsafe legacy path: {old}")
                new = f"assets/card_images/{path.name}"
                if not (ROOT / new).is_file():
                    raise ValueError(f"image file absent: {new}")
                changes.append({"table": table, "key": row[:-1], "old": old, "new": new})
                if apply:
                    where = " AND ".join(f"{column}=?" for column in key_columns)
                    conn.execute(f"UPDATE {table} SET image_path=? WHERE {where} AND image_path=?",
                                 (new, *row[:-1], old))
        if not apply:
            conn.rollback()
    return {"applied": apply, "count": len(changes), "changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = normalize(args.db, args.apply)
    print(json.dumps({"applied": result["applied"], "count": result["count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
