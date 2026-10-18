import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from core.database import DatabaseManager
from core.models import Card,CardRarity
from systems.attack_catalog import defaults,example,read,write,catalog_in,save_in,records,CatalogConflict
from systems.group_attacks import GroupAttacks,now_utc,active_player_in
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import GameModeSystem
from systems.progression_config import config_in,period_bounds
from systems.match_activity import ActiveMatchError,require_free_in
from systems.progression_rare import issue


@pytest.fixture
def scene(tmp_path):
    db=DatabaseManager(str(tmp_path/'attacks.db'))
    with sqlite3.connect(db.db_path) as conn:conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    for key,amount in [('strong',90),('weak',1),('equal',50)]:
        db.add_card(Card(key,key,CardRarity.NORMAL,*([amount]*4),[]))
    for uid in range(1,7):
        db.get_or_create_player(uid,first_name='P'+str(uid))
        with sqlite3.connect(db.db_path) as conn:
            for key in ('strong','weak','equal'):CardInventorySystem.grant_in(conn,uid,key,'normal')
    with sqlite3.connect(db.db_path) as conn:conn.execute('UPDATE players SET coins=1000,hearts=8')
    modes=GameModeSystem(db)
    modes._random_arena=lambda exclude=None:{'id':'test','arena_id':'test','name':'آزمایش','name_fa':'آزمایش','emoji':'🏟','effects':[],'disabled_stats':[],'abilities_enabled':True,'passives_enabled':True}
    return db,GroupAttacks(db,modes)


def setup(scene,size=1,mutate=None,chat=-100):
    db,engine=scene
    attack=example();attack['enabled']=True;attack['id']='test';attack['death_after']=0
    attack['enemies']=[copy.deepcopy(attack['enemies'][0]) for _ in range(size)]
    config=defaults();config.update(start_hour=0,end_hour=24)
    config['attacks']=[attack]
    if mutate:mutate(config,attack)
    with sqlite3.connect(db.db_path) as conn:
        config['revision']=catalog_in(conn)['revision'];save_in(conn,config,'test')
        day=period_bounds(config_in(conn)[1],'daily')[2]
        write(conn,'activity:'+day+':'+str(chat),list(range(1,7)))
    engine.tick()
    with sqlite3.connect(db.db_path) as conn:event_id=read(conn,'open:'+str(chat))
    return engine.get(event_id) if event_id else None


def play(engine,event,index,user,card='strong'):
    joined=engine.join(event['id'],index,user,event['chat_id'])
    selected=joined['slots'][index]['cards'].index(card)
    engine.choose_card(event['id'],index,user,selected)
    engine.choose_ability(event['id'],index,user,'skip')
    return engine.choose_stat(event['id'],index,user,'power')


def scalar(db,sql,args=()):
    with sqlite3.connect(db.db_path) as conn:return conn.execute(sql,args).fetchone()[0]


def test_solo_win_escrow_refund_and_rewards(scene):
    db,engine=scene;event=setup(scene)
    result=play(engine,event,0,1)
    assert result['status']=='win'
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1020
    assert scalar(db,'SELECT total_xp FROM player_progression WHERE user_id=1')==10
    assert scalar(db,'SELECT coins FROM players WHERE user_id=2')==1000
    with sqlite3.connect(db.db_path) as conn:assert not active_player_in(conn,1)
    assert result['receipts']['1']['attack_coins']==20
    with pytest.raises(ValueError):engine.choose_stat(event['id'],0,1,'power')
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1020


def test_solo_loss_only_opted_player_loses(scene):
    db,engine=scene;event=setup(scene)
    result=play(engine,event,0,1,'weak')
    assert result['status']=='loss'
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==990
    assert scalar(db,'SELECT coins FROM players WHERE user_id=2')==1000


