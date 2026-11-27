"""Real Telegram callbacks change an owned form by editing the existing menu."""
import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import CallbackQueryHandler
from datetime import datetime, timezone

from bot.handlers import card_forms
from bot.main import TelegramCardBot
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import GameModeSystem
from tests.test_bot_collection_flow import collection, event


@pytest.fixture
def forms(collection):
    with sqlite3.connect(collection.db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 101, 'hero', 'epic', 2)
        CardInventorySystem.grant_in(conn, 101, 'hero', 'legend', 1)
    for rarity in card_forms.FORMS:
        collection.db.set_card_variant_media_file_id('hero', rarity, 'sticker-' + rarity, 'sticker')
    return collection, SimpleNamespace(user_data={}, bot_data={})


def open_detail(handler, context, card_id='hero'):
    update, bot = event('cardinfo_' + card_id)
    bot.send_sticker = AsyncMock()
    context.bot = bot
    asyncio.run(handler.cardinfo_handler(update, context))
    rows = bot.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    return next((button.callback_data for row in rows for button in row if button.callback_data.startswith('cf:')), None)


def invoke(handler, context, data):
    update, bot = event(data)
    bot.send_sticker = AsyncMock()
    context.bot = bot
    asyncio.run(handler.card_form_handler(update, context))
    return update, bot


def test_selector_only_lists_owned_forms_and_highlights_active(forms):
    handler, context = forms
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute("DELETE FROM player_card_stacks WHERE user_id=101 AND card_id='hero' AND rarity='epic'")
    data = open_detail(handler, context)
    assert data
    _, bot = invoke(handler, context, data)
    call = bot.edit_message_text.await_args.kwargs
    choices = [b for row in call['reply_markup'].inline_keyboard for b in row if b.callback_data.startswith('cf:')]
    assert [b.callback_data.rsplit(':', 1)[1] for b in choices] == ['normal', 'legend']
    assert 'فعال' in choices[0].text and 'فعال' not in choices[1].text
    assert all(len(b.callback_data.encode()) <= 64 for b in choices)
    bot.send_message.assert_not_awaited()


def test_single_form_does_not_offer_form_selection(collection):
    context = SimpleNamespace(user_data={}, bot_data={})
    with sqlite3.connect(collection.db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 101, 'hero', 'normal', 9)
    assert open_detail(collection, context) is None


def test_favorite_refresh_keeps_form_selection_without_another_sticker(forms):
    handler, context = forms
    open_detail(handler, context)
    update, bot = event('toggle_fav_hero')
    bot.send_sticker = AsyncMock()
    asyncio.run(handler.toggle_favorite_handler(update, context))
    assert 'cf:' in str(bot.edit_message_text.await_args.kwargs['reply_markup'])
    bot.send_sticker.assert_not_awaited()


def test_picking_the_current_form_does_not_emit_media_or_consume_choices(forms):
    handler, context = forms
    data = open_detail(handler, context).rsplit(':', 1)[0]
    _, bot = invoke(handler, context, data + ':normal')
    bot.send_sticker.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()
    _, bot = invoke(handler, context, data + ':legend')
    bot.send_sticker.assert_awaited_once()


@pytest.mark.parametrize('source,target', [('normal','epic'), ('normal','legend'), ('legend','normal'), ('epic','normal')])
def test_selection_edits_same_message_and_sends_exact_sticker_without_spending(forms, source, target):
    handler, context = forms
    inventory = CardInventorySystem(handler.db)
    assert inventory.activate(101, 'hero', source)['ok']
    counts = inventory.counts(101, 'hero')
    player = vars(handler.db.get_or_create_player(101)).copy()
    data = open_detail(handler, context).rsplit(':', 1)[0] + ':' + target
    update, bot = invoke(handler, context, data)
    assert handler.db.get_card_by_id_for_player('hero', 101).rarity.value == target
    assert inventory.counts(101, 'hero') == counts
    assert vars(handler.db.get_or_create_player(101)) == player
    bot.edit_message_text.assert_awaited_once()
    call = bot.edit_message_text.await_args.kwargs
    assert call['message_id'] == update.callback_query.message.message_id == 1
    assert card_forms.NAMES[source] in call['text'] and card_forms.NAMES[target] in call['text']
    assert call['parse_mode'] is None
    assert call['reply_markup'].inline_keyboard[0][0].callback_data == 'mycards_menu_1'
    bot.send_message.assert_not_awaited()
    bot.send_sticker.assert_awaited_once()
    assert bot.send_sticker.await_args.kwargs['sticker'] == 'sticker-' + target
    assert bot.send_sticker.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data == 'card_stats:' + target + ':hero'
    _, repeated = invoke(handler, context, data)
    repeated.send_sticker.assert_not_awaited()
    assert repeated.answer_callback_query.await_args.kwargs['show_alert']
    back_update, back_bot = event('mycards_menu_1')
    asyncio.run(handler.mycards_navigation_handler(back_update, context))
    assert 'mycards_normal_1' in str(back_bot.edit_message_text.await_args.kwargs['reply_markup'])


