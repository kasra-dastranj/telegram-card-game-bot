#!/usr/bin/env python3
"""Import approved, fully specified cards. Dry-run unless --apply is passed."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RARITIES = ("normal", "epic", "legend")
STATS = ("power", "speed", "iq", "popularity")
TYPES = ("POWER_TYPE", "SPEED_TYPE", "IQ_TYPE", "POPULARITY_TYPE")


def validate(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        raise ValueError("manifest needs a cards array")
    ids, names = set(), set()
    for card in payload["cards"]:
        if not isinstance(card, dict) or card.get("approved") is not True:
            raise ValueError("each card needs approved: true")
        cid, name = card.get("card_id"), card.get("name")
        if not isinstance(cid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", cid):
            raise ValueError(f"invalid stable card_id: {cid}")
        if not isinstance(name, str) or not name.strip() or cid in ids or name.casefold() in names:
            raise ValueError(f"missing or duplicate name/card_id: {cid}")
        ids.add(cid)
        names.add(name.casefold())
        if card.get("rarity") not in RARITIES or not isinstance(card.get("biography"), str) or not card["biography"].strip():
            raise ValueError(f"{cid}: base rarity and biography required")
        if not isinstance(card.get("dialogs", []), list) or any(not isinstance(x, str) for x in card.get("dialogs", [])):
            raise ValueError(f"{cid}: dialogs must be strings")
        forms = card.get("variants")
        if not isinstance(forms, dict) or set(forms) != set(RARITIES):
            raise ValueError(f"{cid}: normal, epic and legend forms required")
        for rarity, form in forms.items():
            if not isinstance(form, dict):
                raise ValueError(f"{cid}/{rarity}: invalid form")
            if any(type(form.get(s)) is not int or not 0 <= form[s] <= 100 for s in STATS):
                raise ValueError(f"{cid}/{rarity}: all four stats must be integers 0..100")
            if form.get("card_type") not in TYPES:
                raise ValueError(f"{cid}/{rarity}: invalid card_type")
            if not isinstance(form.get("abilities"), list) or any(not isinstance(x, str) for x in form["abilities"]):
                raise ValueError(f"{cid}/{rarity}: abilities must be strings")
            if not isinstance(form.get("card_effects", []), list) or not isinstance(form.get("passive", {}), dict):
                raise ValueError(f"{cid}/{rarity}: invalid effects or passive")
            image = form.get("image_path")
            if not isinstance(image, str) or not image:
                raise ValueError(f"{cid}/{rarity}: image_path required")
            path = Path(image)
            resolved = (ROOT / path).resolve()
            shared_images = (ROOT / "assets/card_images").resolve()
            in_project = resolved.is_relative_to(ROOT.resolve())
            in_shared_images = (path.parts[:2] == ("assets", "card_images")
                                and resolved.is_relative_to(shared_images))
            if (path.is_absolute() or ".." in path.parts or not resolved.is_file()
                    or not (in_project or in_shared_images)):
                raise ValueError(f"{cid}/{rarity}: image missing or outside project: {image}")
            if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise ValueError(f"{cid}/{rarity}: invalid image format")
            form["image_path"] = path.as_posix()
    return payload["cards"]


def form_values(form: dict) -> tuple:
    return (
        *(form[s] for s in STATS),
        json.dumps(form["abilities"], ensure_ascii=False),
        json.dumps(form.get("card_effects", []), ensure_ascii=False),
        form["image_path"], form["card_type"],
        json.dumps(form.get("passive", {}), ensure_ascii=False),
    )


def import_manifest(db_path: str | Path, cards: list[dict], *, apply: bool = False) -> list[dict]:
    cards = validate({"cards": cards})
    conn = sqlite3.connect(db_path, timeout=15)
    changes = []
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        now = datetime.now(timezone.utc).isoformat()
        for card in cards:
            cid = card["card_id"]
            other = conn.execute("SELECT card_id FROM cards WHERE name=? COLLATE NOCASE", (card["name"],)).fetchone()
            if other and other[0] != cid:
                raise ValueError(f"name already belongs to another card: {card['name']}")
            base = card["variants"][card["rarity"]]
            values = (card["name"].strip(), card["rarity"], *form_values(base)[:6],
                      json.dumps(card.get("dialogs", []), ensure_ascii=False),
                      card["biography"].strip(), base["image_path"], base["card_type"])
            old = conn.execute("""SELECT name,rarity,power,speed,iq,popularity,abilities,card_effects,
                                   dialogs,biography,image_path,card_type FROM cards WHERE card_id=?""", (cid,)).fetchone()
            if old != values:
                changes.append({"card_id": cid, "record": "card", "action": "update" if old else "create"})
                if apply:
                    conn.execute("""INSERT INTO cards(card_id,name,rarity,power,speed,iq,popularity,
                        abilities,card_effects,dialogs,biography,image_path,card_type,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(card_id) DO UPDATE SET name=excluded.name,rarity=excluded.rarity,
                        power=excluded.power,speed=excluded.speed,iq=excluded.iq,popularity=excluded.popularity,
                        abilities=excluded.abilities,card_effects=excluded.card_effects,dialogs=excluded.dialogs,
                        biography=excluded.biography,image_path=excluded.image_path,card_type=excluded.card_type""",
                        (cid, *values, now))
                    if old and old[10] != base["image_path"]:
                        conn.execute("DELETE FROM card_media_cache WHERE card_id=?", (cid,))
            for rarity in RARITIES:
                values = form_values(card["variants"][rarity])
                old = conn.execute("""SELECT power,speed,iq,popularity,abilities,card_effects,image_path,
                                      card_type,passive FROM card_variants WHERE card_id=? AND rarity=?""",
                                   (cid, rarity)).fetchone()
                if old == values:
                    continue
                changes.append({"card_id": cid, "record": rarity, "action": "update" if old else "create"})
                if apply:
                    conn.execute("""INSERT INTO card_variants(variant_id,card_id,rarity,power,speed,iq,
                        popularity,abilities,card_effects,image_path,card_type,passive,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(card_id,rarity) DO UPDATE SET power=excluded.power,speed=excluded.speed,
                        iq=excluded.iq,popularity=excluded.popularity,abilities=excluded.abilities,
                        card_effects=excluded.card_effects,image_path=excluded.image_path,
                        card_type=excluded.card_type,passive=excluded.passive,updated_at=excluded.updated_at""",
                        (str(uuid.uuid4()), cid, rarity, *values, now, now))
                    if old and old[6] != card["variants"][rarity]["image_path"]:
                        conn.execute("""DELETE FROM card_variant_media_cache
                                        WHERE variant_id=(SELECT variant_id FROM card_variants
                                                          WHERE card_id=? AND rarity=?)""", (cid, rarity))
        if apply:
            conn.commit()
        else:
            conn.rollback()
        return changes
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--db", type=Path, default=ROOT / "game_bot.db")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        cards = validate(json.loads(args.manifest.read_text(encoding="utf-8")))
        changes = import_manifest(args.db, cards, apply=args.apply)
    except (ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(f"Import rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "changes": changes}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
