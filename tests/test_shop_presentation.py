import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from PIL import Image
import pytest
from telegram.error import BadRequest

from bot import shop_visuals
from bot.handlers.progression import handle
from bot.main import TelegramCardBot
from bot.shop_presentation import show_catalog
from core.database import DatabaseManager
from systems.progression_config import config_in, save_config_in
from systems.progression_economy import ProgressionEconomy


@pytest.fixture
def shop(tmp_path, monkeypatch):
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db = DatabaseManager(str(tmp_path/'shop.db'))
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    for uid in (1,2):
        bot.db.get_or_create_player(uid,first_name='Tester')
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE players SET coins=1000,hearts=1,last_heart_reset=?',(datetime.now(timezone.utc).isoformat(),))
    events, current = [], {'id':10,'next':100}

    async def photo(value,**kwargs):
        current['next'] += 1
        events.append(('photo',value.getvalue(),kwargs))
        return SimpleNamespace(message_id=current['next'])

    async def text(value,**kwargs):
        current['next'] += 1
        current['id'] = current['next']
        events.append(('text',value,kwargs))
        return SimpleNamespace(message_id=current['next'])

    context = SimpleNamespace(user_data={},bot_data={},bot=SimpleNamespace(edit_message_media=AsyncMock()))
    renderer = Mock(wraps=shop_visuals.render)
    monkeypatch.setattr(shop_visuals,'render',renderer)

    def click(data='v2_shop',uid=1):
        message = SimpleNamespace(chat_id=uid,message_id=current['id'],reply_photo=AsyncMock(side_effect=photo),
                                  reply_text=AsyncMock(side_effect=text))
        query = SimpleNamespace(data=data,from_user=SimpleNamespace(id=uid),message=message,
                                answer=AsyncMock(),edit_message_text=AsyncMock(),edit_message_reply_markup=AsyncMock())
        update = SimpleNamespace(effective_user=query.from_user,effective_message=message,callback_query=query)
        asyncio.run(bot.shop_menu_handler(update,context) if data=='shop_menu' else handle(bot,update,context))
        return update
    return bot,context,events,click,renderer


def row(db,sql,args=()):
    with sqlite3.connect(db.db_path) as conn:
        return conn.execute(sql,args).fetchone()


def configure(bot,mutate):
    with sqlite3.connect(bot.db.db_path) as conn:
        _, config = config_in(conn)
        mutate(config)
        save_config_in(conn,config,'offline-test')


def buy_button(update,events):
    if update.callback_query.edit_message_text.await_count:
        markup = update.callback_query.edit_message_text.await_args.kwargs['reply_markup']
    else:
        markup = next(event[2]['reply_markup'] for event in reversed(events) if event[0]=='text')
    return next(button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data.startswith('v2_buy_'))


def test_store_board_quote_receipt_reuses_photo_and_keeps_text_controls(shop):
    bot,context,events,click,renderer = shop
    initial = click('shop_menu')
    assert [event[0] for event in events] == ['photo','text']
    assert Image.open(BytesIO(events[0][1])).size == (1200,1000)
    assert 'چی برای نبرد بعدیت' in events[1][1] and '1,000' in events[1][1]
    callbacks = [b.callback_data for r in events[1][2]['reply_markup'].inline_keyboard for b in r]
    assert 'back_to_main' in callbacks and 'v2_cards_0' in callbacks and 'v2_missions' in callbacks
    assert 'v2_silver_claim' not in callbacks
    initial.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert row(bot.db,'SELECT COUNT(*) FROM shop_quotes')[0] == 0
    update = click('v2_quote_silver_ticket')
    assert context.bot.edit_message_media.await_count == 1
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert 'Silver Ticket' in text and '100' in text and '۵ دقیقه' in text
    receipt = click(buy_button(update,events))
    assert 'مال تو شد' in receipt.callback_query.edit_message_text.await_args.args[0]
    assert row(bot.db,'SELECT coins FROM players WHERE user_id=1')[0] == 900
    assert row(bot.db,"SELECT quantity FROM player_economy_items WHERE user_id=1 AND item='silver_ticket'")[0] == 1
    count = len(events)
    replay = click(update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data)
    assert 'قبلاً ثبت شده' in replay.callback_query.edit_message_text.await_args.args[0]
    assert row(bot.db,'SELECT coins FROM players WHERE user_id=1')[0] == 900
    assert row(bot.db,"SELECT COUNT(*) FROM reward_ledger WHERE source='shop'")[0] == 1
    assert len(events) == count  # No duplicate photo/control message per step.
    click('v2_shop')
    model = renderer.call_args.args[0]
    ticket = next(item for item in model['products'] if item['item']=='silver_ticket')
    assert ticket['price'] == 200 and model['coins'] == 900


