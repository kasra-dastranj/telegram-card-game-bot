"""Offline admin delivery and event Rare receipts, with real SQLite transactions."""
import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from telegram.error import Forbidden

from bot.custom_card_notifications import deliver as send_notices
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems import rare_delivery
from systems.custom_card_notices import RARE_PREFIX, wake_user
from systems.progression_rare import issue
from systems.rare_cards_system import RareCardsSystem
from tests.test_group_attacks import scene, setup, play
from web.web_api import WebAPI

TOKEN = {'X-Admin-Token':'offline-rare-admin'}


@pytest.fixture
def rare(tmp_path, monkeypatch):
    monkeypatch.setenv('ARENA_ADMIN_TOKEN', TOKEN['X-Admin-Token'])
    monkeypatch.setenv('ADMIN_API_TOKEN', 'different-custom-authority')
    db = DatabaseManager(str(tmp_path/'rare.db'))
    for user in (101,102):
        db.get_or_create_player(user, first_name='بازیکن '+str(user))
    image = tmp_path/'rare.png'; Image.new('RGB',(120,180),'navy').save(image)
    for key,rarity in (('rare',CardRarity.RARE),('normal',CardRarity.NORMAL)):
        db.add_card(Card(key,'Rare <&> 🎴' if key=='rare' else key,rarity,41,52,63,74,
                         ['اثر آزمایشی'],biography='داستان کارت',image_path=str(image)))
    api = WebAPI(db)
    api.modes.set_card_metadata('rare', traits=['hero'], hidden_stats={'charisma':99})
    return db, api.app.test_client()


def query(db, sql, args=()):
    with sqlite3.connect(db.db_path) as conn:
        return conn.execute(sql,args).fetchall()


def notices(db):
    return [json.loads(r[0]) for r in query(db,'SELECT value_json FROM foundation_settings WHERE key LIKE ?', (RARE_PREFIX+'%',))]


def supply(rare, total=3):
    db,client=rare
    response=client.post('/api/rare/supply',headers=TOKEN,json={'card_id':'rare','total':total,'expected_supply':None})
    assert response.status_code==200,response.get_json()


def grant(rare, **extra):
    return rare[1].post('/api/rare/deliver',headers=TOKEN,json={
        'card_id':'rare','user_id':101,'request_key':'delivery-one','review_confirmed':True,**extra})


@pytest.mark.parametrize('endpoint,method', [('cards','get'),('players?q=101','get'),('supply','post'),('deliver','post')])
def test_auth_precedes_data_access(rare, endpoint, method):
    _,client=rare
    for headers in ({},{'X-Admin-Token':'different-custom-authority'}):
        assert getattr(client,method)('/api/rare/'+endpoint,headers=headers).status_code==403


def test_first_supply_admin_handoff_receipt_and_retry_change_no_wallet_or_xp(rare):
    db,client=rare
    initial=client.get('/api/rare/cards',headers=TOKEN)
    assert initial.headers['Cache-Control']=='private, no-store'
    assert initial.get_json()['cards'][0]['supply'] is None
    assert client.get('/api/rare/players?q=101',headers=TOKEN).get_json()['players'][0]['user_id']==101
    supply(rare)
    before=[query(db,'SELECT * FROM '+t) for t in ('players','player_progression','progression_capacities')]
    result=grant(rare);assert result.status_code==200,result.get_json()
    assert result.get_json()['serial']==1 and result.get_json()['notification']=='queued'
    assert grant(rare).get_json()['replayed']
    assert grant(rare,user_id=102).get_json()['error_code']=='idempotency_conflict'
    assert grant(rare,card_id='normal').get_json()['error_code']=='idempotency_conflict'
    assert [query(db,'SELECT * FROM '+t) for t in ('players','player_progression','progression_capacities')]==before
    assert query(db,'SELECT rarity,quantity FROM player_card_stacks')==[('rare',1)]
    assert query(db,'SELECT serial,source FROM rare_card_instances')==[(1,'admin')]
    assert len(notices(db))==1
    audit=json.loads(query(db,"SELECT payload_json FROM reward_ledger WHERE source='rare_admin'")[0][0])
    assert audit['actor'].startswith('token-admin:') and TOKEN['X-Admin-Token'] not in str(audit)


