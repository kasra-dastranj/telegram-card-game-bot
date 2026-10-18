import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from bot.handlers.progression import handle,show_menu
from bot.level_notifications import deliver,text as level_text
from bot.main import TelegramCardBot
from core.database import DatabaseManager
from core.models import Card,CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import ABILITY_DEFINITIONS,GameModeSystem
from systems.level_notices import pending
from systems.progression_config import config_in,save_config_in,validate_config
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import apply_in


@pytest.fixture
def scene(tmp_path):
    db=DatabaseManager(str(tmp_path/'personal.db'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    db.get_or_create_player(1)
    db.add_card(Card('hero','Hero',CardRarity.NORMAL,10,20,30,40,[]))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('UPDATE players SET coins=1000 WHERE user_id=1')
        CardInventorySystem.grant_in(conn,1,'hero','normal',3)
    bot=TelegramCardBot.__new__(TelegramCardBot)
    bot.db=db
    bot.skins=NS(get_card_skins=lambda _:[])
    message=NS(chat_id=1,chat=NS(type='private'),reply_text=AsyncMock(),reply_sticker=AsyncMock())
    query=NS(data='v2_shop',from_user=NS(id=1),message=message,answer=AsyncMock(),edit_message_text=AsyncMock())
    update=NS(callback_query=query,effective_user=query.from_user,effective_message=message)
    context=NS(user_data={},bot_data={},bot=NS(send_message=AsyncMock()))
    return bot,update,context


def scalar(db,sql,args=()):
    with sqlite3.connect(db.db_path) as conn:return conn.execute(sql,args).fetchone()[0]


@pytest.mark.parametrize('key',list(ABILITY_DEFINITIONS))
def test_ability_purchase_shared_inventory_and_replay(scene,key):
    bot,_,_=scene
    economy=ProgressionEconomy(bot.db)
    with sqlite3.connect(bot.db.db_path) as conn:
        price=config_in(conn)[1]['ability_shop'][key]['price']
    quote=economy.quote(1,'ability:'+key)
    assert quote['ok'] and quote['price']==price
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:economy.purchase(1,quote['quote_id']),range(2)))
    assert all(r['ok'] for r in results) and sum(bool(r.get('replayed')) for r in results)==1
    assert scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')==1000-price
    assert scalar(bot.db,'SELECT quantity FROM player_ability_inventory WHERE user_id=1 AND ability_key=?',(key,))==1
    assert scalar(bot.db,"SELECT COUNT(*) FROM reward_ledger WHERE source='shop'")==1
    entry=next(p for p in economy.ability_catalog(1)['products'] if p['key']==key)
    assert entry['quantity']==1
    modes=GameModeSystem(bot.db)
    assert next(item for item in modes.list_player_abilities(1) if item['ability_key']==key)['quantity']==1


@pytest.mark.parametrize('failure',['balance','price','disabled','unknown','foreign','expired'])
def test_ability_failed_purchase_is_atomic(scene,failure):
    bot,_,_=scene
    economy=ProgressionEconomy(bot.db)
    quote=economy.quote(1,'ability:reveal_opponent')
    with sqlite3.connect(bot.db.db_path) as conn:
        if failure=='balance':conn.execute('UPDATE players SET coins=0 WHERE user_id=1')
        elif failure in ('price','disabled'):
            _,config=config_in(conn)
            config['ability_shop']['reveal_opponent'].update({'price':21} if failure=='price' else {'enabled':False})
            save_config_in(conn,config,'test')
        elif failure=='expired':conn.execute("UPDATE shop_quotes SET expires_at='2000-01-01T00:00:00+00:00'")
    result=economy.quote(1,'ability:made_up') if failure=='unknown' else economy.purchase(2 if failure=='foreign' else 1,quote['quote_id'])
    assert not result['ok']
    assert scalar(bot.db,'SELECT COUNT(*) FROM player_ability_inventory')==0
    assert scalar(bot.db,"SELECT COUNT(*) FROM reward_ledger WHERE source='shop'")==0
    assert scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')==(0 if failure=='balance' else 1000)


