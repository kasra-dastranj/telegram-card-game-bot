"""Permanent trait vocabulary, independent of the cards currently using it."""
import json
import sqlite3
from contextlib import closing


DEFAULT_TRAITS = ('hero', 'funny', 'leader', 'villain', 'monster', 'god',
                  'warrior', 'assassin', 'detective', 'mage')


def _stored_traits(raw):
    values = json.loads(raw or '[]')
    if not isinstance(values, list):
        raise ValueError('Stored card traits must be a list')
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def remember_traits(conn, traits):
    """Use the caller's transaction; removing a card never removes vocabulary."""
    conn.executemany(
        'INSERT OR IGNORE INTO card_trait_registry(trait_key, name) VALUES (?, ?)',
        ((value.strip().casefold(), value.strip()) for value in traits
         if isinstance(value, str) and value.strip()),
    )


def remember_card_traits(conn, card_id, traits):
    previous = conn.execute('SELECT traits FROM card_mode_metadata WHERE card_id=?',
                            (card_id,)).fetchone()
    if previous:
        remember_traits(conn, _stored_traits(previous[0]))
    remember_traits(conn, traits)


def ensure_variant_traits_schema(conn):
    """NULL inherits legacy character traits; [] is an explicitly empty form."""
    columns = {row[1] for row in conn.execute('PRAGMA table_info(card_variants)')}
    if not columns:
        raise RuntimeError('Expected card_variants table is missing')
    if 'traits' not in columns:
        conn.execute('ALTER TABLE card_variants ADD COLUMN traits TEXT')


def variant_traits(conn, card_id, rarity):
    row = conn.execute('SELECT traits FROM card_variants WHERE card_id=? AND rarity=?',
                       (card_id, rarity)).fetchone()
    if row and row[0] is not None:
        return _stored_traits(row[0])
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_mode_metadata' AND type='table'").fetchone():
        row = conn.execute('SELECT traits FROM card_mode_metadata WHERE card_id=?', (card_id,)).fetchone()
        if row:
            return _stored_traits(row[0])
    return []


def save_variant_traits(conn, card_id, rarity, traits):
    """Persist a form override and its vocabulary in the caller's transaction."""
    if rarity not in ('normal', 'epic', 'legend'):
        raise ValueError('Invalid card form')
    if not isinstance(traits, list) or any(not isinstance(value, str) for value in traits):
        raise ValueError('Card traits must be a list of strings')
    ensure_trait_registry_schema(conn)
    remember_traits(conn, variant_traits(conn, card_id, rarity))
    remember_traits(conn, traits)
    conn.execute('UPDATE card_variants SET traits=? WHERE card_id=? AND rarity=?',
                 (json.dumps(traits, ensure_ascii=False), card_id, rarity))


def ensure_trait_registry_schema(conn):
    """Additive, idempotent migration; backfill all existing card traits."""
    conn.execute('''CREATE TABLE IF NOT EXISTS card_trait_registry (
        trait_key TEXT PRIMARY KEY,
        name TEXT NOT NULL
    )''')
    remember_traits(conn, DEFAULT_TRAITS)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='card_mode_metadata'").fetchone():
        for row in conn.execute('SELECT traits FROM card_mode_metadata').fetchall():
            remember_traits(conn, _stored_traits(row[0]))
    if 'traits' in {row[1] for row in conn.execute('PRAGMA table_info(card_variants)')}:
        for row in conn.execute('SELECT traits FROM card_variants WHERE traits IS NOT NULL').fetchall():
            remember_traits(conn, _stored_traits(row[0]))


class CardTraitRegistry:
    def __init__(self, db):
        self.db_path = db.db_path

    def list_traits(self):
        with closing(sqlite3.connect(self.db_path, timeout=10)) as conn:
            return sorted(row[0] for row in conn.execute('SELECT name FROM card_trait_registry'))

    def add_trait(self, name):
        if not isinstance(name, str):
            raise ValueError('نام Trait باید متن باشد')
        name = name.strip()
        if not name or len(name) > 100 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError('نام Trait باید بین ۱ تا ۱۰۰ کاراکتر و بدون نویسهٔ کنترلی باشد')
        with closing(sqlite3.connect(self.db_path, timeout=10)) as conn:
            with conn:
                remember_traits(conn, [name])
                return conn.execute('SELECT name FROM card_trait_registry WHERE trait_key=?',
                                    (name.casefold(),)).fetchone()[0]
