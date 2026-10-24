"""New invitations from completed matches; no replay of old choices/rewards."""
import json
from contextlib import closing
from datetime import datetime, timezone

from systems.match_activity import require_free_in
from systems.shared_foundation import context_in


def create(modes, kind, key, user_id, clicked_chat_id):
    from systems.game_mode_system import EASY_LOBBY_TTL_SECONDS, QUICK_GROUP_TTL_SECONDS
    if kind not in ('quick', 'deck', 'easy'):
        raise ValueError('این بازی قابل تکرار نیست.')
    with closing(modes._connect()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if kind == 'deck':
            from bot.deck_reports import load_in
            report = load_in(conn, key)
            if not report or not report.get('completed'):
                raise ValueError('این بازی هنوز تمام نشده یا گزارشش موجود نیست.')
            row = conn.execute("""SELECT r.* FROM game_requests r JOIN game_match_states s USING(request_id)
                WHERE r.mode='deck' AND json_extract(s.state_json,'$.fight_id')=? LIMIT 1""", (key,)).fetchone()
            source = dict(row) if row else None
            if source is None:
                raise ValueError('اطلاعات دعوت این بازی قدیمی موجود نیست؛ «بتل مبارزه» بنویس.')
            previous = context_in(conn, 'fight:' + key, 'deck')
            variant = previous.selection_variant
            players = report['players']
            state = {}
        else:
            row = conn.execute('SELECT * FROM game_requests WHERE request_id=? AND mode=?', (key, kind)).fetchone()
            result = conn.execute('SELECT report_json FROM game_match_reports WHERE request_id=?', (key,)).fetchone()
            if not row or row['status'] != 'completed' or not result:
                raise ValueError('این بازی هنوز تمام نشده یا گزارشش موجود نیست.')
            source = dict(row)
            report = json.loads(result[0])
            players = report.get('players') or [int(uid) for uid in report.get('scores', {})]
            variant = source['variant']
            saved = conn.execute('SELECT state_json FROM game_match_states WHERE request_id=?', (key,)).fetchone()
            state = json.loads(saved[0]) if saved else {}
        if user_id not in players:
            raise ValueError('فقط بازیکن‌های همین بازی می‌توانند بازی دوباره بسازند.')
        chat_id = source.get('origin_chat_id')
        if clicked_chat_id < 0 and clicked_chat_id != chat_id:
            raise ValueError('بازی دوباره را از گروه اصلی یا پیوی خودت باز کن.')
        if kind == 'easy' and (not chat_id or chat_id >= 0):
            raise ValueError('ایزی باید در گروه اصلی دوباره تشکیل شود.')
        replay_key = f'nav-rematch:{kind}:{key}'
        prior = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (replay_key,)).fetchone()
        if prior:
            existing = conn.execute('SELECT * FROM game_requests WHERE request_id=?', (json.loads(prior[0]),)).fetchone()
            now = datetime.now(timezone.utc).isoformat()
            delegated_done = False
            if existing and existing['mode'] == 'deck':
                saved = conn.execute('SELECT state_json FROM game_match_states WHERE request_id=?', (existing['request_id'],)).fetchone()
                fight_id = json.loads(saved[0]).get('fight_id') if saved else None
                if fight_id:
                    from bot.deck_reports import load_in
                    delegated_done = bool((load_in(conn, fight_id) or {}).get('completed'))
            if existing and not delegated_done and (existing['status'] in ('active', 'accepted') or existing['status'] == 'waiting' and existing['expires_at'] > now):
                return dict(existing), False
        require_free_in(conn, user_id)
        allowed, reason = modes.mode_access.check_in(conn, user_id, kind)
        if not allowed:
            raise ValueError(reason)
        if not modes.db.get_player_cards(user_id):
            raise ValueError('برای بازی اول یک کارت بگیر؛ در پیوی /claim بزن.')
        from systems.deck_system import DeckSystem
        if kind == 'deck' and variant == 'normal' and not DeckSystem(modes.db).get_valid_decks(user_id):
            raise ValueError('یک دک معتبر لازم داری؛ در پیوی دکت را بساز یا اصلاح کن.')
        if kind == 'deck' and variant == 'random':
            from systems.shared_foundation import eligible_cards
            if len(eligible_cards(modes.db, modes.db.get_player_cards(user_id), 'deck')) < 3:
                raise ValueError('Deck Random حداقل سه کارت مجاز می‌خواهد؛ اول از پیوی کارت بگیر.')
        target = next((uid for uid in players if uid != user_id), None)
        if kind != 'easy' and target is None:
            raise ValueError('حریف این بازی مشخص نیست؛ چالش تازه بساز.')
        if not chat_id or chat_id >= 0:
            chat_id = target
        request = modes._insert_request(conn, user_id, kind, variant,
            'easy_lobby' if kind == 'easy' else 'group_challenge' if chat_id < 0 else 'direct_rematch',
            EASY_LOBBY_TTL_SECONDS if kind == 'easy' else QUICK_GROUP_TTL_SECONDS,
            origin_chat_id=chat_id, rounds=source['rounds'], allow_custom_cards=bool(state.get('allow_custom_cards')))
        new_key = request['request_id']
        if kind == 'easy':
            modes._save_state(conn, new_key, {'mode': 'easy', 'allow_custom_cards': bool(state.get('allow_custom_cards')),
                'phase': 'lobby', 'players': [user_id], 'rounds': source['rounds'], 'current_round': 0,
                'scores': {str(user_id): 0}, 'question': None, 'choices': {}, 'options': {}, 'round_history': []})
        else:
            conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES (?,?)',
                         ('challenge-target:' + new_key, json.dumps(target)))
        conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES (?,?)', (replay_key, json.dumps(new_key)))
        return request, True
