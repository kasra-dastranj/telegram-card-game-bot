import asyncio
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot import navigation
from bot.game_help import GUIDES, catalog
from bot.handlers import customization
from systems.rematches import create as rematch
from tests.test_easy_presentation import scene


def group(update, uid=1):
    update.effective_chat = SimpleNamespace(id=-100123, type='supergroup')
    update.message.chat = update.effective_chat
    update.message.chat_id = -100123
    update.message.message_id = 10
    update.message.reply_to_message = None
    update.message.reply_text.return_value = SimpleNamespace(chat_id=-100123, message_id=11)
    update.callback_query.message = update.message


def completed_quick(bot):
    req = bot.modes.create_group_challenge(1, 'quick', 'normal', -100123)
    key = req['request_id']
    assert bot.modes.accept_request(key, 2)[0]
    bot.modes.start_quick_match(key)
    bot.modes.select_quick_card(key, 1, 'hero')
    state, _ = bot.modes.select_quick_card(key, 2, 'other')
    bot.modes.select_quick_ability(key, 1, 'skip')
    state, _ = bot.modes.select_quick_ability(key, 2, 'skip')
    for uid in (1, 2):
        stat = bot.modes.allowed_quick_stats(state, uid)[0]
        bot.modes.select_quick_stat(key, uid, stat)
    return key


@pytest.mark.parametrize('phrase,mode', [('بتل دک', 'deck'), ('  بتل   كوييك  ', 'quick'), ('بتل ایزی', 'easy')])
def test_mode_shortcuts_are_guides_and_never_create_matches(scene, phrase, mode):
    bot, update, context, _ = scene
    update.callback_query = None
    update.message.text = phrase
    assert asyncio.run(navigation.text(bot, update, context))
    assert update.message.reply_text.await_args.args[0].startswith(GUIDES[mode])
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM game_requests').fetchone()[0] == 0


def test_catalog_aliases_unknown_messages_and_draft_priority(scene):
    bot, update, context, _ = scene
    bot.leaderboard_command = AsyncMock()
    update.message.text = 'بتل رتبه'
    asyncio.run(navigation.text(bot, update, context))
    bot.leaderboard_command.assert_awaited_once_with(update, context)
    for ordinary in ('امروز بتل بازی کردم', 'بتلمن', 'سلام'):
        update.message.text = ordinary
        assert not asyncio.run(navigation.text(bot, update, context))
    assert all(name in catalog() for name in ('بتل دک', 'بتل کوییک', 'بتل ایزی', '/fight', '/profile', '/leaderboard'))
    context.user_data['easy_victory_draft'] = {'expires_at': time.time() + 100}
    update.message.text = 'بتل ایزی'
    asyncio.run(bot._deck_name_message_router(update, context))
    from systems.easy_presentation import read
    assert read(bot.db, 1)['slogan'] == 'بتل ایزی'


def test_reply_profile_uses_subject_without_controls_and_does_not_register_strangers(scene):
    bot, update, context, _ = scene
    group(update)
    update.callback_query = None
    update.message.text = 'بتل این'
    target = SimpleNamespace(id=2, first_name='Varan', username=None, is_bot=False)
    update.message.reply_to_message = SimpleNamespace(from_user=target)
    asyncio.run(navigation.text(bot, update, context))
    sent = update.message.reply_text.await_args
    assert 'Varan' in sent.args[0] and 'رتبهٔ گروه' in sent.args[0]
    assert sent.kwargs['reply_markup'] is None
    target.id = 9999
    asyncio.run(navigation.text(bot, update, context))
    assert 'ثبت نشده' in update.message.reply_text.await_args.args[0]
    with sqlite3.connect(bot.db.db_path) as conn:
        assert not conn.execute('SELECT 1 FROM players WHERE user_id=9999').fetchone()


def test_reply_invitation_only_named_opponent_can_accept_and_owner_controls_menu(scene):
    bot, update, context, _ = scene
    group(update)
    target = SimpleNamespace(id=2, first_name='Varan', is_bot=False)
    update.message.reply_to_message = SimpleNamespace(from_user=target)
    asyncio.run(bot.fight_command(update, context))
    query = update.callback_query
    query.message.message_id = 11
    query.data = 'gm_mode_quick'
    query.from_user = SimpleNamespace(id=3)
    asyncio.run(bot.game_mode_select_handler(update, context))
    assert query.answer.await_args.kwargs['show_alert']
    query.from_user = update.effective_user
    query.data = 'gm_variant_quick_normal'
    bot._schedule_mode_job = Mock()
    asyncio.run(bot.game_variant_handler(update, context))
    button = query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[0][0]
    key = button.callback_data.removeprefix('gm_accept_')
    assert not bot.modes.accept_request(key, 3)[0]
    assert bot.modes.get_request(key)['opponent_id'] is None
    assert bot.modes.accept_request(key, 2)[0]


