"""Give every new player three distinct, deterministic Normal starter cards."""

from __future__ import annotations

from systems.shared_foundation import economic_card_eligible
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from systems.card_inventory_system import CardInventorySystem


STARTER_NAMES = ("John Wick", "Heisenberg", "Rehi")


def grant_starter_cards(db, user_id: int) -> list[str]:
    """Grant all three together, only if the player has no cards yet."""
    normal_cards = [
        card for card in db.get_all_cards() if economic_card_eligible(card)
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
            from systems.progression_config import enabled_in, config_in
            if enabled_in(conn):
                from systems.reward_ledger import receipt_in, capacities_in
                if receipt_in(conn, 'starter_cards', user_id):
                    return []
                _, rules = config_in(conn)
                if capacities_in(conn, user_id, rules)['legacy']:
                    return []  # Existing accounts are frozen until product cutover approval.
            if conn.execute(
                "SELECT 1 FROM player_cards WHERE user_id=? LIMIT 1", (user_id,)
            ).fetchone():
                return []
            if not conn.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,)).fetchone():
                return []
            for card in selected:
                CardInventorySystem.grant_in(conn, user_id, card.card_id, "normal")
            if enabled_in(conn):
                from systems.reward_ledger import record_in
                version, _ = config_in(conn)
                record_in(conn, 'starter_cards', user_id, 'starter', 'starter_grant', {},
                          {'ok':True,'card_ids':[card.card_id for card in selected]}, version,
                          inventory={card.card_id+':normal':1 for card in selected})
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