def test_old_config_read_does_not_rewrite_and_prices_validate(scene):
    bot,_,_=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        version,config=config_in(conn)
        config.pop('ability_shop')
        raw=json.dumps(config)
        conn.execute('UPDATE economy_config_versions SET config_json=? WHERE version=?',(raw,version))
        assert config_in(conn)[1]['ability_shop']['reveal_opponent']['price']==20
        assert conn.execute('SELECT config_json FROM economy_config_versions WHERE version=?',(version,)).fetchone()[0]==raw
        config=validate_config(config)
        config['ability_shop']['reveal_opponent']['price']=True
        with pytest.raises(ValueError):validate_config(config)


@pytest.mark.parametrize('entry',['v2_shop','v2_quote_ability:reveal_opponent','v2_buy_stale','v2_action_stale',
                                'shop_menu_handler','shop_do_convert_handler','skin_buy_handler','shop_confirm_upgrade_handler'])
@pytest.mark.parametrize('chat_type',['group','supergroup','missing'])
def test_group_shop_stale_buttons_do_not_mutate_or_send(scene,entry,chat_type):
    bot,update,context=scene
    update.callback_query.message.chat=NS(type=chat_type)
    with sqlite3.connect(bot.db.db_path) as conn:
        before=list(conn.iterdump())
    if entry.startswith('v2_'):
        update.callback_query.data=entry
        asyncio.run(handle(bot,update,context))
    else:asyncio.run(getattr(bot,entry)(update,context))
    update.callback_query.answer.assert_awaited_once()
    assert update.callback_query.answer.await_args.kwargs['show_alert']
    update.callback_query.edit_message_text.assert_not_awaited()
    update.effective_message.reply_text.assert_not_awaited()
    with sqlite3.connect(bot.db.db_path) as conn:assert list(conn.iterdump())==before


def test_ability_panel_all_counts_and_quote_returns_to_it(scene):
    bot,update,context=scene
    update.callback_query.data='v2_abilities'
    asyncio.run(handle(bot,update,context))
    rendered=update.callback_query.edit_message_text.await_args.args[0]
    assert 'مشترکه' in rendered and rendered.count('موجودی:')==10
    buttons=update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert sum(b.callback_data.startswith('v2_quote_ability:') for row in buttons for b in row)==10
    update.callback_query.data='v2_quote_ability:reveal_opponent'
    asyncio.run(handle(bot,update,context))
    buttons=update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert buttons[-1][0].callback_data=='v2_abilities'


def test_sell_emoji_only_on_new_success(scene):
    bot,update,context=scene
    with sqlite3.connect(bot.db.db_path) as conn:version=config_in(conn)[0]
    context.user_data['economy_actions']={'sale':{'kind':'sell','card_id':'hero','rarity':'normal','request_key':'sale','config_version':version}}
    update.callback_query.data='v2_action_sale'
    asyncio.run(handle(bot,update,context))
    asyncio.run(handle(bot,update,context))
    update.effective_message.reply_text.assert_awaited_once_with('💰')
    assert scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')==1010


@pytest.mark.parametrize('entry',['cardinfo_hero','card_view_hero'])
def test_card_detail_sends_exact_active_form_sticker(scene,entry):
    bot,update,context=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        CardInventorySystem.grant_in(conn,1,'hero','epic',1)
        conn.execute("UPDATE player_cards SET rarity_override='epic' WHERE user_id=1 AND card_id='hero'")
    bot.db.set_card_variant_media_file_id('hero','epic','epic-sticker','sticker')
    update.callback_query.data=entry
    asyncio.run((bot.cardinfo_handler if entry.startswith('cardinfo') else bot.card_view_handler)(update,context))
    update.effective_message.reply_sticker.assert_awaited_once_with('epic-sticker')
    call=update.callback_query.edit_message_text.await_args
    assert 'Epic' in (call.kwargs['text'] if 'text' in call.kwargs else call.args[0])


def award(bot,key='xp',xp=400):
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        return apply_in(conn,key,1,'test','xp',config_in(conn)[0],xp=xp)


def test_level_notices_snapshot_actual_rewards_and_private_delivery_once(scene):
    bot,_,context=scene
    result=award(bot)
    notices=pending(bot.db)
    assert len(notices)==result['new_level']-result['old_level']
    assert sum(n['rewards']['coins'] for _,n in notices)==result['level_coins']
    assert any(n['rewards']['silver_claims']==1 for _,n in notices)
    award(bot) # receipt replay
    assert len(pending(bot.db))==len(notices)
    asyncio.run(deliver(bot,context));asyncio.run(deliver(bot,context))
    assert context.bot.send_message.await_count==len(notices) and not pending(bot.db)
    assert all(call.kwargs['chat_id']==1 for call in context.bot.send_message.await_args_list)
    assert 'سیلور کلیم' in '\n'.join(call.kwargs['text'] for call in context.bot.send_message.await_args_list)