def test_rematch_concurrency_creates_one_new_targeted_invitation_and_never_reawards(scene):
    bot, _, _, _ = scene
    key = completed_quick(bot)
    with sqlite3.connect(bot.db.db_path) as conn:
        before = conn.execute('SELECT * FROM match_reward_events').fetchall()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda uid: rematch(bot.modes, 'quick', key, uid, -100123), (1, 2)))
    assert results[0][0]['request_id'] == results[1][0]['request_id']
    assert sum(fresh for _, fresh in results) == 1
    request = results[0][0]
    assert request['status'] == 'waiting' and request['variant'] == 'normal'
    with pytest.raises(ValueError):
        rematch(bot.modes, 'quick', key, 3, -100123)
    with pytest.raises(ValueError):
        rematch(bot.modes, 'quick', key, 1, -999)
    assert not bot.modes.accept_request(request['request_id'], 3)[0]
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute('SELECT * FROM match_reward_events').fetchall() == before


def test_resume_only_own_quick_choices_and_original_deadline(scene):
    bot, update, context, _ = scene
    request = bot.modes.create_group_challenge(1, 'quick', 'normal', -100123)
    key = request['request_id']
    bot.modes.accept_request(key, 2)
    state = bot.modes.start_quick_match(key)
    deadline = state['deadline']
    bot._schedule_mode_job = Mock()
    update.effective_chat = SimpleNamespace(type='private', id=1)
    asyncio.run(navigation.resume(bot, update, context))
    rows = update.message.reply_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert any(button.callback_data.startswith('gm_qcard_' + key) for row in rows for button in row)
    assert bot.modes.get_state(key)['deadline'] == deadline
    bot._schedule_mode_job.assert_not_called()
    bot.modes.select_quick_card(key, 1, 'hero')
    update.message.reply_text.reset_mock()
    asyncio.run(navigation.resume(bot, update, context))
    rows = update.message.reply_text.await_args.kwargs['reply_markup']
    assert rows is None  # Own already-submitted choice cannot be changed.


def test_customization_private_only_and_all_slots_accessible(scene):
    bot, update, context, _ = scene
    update.callback_query.data = 'style_menu'
    asyncio.run(customization.handle(bot, update, context))
    rows = update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    targets = {button.callback_data for row in rows for button in row}
    assert {'avatar_page_profile_0', 'avatar_page_easy_0', 'avatar_page_deck_0', 'easy_victory_menu', 'deck_victory_menu', 'style_voices'} <= targets
    group(update)
    update.callback_query.edit_message_text.reset_mock()
    asyncio.run(customization.handle(bot, update, context))
    update.callback_query.edit_message_text.assert_not_awaited()
    assert update.callback_query.answer.await_args.kwargs['show_alert']


def test_easy_rematch_requires_fresh_ready_and_keeps_round_count(scene):
    bot, _, _, _ = scene
    source = bot.modes.create_easy_lobby(1, -100123, 1)
    key = source['request_id']
    bot.modes.join_easy_lobby(key, 2)
    assert bot.modes.start_easy_match(key)[0]
    for uid in (1, 2):
        card = bot.modes.get_easy_options(key, uid)[0]
        assert bot.modes.select_easy_card(key, uid, card.card_id)[0]
    bot.modes.resolve_easy_round(key)
    replay, fresh = rematch(bot.modes, 'easy', key, 2, -100123)
    assert fresh
    state = bot.modes.get_state(replay['request_id'])
    assert state['players'] == [2] and state['rounds'] == 1 and state['choices'] == {}
    repeated, fresh = rematch(bot.modes, 'easy', key, 1, -100123)
    assert not fresh and repeated['request_id'] == replay['request_id']
    assert bot.modes.get_state(replay['request_id'])['players'] == [2]
    assert bot.modes.join_easy_lobby(replay['request_id'], 1)[0]