def test_squad_unfinished_three_wins_pays_nothing(scene):
    db,engine=scene;event=setup(scene,4)
    for index in range(3):result=play(engine,event,index,index+1)
    assert result['status']=='open'
    engine.tick(now_utc()+timedelta(hours=4))
    result=engine.get(event['id'])
    assert result['status']=='void'
    assert scalar(db,'SELECT MIN(coins) FROM players')==1000
    assert scalar(db,'SELECT SUM(total_xp) FROM player_progression')==0


def test_squad_decisive_losses_settle_even_if_last_fight_unclaimed(scene):
    db,engine=scene;event=setup(scene,4)
    for index in range(3):result=play(engine,event,index,index+1,'weak')
    assert result['status']=='loss'
    assert scalar(db,'SELECT MIN(coins) FROM players WHERE user_id<=3')==990
    assert scalar(db,'SELECT coins FROM players WHERE user_id=4')==1000


def test_squad_full_win_pays_every_participant_equally_even_loser(scene):
    db,engine=scene;event=setup(scene,4)
    for index,card in enumerate(['strong','strong','weak','strong']):result=play(engine,event,index,index+1,card)
    assert result['status']=='win'
    assert {r['attack_coins'] for r in result['receipts'].values()}=={20}
    assert scalar(db,'SELECT MIN(coins) FROM players WHERE user_id<=4')==1020
    assert scalar(db,'SELECT MAX(coins) FROM players WHERE user_id<=4')==1020


def test_squad_draw_changes_nothing(scene):
    db,engine=scene;event=setup(scene,4)
    for index,card in enumerate(['strong','weak','strong','weak']):result=play(engine,event,index,index+1,card)
    assert result['status']=='tie'
    assert scalar(db,'SELECT MIN(coins) FROM players')==1000
    assert scalar(db,'SELECT SUM(total_xp) FROM player_progression')==0


def test_same_player_cannot_enter_two_slots_and_slot_is_atomic(scene):
    db,engine=scene;event=setup(scene,4)
    def join(uid):
        try:return engine.join(event['id'],0,uid,-100)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(join,[1,2]))
    assert sum(r is not None for r in results)==1
    user=engine.get(event['id'])['slots'][0]['user']
    with pytest.raises(ValueError):engine.join(event['id'],1,user,-100)
    assert scalar(db,'SELECT SUM(coins) FROM players')==5990


def test_active_guard_both_directions_and_lease_recovery(scene):
    db,engine=scene;event=setup(scene)
    engine.join(event['id'],0,1,-100)
    with sqlite3.connect(db.db_path) as conn:
        with pytest.raises(ActiveMatchError):require_free_in(conn,1)
    with pytest.raises(ActiveMatchError):engine.modes.create_invite(1,'quick','normal')


def test_cancel_refunds_stakes_and_frees_player(scene):
    db,engine=scene;event=setup(scene)
    engine.join(event['id'],0,1,-100)
    engine.cancel(event['id']);engine.cancel(event['id'])
    with sqlite3.connect(db.db_path) as conn:require_free_in(conn,1)
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000


def test_rare_supply_reserved_and_granted_once(scene):
    db,engine=scene
    from systems.rare_cards_system import create_rare_cards_tables
    create_rare_cards_tables(db.db_path)
    db.add_card(Card('limited','Limited',CardRarity.RARE,90,90,90,90,[]))
    with sqlite3.connect(db.db_path) as conn:conn.execute("INSERT INTO rare_cards_info VALUES('limited',1000,1,0)")
    event=setup(scene,mutate=lambda c,a:a['win']['cards'].append({'card_id':'limited','rarity':'rare','quantity':1}))
    assert not issue(db,2,'limited','event','other')['success']
    result=play(engine,event,0,1)
    assert result['receipts']['1']['cards'][0]['serials']==[1]
    assert scalar(db,"SELECT total_issued FROM rare_cards_info WHERE card_id='limited'")==1
    assert CardInventorySystem(db).counts(1,'limited')=={'rare':1}


