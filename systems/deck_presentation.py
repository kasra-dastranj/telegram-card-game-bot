"""Deck display metadata in the existing JSON settings store; no startup migration.

Keys are namespaced by immutable deck ID and deleted with the deck. These are
player-authored presentation values, never economy or feature-flag settings.
"""
import json
import unicodedata

DEFAULT_SLOGAN = 'دیدین؟ اینه قدرت دک من!'
MAX_SLOGAN_LENGTH = 120
PREFIX = 'deck_presentation:'


def normalize_slogan(value):
    if not isinstance(value, str):
        raise ValueError('شعار باید متن باشه.')
    text = ' '.join(value.split())
    text = ''.join(c for c in text if unicodedata.category(c) not in ('Cc', 'Cf') or c in '\u200c\u200d')
    if not text or len(text) > MAX_SLOGAN_LENGTH:
        raise ValueError('یه شعار بین ۱ تا ۱۲۰ کاراکتر بنویس.')
    return text


def read_in(conn, deck_id):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (PREFIX + deck_id,)).fetchone()
    return json.loads(row[0]) if row else {}


def save_in(conn, deck_id, slogan):
    value = {'victory_slogan': normalize_slogan(slogan)}
    conn.execute('INSERT OR REPLACE INTO foundation_settings(key,value_json) VALUES (?,?)',
                 (PREFIX + deck_id, json.dumps(value, ensure_ascii=False)))


def delete_in(conn, deck_id):
    conn.execute('DELETE FROM foundation_settings WHERE key=?', (PREFIX + deck_id,))
