"""Explicit Persian shortcuts; shared entry points, no inferred chat actions."""
import json
import sqlite3
import time
from contextlib import closing

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

from bot.game_help import catalog, mode_guide


def normalize(text):
    return ' '.join((text or '').translate(str.maketrans({'ي': 'ی', 'ك': 'ک', '\u200c': ' '})).split())


def private_link(context, payload='nav'):
    return 'https://t.me/' + (getattr(context.bot, 'username', None) or 'TelBattleBot') + '?start=' + payload


def menu_context(bot, query):
    message = query.message
    if not isinstance(getattr(message, 'message_id', None), int) or not getattr(bot.db, 'db_path', None):
        return None
    with closing(sqlite3.connect(bot.db.db_path)) as conn:
        row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',
            (f'nav-menu:{message.chat_id}:{message.message_id}',)).fetchone()
    if not row:
        return None
    value = json.loads(row[0])
    if value['owner'] != query.from_user.id:
        raise ValueError('این منوی دعوت برای سازندهٔ آن است؛ خودت «بتل مبارزه» بنویس.')
    if time.time() > value['expires']:
        raise ValueError('این منو منقضی شده؛ دوباره «بتل مبارزه» بنویس.')
    return value


def bind_target(bot, message, owner_id, target):
    value = {'owner': owner_id, 'target': target.id, 'name': (target.first_name or 'بازیکن')[:64],
             'expires': time.time() + 300}
    with closing(sqlite3.connect(bot.db.db_path)) as conn, conn:
        conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES (?,?)',
                     (f'nav-menu:{message.chat_id}:{message.message_id}', json.dumps(value)))


def reply_target(update):
    reply = getattr(getattr(update, 'effective_message', None) or update.message, 'reply_to_message', None)
    if not reply or getattr(reply, 'sender_chat', None):
        return None
    user = getattr(reply, 'from_user', None)
    return user if user and not getattr(user, 'is_bot', False) else None


async def guide(bot, update, context, mode=None):
    query = update.callback_query
    if query:
        await query.answer()
    text = mode_guide(bot, mode, update.effective_user.id) if mode else catalog()
    rows = [[Button('🃏 راهنمای دک', callback_data='bn_guide_deck'),
             Button('⚡ راهنمای کوییک', callback_data='bn_guide_quick')],
            [Button('🎉 راهنمای ایزی', callback_data='bn_guide_easy')],
            [Button('📖 همهٔ دستورها', callback_data='bn_help')]]
    if query and not getattr(query.message, 'photo', None):
        await query.edit_message_text(text, reply_markup=Markup(rows))
    else:
        await update.effective_message.reply_text(text, reply_markup=Markup(rows))


async def home(bot, update, context):
    rows = [[Button('⚔️ مبارزه', callback_data='bn_fight')],
            [Button('👤 پروفایل من', callback_data='easy_profile'), Button('📖 راهنما', callback_data='bn_help')]]
    if update.effective_chat.type == 'private':
        rows.append([Button('🎭 ظاهر و برد', callback_data='style_menu')])
    if active_location(bot.db, update.effective_user.id):
        rows.insert(0, [Button('▶️ ادامهٔ بازی فعال', callback_data='bn_resume')])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text('🎮 بتل؛ کجا بریم؟', reply_markup=Markup(rows))
    else:
        await update.effective_message.reply_text('🎮 بتل؛ کجا بریم؟', reply_markup=Markup(rows))


async def text(bot, update, context):
    message = getattr(update, 'effective_message', None) or update.message
    value = normalize(message.text)
    if value != 'بتل' and not value.startswith('بتل '):
        return False
    action = value.removeprefix('بتل').strip()
    if action in ('دک', 'کوییک', 'کوئیک', 'کوییک مود', 'ایزی'):
        await guide(bot, update, context, 'deck' if action == 'دک' else 'easy' if action == 'ایزی' else 'quick')
    elif action == 'مبارزه':
        await bot.fight_command(update, context)
    elif action == 'من':
        await bot.profile_command(update, context)
    elif action == 'این':
        target = reply_target(update)
        if not target:
            await update.effective_message.reply_text('روی پیام یک بازیکن ریپلای کن و بنویس «بتل این».')
        else:
            await bot.profile_command(update, context, subject=target)
    elif action == 'رتبه':
        await bot.leaderboard_command(update, context)
    elif action == 'کلیم':
        await bot.claim_command(update, context)
    elif action == 'راهنما':
        await guide(bot, update, context)
    elif not action:
        await home(bot, update, context)
    else:
        await update.effective_message.reply_text('این عبارت را نمی‌شناسم؛ برای دیدن دستورها «بتل راهنما» بنویس.')
    return True