def test_three_group_wins_retire_only_that_groups_enemy(scene):
    db,engine=scene;event=setup(scene,mutate=lambda c,a:a.update(death_after=3))
    for count in range(3):
        result=play(engine,event,0,1)
        if count<2:
            with sqlite3.connect(db.db_path) as conn:
                prior=read(conn,'group:-100');prior['at']=(now_utc()-timedelta(hours=4)).isoformat();prior['count']=0;write(conn,'group:-100',prior)
            engine.tick();
            with sqlite3.connect(db.db_path) as conn:event=engine.get(read(conn,'open:-100'))
    assert result['killed'] and result['progress']['wins']==3
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1110
    with sqlite3.connect(db.db_path) as conn:
        assert read(conn,'progress:-100:test')['dead']
        assert not read(conn,'progress:-200:test',{}).get('dead')


def test_catalog_conflict_and_invalid_reward_rejected(scene):
    db,_=scene
    with sqlite3.connect(db.db_path) as conn:
        config=defaults();save_in(conn,config,'one')
        with pytest.raises(CatalogConflict):save_in(conn,config,'two')
        attack=example();attack['win']['cards']=[{'card_id':'missing','rarity':'legend','quantity':1}]
        config=catalog_in(conn);config['attacks']=[attack]
        with pytest.raises(ValueError):save_in(conn,config,'test')


def test_group_needs_four_different_active_players_and_no_overlapping_attack(scene):
    db,engine=scene;event=setup(scene)
    with sqlite3.connect(db.db_path) as conn:
        day=period_bounds(config_in(conn)[1],'daily')[2]
        write(conn,'activity:'+day+':-200',[1,2,3])
    engine.tick();engine.tick()
    with sqlite3.connect(db.db_path) as conn:
        assert read(conn,'open:-100')==event['id']
        assert not read(conn,'open:-200')
        write(conn,'activity:'+day+':-200',[1,2,3,4])
    engine.tick()
    with sqlite3.connect(db.db_path) as conn:assert read(conn,'open:-200')


def test_admission_shortage_and_existing_match_do_not_take_stakes(scene):
    db,engine=scene;event=setup(scene)
    invite=engine.modes.create_invite(1,'quick','normal')
    assert engine.modes.accept_request(invite['request_id'],2)[0]
    with pytest.raises(ActiveMatchError):engine.join(event['id'],0,1,-100)
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000
    with sqlite3.connect(db.db_path) as conn:conn.execute('UPDATE players SET coins=0 WHERE user_id=3')
    with pytest.raises(ValueError,match='attack_stake_shortage'):engine.join(event['id'],0,3,-100)
    assert engine.get(event['id'])['participants']=={}


def test_choice_timeout_unlocks_and_cannot_continue_or_consume_ability(scene):
    db,engine=scene;event=setup(scene)
    engine.join(event['id'],0,1,-100)
    with sqlite3.connect(db.db_path) as conn:
        event=read(conn,'event:'+event['id']);event['slots'][0]['deadline']=(now_utc()-timedelta(seconds=1)).isoformat();write(conn,'event:'+event['id'],event)
        write(conn,'player:1',{'event':event['id'],'deadline':event['slots'][0]['deadline']})
        require_free_in(conn,1)
    with pytest.raises(ValueError,match='attack_choice_expired'):engine.choose_card(event['id'],0,1,0)
    engine.tick()
    assert engine.get(event['id'])['status']=='loss'
    with sqlite3.connect(db.db_path) as conn:require_free_in(conn,1)


def test_shared_ability_once_and_void_returns_it(scene):
    db,engine=scene;event=setup(scene,4)
    engine.modes.grant_ability(1,'weaken_power',1)
    joined=engine.join(event['id'],0,1,-100)
    engine.choose_card(event['id'],0,1,joined['slots'][0]['cards'].index('strong'))
    engine.choose_ability(event['id'],0,1,'weaken_power')
    with pytest.raises(ValueError):engine.choose_ability(event['id'],0,1,'weaken_power')
    assert not engine.modes.list_player_abilities(1)
    engine.cancel(event['id']);engine.cancel(event['id'])
    assert engine.modes.list_player_abilities(1)[0]['quantity']==1
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000


