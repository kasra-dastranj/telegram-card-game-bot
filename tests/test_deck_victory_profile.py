import asyncio
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Update
from telegram.ext import CallbackQueryHandler
from bot.main import TelegramCardBot
from bot.handlers import deck_victory, easy_victory
from bot.deck_reports import snapshot_deck_selection, load_in, victory_caption
from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems import deck_victory as settings
from systems.deck_presentation import DEFAULT_SLOGAN


@pytest.fixture
def scene(tmp_path):
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db = DatabaseManager(str(tmp_path / 'deck-profile.db'))
    from systems.game_mode_system import GameModeSystem
    bot.modes = GameModeSystem(bot.db)
    bot.game = GameLogic(bot.db)
    bot.is_user_in_channel = AsyncMock(return_value=True)
    for uid in (1, 2):
        bot.db.get_or_create_player(uid, first_name='Player ' + str(uid))
    for cid in 'abc':
        bot.db.add_card(Card(cid, cid.upper(), CardRarity.NORMAL, 20, 30, 40, 50, []))
        bot.db.add_card_to_player(1, cid)
    message = SimpleNamespace(text='', reply_text=AsyncMock(), chat=SimpleNamespace(type='private'))
    user = SimpleNamespace(id=1, username='one', first_name='Player 1')
    query = SimpleNamespace(data='deck_victory_menu', from_user=user, message=message,
                            answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_user=user, effective_chat=message.chat,
                             effective_message=message, message=message)
    context = SimpleNamespace(user_data={})
    return bot, update, context


def test_profile_route_has_no_character_selector_and_saves_only_own_text(scene):
    bot, update, context = scene
    routes = []
    bot.setup_handlers(SimpleNamespace(add_handler=routes.append))
    telegram_update = Update(1, callback_query=update.callback_query)
    matched = [r for r in routes if isinstance(r, CallbackQueryHandler) and r.check_update(telegram_update)]
    assert len(matched) == 1
    asyncio.run(matched[0].callback(update, context))
    markup = update.callback_query.edit_message_text.await_args.kwargs['reply_markup']
    assert not any('cards' in b.callback_data or 'pick' in b.callback_data for row in markup.inline_keyboard for b in row)
    update.callback_query.data = 'deck_victory_slogan'
    asyncio.run(deck_victory.handle(bot, update, context))
    update.message.text = 'x' * 121
    asyncio.run(bot._deck_name_message_router(update, context))
    assert 'deck_victory_draft' in context.user_data and settings.read(bot.db, 1) == ''
    update.message.text = '  بردیم! <win>_* \u202e '
    asyncio.run(bot._deck_name_message_router(update, context))
    assert settings.read(DatabaseManager(bot.db.db_path), 1) == 'بردیم! <win>_*'
    assert settings.read(bot.db, 2) == ''
    assert 'deck_victory_draft' not in context.user_data
    assert update.message.reply_text.await_args.kwargs['parse_mode'] is None
    update.callback_query.data = 'deck_victory_clear'
    asyncio.run(deck_victory.handle(bot, update, context))
    assert settings.read(bot.db, 1) == ''


def test_profile_button_cancel_expiry_group_and_deck_easy_drafts(scene):
    bot, update, context = scene
    asyncio.run(bot.profile_command(update, context))
    markup = update.callback_query.edit_message_text.await_args.kwargs['reply_markup']
    assert any(b.callback_data == 'style_menu' for row in markup.inline_keyboard for b in row)
    for target in ('deck_victory_menu', 'easy_victory_menu'):
        context.user_data['deck_victory_draft'] = {'expires_at': time.time() + 10}
        update.callback_query.data = target
        asyncio.run((deck_victory if target.startswith('deck') else easy_victory).handle(bot, update, context))
        assert 'deck_victory_draft' not in context.user_data
    context.user_data['deck_victory_draft'] = {'expires_at': 0}
    update.message.text = 'دیر شد'
    asyncio.run(bot._deck_name_message_router(update, context))
    assert settings.read(bot.db, 1) == '' and 'deck_victory_draft' not in context.user_data
    context.user_data.update(deck_build={'waiting_name': True}, deck_victory_draft={'expires_at': 9999999999})
    bot.deck_name_message_handler = AsyncMock()
    asyncio.run(bot._deck_name_message_router(update, context))
    bot.deck_name_message_handler.assert_awaited_once()
    assert 'deck_victory_draft' not in context.user_data
    update.callback_query.data = 'deck_victory_slogan'
    asyncio.run(deck_victory.handle(bot, update, context))
    assert 'deck_victory_draft' not in context.user_data
    context.user_data.clear()
    update.effective_chat.type = 'group'
    asyncio.run(deck_victory.handle(bot, update, context))
    assert update.callback_query.answer.await_args.kwargs['show_alert']
    assert 'deck_victory_draft' not in context.user_data


def test_profile_slogan_frozen_at_selection_and_no_unwritten_default(scene):
    bot, _, _ = scene
    deck_id = bot.db.create_deck(1, 'دک', 'a', 'b', 'c', victory_slogan='شعار قدیمی دک')
    fight = bot.db.create_fight(1, 2, -100, mode='deck')
    settings.save(bot.db, 1, 'شعار پروفایل')
    snapshot_deck_selection(bot.db.db_path, fight, 1, bot.db.get_deck_by_id(deck_id))
    settings.save(bot.db, 1, 'بعداً عوض شد')
    snapshot_deck_selection(bot.db.db_path, fight, 1, bot.db.get_deck_by_id(deck_id))
    bot.db.delete_deck(deck_id)
    with sqlite3.connect(bot.db.db_path) as conn:
        report = load_in(conn, fight)
    assert 'شعار پروفایل' in victory_caption(report, 1)
    assert 'بعداً' not in victory_caption(report, 1)
    assert victory_caption(report, None) == 'این دست مساوی شد!'
    assert DEFAULT_SLOGAN not in victory_caption({}, 1)
    assert DEFAULT_SLOGAN not in victory_caption({'decks': {'1': {'victory_slogan': DEFAULT_SLOGAN}}}, 1)
