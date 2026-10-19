"""Durable delivery receipts, queued in the same transaction as private grants."""
import json
import sqlite3
import time
import uuid
from contextlib import closing

PREFIX = 'custom-card-notice:'
LEASE_SECONDS = 180


def queue_in(conn, user_id, card_id):
    row = conn.execute("SELECT d.payload_json,c.abilities FROM custom_definitions d JOIN cards c USING(card_id) WHERE card_id=? AND d.status='active'", (card_id,)).fetchone()
    if not row:
        raise ValueError('active_custom_card_required')
    key = PREFIX + str(user_id) + ':' + card_id
    payload = json.loads(row[0])
    payload['abilities'] = json.loads(row[1])
    payload['traits'] = payload.get('metadata', {}).get('traits', payload.get('traits', []))
    notice = {'user_id':user_id, 'card_id':card_id, 'generation':uuid.uuid4().hex,
              'payload':payload, 'state':'pending', 'photo_done':False,
              'text_next':0, 'attempts':0, 'next_attempt':0, 'lease_until':0, 'lease':None}
    conn.execute('INSERT INTO foundation_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',
                 (key, json.dumps(notice)))


def claim(db):
    """A committed short lease prevents concurrent bot processes claiming twice."""
    with closing(sqlite3.connect(db.db_path, timeout=15)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("""SELECT key,value_json FROM foundation_settings
            WHERE key LIKE ? AND json_extract(value_json,'$.state') IN ('pending','retry','sending')
              AND json_extract(value_json,'$.next_attempt')<=?
              AND json_extract(value_json,'$.lease_until')<=?
            ORDER BY rowid LIMIT 1""", (PREFIX+'%', time.time(), time.time())).fetchone()
        if not row:
            return None
        value = json.loads(row[1])
        value.update(state='sending', lease=uuid.uuid4().hex,
                     lease_until=time.time()+LEASE_SECONDS, attempts=value['attempts']+1)
        conn.execute('UPDATE foundation_settings SET value_json=? WHERE key=?', (json.dumps(value), row[0]))
        return row[0], value


def checkpoint(db, key, notice, **changes):
    """Old leases/replaced grant generations may never acknowledge a new notice."""
    with closing(sqlite3.connect(db.db_path, timeout=15)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (key,)).fetchone()
        if not row:
            return False
        value = json.loads(row[0])
        if (value['generation'] != notice['generation'] or value['lease'] != notice['lease']
                or value['state'] != 'sending'):
            return False
        value.update(changes)
        value['lease_until'] = time.time()+LEASE_SECONDS if value['state']=='sending' else 0
        conn.execute('UPDATE foundation_settings SET value_json=? WHERE key=?', (json.dumps(value), key))
        notice.update(value)
        return True


def wake_user(db, user_id):
    """A private /start can retry a blocked/failed receipt, never a sent receipt."""
    with closing(sqlite3.connect(db.db_path, timeout=15)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        rows = conn.execute("""SELECT key,value_json FROM foundation_settings
            WHERE key LIKE ? AND json_extract(value_json,'$.state') IN ('blocked','failed')""",
            (PREFIX+str(user_id)+':%',)).fetchall()
        for key, raw in rows:
            value = json.loads(raw)
            value.update(state='retry', attempts=0, next_attempt=0, lease_until=0, lease=None)
            conn.execute('UPDATE foundation_settings SET value_json=? WHERE key=?', (json.dumps(value), key))
