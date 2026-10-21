"""Limited Rare delivery; all callers commit serial, stack and notice together."""
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from systems.card_inventory_system import CardInventorySystem
from systems.progression_config import config_in
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import receipt_in, record_in


def issue_in(conn, user, card, operation, source, *, encounter=None):
    from systems.attack_rewards import rare_available_in
    from systems.custom_card_notices import queue_rare_in
    if not conn.execute('SELECT 1 FROM players WHERE user_id=?', (user,)).fetchone():
        raise ValueError('player_not_found')
    if not conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='official' AND rarity='rare'", (card,)).fetchone():
        raise ValueError('rare_required')
    if rare_available_in(conn, card, encounter) < 1:
        raise ValueError('rare_supply_empty')
    serial = conn.execute('SELECT total_issued+1 FROM rare_cards_info WHERE card_id=?', (card,)).fetchone()[0]
    conn.execute('UPDATE rare_cards_info SET total_issued=total_issued+1 WHERE card_id=?', (card,))
    conn.execute('INSERT INTO rare_card_instances VALUES(?,?,?,?,?,?)',
                 (card, serial, user, operation, source, datetime.now(timezone.utc).isoformat()))
    CardInventorySystem.grant_in(conn, user, card, 'rare')
    queue_rare_in(conn, user, card, serial)
    return serial


def deliver(db, actor, user, card, request_key):
    """Offline payment is reviewed by the admin; never debit a player's wallet."""
    if type(user) is not int or not 0 < user < 2**63:
        raise ValueError('invalid_player_id')
    if not isinstance(card, str) or not 1 <= len(card) <= 128:
        raise ValueError('rare_required')
    operation = ProgressionEconomy.operation_key('rare-admin', request_key)
    payload = {'card_id':card, 'actor':actor}
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        # An operation ID is global, including changes of recipient on retries.
        existing = conn.execute('SELECT user_id FROM rare_card_instances WHERE operation_id=?', (operation,)).fetchone()
        if existing and existing[0] != user:
            raise ValueError('idempotency_conflict')
        prior = receipt_in(conn, operation, user, payload)
        if prior:
            return prior
        serial = issue_in(conn, user, card, operation, 'admin')
        version, _ = config_in(conn)
        result = {'ok':True, 'card_id':card, 'user_id':user, 'serial':serial, 'notification':'queued'}
        record_in(conn, operation, user, 'rare_admin', 'rare_issue', payload, result, version,
                  inventory={card+':rare':1})
        return result


def set_supply(db, actor, card, total, expected):
    """Initialize or edit supply without resetting serials or promised rewards."""
    if not isinstance(card,str) or not 1 <= len(card) <= 128:
        raise ValueError('rare_required')
    if type(total) is not int or not 0 <= total <= 1_000_000:
        raise ValueError('invalid_rare_supply')
    if expected is not None and (type(expected) is not int or expected < 0):
        raise ValueError('invalid_rare_supply')
    from systems.attack_rewards import rare_available_in
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='official' AND rarity='rare'", (card,)).fetchone():
            raise ValueError('rare_required')
        # This is the existing Rare table, not a migration or a serial reset.
        conn.execute('''CREATE TABLE IF NOT EXISTS rare_cards_info (
            card_id TEXT PRIMARY KEY,price_coins INTEGER NOT NULL,
            limited_quantity INTEGER NOT NULL,total_issued INTEGER DEFAULT 0,
            FOREIGN KEY(card_id) REFERENCES cards(card_id))''')
        old = conn.execute('SELECT limited_quantity,total_issued FROM rare_cards_info WHERE card_id=?', (card,)).fetchone()
        if (old[0] if old else None) != expected:
            raise ValueError('supply_changed')
        reserved = old[0]-old[1]-rare_available_in(conn, card) if old else 0
        if old and total < old[1]+reserved:
            raise ValueError('rare_supply_reserved_or_issued')
        if old:
            conn.execute('UPDATE rare_cards_info SET limited_quantity=? WHERE card_id=?', (total, card))
        else:
            conn.execute('INSERT INTO rare_cards_info VALUES(?,0,?,0)', (card, total))
        audit = {'actor':actor, 'card_id':card, 'before':expected, 'after':total,
                 'issued':old[1] if old else 0, 'at':datetime.now(timezone.utc).isoformat()}
        conn.execute('INSERT INTO foundation_settings VALUES(?,?)', ('rare-supply-audit:'+uuid.uuid4().hex, json.dumps(audit)))
        return {'ok':True}


def catalog(db):
    from systems.attack_rewards import rare_available_in
    with closing(sqlite3.connect(db.db_path)) as conn:
        has_info = conn.execute("SELECT 1 FROM sqlite_master WHERE name='rare_cards_info'").fetchone()
        result = []
        for card, name in conn.execute("SELECT card_id,name FROM cards WHERE origin='official' AND rarity='rare' ORDER BY name"):
            info = conn.execute('SELECT limited_quantity,total_issued FROM rare_cards_info WHERE card_id=?', (card,)).fetchone() if has_info else None
            available = rare_available_in(conn, card) if info else 0
            result.append({'card_id':card, 'name':name, 'supply':info[0] if info else None,
                           'issued':info[1] if info else 0, 'available':available,
                           'reserved':info[0]-info[1]-available if info else 0})
        return result
