"""One random ten-card Normal starter pack, including eligible returning players."""

from __future__ import annotations

from systems.shared_foundation import economic_card_eligible
import random
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from systems.card_inventory_system import CardInventorySystem


STARTER_COUNT = 10
STARTER_OPERATION = 'starter_cards_v2_10'
OFFER_PREFIX = 'starter_offer:v2_10:'
EXCLUDED_PREFIX = 'starter_excluded:v2_10:'


def grant_starter_cards(db, user_id: int, *, allow_existing=True) -> list[str]:
    """Compatibility entry for Mini App/scripts: names only on a new grant."""
    result = grant_starter_pack(db, user_id, allow_existing=allow_existing)
    return result.get('names', []) if not result.get('replayed') else []


def starter_status(db, user_id):
    """Read eligibility without granting, schema changes or capacity backfills."""
    with closing(sqlite3.connect(db.db_path)) as conn:
        return _status_in(conn, user_id)


def _owned_in(conn, user_id):
    # Count characters, not duplicate copies or multiple forms of one character.
    return {row[0] for row in conn.execute("""
        SELECT pc.card_id FROM player_cards pc JOIN cards c USING(card_id) WHERE pc.user_id=?
        UNION SELECT s.card_id FROM player_card_stacks s JOIN cards c USING(card_id)
            WHERE s.user_id=? AND s.quantity>0
        UNION SELECT g.card_id FROM custom_grants g JOIN custom_definitions d USING(card_id)
            WHERE g.user_id=? AND g.active=1 AND d.status='active'
    """, (user_id, user_id, user_id))}


def _status_in(conn, user_id, *, allow_existing=True):
    from systems.reward_ledger import receipt_in
    prior = receipt_in(conn, STARTER_OPERATION, user_id)
    if prior:
        return prior
    if not conn.execute('SELECT 1 FROM players WHERE user_id=?', (user_id,)).fetchone():
        return {'ok': False, 'reason': 'missing_player'}
    if conn.execute('SELECT 1 FROM foundation_settings WHERE key=?', (EXCLUDED_PREFIX + str(user_id),)).fetchone():
        return {'ok': False, 'reason': 'has_cards'}
    owned = _owned_in(conn, user_id)
    if not allow_existing:
        capacity = conn.execute('SELECT legacy FROM progression_capacities WHERE user_id=?', (user_id,)).fetchone()
        if owned or (capacity and capacity[0]) or receipt_in(conn, 'starter_cards', user_id):
            return {'ok': False, 'reason': 'start_required'}
    offered = conn.execute('SELECT 1 FROM foundation_settings WHERE key=?', (OFFER_PREFIX + str(user_id),)).fetchone()
    if not offered and len(owned) >= STARTER_COUNT:
        return {'ok': False, 'reason': 'has_cards'}
    return {'ok': True, 'pending': True}


def _remember_in(conn, user_id, status):
    prefix = OFFER_PREFIX if status.get('pending') else EXCLUDED_PREFIX if status.get('reason') == 'has_cards' else None
    if prefix:
        conn.execute('INSERT OR IGNORE INTO foundation_settings(key,value_json) VALUES (?,?)', (prefix + str(user_id), 'true'))


def offer_starter_pack(db, user_id):
    """Freeze first-start eligibility; spending cards later cannot unlock a gift."""
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        _remember_in(conn, user_id, _status_in(conn, user_id))


def grant_starter_pack(db, user_id, *, allow_existing=True):
    """Atomically grant ten Normal copies and persist the random draw once."""
    with closing(sqlite3.connect(db.db_path, timeout=15)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        status = _status_in(conn, user_id, allow_existing=allow_existing)
        _remember_in(conn, user_id, status)
        if not status.get('ok') or status.get('replayed'):
            return status
        return _grant_in(db, conn, user_id)


def _grant_in(db, conn, user_id):
    normal_cards = [
        card for card in db.get_all_cards() if economic_card_eligible(card)
        if getattr(card.rarity, "value", card.rarity) == "normal"
    ]
    if len(normal_cards) < STARTER_COUNT:
        return {'ok': False, 'reason': 'pool_unavailable'}
    owned = _owned_in(conn, user_id)
    unseen = [card for card in normal_cards if card.card_id not in owned]
    selected = random.sample(unseen, min(STARTER_COUNT, len(unseen)))
    if len(selected) < STARTER_COUNT:
        selected += random.sample([card for card in normal_cards if card.card_id in owned], STARTER_COUNT - len(selected))
    for card in selected:
        CardInventorySystem.grant_in(conn, user_id, card.card_id, 'normal')
    from systems.progression_config import config_in
    from systems.reward_ledger import record_in
    version, _ = config_in(conn)
    result = {'ok': True, 'card_ids': [card.card_id for card in selected],
              'names': [card.name for card in selected]}
    record_in(conn, STARTER_OPERATION, user_id, 'starter', 'starter_grant', {}, result, version,
              inventory={card.card_id + ':normal': 1 for card in selected})
    conn.execute('DELETE FROM foundation_settings WHERE key=?', (OFFER_PREFIX + str(user_id),))
    if not conn.execute('SELECT 1 FROM player_decks WHERE player_id=? LIMIT 1', (user_id,)).fetchone():
        now = datetime.now(timezone.utc).isoformat()
        conn.execute('''INSERT INTO player_decks
            (deck_id,player_id,deck_name,card_id_1,card_id_2,card_id_3,is_valid,created_at,updated_at)
            VALUES(?,?,?,?,?,?,1,?,?)''', (str(uuid.uuid4()), user_id, 'دک آغازین',
                selected[0].card_id, selected[1].card_id, selected[2].card_id, now, now))
    return result
