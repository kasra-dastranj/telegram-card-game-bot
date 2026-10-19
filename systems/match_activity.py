"""Database-backed admission checks. Call under BEGIN IMMEDIATE when admitting players.

No separate permanent busy flag: activity is derived from the live match and its
deadline. Waiting invitations do not reserve a player (inline offers several).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

BUSY_MESSAGE = "برای ورود به بازی جدید، اول بازی قبلیت رو تموم کن."
MAX_UNTIMED_SECONDS = 15 * 60
TERMINAL = {'completed', 'finished', 'cancelled', 'expired'}


class ActiveMatchError(ValueError):
    def __init__(self):
        super().__init__(BUSY_MESSAGE)


def _date(value, *, local=False):
    try:
        result = datetime.fromisoformat(str(value))
        return result.astimezone(None if local else timezone.utc).replace(tzinfo=None) if result.tzinfo else result
    except (TypeError, ValueError):
        return datetime.min


def _rows(conn, table, sql, args):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return []
    cursor = conn.execute(sql, args)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def deadline_passed(value, *, now=None):
    return _date(value) <= (now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None))


def active_in(conn: sqlite3.Connection, user_id: int, *, exclude_request=None, exclude_fight=None) -> bool:
    from systems.group_attacks import active_player_in
    if active_player_in(conn,user_id):return True
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    local_now = datetime.now()  # Legacy fight/solo/risk timestamps are local-naive.
    for fight in _rows(conn, 'active_fights',
            "SELECT f.*,b.status AS battle_status FROM active_fights f LEFT JOIN battle_states b ON b.fight_id=f.fight_id WHERE (f.challenger_id=? OR f.opponent_id=?) AND f.status NOT IN ('completed','cancelled','expired')", (user_id, user_id)):
        if fight['fight_id'] == exclude_fight or fight['status'] in TERMINAL:
            continue
        if fight['battle_status'] in TERMINAL:
            conn.execute("UPDATE active_fights SET status='completed' WHERE fight_id=?", (fight['fight_id'],))
            continue
        deadline = _date(fight['expires_at'], local=True) if fight['expires_at'] else _date(fight['created_at'], local=True) + timedelta(seconds=MAX_UNTIMED_SECONDS)
        if deadline > local_now:
            return True
        conn.execute("UPDATE active_fights SET status='cancelled' WHERE fight_id=?", (fight['fight_id'],))
        conn.execute("UPDATE battle_states SET status='completed' WHERE fight_id=?", (fight['fight_id'],))
    for fight in _rows(conn, 'solo_fights', "SELECT * FROM solo_fights WHERE player_id=? AND status NOT IN ('completed','cancelled','expired')", (user_id,)):
        if fight['status'] in TERMINAL:
            continue
        if _date(fight['created_at'], local=True) + timedelta(seconds=MAX_UNTIMED_SECONDS) > local_now:
            return True
        conn.execute("UPDATE solo_fights SET status='cancelled',completed_at=? WHERE fight_id=?",
                     (now.isoformat(), fight['fight_id']))
    for match in _rows(conn, 'risk_matches',
            "SELECT * FROM risk_matches WHERE (challenger_id=? OR opponent_id=?) AND status NOT IN ('completed','cancelled','expired')", (user_id, user_id)):
        if match['status'] in TERMINAL:
            continue
        if _date(match['created_at'], local=True) + timedelta(seconds=MAX_UNTIMED_SECONDS) > local_now:
            return True
        # Return escrow, including an unmatched raise, once; no XP or winner.
        changed = conn.execute("UPDATE risk_matches SET status='completed',bluff_phase='done',winner_id=NULL WHERE match_id=? AND status!='completed'", (match['match_id'],))
        if changed.rowcount:
            from systems.risk_mode_system import record_cash_in
            pending = int(match['raise_amount'] or 0) if match['bluff_phase'] == 'raise_pending' else 0
            pot = int(match['current_pot'])
            pending = max(0, min(pending, pot))
            first = (pot - pending) // 2 + (pending if match['raise_by'] == match['challenger_id'] else 0)
            for uid, amount in ((match['challenger_id'], first), (match['opponent_id'], pot - first)):
                conn.execute("UPDATE players SET coins=coins+? WHERE user_id=?", (amount, uid))
                record_cash_in(conn, match['match_id'], uid, amount, 'timeout_refund')
    for request in _rows(conn, 'game_requests',
            "SELECT r.*,s.state_json FROM game_requests r LEFT JOIN game_match_states s ON s.request_id=r.request_id WHERE (r.creator_id=? OR r.opponent_id=? OR r.mode='easy') AND r.status IN ('waiting','accepted','active')",
            (user_id, user_id)):
        if request['request_id'] == exclude_request:
            continue
        try:
            state = json.loads(request['state_json'] or '{}')
            if not isinstance(state, dict):
                state = {}
        except (ValueError, TypeError):
            state = {}
        participants = state.get('players', [])
        if not isinstance(participants, list):
            participants = []
        if user_id not in (request['creator_id'], request['opponent_id']) and user_id not in participants:
            continue
        if state.get('phase') in TERMINAL:
            continue
        if request['mode'] == 'deck' and state.get('fight_id'):
            continue  # Delegated to active_fights, including its completion.
        if request['status'] == 'waiting':
            if request['mode'] == 'easy' and state.get('phase') == 'lobby' and _date(request['expires_at']) > now:
                return True
            continue
        if request['status'] == 'accepted':
            if _date(request['accepted_at'] or request['updated_at']) + timedelta(seconds=60) > now:
                return True  # Short handoff reservation, never a permanent orphan.
            continue
        deadline = _date(state.get('deadline'))
        if request['mode'] == 'easy' or (request['mode'] == 'quick' and state.get('phase') == 'ability_selection'):
            deadline += timedelta(seconds=120)  # Allow the round timer to advance.
        if deadline > now:
            return True
        if request['mode'] == 'easy':
            state['phase'] = 'expired'
            conn.execute("UPDATE game_match_states SET state_json=? WHERE request_id=?", (json.dumps(state), request['request_id']))
            conn.execute("UPDATE game_requests SET status='expired' WHERE request_id=?", (request['request_id'],))
    return False


def require_free_in(conn, *players, exclude_request=None, exclude_fight=None):
    for uid in set(players) - {None, 0}:
        if active_in(conn, uid, exclude_request=exclude_request, exclude_fight=exclude_fight):
            raise ActiveMatchError()