def active_location(db, user_id):
    from systems.match_activity import active_in
    if not getattr(db, 'db_path', None):
        return None
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        if not active_in(conn, user_id):
            return None
        for row in conn.execute('''SELECT r.*,s.state_json FROM game_requests r LEFT JOIN game_match_states s
            USING(request_id) WHERE r.status IN ('active','accepted','waiting') ORDER BY r.updated_at DESC'''):
            item = dict(row)
            state = json.loads(item.pop('state_json') or '{}')
            if user_id not in (item['creator_id'], item['opponent_id']) and user_id not in state.get('players', []):
                continue
            if state.get('phase') in ('completed', 'expired', 'cancelled'):
                continue
            if item['status'] == 'waiting' and not (item['mode'] == 'easy' and state.get('phase') == 'lobby'):
                continue
            from systems.match_activity import deadline_passed
            if item['status'] == 'waiting' and deadline_passed(item['expires_at']):
                continue
            if state.get('fight_id'):
                live = conn.execute("SELECT 1 FROM active_fights WHERE fight_id=? AND status NOT IN ('completed','cancelled','expired')",
                                    (state['fight_id'],)).fetchone()
                if not live:
                    continue
            return dict(item, state=state)
        row = conn.execute("SELECT * FROM active_fights WHERE (challenger_id=? OR opponent_id=?) AND status NOT IN ('completed','cancelled','expired')",
                           (user_id, user_id)).fetchone()
        return {'fight_id': row['fight_id'], 'origin_chat_id': row['chat_id']} if row else {'mode': 'other'}


def message_link(chat_id, message_id):
    if str(chat_id).startswith('-100') and isinstance(message_id, int):
        return f'https://t.me/c/{str(chat_id)[4:]}/{message_id}'
    return None


async def active_notice(bot, update, context):
    location = active_location(bot.db, update.effective_user.id)
    if not location:
        return False
    rows = []
    link = message_link(location.get('origin_chat_id'), location.get('origin_message_id'))
    if link:
        rows.append([Button('📍 پیام بازی در گروه', url=link)])
    rows.append([Button('▶️ ادامه در پیوی', url=private_link(context, 'nav_resume'))]
                if update.effective_chat.type != 'private' else [Button('▶️ ادامهٔ بازی', callback_data='bn_resume')])
    await update.effective_message.reply_text('یه بازی فعال داری؛ از همین مسیر ادامه بده. مهلت بازی تغییر نمی‌کند.', reply_markup=Markup(rows))
    return True


async def resume(bot, update, context):
    if update.effective_chat.type != 'private':
        return await active_notice(bot, update, context)
    user_id = update.effective_user.id
    location = active_location(bot.db, user_id)
    if not location:
        await update.effective_message.reply_text('بازی فعالی نداری؛ «بتل مبارزه» بنویس.')
        return
    state = location.get('state', {})
    request_id = location.get('request_id')
    phase = state.get('phase')
    from systems.match_activity import deadline_passed
    if state.get('deadline') and deadline_passed(state['deadline']):
        await update.effective_message.reply_text('مهلت این مرحله تمام شده؛ منتظر اعلام نتیجه یا مرحلهٔ بعد باش.')
        return
    rows = []
    if location.get('mode') == 'quick' and request_id:
        key = str(user_id)
        if phase == 'card_selection' and key not in state.get('cards', {}):
            # Reuse valid callback IDs; never restart phase jobs or deadlines.
            cards = bot.db.get_player_cards(user_id)
            from systems.shared_foundation import eligible_cards
            cards = eligible_cards(bot.db, cards, 'quick', request_id)
            rows = [[Button(card.name, callback_data=f'gm_qcard_{request_id}_{card.card_id}')]
                    for card in cards[:8]]
            if len(cards) > 8:
                rows.append([Button('بعدی', callback_data=f'gm_qpage_{request_id}_1')])
        elif phase == 'ability_selection' and key not in state.get('ability_choices', {}):
            arena = state.get('arena_snapshot') or bot.modes._arena(state['arena'])
            abilities = bot.modes.list_player_abilities(user_id) if arena.get('abilities_enabled', True) else []
            rows = [[Button(item['title'], callback_data=f"gm_qability_{request_id}_{item['ability_key']}")] for item in abilities]
            rows.append([Button('بدون Ability', callback_data=f'gm_qability_{request_id}_skip')])
        elif phase == 'stat_selection' and key not in state.get('stat_choices', {}):
            from bot.handlers.game_modes import STAT_LABELS
            preview = bot.modes.quick_stat_preview(state, user_id)
            rows = [[Button(f"{STAT_LABELS[stat]}: {preview['final_values'][stat]}", callback_data=f'gm_qstat_{request_id}_{stat}')]
                    for stat in bot.modes.allowed_quick_stats(state, user_id)]
    link = message_link(location.get('origin_chat_id'), location.get('origin_message_id'))
    fight_id = state.get('fight_id') or location.get('fight_id')
    if fight_id:
        panel = context.bot_data.get(f'deck_selection_panel_{fight_id}_{user_id}')
        group_panel = context.bot_data.get(f'deck_{fight_id}_status_message')
        if isinstance(group_panel, dict):
            group_panel = group_panel.get('message_id')
        link = message_link(location.get('origin_chat_id'), group_panel) or link
        if panel:
            decks = bot.db.get_battle_deck_state(fight_id)
            fight = bot.db.get_fight_by_id(fight_id)
            role = 'challenger' if fight and fight.challenger_id == user_id else 'opponent'
            if fight and not decks.get(role + '_deck_selected'):
                await bot._send_deck_selection(context, fight_id, user_id)
    if link:
        rows.append([Button('📍 ادامه در پیام بازی', url=link)])
    await update.effective_message.reply_text('▶️ بازی فعلی؛ انتخاب ثبت‌شده تغییر نمی‌کند و مهلت از نو شروع نمی‌شود.'
        if rows else 'انتخابت ثبت شده یا نوبت در پیام مشترک بازی است؛ منتظر نوبت یا نتیجه باش.', reply_markup=Markup(rows) if rows else None)