@pytest.mark.parametrize('key',['lock_power','lock_speed','lock_iq','lock_popularity','reveal_opponent','weaken_speed'])
def test_quick_abilities_use_shared_inventory(scene,key):
    db,engine=scene;event=setup(scene)
    engine.modes.grant_ability(1,key)
    joined=engine.join(event['id'],0,1,-100)
    engine.choose_card(event['id'],0,1,joined['slots'][0]['cards'].index('strong'))
    chosen=engine.choose_ability(event['id'],0,1,key)
    if key.startswith('lock_'):assert chosen['slots'][0]['npc_stat']!=key[5:]
    assert not engine.modes.list_player_abilities(1)
    assert engine.choose_stat(event['id'],0,1,'power')['status']=='win'


def test_unanswered_expiry_does_not_charge_or_repeat_same_day(scene):
    db,engine=scene;event=setup(scene)
    engine.tick(now_utc()+timedelta(hours=4))
    engine.tick(now_utc()+timedelta(hours=5))
    assert engine.get(event['id'])['status']=='void'
    assert scalar(db,'SELECT MIN(coins) FROM players')==1000
    with sqlite3.connect(db.db_path) as conn:assert len(records(conn,'event:'))==1


def test_ongoing_encounter_keeps_its_reward_and_enemy_snapshot(scene):
    db,engine=scene;event=setup(scene)
    with sqlite3.connect(db.db_path) as conn:
        config=catalog_in(conn);config['attacks'][0]['win']['coins']=999
        config['attacks'][0]['enemies'][0]['stats']=dict.fromkeys(('power','speed','iq','popularity'),100)
        save_in(conn,config,'edit')
    assert play(engine,event,0,1)['receipts']['1']['attack_coins']==20


def test_rewards_including_all_forms_and_no_new_ownership_on_defeat(scene):
    db,engine=scene
    event=setup(scene,mutate=lambda c,a:a['win']['cards'].extend([
        {'card_id':'equal','rarity':r,'quantity':1} for r in ('normal','epic','legend')]))
    result=play(engine,event,0,1)
    assert len(result['receipts']['1']['cards'])==3
    assert CardInventorySystem(db).counts(1,'equal')=={'normal':2,'epic':1,'legend':1}
    assert db.get_card_by_id_for_player('equal',1).rarity==CardRarity.NORMAL