def test_card_editor_can_create_and_edit_standalone_rare_without_resetting_delivery(rare):
    db,client=rare
    body={'name':'Rare ساخته‌شده در پنل','rarity':'rare','power':45,'speed':56,'iq':67,'popularity':78,
          'traits':['hero'],'hidden_stats':{'charisma':91},'biography':'بیوگرافی','abilities':['اثر'],
          'photo_file_id':'rare-photo','sticker_file_id':'rare-sticker'}
    response=client.post('/api/cards',json=body)
    assert response.status_code==201,response.get_json()
    card=response.get_json()['card']['id']
    assert db.get_card_by_id_for_rarity(card,'rare').power==45
    assert db.get_card_variant_media_file_id(card,'rare','sticker')=='rare-sticker'
    assert not db.get_card_variants(card)  # Rare is not a three-form character.
    rare_delivery.set_supply(db,'admin',card,2,None)
    rare_delivery.deliver(db,'admin',101,card,'created-in-editor')
    response=client.put('/api/cards/'+card,json={**body,'power':90,'traits':['funny']})
    assert response.status_code==200,response.get_json()
    assert db.get_card_by_id_for_rarity(card,'rare').power==90
    assert query(db,'SELECT total_issued FROM rare_cards_info WHERE card_id=?',(card,))==[(1,)]
    assert len(notices(db))==1 and notices(db)[0]['payload']['power']==45
    # Even an old, pre-fix Rare with generated Normal/Epic forms cannot enter Claim.
    db.save_card_variant(card,'normal',{'power':1,'speed':1,'iq':1,'popularity':1})
    db.save_card_variant(card,'epic',{'power':2,'speed':2,'iq':2,'popularity':2})
    from systems.progression_config import seed_config
    from systems.progression_economy import ProgressionEconomy
    with sqlite3.connect(db.db_path) as conn:
        for kind in ('daily','silver'):
            assert card not in ProgressionEconomy.pool(conn,seed_config(),kind)


@pytest.mark.parametrize('extra,error', [({'user_id':99999},'player_not_found'),({'user_id':'101'},'invalid_player_id'),
    ({'user_id':True},'invalid_player_id'),({'card_id':'normal'},'rare_required'),
    ({'review_confirmed':False},'review_required'),({'request_key':None},'invalid_request_key')])
def test_bad_admin_delivery_never_creates_stack_serial_or_notice(rare,extra,error):
    supply(rare)
    result=grant(rare,**extra)
    assert result.status_code==400 and result.get_json()['error_code']==error
    assert not query(rare[0],'SELECT * FROM rare_card_instances') and not notices(rare[0])


def test_supply_and_delivery_honor_attack_reservations_and_stale_edits(rare):
    db,client=rare;supply(rare,2)
    with sqlite3.connect(db.db_path) as conn:
        from systems.attack_catalog import write
        write(conn,'reserve:active-encounter',{'rare':2})
    assert grant(rare).get_json()['error_code']=='rare_supply_empty'
    assert client.get('/api/rare/cards',headers=TOKEN).get_json()['cards'][0]['reserved']==2
    for total,expected,error in ((1,2,'rare_supply_reserved_or_issued'),(8,None,'supply_changed'),(-1,2,'invalid_rare_supply')):
        response=client.post('/api/rare/supply',headers=TOKEN,json={'card_id':'rare','total':total,'expected_supply':expected})
        assert response.get_json()['error_code']==error
    assert client.post('/api/rare/supply',headers=TOKEN,json={'card_id':'rare','total':3,'expected_supply':2}).status_code==200
    assert grant(rare).get_json()['serial']==1
    assert query(db,'SELECT limited_quantity,total_issued FROM rare_cards_info')==[(3,1)]


def test_concurrent_retries_and_last_copy_are_atomic(rare):
    db,_=rare;supply(rare,1)
    def run(_):return rare_delivery.deliver(db,'test-admin',101,'rare','same-key')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sum(bool(r.get('replayed')) for r in results)==1
    with pytest.raises(ValueError,match='rare_supply_empty'):
        rare_delivery.deliver(db,'test-admin',102,'rare','another-key')
    assert len(notices(db))==1 and query(db,'SELECT total_issued FROM rare_cards_info')==[(1,)]


def test_queue_failure_rolls_back_serial_supply_and_ownership(rare,monkeypatch):
    db,_=rare;supply(rare)
    def fail(*args):raise ValueError('simulated_notice_failure')
    monkeypatch.setattr('systems.custom_card_notices.queue_rare_in',fail)
    with pytest.raises(ValueError,match='simulated_notice_failure'):
        rare_delivery.deliver(db,'admin',101,'rare','failed-key')
    assert query(db,'SELECT total_issued FROM rare_cards_info')==[(0,)]
    assert not query(db,'SELECT * FROM rare_card_instances') and not query(db,'SELECT * FROM player_card_stacks')


