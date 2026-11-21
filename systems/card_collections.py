"""Multiple collections, with lossless support for the legacy series column."""
import json


def collection_names(value):
    if isinstance(value, dict):
        value = value.get('collections', value.get('series'))
    if value is None or value == '':
        return []
    if isinstance(value, str):
        if value.lstrip().startswith('['):
            value = json.loads(value)
        else:
            value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError('Collections must be a list of names')
    result, seen = [], set()
    for name in value:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError('Collection names must be 1..100 characters')
        name = name.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError('Invalid collection name')
        if name.casefold() not in seen:
            result.append(name)
            seen.add(name.casefold())
    return result


def stored_collections(value):
    names = collection_names(value)
    return (names[0] if len(names) == 1 else json.dumps(names, ensure_ascii=False)) if names else None


def remember_collections(conn, names):
    conn.execute('CREATE TABLE IF NOT EXISTS card_collection_registry '
                 '(collection_key TEXT PRIMARY KEY,name TEXT NOT NULL)')
    conn.executemany('INSERT OR IGNORE INTO card_collection_registry VALUES(?,?)',
                     [(name.casefold(), name) for name in collection_names(names)])


def list_collections(conn):
    # Reading editor options must not create schema or write a production DB.
    names = set()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_collection_registry'").fetchone():
        names.update(row[0] for row in conn.execute('SELECT name FROM card_collection_registry'))
    for row in conn.execute('SELECT series FROM card_mode_metadata').fetchall():
        names.update(collection_names(row[0]))
    return sorted(names)