def test_activity_is_per_group_day_and_replay_does_not_fake_today(scene):
    from systems.match_rewards_system import MatchRewardsSystem
    db,engine=scene
    for a,b in [(1,2),(3,4)]:
        request=engine.modes.create_group_challenge(a,'quick','normal',-100)
        assert engine.modes.accept_request(request['request_id'],b)[0]
        awards={uid:{'result':'win' if uid==a else 'loss','card_id':'strong','opponent_id':b if uid==a else a} for uid in (a,b)}
        with sqlite3.connect(db.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            MatchRewardsSystem.award(conn,request['request_id'],'quick',awards)
    with sqlite3.connect(db.db_path) as conn:
        day=period_bounds(config_in(conn)[1],'daily')[2]
        assert read(conn,'activity:'+day+':-100')==[1,2,3,4]
        assert not read(conn,'activity:'+day+':-200')
        conn.execute("UPDATE match_reward_events SET awarded_at='2000-01-01T00:00:00+00:00'")
        write(conn,'activity:'+day+':-100',[])
        MatchRewardsSystem.award(conn,request['request_id'],'quick',awards)
        assert read(conn,'activity:'+day+':-100')==[]


def test_rare_cancellation_releases_supply_and_no_schema_startup_change(scene):
    db,engine=scene
    from systems.rare_cards_system import create_rare_cards_tables
    create_rare_cards_tables(db.db_path)
    db.add_card(Card('limited','Limited',CardRarity.RARE,90,90,90,90,[]))
    with sqlite3.connect(db.db_path) as conn:conn.execute("INSERT INTO rare_cards_info VALUES('limited',1000,1,0)")
    event=setup(scene,mutate=lambda c,a:a['win']['cards'].append({'card_id':'limited','rarity':'rare','quantity':1}))
    engine.cancel(event['id'])
    assert issue(db,2,'limited','event','after-cancel')['success']
    with sqlite3.connect(db.db_path) as conn:
        before=list(conn.iterdump())
    DatabaseManager(db.db_path)
    with sqlite3.connect(db.db_path) as conn:assert list(conn.iterdump())==before


def test_admin_auth_preview_and_optimistic_save(scene,monkeypatch):
    from web.web_api import WebAPI
    db,engine=scene
    monkeypatch.setenv('ARENA_ADMIN_TOKEN','offline-test')
    api=WebAPI(db);client=api.app.test_client();headers={'X-Admin-Token':'offline-test'}
    assert client.get('/api/attacks/catalog').status_code==403
    assert client.get('/api/attacks/events').status_code==403
    assert client.get('/api/attacks/options').status_code==403
    config=client.get('/api/attacks/catalog',headers=headers).get_json()['catalog']
    assert client.put('/api/attacks/catalog',json=config).status_code==403
    assert client.post('/api/attacks/events/not-real/cancel').status_code==403
    with sqlite3.connect(db.db_path) as conn:before=list(conn.iterdump())
    assert client.post('/api/attacks/preview',headers=headers,json=config).status_code==200
    with sqlite3.connect(db.db_path) as conn:assert list(conn.iterdump())==before
    assert client.put('/api/attacks/catalog',headers=headers,json=config).status_code==200
    assert client.put('/api/attacks/catalog',headers=headers,json=config).status_code==409
    page=client.get('/group-attacks')
    try:assert page.status_code==200 and 'حمله'.encode() in page.get_data()
    finally:page.close()


def test_bot_offer_then_confirm_and_exact_private_quick_flow(scene):
    import asyncio
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock
    from bot.group_attacks import handle,maintenance
    db,system=scene;event=setup(scene)
    bot=NS(db=db,modes=system.modes,is_user_in_channel=AsyncMock(return_value=True))
    telegram=NS(get_chat_member=AsyncMock(return_value=NS(status='member')),send_message=AsyncMock(return_value=NS(message_id=10)),send_sticker=AsyncMock(),edit_message_text=AsyncMock(),edit_message_reply_markup=AsyncMock())
    context=NS(user_data={},bot_data={},bot=telegram)
    query=NS(data='ga_offer:'+event['id']+':0',from_user=NS(id=1),message=NS(chat_id=-100),answer=AsyncMock(),edit_message_text=AsyncMock())
    update=NS(callback_query=query,effective_user=query.from_user)
    asyncio.run(handle(bot,update,context))
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000
    assert 'رزرو' in telegram.send_message.await_args.kwargs['text']
    query.message.chat_id=1;query.data='ga_join:'+event['id']+':0'
    asyncio.run(handle(bot,update,context))
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==990
    selected=system.get(event['id'])['slots'][0]['cards'].index('strong')
    for action in ['ga_card:'+event['id']+':0:'+str(selected),'ga_ability:'+event['id']+':0:skip','ga_stat:'+event['id']+':0:power']:
        query.data=action;asyncio.run(handle(bot,update,context))
    assert system.get(event['id'])['status']=='win'
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1020
    asyncio.run(maintenance(bot,context));count=telegram.send_message.await_count
    asyncio.run(maintenance(bot,context));assert telegram.send_message.await_count==count


def test_bot_denies_wrong_group_or_nonmember_before_escrow(scene):
    import asyncio
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock
    from bot.group_attacks import handle
    db,system=scene;event=setup(scene)
    bot=NS(db=db,modes=system.modes)
    context=NS(bot=NS(get_chat_member=AsyncMock(return_value=NS(status='left'))))
    query=NS(data='ga_join:'+event['id']+':0',from_user=NS(id=1),message=NS(chat_id=1),answer=AsyncMock())
    asyncio.run(handle(bot,NS(callback_query=query,effective_user=query.from_user),context))
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000
    assert not system.get(event['id'])['participants']


def test_daily_entry_limit_is_shared_between_groups_and_stakes_atomic(scene):
    db,engine=scene
    event=setup(scene,mutate=lambda c,a:c.update(user_daily_limit=1))
    engine.join(event['id'],0,1,-100);engine.cancel(event['id'])
    other=setup(scene,chat=-200,mutate=lambda c,a:c.update(user_daily_limit=1))
    with pytest.raises(ValueError,match='attack_daily_limit'):engine.join(other['id'],0,1,-200)
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000


def test_decisive_loss_charges_all_opted_participants_equally(scene):
    db,engine=scene;event=setup(scene,4)
    for index in range(4):engine.join(event['id'],index,index+1,-100)
    for index in range(3):
        current=engine.get(event['id']);chosen=current['slots'][index]['cards'].index('weak')
        engine.choose_card(event['id'],index,index+1,chosen)
        engine.choose_ability(event['id'],index,index+1,'skip')
        result=engine.choose_stat(event['id'],index,index+1,'power')
    assert result['status']=='loss' and len(result['receipts'])==4
    assert scalar(db,'SELECT MIN(coins) FROM players WHERE user_id<=4')==990
    assert scalar(db,'SELECT MAX(coins) FROM players WHERE user_id<=4')==990
    with sqlite3.connect(db.db_path) as conn:
        for user in range(1,5):require_free_in(conn,user)


def test_rare_insufficient_stock_never_announces_unfunded_reward(scene):
    db,engine=scene
    from systems.rare_cards_system import create_rare_cards_tables
    create_rare_cards_tables(db.db_path)
    db.add_card(Card('limited','Limited',CardRarity.RARE,90,90,90,90,[]))
    with sqlite3.connect(db.db_path) as conn:conn.execute("INSERT INTO rare_cards_info VALUES('limited',1000,1,0)")
    event=setup(scene,4,mutate=lambda c,a:a['win']['cards'].append({'card_id':'limited','rarity':'rare','quantity':1}))
    assert event is None
    with sqlite3.connect(db.db_path) as conn:assert not records(conn,'reserve:') and not records(conn,'event:')


def test_admin_referenced_card_cannot_be_deleted_and_override_is_snapshot(scene):
    db,engine=scene
    def change(c,a):
        a['enemies'][0].update(card_id='strong',name='دشمن ویژه',use_custom_stats=True,stats=dict.fromkeys(('power','speed','iq','popularity'),10))
    event=setup(scene,mutate=change)
    assert not db.delete_card('strong')
    assert event['attack']['enemies'][0]['stats']['power']==10
    assert db.get_card_by_id('strong').power==90
    assert play(engine,event,0,1)['status']=='win'


def test_scheduler_interruption_refunds_instead_of_punishing_offline_player(scene):
    db,engine=scene;event=setup(scene)
    engine.join(event['id'],0,1,-100)
    with sqlite3.connect(db.db_path) as conn:write(conn,'heartbeat',(now_utc()-timedelta(minutes=10)).isoformat())
    engine.tick()
    assert engine.get(event['id'])['status']=='void'
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000
    with sqlite3.connect(db.db_path) as conn:require_free_in(conn,1)


def test_failed_group_delivery_does_not_block_other_groups_scheduler(scene):
    db,engine=scene;event=setup(scene)
    with sqlite3.connect(db.db_path) as conn:
        day=period_bounds(config_in(conn)[1],'daily')[2]
        write(conn,'activity:'+day+':-200',[1,2,3,4])
        for index in range(4):write(conn,'notice:offline'+str(index),{'next_attempt':(now_utc()+timedelta(minutes=10)).isoformat()})
    engine.tick()
    with sqlite3.connect(db.db_path) as conn:assert read(conn,'open:-200')


def test_private_message_failure_refunds_opted_player(scene):
    import asyncio
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock
    from bot.group_attacks import handle
    db,system=scene;event=setup(scene)
    bot=NS(db=db,modes=system.modes,is_user_in_channel=AsyncMock(return_value=True))
    context=NS(bot_data={},bot=NS(get_chat_member=AsyncMock(return_value=NS(status='member'))))
    query=NS(data='ga_join:'+event['id']+':0',from_user=NS(id=1),message=NS(chat_id=1),answer=AsyncMock(),edit_message_text=AsyncMock(side_effect=RuntimeError('offline')))
    asyncio.run(handle(bot,NS(callback_query=query,effective_user=query.from_user),context))
    assert system.get(event['id'])['status']=='void'
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000
    with sqlite3.connect(db.db_path) as conn:require_free_in(conn,1)


def test_concurrent_final_choice_pays_once(scene):
    db,engine=scene;event=setup(scene)
    joined=engine.join(event['id'],0,1,-100)
    engine.choose_card(event['id'],0,1,joined['slots'][0]['cards'].index('strong'))
    engine.choose_ability(event['id'],0,1,'skip')
    def choose(_):
        try:return engine.choose_stat(event['id'],0,1,'power')
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(choose,range(2)))
    assert sum(r is not None for r in results)==1
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1020
    assert scalar(db,'SELECT total_xp FROM player_progression WHERE user_id=1')==10