@pytest.mark.parametrize('v2',[False,True])
def test_legacy_and_v2_sources_queue_once_without_backfilling_old_cards(rare,v2):
    db,_=rare;supply(rare)
    from systems.rare_cards_system import create_rare_cards_tables
    create_rare_cards_tables(db.db_path)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json=? WHERE key='progression_v2_enabled'",(json.dumps(v2),))
    service=RareCardsSystem(db)
    assert service.issue_rare_card(101,'rare','event',request_key='event-key')['success']
    assert service.issue_rare_card(101,'rare','event',request_key='event-key')['replayed']
    assert len(notices(db))==1
    assert not service.create_rare_card('rare','Reset',1,1,1,1,[])
    assert query(db,"SELECT total_issued FROM rare_cards_info WHERE card_id='rare'")==[(1,)]


@pytest.mark.parametrize('image',[False,True])
def test_rare_private_message_has_public_details_art_and_one_working_details_button(rare,image):
    db,_=rare;supply(rare);grant(rare)
    if not image:
        with sqlite3.connect(db.db_path) as conn:
            conn.execute("UPDATE cards SET image_path='' WHERE card_id='rare'")
            conn.execute("UPDATE card_variants SET image_path='' WHERE card_id='rare'")
    context=SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock(),send_message=AsyncMock()))
    asyncio.run(send_notices(SimpleNamespace(db=db),context))
    sender=context.bot.send_photo if image else context.bot.send_message
    sender.assert_awaited_once()
    call=sender.await_args.kwargs
    assert call['chat_id']==101
    body=call['caption' if image else 'text']
    assert all(value in body for value in ('مبارکت','Rare','41','52','63','74','230','داستان کارت','hero','شمارهٔ نسخه'))
    assert all(value not in body for value in ('charisma','کاریزما','99','شخصی‌سازی'))
    assert [b.callback_data for row in call['reply_markup'].inline_keyboard for b in row]==['cardinfo_rare']
    if image:assert Image.open(BytesIO(call['photo'].getvalue())).size[0]>0
    assert notices(db)[0]['state']=='sent'
    asyncio.run(send_notices(SimpleNamespace(db=db),context));sender.assert_awaited_once()


def test_rare_blocked_notice_wakes_only_for_recipient_and_does_not_reissue(rare):
    db,_=rare;supply(rare);grant(rare)
    context=SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock(side_effect=Forbidden('blocked')),send_message=AsyncMock()))
    asyncio.run(send_notices(SimpleNamespace(db=db),context))
    assert notices(db)[0]['state']=='blocked'
    wake_user(db,102);assert notices(db)[0]['state']=='blocked'
    wake_user(db,101);context.bot.send_photo.side_effect=None
    asyncio.run(send_notices(SimpleNamespace(db=db),context))
    assert notices(db)[0]['state']=='sent' and query(db,'SELECT quantity FROM player_card_stacks')==[(1,)]


def test_lost_rare_ownership_cancels_message_before_private_send(rare):
    db,_=rare;supply(rare);grant(rare)
    with sqlite3.connect(db.db_path) as conn:conn.execute('DELETE FROM player_card_stacks WHERE user_id=101')
    context=SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock(),send_message=AsyncMock()))
    asyncio.run(send_notices(SimpleNamespace(db=db),context))
    context.bot.send_photo.assert_not_awaited();context.bot.send_message.assert_not_awaited()
    assert notices(db)[0]['state']=='cancelled'


def test_attack_win_and_kill_rare_rewards_queue_for_every_actual_recipient(scene):
    db,engine=scene
    db.add_card(Card('limited','Limited',CardRarity.RARE,50,50,50,50,[]))
    rare_delivery.set_supply(db,'test','limited',8,None)
    def rewards(config,attack):
        attack['death_after']=1
        for reward in ('win','death_reward'):
            attack[reward]['cards'].append({'card_id':'limited','rarity':'rare','quantity':1})
    event=setup(scene,4,mutate=rewards)
    for index,card in enumerate(('strong','strong','weak','strong')):
        result=play(engine,event,index,index+1,card)
    assert result['status']=='win' and result['killed']
    assert len(notices(db))==8
    assert sorted(n['user_id'] for n in notices(db))==[1,1,2,2,3,3,4,4]
    assert query(db,'SELECT total_issued FROM rare_cards_info')==[(8,)]
    engine.tick();assert len(notices(db))==8
    context=SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock(),send_message=AsyncMock()))
    asyncio.run(send_notices(SimpleNamespace(db=db),context))
    asyncio.run(send_notices(SimpleNamespace(db=db),context))
    assert context.bot.send_message.await_count==8
    assert {c.kwargs['chat_id'] for c in context.bot.send_message.await_args_list}=={1,2,3,4}
