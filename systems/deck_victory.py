"""Player-wide Deck victory text; cosmetics only, no startup migration."""
import json
import sqlite3
from contextlib import closing

from systems.deck_presentation import normalize_slogan

PREFIX = 'deck_victory:'


def read_in(conn, user_id):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',
                       (PREFIX + str(user_id),)).fetchone()
    try:
        value = json.loads(row[0]) if row else {}
        return normalize_slogan(value['slogan']) if value.get('slogan') else ''
    except (ValueError, TypeError, AttributeError, KeyError):
        return ''


def read(db, user_id):
    with closing(sqlite3.connect(db.db_path)) as conn:
        return read_in(conn, user_id)


def save(db, user_id, slogan):
    slogan = normalize_slogan(slogan)
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES (?,?)',
                     (PREFIX + str(user_id), json.dumps({'slogan': slogan}, ensure_ascii=False)))


def clear(db, user_id):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('DELETE FROM foundation_settings WHERE key=?', (PREFIX + str(user_id),))
