"""All-time group points from settled matches, keyed by match and player."""
import sqlite3
from contextlib import closing


def ensure_in(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS group_score_events (
        request_id TEXT NOT NULL, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
        score INTEGER NOT NULL, awarded_at TEXT NOT NULL,
        PRIMARY KEY(request_id, user_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_group_score_chat ON group_score_events(chat_id,user_id)')


def _table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _chat_in(conn, request_id):
    if _table(conn, 'game_requests'):
        row = conn.execute('SELECT origin_chat_id FROM game_requests WHERE request_id=?', (request_id,)).fetchone()
        if row and row[0] and row[0] < 0:
            return row[0]
    if request_id.startswith('fight:') and _table(conn, 'active_fights'):
        row = conn.execute('SELECT chat_id FROM active_fights WHERE fight_id=?', (request_id[6:],)).fetchone()
        if row and row[0] and row[0] < 0:
            return row[0]
    if request_id.startswith('risk:') and _table(conn, 'risk_matches'):
        row = conn.execute('SELECT chat_id FROM risk_matches WHERE match_id=?', (request_id[5:],)).fetchone()
        if row and row[0] and row[0] < 0:
            return row[0]
    return None


def record_in(conn, request_id, awards):
    """Run in the reward transaction, before finished fights are removed."""
    chat_id = _chat_in(conn, request_id)
    if chat_id is None:
        return
    ensure_in(conn)
    for user_id, award in awards.items():
        row = conn.execute('SELECT awarded_at FROM match_reward_events WHERE request_id=? AND user_id=?',
                           (request_id, int(user_id))).fetchone()
        if row:
            conn.execute('INSERT OR IGNORE INTO group_score_events VALUES (?,?,?,?,?)',
                         (request_id, int(user_id), chat_id, int(award['score']), row[0]))


def standings(db, chat_id):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        ensure_in(conn)
        rows = conn.execute('''SELECT user_id,SUM(score) AS points FROM group_score_events
            WHERE chat_id=? GROUP BY user_id HAVING SUM(score)>0 ORDER BY points DESC,user_id''', (chat_id,)).fetchall()
    result, previous_points, position = [], None, 0
    for index, (user_id, points) in enumerate(rows, 1):
        if points != previous_points:
            position = index
        result.append({'user_id': user_id, 'score': int(points), 'rank': position})
        previous_points = points
    return result


def rank(db, chat_id, user_id):
    return next(((item['rank'], item['score']) for item in standings(db, chat_id)
                 if item['user_id'] == user_id), (None, None))