def test_deck_rematch_keeps_random_variant_after_fight_cleanup(scene):
    bot, _, _, _ = scene
    from core.models import Card, CardRarity
    for cid in ('extra1', 'extra2'):
        bot.db.add_card(Card(cid, cid, CardRarity.NORMAL, 50, 50, 50, 50, []))
        for uid in (1, 2):
            bot.db.add_card_to_player(uid, cid)
    source = bot.modes.create_group_challenge(1, 'deck', 'random', -100123)
    assert bot.modes.accept_request(source['request_id'], 2)[0]
    fight = bot.db.create_fight(1, 2, -100123, mode='deck', selection_variant='random', request_id=source['request_id'])
    from bot.deck_reports import save_in
    with sqlite3.connect(bot.db.db_path) as conn:
        save_in(conn, fight, {'mode': 'deck', 'players': [1, 2], 'completed': True, 'rounds': []})
    bot.db.delete_fight(fight)
    request, fresh = rematch(bot.modes, 'deck', fight, 1, -100123)
    assert fresh and request['mode'] == 'deck' and request['variant'] == 'random'
    assert bot.modes.accept_request(request['request_id'], 2)[0]
    next_fight = bot.db.create_fight(1, 2, -100123, mode='deck', selection_variant='random', request_id=request['request_id'])
    with sqlite3.connect(bot.db.db_path) as conn:
        save_in(conn, next_fight, {'mode': 'deck', 'players': [1, 2], 'completed': True, 'rounds': []})
    bot.db.delete_fight(next_fight)
    newest, fresh = rematch(bot.modes, 'deck', fight, 1, -100123)
    assert fresh and newest['request_id'] != request['request_id']


def test_live_economy_guides_fit_telegram_and_use_actual_settings(scene):
    from bot.game_help import mode_guide
    bot, _, _, _ = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    for mode in ('quick', 'deck', 'easy'):
        value = mode_guide(bot, mode, 1)
        assert len(value.encode('utf-16-le')) // 2 <= 4096
        assert 'پاداش فعلی' in value
    assert '× ۵' in mode_guide(bot, 'deck', 1)
    assert 'بازی یک‌راندی XP و Score ندارد.' in mode_guide(bot, 'easy', 1)


def test_expired_reply_menu_and_busy_entry_preserve_existing_game(scene):
    bot, update, context, _ = scene
    group(update)
    query = update.callback_query
    navigation.bind_target(bot, SimpleNamespace(chat_id=-100123, message_id=10), 1,
                           SimpleNamespace(id=2, first_name='Varan'))
    with sqlite3.connect(bot.db.db_path) as conn:
        row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', ('nav-menu:-100123:10',)).fetchone()
        item = json.loads(row[0]); item['expires'] = 0
        conn.execute('UPDATE foundation_settings SET value_json=? WHERE key=?', (json.dumps(item), 'nav-menu:-100123:10'))
    query.data = 'gm_variant_quick_normal'
    asyncio.run(bot.game_variant_handler(update, context))
    assert query.answer.await_args.kwargs['show_alert']
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM game_requests').fetchone()[0] == 0
    source = bot.modes.create_group_challenge(1, 'quick', 'normal', -100123)
    bot.modes.accept_request(source['request_id'], 2)
    state = bot.modes.start_quick_match(source['request_id'])
    bot._schedule_mode_job = Mock()
    asyncio.run(bot.fight_command(update, context))
    assert 'بازی فعال' in update.message.reply_text.await_args.args[0]
    assert bot.modes.get_state(source['request_id']) == state
    bot._schedule_mode_job.assert_not_called()


def test_registered_shortcuts_do_not_shadow_private_drafts_or_game_callbacks(scene):
    from telegram import Update, User, Message, Chat
    from telegram.ext import MessageHandler, CallbackQueryHandler
    from datetime import datetime, timezone
    bot, _, _, _ = scene
    routes = []
    bot.setup_handlers(SimpleNamespace(add_handler=routes.append))
    user = User(1, 'MH', False)
    for chat_type, chat_id in (('supergroup', -100123), ('private', 1)):
        update = Update(1, message=Message(1, datetime.now(timezone.utc), Chat(chat_id, chat_type), from_user=user, text='بتل ایزی'))
        assert len([route for route in routes if isinstance(route, MessageHandler) and route.check_update(update)]) == 1
    callbacks = [route for route in routes if isinstance(route, CallbackQueryHandler)]
    for data in ('bn_help', 'bn_guide_deck', 'bn_again_quick_abcdef123456', 'style_menu', 'style_preview_easy', 'gm_mode_easy'):
        assert sum(bool(route.pattern and route.pattern.match(data)) for route in callbacks) == 1
