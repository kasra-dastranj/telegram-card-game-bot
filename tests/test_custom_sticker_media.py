"""Private dual artwork, legacy fallbacks and post-win/receipt sticker delivery."""
import asyncio
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image
import pytest
from telegram.error import RetryAfter

from bot.battle_visual_delivery import card_art
from bot.card_reward_presentation import send_card_sticker, send_claim_card
from bot.custom_card_notifications import deliver
from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.basic import BasicHandlersMixin
from bot.handlers.game_modes import GameModeHandlersMixin
from core.card_media import sticker_path
from core.models import Card, CardRarity
from systems.custom_cards import ensure_custom_schema, media_path
from tests.test_custom_admin_fulfillment import form, definition, revise
from tests.test_custom_card_notifications import due, notices
from tests.test_custom_cards_phase3 import custom, post
from tests.test_rare_delivery import rare, supply, grant


def artwork(color):
    image = Image.new('RGBA', (240, 400), (0, 0, 0, 0))
    image.paste(color, (70, 30, 180, 350))
    stream = BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def test_existing_custom_definitions_upgrade_without_losing_the_original_image():
    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE foundation_settings(key TEXT PRIMARY KEY,value_json TEXT)')
        conn.execute('CREATE TABLE custom_definitions(card_id TEXT PRIMARY KEY,order_id TEXT,payload_json TEXT,'
                     'status TEXT,media_id TEXT,actor TEXT,created_at TEXT,updated_at TEXT)')
        conn.execute("INSERT INTO custom_definitions VALUES('cc-old','order','{}','active','original-image','admin','old','old')")
        ensure_custom_schema(conn)
        ensure_custom_schema(conn)
        assert conn.execute('SELECT media_id,sticker_media_id,status FROM custom_definitions').fetchone() == ('original-image', None, 'active')


def upload(custom, color, kind='photo'):
    response = custom[2].post('/api/custom/media', headers={'X-Admin-Token': 'synthetic-test-admin'},
                             data={'kind': kind, 'image': (BytesIO(artwork(color)), 'art.png')})
    assert response.status_code == 201, response.get_json()
    return response.get_json()['media_id']


def make_card(custom, with_sticker=True):
    payload = form(users=[1])
    payload['media_id'] = upload(custom, 'blue')
    if with_sticker:
        payload['sticker_media_id'] = upload(custom, 'red', 'sticker')
    response = post(custom, 'fulfill', payload)
    assert response.status_code == 200, response.get_json()
    return custom[0].get_card_by_id(response.get_json()['card_id']), payload