def test_failed_notification_retries_later_without_repaying(scene):
    bot,_,context=scene
    award(bot,xp=100)
    balance=scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')
    context.bot.send_message.side_effect=RuntimeError('offline')
    asyncio.run(deliver(bot,context))
    assert not pending(bot.db)
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json=json_set(value_json,'$.next_attempt',0) WHERE key LIKE 'level-notice:%'")
    context.bot.send_message.side_effect=None
    asyncio.run(deliver(bot,context))
    assert scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')==balance
    assert not pending(bot.db)


def test_legacy_frozen_levels_congratulate_without_fake_prizes(scene):
    bot,_,_=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE progression_capacities SET legacy=1 WHERE user_id=1')
    award(bot,xp=100)
    notice=pending(bot.db)[0][1]
    assert notice['rewards']=={} and 'به حسابت اضافه شدن' not in level_text(notice)
    assert scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')==1000


def test_rolled_back_xp_has_no_notice(scene):
    bot,_,_=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        apply_in(conn,'rollback',1,'test','xp',config_in(conn)[0],xp=100)
        conn.rollback()
    assert not pending(bot.db)


def test_legacy_xp_helper_queues_actual_coins(scene):
    bot,_,_=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='false' WHERE key='progression_v2_enabled'")
        conn.execute('INSERT INTO level_coin_rules VALUES(2,12)')
    bot.db.add_xp(1,100)
    assert pending(bot.db)[0][1]['rewards']=={'coins':12}


def test_missions_paginate_all_entries_and_claim_has_own_back_button(scene):
    from systems.progression_missions import save_mission_in
    bot,update,context=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        for index in range(26):
            save_mission_in(conn,{'mission_id':f'm{index:02}','title':f'Mission-{index:02}',
                'description':'یه کارت بفروش و پاداشت رو بگیر.','start':None,'end':None,
                'status':'active','type':'official_sales','target':1,'filters':{},'eligibility':{},
                'xp_reward':5,'coin_reward':2,'repeat_policy':'once'},'test')
    ProgressionEconomy(bot.db).sell(1,'hero','normal','mission-sale')
    seen=set()
    for page in range(6):
        update.callback_query.data='v2_missions_'+str(page)
        asyncio.run(handle(bot,update,context))
        panel=update.callback_query.edit_message_text.await_args
        assert 'آمادهٔ دریافت' in panel.args[0] and '▰' in panel.args[0]
        buttons=panel.kwargs['reply_markup'].inline_keyboard
        for row in buttons:
            for button in row:
                if button.callback_data.startswith('v2_action_'):
                    seen.add(context.user_data['economy_actions'][button.callback_data[10:]]['mission_id'])
    assert len(seen)==26
    update.callback_query.data=next(b.callback_data for row in buttons for b in row if b.callback_data.startswith('v2_action_'))
    asyncio.run(handle(bot,update,context))
    assert update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data=='v2_missions'
    balance=scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')
    asyncio.run(handle(bot,update,context))
    assert scalar(bot.db,'SELECT coins FROM players WHERE user_id=1')==balance


def test_favorite_refresh_does_not_resend_sticker(scene):
    bot,update,context=scene
    update.callback_query.data='toggle_fav_hero'
    asyncio.run(bot.toggle_favorite_handler(update,context))
    update.effective_message.reply_sticker.assert_not_awaited()


def test_capped_level_hearts_report_only_real_capacity_increase(scene):
    bot,_,_=scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE progression_capacities SET purchased_hearts=12 WHERE user_id=1')
    award(bot,xp=3000)
    assert all(not notice['rewards'].get('hearts') for _,notice in pending(bot.db))


def test_ability_receipt_shows_shared_quantity_and_navigation(scene):
    bot,update,context=scene
    quote=ProgressionEconomy(bot.db).quote(1,'ability:reveal_opponent')
    update.callback_query.data='v2_buy_'+quote['quote_id']
    asyncio.run(handle(bot,update,context))
    panel=update.callback_query.edit_message_text.await_args
    assert '1 تا داری' in panel.args[0]
    assert panel.kwargs['reply_markup'].inline_keyboard[0][0].callback_data=='v2_abilities'