def test_browsing_uses_current_prices_and_preserves_quotes_money_hearts_and_ledger(shop):
    bot,_,_,click,_ = shop
    before = row(bot.db,'SELECT coins,hearts,last_heart_reset FROM players WHERE user_id=1')
    before_ledger = row(bot.db,'SELECT COUNT(*) FROM reward_ledger')
    economy = ProgressionEconomy(bot.db)
    configure(bot,lambda config:config['shop']['silver_ticket'].update(price=137,factor=3))
    catalog = economy.shop_catalog(1)
    assert next(p['price'] for p in catalog['products'] if p['item']=='silver_ticket') == 137
    click();click()
    assert row(bot.db,'SELECT coins,hearts,last_heart_reset FROM players WHERE user_id=1') == before
    assert row(bot.db,'SELECT COUNT(*) FROM reward_ledger') == before_ledger
    assert row(bot.db,'SELECT COUNT(*) FROM shop_quotes')[0] == 0


@pytest.mark.parametrize('problem',['expired','config_changed','insufficient','foreign'])
def test_confirmation_failure_does_not_spend_and_keeps_shop_navigation(shop,problem):
    bot,_,events,click,_ = shop
    click()
    update = click('v2_quote_silver_ticket')
    callback = buy_button(update,events)
    if problem=='expired':
        with sqlite3.connect(bot.db.db_path) as conn:
            conn.execute('UPDATE shop_quotes SET expires_at=?',(datetime.now(timezone.utc)-timedelta(minutes=6),))
    elif problem=='config_changed':
        configure(bot,lambda config:config['shop']['silver_ticket'].update(price=101))
    elif problem=='insufficient':
        with sqlite3.connect(bot.db.db_path) as conn:
            conn.execute('UPDATE players SET coins=1 WHERE user_id=1')
    expected = row(bot.db,'SELECT coins FROM players WHERE user_id=1')
    result = click(callback,uid=2 if problem=='foreign' else 1)
    assert 'مال تو شد' not in result.callback_query.edit_message_text.await_args.args[0]
    assert row(bot.db,'SELECT coins FROM players WHERE user_id=1') == expected
    assert row(bot.db,"SELECT COUNT(*) FROM reward_ledger WHERE source='shop'")[0] == 0
    callbacks = [b.callback_data for r in result.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard for b in r]
    assert 'v2_shop' in callbacks and 'back_to_main' in callbacks


@pytest.mark.parametrize('condition',['disabled','sold_out','hearts_full','heart_cap','all_disabled'])
def test_catalog_shows_real_availability_and_server_still_enforces_it(shop,condition):
    bot,_,_,click,renderer = shop
    if condition in ('disabled','sold_out','all_disabled'):
        def change(config):
            if condition=='all_disabled':
                for rule in config['shop'].values():rule['enabled']=False
            else:
                config['shop']['silver_ticket'].update({'enabled':False} if condition=='disabled' else {'stock':0})
        configure(bot,change)
    else:
        with sqlite3.connect(bot.db.db_path) as conn:
            if condition=='hearts_full':conn.execute('UPDATE players SET hearts=8 WHERE user_id=1')
            else:conn.execute('UPDATE progression_capacities SET base_hearts=20 WHERE user_id=1')
    click()
    products = renderer.call_args.args[0]['products']
    if condition=='disabled':assert not any(p['item']=='silver_ticket' for p in products)
    elif condition=='all_disabled':assert products == []
    else:
        item = 'silver_ticket' if condition=='sold_out' else 'refill' if condition=='hearts_full' else 'permanent_heart'
        assert not next(p for p in products if p['item']==item)['available']
        result = click('v2_quote_'+item)
        assert not any(b.callback_data.startswith('v2_buy_') for r in result.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard for b in r)