def test_forged_unowned_form_or_lost_card_never_changes_inventory(forms):
    handler, context = forms
    data = open_detail(handler, context).rsplit(':', 1)[0]
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute("DELETE FROM player_card_stacks WHERE user_id=101 AND card_id='hero' AND rarity='legend'")
    _, bot = invoke(handler, context, data + ':legend')
    assert bot.answer_callback_query.await_args.kwargs['show_alert']
    assert handler.db.get_card_by_id_for_player('hero', 101).rarity == CardRarity.NORMAL
    bot.edit_message_text.assert_not_awaited()
    bot.send_sticker.assert_not_awaited()
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute("DELETE FROM player_cards WHERE user_id=101 AND card_id='hero'")
        conn.execute("DELETE FROM player_card_stacks WHERE user_id=101 AND card_id='hero'")
    _, bot = invoke(handler, context, data + ':epic')
    assert bot.answer_callback_query.await_args.kwargs['show_alert']
    bot.send_sticker.assert_not_awaited()


def test_active_match_keeps_existing_form(forms):
    handler, context = forms
    data = open_detail(handler, context).rsplit(':', 1)[0] + ':legend'
    handler.db.get_or_create_player(202)
    modes = GameModeSystem(handler.db)
    request = modes.create_group_challenge(101, 'quick', 'normal', -100123)
    assert modes.accept_request(request['request_id'], 202)[0]
    _, bot = invoke(handler, context, data)
    assert bot.answer_callback_query.await_args.kwargs['show_alert']
    assert handler.db.get_card_by_id_for_player('hero', 101).rarity == CardRarity.NORMAL
    bot.send_sticker.assert_not_awaited()


def test_group_or_other_user_cannot_use_private_controls(forms):
    handler, context = forms
    data = open_detail(handler, context).rsplit(':', 1)[0] + ':legend'
    update, bot = event(data)
    message = Message(1, datetime.now(timezone.utc), Chat(-100123, 'supergroup'), text='forwarded')
    message.set_bot(bot)
    query = CallbackQuery('q', User(101, 'Owner', False), 'chat', message=message, data=data)
    query.set_bot(bot)
    asyncio.run(handler.card_form_handler(Update(1, callback_query=query), context))
    assert bot.answer_callback_query.await_args.kwargs['show_alert']
    _, other = invoke(handler, SimpleNamespace(user_data={}, bot_data={}), data)
    assert other.answer_callback_query.await_args.kwargs['show_alert']
    assert handler.db.get_card_by_id_for_player('hero', 101).rarity == CardRarity.NORMAL


def test_missing_sticker_keeps_success_in_same_message(forms):
    handler, context = forms
    data = open_detail(handler, context).rsplit(':', 1)[0] + ':legend'
    with patch('bot.card_reward_presentation.send_card_sticker', new=AsyncMock(return_value=False)):
        _, bot = invoke(handler, context, data)
    assert handler.db.get_card_by_id_for_player('hero', 101).rarity == CardRarity.LEGEND
    assert bot.edit_message_text.await_count == 2
    assert {call.kwargs['message_id'] for call in bot.edit_message_text.await_args_list} == {1}
    bot.send_message.assert_not_awaited()


def test_callback_is_registered_and_tokens_stay_short_for_long_card_ids(forms):
    handler, context = forms
    application = Mock()
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.setup_handlers(application)
    handlers = [call.args[0] for call in application.add_handler.call_args_list
                if isinstance(call.args[0], CallbackQueryHandler) and call.args[0].pattern
                and call.args[0].pattern.match('cf:token:legend')]
    assert len(handlers) == 1
    key = 'long_' + 'شخصیت' * 15
    handler.db.add_card(Card(key, 'Long', CardRarity.NORMAL, 1, 2, 3, 4, []))
    with sqlite3.connect(handler.db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 101, key, 'normal')
        CardInventorySystem.grant_in(conn, 101, key, 'epic')
    button = card_forms.button(handler, context, 101, handler.db.get_card_by_id_for_player(key, 101))
    assert len(button.callback_data.encode()) <= 64
