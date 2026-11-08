"""Sticker buttons retain the shown form and disclose only public card details."""
import asyncio
from datetime import datetime, timezone
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.error import BadRequest

from bot.card_sticker_details import button, details, handle
from bot.card_reward_presentation import send_card_sticker, send_claim_card
from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.game_modes import GameModeHandlersMixin
from core.database import DatabaseManager
from core.models import Card, CardRarity
from tests.test_custom_cards_phase3 import custom, post
from tests.test_custom_admin_fulfillment import form


def event(data, user_id=101, chat_id=None):
    user = User(user_id, 'Tester', False)
    message = Message(20, datetime.now(timezone.utc), Chat(chat_id or user_id, 'private' if chat_id is None else 'group'))
    transport = SimpleNamespace(answer_callback_query=AsyncMock(), send_message=AsyncMock(),
                                edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock())
    message.set_bot(transport)
    query = CallbackQuery('stats-click', user, 'chat', message=message, data=data)
    query.set_bot(transport)
    return Update(30, callback_query=query), transport


@pytest.fixture
def scene(tmp_path):
    db = DatabaseManager(str(tmp_path / 'details.db'))
    db.add_card(Card('hero:with_parts', 'Sub-Zero <&> _*', CardRarity.NORMAL, 80, 70, 60, 50, []))
    base = db.get_card_variant('hero:with_parts', 'normal')
    db.save_card_variant('hero:with_parts', 'legend', dict(base, power=100, popularity=95))
    return SimpleNamespace(db=db), SimpleNamespace(bot_data={})


@pytest.mark.parametrize('rarity,power,popularity', [('normal', 80, 50), ('legend', 100, 95)])
@pytest.mark.parametrize('chat_id', [None, -100123])
def test_real_callback_shows_requested_form_without_editing_or_mutating_game(scene, rarity, power, popularity, chat_id):
    bot, context = scene
    card = bot.db.get_card_by_id_for_rarity('hero:with_parts', rarity)
    markup = button(card)
    update, transport = event(markup.inline_keyboard[0][0].callback_data, chat_id=chat_id)
    with sqlite3.connect(bot.db.db_path) as conn:
        before = list(conn.iterdump())
    for _ in range(2):
        asyncio.run(handle(bot, update, context))
        text = transport.answer_callback_query.await_args.kwargs['text']
        assert f'قدرت: {power}' in text and f'محبوبیت: {popularity}' in text
        assert rarity.title() in text and '<&> _*' in text
        assert transport.answer_callback_query.await_args.kwargs['show_alert']
    with sqlite3.connect(bot.db.db_path) as conn:
        assert list(conn.iterdump()) == before
    transport.send_message.assert_not_awaited()
    transport.edit_message_text.assert_not_awaited()
    transport.edit_message_reply_markup.assert_not_awaited()
    assert not context.bot_data


@pytest.mark.parametrize('data', ['card_stats:bad:hero', 'card_stats:normal:', 'card_stats:normal:missing',
                                  'card_stats:normal:' + 'x' * 60, 'other:normal:hero', 'card_stats'])
def test_invalid_and_stale_callbacks_are_answered_without_details(scene, data):
    bot, context = scene
    update, transport = event(data)
    asyncio.run(handle(bot, update, context))
    assert 'در دسترس نیست' in transport.answer_callback_query.await_args.kwargs['text']
    assert transport.answer_callback_query.await_count == 1


def test_telegram_limits_bidi_and_rare_form(scene):
    bot, _ = scene
    card = bot.db.get_card_by_id_for_rarity('hero:with_parts', 'normal')
    card.name = '\u202e' + '😎' * 500 + '\nDO NOT PARSE <b>_'
    card.rarity = CardRarity.RARE
    markup = button(card)
    assert len(markup.inline_keyboard[0][0].callback_data.encode('utf-8')) <= 64
    assert '\u202e' not in markup.inline_keyboard[0][0].text
    assert len(details(card).encode('utf-16-le')) // 2 <= 200
    card.card_id = 'x' * 70
    assert button(card) is None