def test_deleted_board_falls_back_to_text_and_purchase_replay_stays_safe(shop):
    bot,context,events,click,_ = shop
    click()
    quote = click('v2_quote_upgrade_card')
    callback = buy_button(quote,events)
    context.bot.edit_message_media.side_effect = BadRequest('board deleted')
    result = click(callback)
    assert 'مال تو شد' in result.callback_query.edit_message_text.await_args.args[0]
    assert row(bot.db,'SELECT coins FROM players WHERE user_id=1')[0] == 800
    click(callback)
    assert row(bot.db,'SELECT coins FROM players WHERE user_id=1')[0] == 800
    assert row(bot.db,"SELECT quantity FROM player_economy_items WHERE user_id=1 AND item='upgrade_card'")[0] == 1


def test_without_photo_support_all_prices_and_purchase_buttons_are_available(shop):
    bot,_,_,_,_ = shop
    query = SimpleNamespace(from_user=SimpleNamespace(id=1),edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query,effective_user=query.from_user)
    asyncio.run(show_catalog(bot,update,SimpleNamespace()))
    call = query.edit_message_text.await_args
    assert '1,000' in call.args[0]
    assert len([b for r in call.kwargs['reply_markup'].inline_keyboard for b in r if b.callback_data.startswith('v2_quote_')]) == 5


def test_return_to_card_and_mission_menus_uses_existing_text_callbacks(shop):
    _,_,_,click,_ = shop
    click()
    for callback in ('v2_cards_0','v2_missions'):
        result = click(callback)
        result.callback_query.edit_message_text.assert_awaited_once()
        callbacks = [b.callback_data for r in result.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard for b in r]
        assert 'back_to_main' in callbacks


def test_upfront_insufficient_coins_shows_shortage_without_purchase_button(shop):
    bot,_,events,click,_ = shop
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE players SET coins=1 WHERE user_id=1')
    click()
    quote = click('v2_quote_silver_ticket')
    call = quote.callback_query.edit_message_text.await_args
    assert 'سکه دیگه لازم داری' in call.args[0]
    assert not any(b.callback_data.startswith('v2_buy_') for r in call.kwargs['reply_markup'].inline_keyboard for b in r)


def test_skin_quote_names_real_skin_and_cancel_returns_to_its_card(shop):
    bot,context,events,click,renderer = shop
    from core.models import Card, CardRarity
    from systems.skins_system import SkinsSystem
    bot.db.add_card(Card('hero','Hero',CardRarity.NORMAL,1,2,3,4,[]))
    bot.db.add_card_to_player(1,'hero')
    bot.skins = SkinsSystem(bot.db)
    bot.skins.create_skin('blue_skin','hero','Blue <ستاره>_*','normal','',price=50)
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(data='skin_buy_blue_skin',from_user=SimpleNamespace(id=1),message=message,
                            answer=AsyncMock(),edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query,effective_user=query.from_user,effective_message=message)
    asyncio.run(bot.skin_buy_handler(update,context))
    call = query.edit_message_text.await_args
    assert 'Blue <ستاره>_*' in call.args[0] and call.kwargs['parse_mode'] is None
    assert call.kwargs['reply_markup'].inline_keyboard[-1][0].callback_data == 'skins_menu_hero'
