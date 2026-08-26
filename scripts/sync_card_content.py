#!/usr/bin/env python3
"""Synchronize authored biographies and victory lines into the cards table."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.card_content import content_for_card, load_card_content, normalize_card_name


PLACEHOLDER_BIOGRAPHIES = {"", "biography not available."}


def _dialog_list(raw_value):
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = [raw_value]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def sync_card_content(db_path: Path, data_path: Optional[Path], apply: bool, overwrite: bool = False):
    content = load_card_content(data_path)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    rows = list(connection.execute("SELECT card_id, name, biography, dialogs FROM cards ORDER BY name"))
    matched_source_names = set()
    updates = []

    for row in rows:
        entry = content_for_card(row["name"], content)
        if not entry:
            continue
        matched_source_names.add(normalize_card_name(row["name"]))
        authored_biography = str(entry.get("biography") or "").strip()
        current_biography = str(row["biography"] or "").strip()
        biography = current_biography
        if authored_biography and (overwrite or current_biography.casefold() in PLACEHOLDER_BIOGRAPHIES):
            biography = authored_biography

        authored_dialogs = _dialog_list(entry.get("victory_lines"))
        current_dialogs = _dialog_list(row["dialogs"])
        dialogs = authored_dialogs if overwrite else list(dict.fromkeys([*current_dialogs, *authored_dialogs]))
        serialized_dialogs = json.dumps(dialogs, ensure_ascii=False)

        if biography != current_biography or serialized_dialogs != (row["dialogs"] or ""):
            updates.append((biography, serialized_dialogs, row["card_id"], row["name"]))

    unmatched = [name for name in content if normalize_card_name(name) not in matched_source_names]
    if apply:
        connection.executemany(
            "UPDATE cards SET biography = ?, dialogs = ? WHERE card_id = ?",
            [(biography, dialogs, card_id) for biography, dialogs, card_id, _ in updates],
        )
        connection.commit()
    connection.close()
    return updates, unmatched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("game_bot.db"))
    parser.add_argument("--data", type=Path, help="Optional single content file; defaults to all project card-content files.")
    parser.add_argument("--apply", action="store_true", help="Write changes; without this flag the command is a dry run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing authored content instead of preserving it.")
    args = parser.parse_args()
    updates, unmatched = sync_card_content(args.db, args.data, args.apply, args.overwrite)
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"{mode}: {len(updates)} card(s) would change")
    for _, dialogs, _, name in updates:
        print(f"  - {name}: {len(json.loads(dialogs))} victory line(s)")
    if unmatched:
        print("No card in database for: " + ", ".join(unmatched))


if __name__ == "__main__":
    main()