def test_npc_choice_is_committed_before_players_stat(scene):
    db,engine=scene;event=setup(scene)
    joined=engine.join(event['id'],0,1,-100)
    chosen=engine.choose_card(event['id'],0,1,joined['slots'][0]['cards'].index('strong'))
    npc=chosen['slots'][0]['npc_stat'];stat=next(s for s in ('power','speed','iq','popularity') if s!=npc)
    engine.choose_ability(event['id'],0,1,'skip')
    result=engine.choose_stat(event['id'],0,1,stat)
    assert result['slots'][0]['report']['stats']==[stat,npc]


def test_squad_final_kill_bonus_is_equal_for_every_participant(scene):
    db,engine=scene;event=setup(scene,4,mutate=lambda c,a:a.update(death_after=1))
    for index,card in enumerate(['strong','strong','weak','strong']):result=play(engine,event,index,index+1,card)
    assert result['killed']
    assert {r['attack_coins'] for r in result['receipts'].values()}=={70}
    assert {r['xp'] for r in result['receipts'].values()}=={30}


def test_disabling_v2_cannot_spend_or_reset_reserved_rare(scene):
    db,engine=scene
    from systems.rare_cards_system import create_rare_cards_tables,RareCardsSystem
    create_rare_cards_tables(db.db_path)
    db.add_card(Card('limited','Limited',CardRarity.RARE,90,90,90,90,[]))
    with sqlite3.connect(db.db_path) as conn:conn.execute("INSERT INTO rare_cards_info VALUES('limited',1000,1,0)")
    setup(scene,mutate=lambda c,a:a['win']['cards'].append({'card_id':'limited','rarity':'rare','quantity':1}))
    with sqlite3.connect(db.db_path) as conn:conn.execute("UPDATE foundation_settings SET value_json='false' WHERE key='progression_v2_enabled'")
    assert not RareCardsSystem(db).issue_rare_card(2,'limited')['success']
    assert not RareCardsSystem(db).create_rare_card('limited','Changed',1,1,1,1,[])
    assert scalar(db,"SELECT total_issued FROM rare_cards_info WHERE card_id='limited'")==0


def test_standalone_npc_failed_media_does_not_borrow_a_catalog_sticker():
    import asyncio
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock,Mock
    from bot.group_attacks import send_snapshot
    lookup=Mock(side_effect=AssertionError('unrelated catalog lookup'))
    bot=NS(db=NS(get_card_variant_media_file_id=lookup))
    context=NS(bot=NS(send_sticker=AsyncMock(side_effect=RuntimeError('unavailable'))))
    snapshot=example()['enemies'][0];snapshot['sticker_file_id']='failed-sticker'
    assert not asyncio.run(send_snapshot(bot,context,1,snapshot))
    lookup.assert_not_called()
