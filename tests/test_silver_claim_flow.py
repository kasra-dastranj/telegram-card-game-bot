import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from telegram.error import BadRequest

from bot.handlers.progression import handle
from bot.silver_claim_art import silver_claim_picture
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.progression_config import config_in, save_config_in
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import items_in


@pytest.fixture
def db(tmp_path):
    database = DatabaseManager(str(tmp_path / 'silver.db'))
    database.get_or_create_player(1)
    database.get_or_create_player(2)
    database.add_card(Card('tony', 'Tony <Soprano>', CardRarity.LEGEND, 90, 90, 90, 90, ['legend']))
    form = database.get_card_variant('tony', 'epic')
    database.save_card_variant('tony', 'epic', dict(form, power=55, speed=65, iq=75, popularity=85,
                                                 abilities=['epic <ability>']))
    database.set_card_variant_media_file_id('tony', 'epic', 'epic-sticker', 'sticker')
    database.set_card_variant_media_file_id('tony', 'legend', 'legend-sticker', 'sticker')
    with sqlite3.connect(database.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
        CardInventorySystem.grant_in(conn, 1, 'tony', 'legend')
    return database


def give(db, tickets=0, claims=0):
    with sqlite3.connect(db.db_path) as conn:
        items_in(conn, 1, 'silver_ticket', tickets)
        items_in(conn, 1, 'free_silver_claim', claims)


def balances(db):
    items = ProgressionEconomy(db).inventory(1)['items']
    return items.get('silver_ticket', 0), items.get('free_silver_claim', 0)


def configure(db, **claim_changes):
    with sqlite3.connect(db.db_path) as conn:
        _, config = config_in(conn)
        config['claim'].update(claim_changes)
        return save_config_in(conn, config, 'offline-tester')


def panel(db, chat_type='private'):
    events = []

    async def text(value, **kwargs):
        events.append(('text', value))

    async def photo(value, **kwargs):
        events.append(('photo', value.read() if hasattr(value, 'read') else value, kwargs.get('caption')))

    async def sticker(value, **kwargs):
        events.append(('sticker', value))

    message = SimpleNamespace(chat=SimpleNamespace(type=chat_type), reply_text=AsyncMock(side_effect=text),
                              reply_photo=AsyncMock(side_effect=photo), reply_sticker=AsyncMock(side_effect=sticker))
    user = SimpleNamespace(id=1)
    query = SimpleNamespace(data='v2_silver_claim', id='first-click', from_user=user, message=message,
                            answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(effective_user=user, effective_message=message, callback_query=query)
    bot = SimpleNamespace(db=db, config={'image_settings': {'enable_images': True}})
    return bot, update, SimpleNamespace(user_data={}), events


def click(state, data=None):
    bot, update, context, _ = state
    if data:
        update.callback_query.data = data
    asyncio.run(handle(bot, update, context))


def button(state, title):
    markup = state[1].callback_query.edit_message_text.await_args.kwargs['reply_markup']
    return next(b.callback_data for row in markup.inline_keyboard for b in row if b.text == title)


@pytest.mark.parametrize('cost', [3, 5])
def test_crafting_stores_one_claim_at_configured_cost_and_retries_once(db, cost):
    configure(db, silver_tickets=cost)
    give(db, tickets=cost * 2, claims=2)
    economy = ProgressionEconomy(db)
    version = economy.inventory(1)['config_version']
    receipt = economy.craft_silver_claim(1, 'craft', version)
    assert receipt['ok'] and receipt['tickets_spent'] == cost
    assert balances(db) == (cost, 3)
    configure(db, silver_tickets=cost + 1)
    assert economy.craft_silver_claim(1, 'craft', version)['replayed']
    assert balances(db) == (cost, 3)
    assert CardInventorySystem(db).counts(1, 'tony') == {'legend': 1}
    with sqlite3.connect(db.db_path) as conn:
        ledger = conn.execute("SELECT inventory_json FROM reward_ledger WHERE event_type='silver_craft'").fetchall()
    assert [json.loads(row[0]) for row in ledger] == [{'silver_ticket': -cost, 'free_silver_claim': 1}]


@pytest.mark.parametrize('problem', ['insufficient', 'changed_price'])
def test_unsuccessful_craft_does_not_spend_or_create_claim(db, problem):
    give(db, tickets=2 if problem == 'insufficient' else 6)
    economy = ProgressionEconomy(db)
    version = economy.inventory(1)['config_version']
    if problem == 'changed_price':
        configure(db, silver_tickets=4)
    before = balances(db)
    result = economy.craft_silver_claim(1, 'failed-craft', version)
    assert result['error_code'] == ('insufficient_silver_ticket' if problem == 'insufficient' else 'price_changed')
    assert balances(db) == before


def test_use_never_spends_raw_tickets_and_free_level_claim_works(db):
    economy = ProgressionEconomy(db)
    give(db, tickets=9)
    assert economy.use_silver_claim(1, 'use')['error_code'] == 'insufficient_free_silver_claim'
    assert balances(db) == (9, 0)
    give(db, claims=1)
    result = economy.use_silver_claim(1, 'use')
    assert result['ok'] and result['rarity'] == 'epic'
    assert balances(db) == (9, 0)
    assert economy.use_silver_claim(1, 'use')['replayed']
    assert CardInventorySystem(db).counts(1, 'tony') == {'legend': 1, 'epic': 1}
    assert db.get_card_by_id_for_player('tony', 1).rarity == CardRarity.LEGEND


def test_empty_pool_rolls_back_stored_claim_and_original_miniapp_contract_works(db):
    give(db, tickets=6, claims=1)
    configure(db, silver_pool=['unavailable'])
    economy = ProgressionEconomy(db)
    assert economy.use_silver_claim(1, 'open')['error_code'] == 'empty_pool'
    assert balances(db) == (6, 1)
    configure(db, silver_pool=[])
    assert economy.claim(1, 'silver', 'miniapp-free')['ok']
    assert balances(db) == (6, 0)
    assert economy.claim(1, 'silver', 'miniapp-tickets')['ok']
    assert balances(db) == (3, 0)


@pytest.mark.parametrize('operation,duplicate', [('craft', False), ('craft', True), ('use', False), ('use', True)])
def test_simultaneous_clicks_never_double_spend_or_duplicate_reward(db, operation, duplicate):
    give(db, tickets=3 if operation == 'craft' else 0, claims=1 if operation == 'use' else 0)
    barrier = Barrier(2)

    def perform(index):
        economy = ProgressionEconomy(db)
        key = 'same' if duplicate else str(index)
        barrier.wait(timeout=10)
        return economy.craft_silver_claim(1, key) if operation == 'craft' else economy.use_silver_claim(1, key)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(perform, [1, 2]))
    assert sum(bool(result.get('ok')) and not result.get('replayed') for result in results) == 1
    assert sum(bool(result.get('replayed')) for result in results) == int(duplicate)
    assert balances(db) == ((0, 1) if operation == 'craft' else (0, 0))
    assert CardInventorySystem(db).counts(1, 'tony').get('epic', 0) == (operation == 'use')


@pytest.mark.parametrize('operation', ['craft_silver_claim', 'use_silver_claim'])
@pytest.mark.parametrize('key', [None, '', 'x' * 129])
def test_invalid_keys_do_not_mutate_inventory(db, operation, key):
    give(db, tickets=6, claims=2)
    result = getattr(ProgressionEconomy(db), operation)(1, key)
    assert result['error_code'] == 'invalid_request_key'
    assert balances(db) == (6, 2)


def test_bot_menu_shows_counts_without_claiming_and_shop_no_longer_links_claim(db):
    give(db, tickets=5, claims=3)
    state = panel(db)
    click(state)
    text = state[1].callback_query.edit_message_text.await_args.args[0]
    assert '۳ تا سیلور کلیم داری' in text and '۵ تا سیلور تیکت داری' in text
    assert button(state, 'ساخت سیلور کلیم') and button(state, 'استفاده از سیلور کلیم')
    assert balances(db) == (5, 3) and state[3] == []
    click(state, 'v2_shop')
    keyboard = state[1].callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    callbacks = [b.callback_data for row in keyboard for b in row]
    assert 'v2_silver_claim' not in callbacks
    assert 'free_silver_claim' not in state[1].callback_query.edit_message_text.await_args.args[0]
    assert 'v2_quote_silver_ticket' in callbacks and 'back_to_main' in callbacks


def test_bot_craft_then_use_delivers_art_celebration_actual_epic_media_and_stats(db):
    give(db, tickets=6)
    state = panel(db)
    click(state)
    craft = button(state, 'ساخت سیلور کلیم')
    click(state, craft)
    photo = state[3][0]
    assert photo[0] == 'photo' and 'یه سیلور کلیم به موجودیت اضافه شد' in photo[2]
    assert Image.open(BytesIO(photo[1])).size == (800, 500)
    assert balances(db) == (3, 1)
    state[1].callback_query.id = 'different-callback-id'
    click(state, craft)
    assert len(state[3]) == 1 and balances(db) == (3, 1)
    use = button(state, 'استفاده از سیلور کلیم')
    click(state, use)
    assert state[3][1] == ('text', '🎉')
    assert state[3][2] == ('sticker', 'epic-sticker')
    reward = state[3][3][1]
    assert 'Tony &lt;Soprano&gt;' in reward and '(Epic)' in reward
    for fragment in ['قدرت: 55', 'سرعت: 65', 'آی‌کیو: 75', 'محبوبیت: 85', 'مجموع: 280', 'epic &lt;ability&gt;']:
        assert fragment in reward
    assert 'Legend' not in reward and balances(db) == (3, 0)
    state[1].callback_query.id = 'another-callback-id'
    click(state, use)
    assert balances(db) == (3, 0)
    assert state[3].count(('text', '🎉')) == 1 and state[3].count(('sticker', 'epic-sticker')) == 1
    assert 'قبلاً' in state[3][-1][1]  # The same receipt can recover failed text delivery.
    click(state, button(state, 'مشاهده کارت دریافتی'))
    assert state[3].count(('sticker', 'epic-sticker')) == 2
    assert state[3].count(('text', '🎉')) == 1
    assert CardInventorySystem(db).counts(1, 'tony') == {'legend': 1, 'epic': 1}


@pytest.mark.parametrize('entry', ['menu', 'craft', 'use'])
def test_silver_callbacks_cannot_be_used_in_group(db, entry):
    give(db, tickets=6, claims=1)
    state = panel(db)
    click(state)
    data = 'v2_silver_claim' if entry == 'menu' else button(state, 'ساخت سیلور کلیم' if entry == 'craft' else 'استفاده از سیلور کلیم')
    state[1].effective_message.chat.type = 'group'
    click(state, data)
    assert balances(db) == (6, 1) and state[3] == []


def test_another_user_cannot_use_someone_elses_action_token(db):
    give(db, tickets=6, claims=1)
    state = panel(db)
    click(state)
    data = button(state, 'استفاده از سیلور کلیم')
    other = panel(db)
    other[1].effective_user.id = 2
    click(other, data)
    assert balances(db) == (6, 1) and other[3] == []
    assert CardInventorySystem(db).counts(2, 'tony') == {}


@pytest.mark.parametrize('failure', ['panel', 'celebration', 'media', 'reward'])
def test_telegram_delivery_failure_keeps_receipt_and_retry_does_not_spend_again(db, failure):
    give(db, claims=1)
    state = panel(db)
    click(state)
    data = button(state, 'استفاده از سیلور کلیم')
    query = state[1].callback_query
    if failure == 'panel':
        query.edit_message_text.side_effect = BadRequest('message deleted')
    elif failure == 'media':
        state[1].effective_message.reply_sticker.side_effect = BadRequest('invalid media')
    else:
        original = state[1].effective_message.reply_text.side_effect

        async def fail(value, **kwargs):
            if (failure == 'celebration' and value == '🎉') or (failure == 'reward' and 'آمار کارت' in value):
                raise BadRequest('offline simulated failure')
            return await original(value, **kwargs)

        state[1].effective_message.reply_text.side_effect = fail
    if failure == 'reward':
        click(state, data)
        assert button(state, 'مشاهده کارت دریافتی')
        state[1].effective_message.reply_text.side_effect = original
    else:
        click(state, data)
    query.edit_message_text.side_effect = None
    click(state, data)
    assert balances(db) == (0, 0)
    assert CardInventorySystem(db).counts(1, 'tony') == {'legend': 1, 'epic': 1}
    assert 'آمار کارت' in state[3][-1][1]


def test_craft_photo_failure_falls_back_to_friendly_receipt_without_repeating_craft(db):
    give(db, tickets=3)
    state = panel(db)
    click(state)
    data = button(state, 'ساخت سیلور کلیم')
    state[1].effective_message.reply_photo.side_effect = BadRequest('offline unavailable photo')
    click(state, data)
    assert 'یه سیلور کلیم به موجودیت اضافه شد' in state[3][-1][1]
    click(state, data)
    assert balances(db) == (0, 1) and len(state[3]) == 1


def test_picture_stream_is_independent_and_uses_no_server_asset_files():
    with silver_claim_picture() as first:
        assert Image.open(first).format == 'PNG'
    with silver_claim_picture() as second:
        assert second.tell() == 0 and len(second.read()) < 100_000
