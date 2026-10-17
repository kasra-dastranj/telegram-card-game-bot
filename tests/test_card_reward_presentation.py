import asyncio
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest
from telegram.error import BadRequest

from bot.card_reward_presentation import biography_text, send_claim_card, send_upgrade_cards
from bot.handlers.progression import handle
from bot.main import TelegramCardBot
from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import items_in


@pytest.fixture
def scene(tmp_path):
    db = DatabaseManager(str(tmp_path / 'rewards.db'))
    db.get_or_create_player(1)
    card = Card('hero', 'قهرمان <MH>_*', CardRarity.NORMAL, 40, 30, 20, 10, [],
                biography='داستان من از یه روز بارونی شروع شد. <داستان> & قصه_*', dialogs=['این فقط شعار برده!'])
    db.add_card(card)
    for rarity, color in [('normal', 'red'), ('epic', 'blue'), ('legend', 'green')]:
        image = tmp_path / (rarity + '.png')
        Image.new('RGB', (200, 300), color).save(image)
        form = db.get_card_variant('hero', rarity)
        db.save_card_variant('hero', rarity, dict(form, image_path=str(image)))
        db.set_card_variant_media_file_id('hero', rarity, rarity + '-sticker', 'sticker')
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db, bot.game, bot.config = db, GameLogic(db), {'image_settings': {'enable_images': True}}
    bot.is_user_in_channel = AsyncMock(return_value=True)
    events = []

    async def sticker(value, **kwargs):
        events.append(('sticker', value.getvalue() if isinstance(value, BytesIO) else value))

    async def photo(value, **kwargs):
        events.append(('photo', kwargs))

    async def text(value, **kwargs):
        events.append(('text', value, kwargs))

    message = SimpleNamespace(reply_sticker=AsyncMock(side_effect=sticker), reply_photo=AsyncMock(side_effect=photo),
                              reply_text=AsyncMock(side_effect=text), chat=SimpleNamespace(type='private'))
    user = SimpleNamespace(id=1)
    query = SimpleNamespace(id='click', data='', from_user=user, message=message,
                            answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(effective_user=user, effective_message=message, callback_query=query)
    context = SimpleNamespace(user_data={}, bot_data={}, bot=SimpleNamespace())
    return bot, update, context, events


@pytest.mark.parametrize('entry', ['command', 'button', 'silver'])
@pytest.mark.parametrize('media', ['sticker', 'photo'])
def test_real_claim_entries_show_biography_and_never_victory_slogan(scene, entry, media):
    bot, update, context, events = scene
    if media == 'photo':
        with sqlite3.connect(bot.db.db_path) as conn:
            conn.execute('DELETE FROM card_variant_media_cache')
    if entry == 'silver':
        with sqlite3.connect(bot.db.db_path) as conn:
            conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
            items_in(conn, 1, 'free_silver_claim', 1)
        context.user_data['economy_actions'] = {'test': {'kind': 'silver_use', 'request_key': 'use-one'}}
        update.callback_query.data = 'v2_action_test'
        asyncio.run(handle(bot, update, context))
    else:
        callback = bot.claim_command if entry == 'command' else bot.daily_claim_handler
        asyncio.run(callback(update, context))
    rendered = '\n'.join(e[1]['caption'] or '' if e[0] == 'photo' else e[1] if e[0] == 'text' else '' for e in events)
    assert 'داستان من از یه روز بارونی شروع شد.' in rendered
    assert 'این فقط شعار برده!' not in rendered
    if media == 'photo':
        details = next(e[1] for e in events if e[0] == 'photo')
        assert details['parse_mode'] is None and '<داستان> & قصه_*' in details['caption']
    else:
        index = next(i for i, e in enumerate(events) if e[0] == 'sticker')
        assert 'داستان من' in events[index + 1][1]
    counts = CardInventorySystem(bot.db).counts(1, 'hero')
    assert counts == ({'epic': 1} if entry == 'silver' else {'normal': 1})


def test_long_bio_keeps_all_text_and_emoji_within_telegram_caption_limit(scene):
    bot, update, _, events = scene
    card = bot.db.get_card_by_id_for_rarity('hero', 'normal')
    card.biography = 'داستان 😎 ' * 300
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('DELETE FROM card_variant_media_cache')
    asyncio.run(send_claim_card(update.effective_message, card, bot.config, bot.db))
    caption = events[0][1]['caption']
    assert len(caption.encode('utf-16-le')) // 2 <= 1024
    assert caption + ''.join(e[1] for e in events[1:] if e[0] == 'text') == biography_text(card)


def test_missing_claim_image_keeps_full_biography_and_missing_bio_never_uses_slogan(scene):
    bot, update, _, events = scene
    card = bot.db.get_card_by_id_for_rarity('hero', 'normal')
    assert not asyncio.run(send_claim_card(update.effective_message, card, {}, bot.db))
    assert 'داستان من' in events[0][1]
    card.biography = ''
    assert 'هنوز نوشته نشده' in biography_text(card)
    assert 'این فقط شعار برده!' not in biography_text(card)


@pytest.mark.parametrize('target', ['epic', 'legend'])
def test_real_v2_upgrade_sends_source_then_target_even_with_higher_active_form_and_no_replay(scene, target):
    bot, update, context, events = scene
    source = 'normal' if target == 'epic' else 'epic'
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
        conn.execute("INSERT INTO economy_character_rules VALUES('hero','A')")
        CardInventorySystem.grant_in(conn, 1, 'hero', source, 12)
        CardInventorySystem.grant_in(conn, 1, 'hero', 'legend', 1)
        items_in(conn, 1, 'upgrade_card', 1)
    economy = ProgressionEconomy(bot.db)
    preview = economy.preview_upgrade(1, 'hero', target)
    assert preview['ok']
    context.user_data['economy_actions'] = {'test': {'kind': 'upgrade', 'card_id': 'hero', 'target': target,
                                                  'request_key': 'one-upgrade', 'config_version': preview['config_version']}}
    update.callback_query.data = 'v2_action_test'
    asyncio.run(handle(bot, update, context))
    assert events == [('sticker', source + '-sticker'), ('sticker', target + '-sticker')]
    assert source.title() + ' → ' + target.title() in update.callback_query.edit_message_text.await_args.args[0]
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM reward_ledger WHERE event_type='official_upgrade'").fetchone()[0] == 1
        inventory = CardInventorySystem.counts_in(conn, 1, 'hero')
        xp = conn.execute('SELECT total_xp FROM player_progression WHERE user_id=1').fetchone()[0]
    asyncio.run(handle(bot, update, context))
    assert len(events) == 2
    with sqlite3.connect(bot.db.db_path) as conn:
        assert CardInventorySystem.counts_in(conn, 1, 'hero') == inventory
        assert conn.execute('SELECT total_xp FROM player_progression WHERE user_id=1').fetchone()[0] == xp


@pytest.mark.parametrize('failure', ['insufficient', 'changed_config'])
def test_failed_upgrade_sends_no_stickers_and_spends_nothing(scene, failure):
    bot, update, context, events = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    version = ProgressionEconomy(bot.db).inventory(1)['config_version']
    context.user_data['economy_actions'] = {'test': {'kind': 'upgrade', 'card_id': 'hero', 'target': 'epic',
                                                  'request_key': 'failed', 'config_version': version + (failure == 'changed_config')}}
    update.callback_query.data = 'v2_action_test'
    asyncio.run(handle(bot, update, context))
    assert events == [] and CardInventorySystem(bot.db).counts(1, 'hero') == {}
    assert 'انجام نشد' in update.callback_query.edit_message_text.await_args.args[0]


def test_local_photos_are_sent_as_actual_webp_stickers_in_correct_order(scene):
    bot, update, context, events = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('DELETE FROM card_variant_media_cache')
    asyncio.run(send_upgrade_cards(bot, update, context, 'hero', 'normal', 'epic'))
    assert [e[0] for e in events] == ['sticker', 'sticker']
    for event, channel in zip(events, [0, 2]):
        image = Image.open(BytesIO(event[1])).convert('RGB')
        assert max(image.size) == 512 and len(event[1]) <= 512 * 1024
        assert image.getpixel((100, 100))[channel] > 200


def test_sticker_failure_preserves_source_target_context_and_transaction(scene):
    bot, update, context, events = scene
    update.effective_message.reply_sticker.side_effect = BadRequest('media unavailable')
    asyncio.run(send_upgrade_cards(bot, update, context, 'hero', 'normal', 'epic'))
    assert 'Normal' in events[0][1] and 'Epic' in events[1][1]
    assert CardInventorySystem(bot.db).counts(1, 'hero') == {}


@pytest.mark.parametrize('kind', ['coin', 'fusion'])
def test_legacy_upgrade_entry_points_send_two_forms_after_success_only(scene, kind):
    bot, update, context, events = scene
    if kind == 'coin':
        player = bot.db.get_or_create_player(1)
        player.coins = 10000
        bot.db.update_player(player)
        bot.db.add_card_to_player(1, 'hero')
        update.callback_query.data = 'shop_confirm_normal_to_epic_hero'
        context.user_data['shop_upgrade_request_key'] = 'coin-one'
        callback = bot.shop_confirm_upgrade_handler
    else:
        from systems.fusion_system import FusionSystem
        bot.fusion = FusionSystem(bot.db)
        for cid in ('extra1', 'extra2'):
            bot.db.add_card(Card(cid, cid, CardRarity.NORMAL, 10, 20, 30, 40, []))
            bot.db.add_card_to_player(1, cid)
        bot.db.add_card_to_player(1, 'hero')
        update.callback_query.data = 'fusion_upgrade_epic_hero'
        context.user_data.update(fusion_selected=['hero', 'extra1', 'extra2'], fusion_request_key='fusion-one')
        callback = bot.fusion_upgrade_handler
    asyncio.run(callback(update, context))
    assert events == [('sticker', 'normal-sticker'), ('sticker', 'epic-sticker')]
    assert CardInventorySystem(bot.db).counts(1, 'hero') == {'epic': 1}
    if kind == 'fusion':
        context.user_data.update(fusion_selected=['hero', 'extra1', 'extra2'], fusion_request_key='fusion-one')
    asyncio.run(callback(update, context))
    assert len(events) == 2