async def handle(bot, update, context):
    data = update.callback_query.data
    if data.startswith('bn_again_'):
        return await again(bot, update, context)
    if data == 'bn_fight':
        return await bot.request_pvp_fight_handler(update, context)
    if data == 'bn_help':
        return await guide(bot, update, context)
    if data.startswith('bn_guide_') and data[9:] in ('quick', 'deck', 'easy'):
        return await guide(bot, update, context, data[9:])
    await update.callback_query.answer()
    if data == 'bn_resume':
        return await resume(bot, update, context)


def again_button(kind, key):
    return Button('🔁 دوباره بازی کنیم', callback_data=f'bn_again_{kind}_{key}')


async def again(bot, update, context):
    query = update.callback_query
    try:
        _, _, kind, key = query.data.split('_', 3)
        from systems.rematches import create
        request, fresh = create(bot.modes, kind, key, query.from_user.id, update.effective_chat.id)
    except ValueError as error:
        message = {'friendly_disabled': 'حالت دوستانه فعلاً غیرفعال است؛ از «بتل مبارزه» حالت دیگری انتخاب کن.',
                   'easy_custom_disabled': 'ورود کارت سفارشی فعلاً غیرفعال است؛ از «بتل مبارزه» یک ایزی بدون کارت سفارشی بساز.'}.get(str(error), str(error))
        await query.answer(message, show_alert=True)
        return
    await query.answer('دعوت تازه آماده شد.' if fresh else 'این بازی دوباره قبلاً آماده شده است.')
    if not fresh and request.get('origin_message_id'):
        link = message_link(request.get('origin_chat_id'), request['origin_message_id'])
        await query.message.reply_text('دعوت بازی دوباره قبلاً ساخته شده؛ پذیرش یا Ready در همان پیام است.',
            reply_markup=Markup([[Button('📍 دعوت بازی دوباره', url=link)]]) if link else None)
        return
    request_id = request['request_id']
    if kind == 'easy':
        text = bot._easy_lobby_text(request_id)
        markup = bot._easy_lobby_markup(request_id)
    else:
        creator = bot.db.get_or_create_player(request['creator_id'])
        text = f"🔁 دعوت بازی دوباره؛ {creator.first_name}\n{kind.title()} / {request['variant']}\nحریف قبلی باید دوباره قبول کند؛ انتخاب‌ها از نو انجام می‌شوند."
        markup = Markup([[Button('✊ قبول مبارزه', callback_data=f'gm_accept_{request_id}')]])
    try:
        panel = await context.bot.send_message(chat_id=request['origin_chat_id'], text=text, reply_markup=markup)
        bot.modes.update_message_reference(request_id, request['origin_chat_id'], panel.message_id)
    except Exception:
        await query.message.reply_text('دعوت ثبت شد ولی ارسال پیام انجام نشد؛ دوباره همین دکمه را بزن. اگر حریف ربات را بسته، باید پیوی ربات را باز کند.')
        return
    from datetime import datetime, timezone
    remaining = max(0, (datetime.fromisoformat(request['expires_at']) - datetime.now(timezone.utc)).total_seconds())
    bot._schedule_mode_job(context, bot.easy_lobby_timeout_job if kind == 'easy' else bot.game_request_expire_job,
        remaining, {'request_id': request_id},
        f'gm-easy-lobby-{request_id}' if kind == 'easy' else f'gm-expire-{request_id}')
