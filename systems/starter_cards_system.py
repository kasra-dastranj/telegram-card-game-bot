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
    """Compatibility entry for Mini App/scripts: names only on a new grant."""
    result = grant_starter_pack(db, user_id)
    return result.get('names', []) if not result.get('replayed') else []


def starter_status(db, user_id):
    """Read eligibility without granting, schema changes or capacity backfills."""
    with closing(sqlite3.connect(db.db_path)) as conn:
        return _status_in(conn, user_id)


def _status_in(conn, user_id):
    from systems.reward_ledger import receipt_in
    from systems.progression_config import enabled_in
    prior = receipt_in(conn, 'starter_cards', user_id)
    if prior:
        return prior
    if not conn.execute('SELECT 1 FROM players WHERE user_id=?', (user_id,)).fetchone():
        return {'ok': False, 'reason': 'missing_player'}
    if enabled_in(conn):
        capacity = conn.execute('SELECT legacy FROM progression_capacities WHERE user_id=?', (user_id,)).fetchone()
        if not capacity or capacity[0]:
            return {'ok': False, 'reason': 'legacy'}
    offered = conn.execute('SELECT 1 FROM foundation_settings WHERE key=?', ('starter_offer:' + str(user_id),)).fetchone()
    if not offered and conn.execute('SELECT 1 FROM player_cards WHERE user_id=? LIMIT 1', (user_id,)).fetchone():
        return {'ok': False, 'reason': 'has_cards'}
    return {'ok': True, 'pending': True}


def offer_starter_pack(db, user_id):
    """Keep an offered pack available if the user claims a daily card first."""
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        status = _status_in(conn, user_id)
        if status.get('pending'):
            conn.execute('INSERT OR IGNORE INTO foundation_settings(key,value_json) VALUES (?,?)',
                         ('starter_offer:' + str(user_id), 'true'))


def grant_starter_pack(db, user_id):
    """Grant and receipt three Normal cards + deck atomically, in both policies."""
    with closing(sqlite3.connect(db.db_path, timeout=15)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        status = _status_in(conn, user_id)
        if not status.get('ok') or status.get('replayed'):
            return status
        return _grant_in(db, conn, user_id)


def _grant_in(db, conn, user_id):
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
        return {'ok': False, 'reason': 'pool_unavailable'}
    for card in selected:
        CardInventorySystem.grant_in(conn, user_id, card.card_id, 'normal')
    from systems.progression_config import config_in
    from systems.reward_ledger import record_in
    version, _ = config_in(conn)
    result = {'ok': True, 'card_ids': [card.card_id for card in selected],
              'names': [card.name for card in selected]}
    record_in(conn, 'starter_cards', user_id, 'starter', 'starter_grant', {}, result, version,
              inventory={card.card_id + ':normal': 1 for card in selected})
    conn.execute('DELETE FROM foundation_settings WHERE key=?', ('starter_offer:' + str(user_id),))
    if not conn.execute('SELECT 1 FROM player_decks WHERE player_id=? LIMIT 1', (user_id,)).fetchone():
        now = datetime.now(timezone.utc).isoformat()
        conn.execute('''INSERT INTO player_decks
            (deck_id,player_id,deck_name,card_id_1,card_id_2,card_id_3,is_valid,created_at,updated_at)
            VALUES(?,?,?,?,?,?,1,?,?)''', (str(uuid.uuid4()), user_id, 'دک آغازین',
                selected[0].card_id, selected[1].card_id, selected[2].card_id, now, now))
    return result
