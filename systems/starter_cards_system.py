"""Give every new player three distinct, deterministic Normal starter cards."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from systems.card_inventory_system import CardInventorySystem


STARTER_NAMES = ("John Wick", "Heisenberg", "Rehi")


def grant_starter_cards(db, user_id: int) -> list[str]:
    """Grant all three together, only if the player has no cards yet."""
    normal_cards = [
        card for card in db.get_all_cards()
        if getattr(card.rarity, "value", card.rarity) == "normal"
    ]
    by_name = {card.name.casefold(): card for card in normal_cards}
    selected = []
    seen = set()
    for name in STARTER_NAMES:
        card = by_name.get(name.casefold())
        if card and card.card_id not in seen:
            selected.append(card)
            seen.add(card.card_id)
    for card in sorted(normal_cards, key=lambda item: item.card_id):
        if len(selected) == 3:
            break
        if card.card_id not in seen:
            selected.append(card)
            seen.add(card.card_id)
    if len(selected) != 3:
        return []

    with closing(sqlite3.connect(db.db_path, timeout=15)) as conn:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM player_cards WHERE user_id=? LIMIT 1", (user_id,)
            ).fetchone():
                return []
            if not conn.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,)).fetchone():
                return []
            for card in selected:
                CardInventorySystem.grant_in(conn, user_id, card.card_id, "normal")
            # Make the three starter characters immediately usable in Deck.
            # Ownership, copies and the first deck commit together.
            if not conn.execute(
                "SELECT 1 FROM player_decks WHERE player_id=? LIMIT 1", (user_id,)
            ).fetchone():
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """INSERT INTO player_decks
                       (deck_id,player_id,deck_name,card_id_1,card_id_2,card_id_3,
                        is_valid,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,1,?,?)""",
                    (str(uuid.uuid4()), user_id, "دک آغازین",
                     selected[0].card_id, selected[1].card_id, selected[2].card_id, now, now),
                )
    return [card.name for card in selected]
