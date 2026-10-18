"""Player-authored Easy victory cosmetics in the existing JSON settings store.

No startup writes, migrations or inventory mutations. Card forms are explicit;
ownership is checked on selection and again immediately before delivery.
"""
import json
import sqlite3
from contextlib import closing

from systems.deck_presentation import normalize_slogan

PREFIX = 'easy_victory:'


def read_in(conn, user_id):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',
                       (PREFIX + str(user_id),)).fetchone()
    try:
        value = json.loads(row[0]) if row else {}
        if not isinstance(value, dict):
            return {}
        result = {}
        if isinstance(value.get('card_id'), str) and value.get('rarity') in ('normal', 'rare', 'epic', 'legend'):
            result.update(card_id=value['card_id'], rarity=value['rarity'])
        if value.get('slogan'):
            result['slogan'] = normalize_slogan(value['slogan']).strip()
        return result
    except (ValueError, TypeError):
        return {}


def read(db, user_id):
    with closing(sqlite3.connect(db.db_path)) as conn:
        return read_in(conn, user_id)


def owned_card_in(db, conn, user_id, card_id, rarity):
    row = conn.execute('''SELECT 1 FROM player_card_stacks s JOIN cards c USING(card_id)
        WHERE s.user_id=? AND s.card_id=? AND s.rarity=? AND s.quantity>0 AND c.origin='official'
        ''', (user_id, card_id, rarity)).fetchone()
    if row:
        return db.get_card_by_id_for_rarity(card_id, rarity)
    from systems.custom_cards import user_card_in
    card = user_card_in(db, conn, user_id, card_id)
    return card if card and card.rarity.value == rarity else None


def owned_card(db, user_id, card_id, rarity):
    with closing(sqlite3.connect(db.db_path)) as conn:
        return owned_card_in(db, conn, user_id, card_id, rarity)


def choices(db, user_id):
    """Every owned official form, plus currently accessible custom characters."""
    with closing(sqlite3.connect(db.db_path)) as conn:
        result = [dict(card_id=row[0], rarity=row[1], name=row[2]) for row in conn.execute('''
            SELECT s.card_id,s.rarity,c.name FROM player_card_stacks s JOIN cards c USING(card_id)
            WHERE s.user_id=? AND s.quantity>0 AND c.origin='official'
            ORDER BY c.name,s.card_id,s.rarity''', (user_id,))]
    from systems.custom_cards import user_cards
    result.extend(dict(card_id=c.card_id, rarity=c.rarity.value, name=c.name) for c in user_cards(db, user_id))
    return result


def save(db, user_id, *, card_id=None, rarity=None, slogan=None):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        value = read_in(conn, user_id)
        if card_id is not None:
            if rarity not in ('normal', 'rare', 'epic', 'legend') or not owned_card_in(db, conn, user_id, card_id, rarity):
                raise ValueError('این فرم کارت رو نداری؛ دوباره از کارت‌های خودت انتخاب کن.')
            value.update(card_id=card_id, rarity=rarity)
        if slogan is not None:
            value['slogan'] = normalize_slogan(slogan).strip()
        conn.execute('INSERT OR REPLACE INTO foundation_settings(key,value_json) VALUES (?,?)',
                     (PREFIX + str(user_id), json.dumps(value, ensure_ascii=False)))
        return value


def clear(db, user_id):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('DELETE FROM foundation_settings WHERE key=?', (PREFIX + str(user_id),))
