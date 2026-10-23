import sqlite3
from types import SimpleNamespace

from systems.group_ranking import record_in, rank, standings


def test_group_scores_are_local_idempotent_and_never_backfill(tmp_path):
    db = SimpleNamespace(db_path=str(tmp_path / 'groups.db'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('CREATE TABLE game_requests(request_id TEXT,origin_chat_id INTEGER)')
        conn.execute('CREATE TABLE match_reward_events(request_id TEXT,user_id INTEGER,awarded_at TEXT)')
        conn.executemany('INSERT INTO game_requests VALUES (?,?)', [('old', -1), ('one', -1), ('two', -2), ('three', -1)])
        conn.executemany('INSERT INTO match_reward_events VALUES (?,?,?)', [('old', 1, 'old'), ('one', 1, 'now'), ('one', 2, 'now'), ('two', 1, 'now'), ('three', 2, 'now')])
    assert standings(db, -1) == []
    with sqlite3.connect(db.db_path) as conn:
        record_in(conn, 'one', {'1': {'score': 10}, '2': {'score': 0}})
        record_in(conn, 'one', {'1': {'score': 10}})
        record_in(conn, 'two', {'1': {'score': 99}})
        record_in(conn, 'three', {'2': {'score': 10}})
    assert rank(db, -1, 1) == (1, 10)
    assert rank(db, -1, 2) == (1, 10)
    assert rank(db, -2, 1) == (1, 99)
    assert rank(db, -2, 2) == (None, None)