@pytest.mark.parametrize('kind', ['group', 'other_user', 'revoked', 'suspended', 'wrong_form'])
def test_custom_details_recheck_private_grant_and_do_not_reveal_hidden_stats(custom, kind):
    card_id = post(custom, 'fulfill', form(users=[1])).get_json()['card_id']
    db = custom[0]
    card = db.get_card_by_id(card_id)
    data = button(card).inline_keyboard[0][0].callback_data
    if kind == 'revoked': post(custom, 'revoke', {'card_id': card_id, 'users': [1]})
    if kind == 'suspended': post(custom, 'status', {'card_id': card_id, 'status': 'suspended'})
    if kind == 'wrong_form': data = data.replace(':normal:', ':legend:')
    update, transport = event(data, user_id=2 if kind == 'other_user' else 1, chat_id=-100123 if kind == 'group' else None)
    asyncio.run(handle(SimpleNamespace(db=db), update, SimpleNamespace()))
    text = transport.answer_callback_query.await_args.kwargs['text']
    assert 'در دسترس نیست' in text and 'شخصیت MH' not in text


def test_custom_owner_sees_public_stats_with_gameplay_flags_off(custom):
    card_id = post(custom, 'fulfill', form(users=[1])).get_json()['card_id']
    data = button(custom[0].get_card_by_id(card_id)).inline_keyboard[0][0].callback_data
    update, transport = event(data, user_id=1)
    asyncio.run(handle(SimpleNamespace(db=custom[0]), update, SimpleNamespace()))
    text = transport.answer_callback_query.await_args.kwargs['text']
    assert 'شخصیت MH' in text and '51' in text and '84' in text
    assert 'survival' not in text and 'مدیریت' not in text


@pytest.mark.parametrize('cached', [True, False])
def test_cached_and_generated_stickers_get_same_button_including_retry(scene, tmp_path, cached):
    bot, context = scene
    path = tmp_path / 'hero.png'
    Image.new('RGB', (128, 128), 'navy').save(path)
    card = bot.db.get_card_by_id_for_rarity('hero:with_parts', 'normal')
    card.image_path = str(path)
    bot.db.set_card_variant_media_file_id(card.card_id, 'normal', 'cached', 'sticker')
    sender = AsyncMock(side_effect=None if cached else [BadRequest('expired id'), SimpleNamespace()])
    assert asyncio.run(send_card_sticker(bot, context, card, sender))
    for call in sender.await_args_list:
        assert call.kwargs['reply_markup'] == button(card)
    if not cached:
        assert isinstance(sender.await_args.args[0], BytesIO)


def test_claim_and_quick_cached_media_have_buttons(scene):
    bot, context = scene
    card = bot.db.get_card_by_id_for_rarity('hero:with_parts', 'legend')
    bot.db.set_card_variant_media_file_id(card.card_id, 'legend', 'legend-sticker', 'sticker')
    message = SimpleNamespace(reply_sticker=AsyncMock(), reply_text=AsyncMock())
    assert asyncio.run(send_claim_card(message, card, {'image_settings': {'enable_images': True}}, bot.db))
    assert message.reply_sticker.await_args.kwargs['reply_markup'] == button(card)
    handler = GameModeHandlersMixin()
    handler.db = bot.db
    context.bot = SimpleNamespace(send_sticker=AsyncMock())
    asyncio.run(handler._send_quick_card_preview(context, 101, card))
    assert context.bot.send_sticker.await_args.kwargs['reply_markup'] == button(card)


def test_deck_round_winner_sticker_has_exact_form_button(scene, tmp_path):
    bot, context = scene
    path = tmp_path / 'winner.webp'
    Image.new('RGB', (128, 128), 'navy').save(path, 'WEBP')
    card = bot.db.get_card_by_id_for_rarity('hero:with_parts', 'legend')
    card.image_path = str(path)
    handler = BattleHandlersMixin()
    handler.config = {}
    context.bot = SimpleNamespace(send_sticker=AsyncMock(), send_photo=AsyncMock())
    assert asyncio.run(handler._send_round_winner_card_media(context, -100123, card))
    assert context.bot.send_sticker.await_args.kwargs['reply_markup'] == button(card)