def delivered_image(sender):
    call = sender.await_args
    stream = call.kwargs.get('sticker') if 'sticker' in call.kwargs else call.args[0]
    image = Image.open(BytesIO(stream.getvalue())).convert('RGBA')
    assert max(image.size) == 512
    assert image.getpixel((0, 0))[3] == 0
    return image.getpixel((image.width // 2, image.height // 2))


def test_private_photo_and_sticker_preserve_alpha_and_distinct_art(custom):
    card, payload = make_card(custom)
    photo = media_path(custom[0], card.card_id)
    sticker = sticker_path(card, db=custom[0])
    assert photo != sticker and sticker.endswith('.webp')
    image = Image.open(photo).convert('RGBA')
    assert image.getpixel((0, 0))[3] == 0
    assert image.getpixel((120, 200))[2] > 240
    handler = SimpleNamespace(db=custom[0])
    context = SimpleNamespace(bot_data={})
    portrait = asyncio.run(card_art(handler, context, card, preserve_alpha=True))
    assert Image.open(BytesIO(portrait)).convert('RGBA').getpixel((120, 200))[2] > 240
    sender = AsyncMock()
    assert asyncio.run(send_card_sticker(handler, context, card, sender))
    assert delivered_image(sender)[0] > 200
    url = '/api/custom/media/' + payload['sticker_media_id']
    assert custom[2].get(url).status_code == 401
    response = custom[2].get(url, headers={'X-Admin-Token': 'synthetic-test-admin'})
    assert response.status_code == 200 and response.mimetype == 'image/webp'
    assert response.headers['Cache-Control'] == 'private, no-store'
    response.close()


@pytest.mark.parametrize('with_sticker', [False, True])
@pytest.mark.parametrize('entry', ['claim', 'quick', 'win', 'collection'])
def test_custom_claim_preview_and_winner_send_stickers(custom, entry, with_sticker):
    card, _ = make_card(custom, with_sticker)
    handler = BattleHandlersMixin() if entry == 'win' else BasicHandlersMixin() if entry == 'collection' else GameModeHandlersMixin()
    handler.db, handler.config = custom[0], {'image_settings': {'enable_images': True}}
    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(send_sticker=AsyncMock(), send_photo=AsyncMock()))
    with patch.object(custom[0], 'get_card_variant_media_file_id', side_effect=AssertionError('custom media is private')):
        if entry == 'claim':
            message = SimpleNamespace(reply_sticker=context.bot.send_sticker, reply_photo=context.bot.send_photo, reply_text=AsyncMock())
            assert asyncio.run(send_claim_card(message, card, handler.config, custom[0]))
        elif entry == 'quick':
            asyncio.run(handler._send_quick_card_preview(context, 1, card))
        elif entry == 'collection':
            query = SimpleNamespace(from_user=SimpleNamespace(id=1), message=SimpleNamespace(chat_id=1, reply_sticker=context.bot.send_sticker))
            asyncio.run(handler._send_owned_card_sticker(query, context, card))
        else:
            assert asyncio.run(handler._send_round_winner_card_media(context, -100123, card))
    context.bot.send_photo.assert_not_awaited()
    context.bot.send_sticker.assert_awaited_once()
    pixel = delivered_image(context.bot.send_sticker)
    assert pixel[0 if with_sticker else 2] > 200


def test_custom_edit_preserves_or_replaces_sticker_without_changing_photo(custom):
    card, payload = make_card(custom)
    edit = revise(custom, card.card_id)  # A legacy client omits sticker_media_id.
    assert post(custom, 'revise', edit).status_code == 200
    assert definition(custom, card.card_id)['sticker_media_id'] == payload['sticker_media_id']
    updated = upload(custom, 'green', 'sticker')
    edit = revise(custom, card.card_id)
    edit['sticker_media_id'] = updated
    assert post(custom, 'revise', edit).status_code == 200
    assert definition(custom, card.card_id)['media_id'] == payload['media_id']
    sender = AsyncMock()
    asyncio.run(send_card_sticker(SimpleNamespace(db=custom[0]), SimpleNamespace(bot_data={}), card, sender))
    assert delivered_image(sender)[1] > 90  # Replacement, no stale Telegram cache.
    post(custom, 'remove_image', {'card_id': card.card_id})
    assert media_path(custom[0], card.card_id) is None
    assert sticker_path(card, db=custom[0]) is None


def test_non_sticker_upload_cannot_be_used_as_sticker_and_rolls_back(custom):
    payload = form(users=[1])
    payload['sticker_media_id'] = upload(custom, 'red')
    response = post(custom, 'fulfill', payload)
    assert response.status_code == 400 and response.get_json()['error'] == 'invalid_private_sticker'
    with sqlite3.connect(custom[0].db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM custom_definitions').fetchone()[0] == 0


def test_custom_receipt_sends_sticker_then_information_once_and_retries_transient_failure(custom):
    make_card(custom)
    bot = SimpleNamespace(db=custom[0])
    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(send_sticker=AsyncMock(side_effect=RetryAfter(1)),
        send_photo=AsyncMock(), send_message=AsyncMock()))
    asyncio.run(deliver(bot, context))
    context.bot.send_photo.assert_not_awaited()
    context.bot.send_message.assert_not_awaited()
    assert next(iter(notices(custom[0]).values()))['state'] != 'sent'
    context.bot_data.pop('_custom_card_notices_pause_until', None)
    context.bot.send_sticker.side_effect = None
    due(custom[0])
    asyncio.run(deliver(bot, context))
    context.bot.send_message.assert_awaited_once()
    assert delivered_image(context.bot.send_sticker)[0] > 200
    assert next(iter(notices(custom[0]).values()))['state'] == 'sent'
    asyncio.run(deliver(bot, context))
    assert context.bot.send_sticker.await_count == 2  # Failed attempt and one successful retry.
    context.bot.send_message.assert_awaited_once()


@pytest.mark.parametrize('dedicated', [False, True])
def test_rare_claim_prefers_sticker_over_cached_photo(custom, tmp_path, monkeypatch, dedicated):
    monkeypatch.chdir(tmp_path)
    db = custom[0]
    photo = tmp_path / 'rare.png'
    photo.write_bytes(artwork('blue'))
    card = Card('rare-hero', 'Rare Hero', CardRarity.RARE, 5, 6, 7, 8, [], image_path=str(photo))
    db.add_card(card)
    db.set_card_variant_media_file_id(card.card_id, 'rare', 'old-cached-photo', 'photo')
    if dedicated:
        directory = tmp_path / 'assets/stickers'
        directory.mkdir(parents=True)
        Image.open(BytesIO(artwork('red'))).save(directory / 'RARE_HERO_RARE.webp', 'WEBP')
    message = SimpleNamespace(reply_sticker=AsyncMock(), reply_photo=AsyncMock(), reply_text=AsyncMock())
    assert asyncio.run(send_claim_card(message, card, {'image_settings': {'enable_images': True}}, db))
    message.reply_photo.assert_not_awaited()
    assert delivered_image(message.reply_sticker)[0 if dedicated else 2] > 200


def test_rare_admin_receipt_uses_its_sticker_then_serial_information(rare):
    db, _ = rare
    supply(rare)
    assert grant(rare).status_code == 200
    db.set_card_variant_media_file_id('rare', 'rare', 'rare-sticker-id', 'sticker')
    db.set_card_variant_media_file_id('rare', 'rare', 'old-photo-id', 'photo')
    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(send_sticker=AsyncMock(), send_photo=AsyncMock(), send_message=AsyncMock()))
    asyncio.run(deliver(SimpleNamespace(db=db), context))
    assert context.bot.send_sticker.await_args.kwargs['sticker'] == 'rare-sticker-id'
    context.bot.send_photo.assert_not_awaited()
    context.bot.send_message.assert_awaited_once()
    assert 'Rare' in context.bot.send_message.await_args.kwargs['text']
    asyncio.run(deliver(SimpleNamespace(db=db), context))
    context.bot.send_sticker.assert_awaited_once()
