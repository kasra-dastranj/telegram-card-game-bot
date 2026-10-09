import json
import sqlite3
import uuid
from io import BytesIO
import pytest
from PIL import Image
from core.database import DatabaseManager
from core.models import Card,CardRarity
from web.web_api import WebAPI
from systems.shared_foundation import context_in,require_card_in,eligible_cards
from systems.custom_cards import CustomCards,access_in,freeze_in,match_card
from systems.match_rewards_system import MatchRewardsSystem


@pytest.fixture
def custom(tmp_path,monkeypatch):
    db=DatabaseManager(str(tmp_path/'game.db'))
    for user in range(1,13):db.get_or_create_player(user)
    db.add_card(Card('official','Same name',CardRarity.NORMAL,5,5,5,5,[]))
    for user in range(1,13):db.add_card_to_player(user,'official')
    monkeypatch.setenv('ADMIN_API_TOKEN','synthetic-test-admin')
    monkeypatch.setenv('TELBATTLE_CUSTOM_MEDIA_ROOT',str(tmp_path/'private'))
    api=WebAPI(db);api.app.config['TESTING']=True
    return db,api,api.app.test_client()


def post(custom,action,data,key=None,auth=True):
    headers={'X-Admin-Token':'synthetic-test-admin'} if auth else {}
    return custom[2].post('/api/custom/'+action,json={'request_key':key or uuid.uuid4().hex,'data':data},headers=headers)


def define(custom,rarity='normal',users=None,media=None):
    users=users or list(range(1,11))
    order=post(custom,'order',{'buyer_id':1,'recipients':users,'rarity':rarity,'amount':'123.45','currency':'TEST','notes':'offline'}).get_json()['order_id']
    card=post(custom,'create',{'order_id':order,'media_id':media,'card':{'name':'Same name','rarity':rarity,'power':5,'speed':6,'iq':7,'popularity':8,'abilities':['hero'],'traits':['hero'],'hidden_stats':{'funny':20}}})
    assert card.status_code==200,card.get_json()
    return order,card.get_json()['card_id']


def activate(custom,rarity='normal',users=None,media=None):
    order,card=define(custom,rarity,users,media)
    assert post(custom,'payment',{'order_id':order}).status_code==200
    assert post(custom,'status',{'card_id':card,'status':'active','review_confirmed':True}).status_code==200
    assert post(custom,'grant',{'order_id':order,'card_id':card,'users':users or list(range(1,11))}).status_code==200
    assert post(custom,'settings',{'custom_cards_enabled':True}).status_code==200
    return order,card


@pytest.mark.parametrize('action',['order','payment','create','edit','status','grant','revoke','remove_image','settings'])
def test_all_admin_actions_reject_player(custom,action):
    assert post(custom,action,{},auth=False).status_code==401


@pytest.mark.parametrize('rarity',['normal','epic','legend'])
def test_shared_definition_ten_grants_no_currency_no_duplicates(custom,rarity):
    db=custom[0]
    with sqlite3.connect(db.db_path) as conn:before=conn.execute('SELECT coins,hearts,total_score FROM players').fetchall()
    order,card=activate(custom,rarity)
    assert post(custom,'grant',{'order_id':order,'card_id':card,'users':[1]},'retry').status_code==200
    assert post(custom,'grant',{'order_id':order,'card_id':card,'users':[1]},'retry').get_json()['replayed']
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM custom_grants WHERE card_id=?',(card,)).fetchone()[0]==10
        assert conn.execute('SELECT origin,rarity FROM cards WHERE card_id=?',(card,)).fetchone()==('custom',rarity)
        assert conn.execute('SELECT COUNT(*) FROM player_card_stacks WHERE card_id=?',(card,)).fetchone()[0]==0
        assert conn.execute('SELECT coins,hearts,total_score FROM players').fetchall()==before
        assert conn.execute('SELECT SUM(total_xp) FROM player_progression').fetchone()[0]==0
        assert not access_in(conn,11,card)
    assert db.get_card_by_id_for_player(card,1).name=='Same name'
    assert db.get_card_by_id_for_player(card,11) is None
    assert post(custom,'revoke',{'card_id':card,'users':[1]}).status_code==200
    assert db.get_card_by_id_for_player(card,1) is None
    assert db.get_card_by_id_for_player(card,2)


def test_payment_review_unknown_ids_atomic_and_defaults_off(custom):
    db=custom[0];order,card=define(custom)
    assert post(custom,'status',{'card_id':card,'status':'active','review_confirmed':True}).status_code==400
    assert post(custom,'grant',{'order_id':order,'card_id':card,'users':[1]}).status_code==400
    assert post(custom,'order',{'buyer_id':1,'recipients':[2,99999],'rarity':'normal','amount':'4','currency':'TEST'}).status_code==400
    assert post(custom,'settings',{'easy_custom_cards_enabled':True}).status_code==400
    assert not any(c.origin=='custom' for c in db.get_player_cards(1))


def enable_v2(custom,easy=False):
    db=custom[0]
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
        conn.execute('UPDATE player_progression SET level=5,total_xp=700')
    assert post(custom,'settings',{'quick_friendly_enabled':True,'easy_custom_cards_enabled':easy,'balance_approved':easy}).status_code==200


@pytest.mark.parametrize('mode',['quick','three_round','deck','risk'])
def test_competitive_and_random_exclude_custom(custom,mode):
    _,card=activate(custom)
    db,api,_=custom
    assert all(c.origin=='official' for c in eligible_cards(db,db.get_player_cards(1),mode))
    from systems.shared_foundation import legacy_context
    with sqlite3.connect(db.db_path) as conn:
        with pytest.raises(ValueError):require_card_in(conn,card,legacy_context(mode),1)


@pytest.mark.parametrize('outcome,loss',[('win',0),('tie',0),('loss',1)])
def test_friendly_same_engine_frozen_revoke_restart_reward_zero(custom,outcome,loss):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom)
    request=api.modes.create_invite(1,'quick','friendly')
    key=request['request_id'];assert api.modes.accept_request(key,2)[0]
    api.modes.start_quick_match(key)
    api.modes.select_quick_card(key,1,card)
    api.modes.select_quick_card(key,2,'official')
    assert post(custom,'revoke',{'card_id':card,'users':[1]}).status_code==200
    with sqlite3.connect(db.db_path) as conn:
        ctx=context_in(conn,key,'quick')
        assert ctx.variant=='friendly'
        require_card_in(conn,card,ctx,1,key)
        award={1:{'result':outcome,'card_id':card,'opponent_card_id':'official','opponent_id':2}}
        paid=MatchRewardsSystem.award(conn,key,'quick',award)
    with sqlite3.connect(db.db_path) as conn:again=MatchRewardsSystem.award(conn,key,'quick',award)
    assert paid['1']['xp']==paid['1']['score']==paid['1']['tp_delta']==0
    assert paid['1']['hearts_lost']==again['1']['hearts_lost']==loss
    assert db.get_fight_stats(1)['total_fights']==0
    assert match_card(db,key,1,card).name=='Same name'
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT fight_type FROM fight_history WHERE user_id=1').fetchone()[0]=='quick_friendly'


def test_revocation_before_second_card_blocks_start(custom):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom)
    request=api.modes.create_invite(1,'quick','friendly');key=request['request_id']
    api.modes.accept_request(key,2);api.modes.start_quick_match(key);api.modes.select_quick_card(key,1,card)
    post(custom,'revoke',{'card_id':card,'users':[1]})
    with pytest.raises(ValueError):api.modes.select_quick_card(key,2,'official')
    assert api.modes.get_state(key)['phase']=='card_selection'


@pytest.mark.parametrize('first_custom,second_custom',[(False,False),(True,True),(True,False)])
def test_friendly_full_quick_engine_ability_stock_retry(custom,monkeypatch,first_custom,second_custom):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom)
    from systems.game_mode_system import QUICK_ARENAS
    monkeypatch.setattr(api.modes, '_random_arena', lambda exclude=None: QUICK_ARENAS[0])
    monkeypatch.setattr(api.modes, 'arena_registry_enabled', False)
    request=api.modes.create_invite(1,'quick','friendly');key=request['request_id']
    api.modes.accept_request(key,2);api.modes.start_quick_match(key)
    api.modes.select_quick_card(key,1,card if first_custom else 'official')
    api.modes.select_quick_card(key,2,card if second_custom else 'official')
    with sqlite3.connect(db.db_path) as conn:conn.execute("INSERT OR REPLACE INTO player_ability_inventory VALUES(1,'reveal_opponent',1)")
    api.modes.select_quick_ability(key,1,'reveal_opponent')
    with pytest.raises(ValueError):api.modes.select_quick_ability(key,1,'reveal_opponent')
    api.modes.select_quick_ability(key,2,'skip')
    api.modes.select_quick_stat(key,1,'iq')
    _,report=api.modes.select_quick_stat(key,2,'power')
    assert report['variant']=='friendly'
    assert all(r['xp']==r['score']==r['tp_delta']==0 for r in report['rewards'].values())
    assert api.modes.resolve_quick(key)==report
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT quantity FROM player_ability_inventory WHERE user_id=1 AND ability_key='reveal_opponent'").fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM reward_ledger WHERE event_type='match'").fetchone()[0]==2


def test_migration_copy_and_backup_preserve_wallet_and_grants(custom,tmp_path):
    from migrations.migrate_custom_cards import apply_migration
    from migrations.migrate_card_trait_registry import copy_database
    db=custom[0];_,card=activate(custom)
    backup=tmp_path/'backup.db';preview=tmp_path/'preview.db'
    copy_database(db.db_path,backup);copy_database(db.db_path,preview);apply_migration(preview)
    for path in (db.db_path,backup,preview):
        with sqlite3.connect(path) as conn:
            assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            assert conn.execute('SELECT SUM(coins),SUM(total_score) FROM players').fetchone()==(0,0)
            assert conn.execute('SELECT COUNT(*) FROM custom_grants WHERE card_id=?',(card,)).fetchone()[0]==10


def test_private_image_admin_and_recipient_access_only(custom,monkeypatch):
    db,api,client=custom
    image=BytesIO();Image.new('RGB',(32,32),'red').save(image,'PNG');image.seek(0)
    upload=client.post('/api/custom/media',data={'image':(image,'../../unsafe.png')},headers={'X-Admin-Token':'synthetic-test-admin'})
    assert upload.status_code==201
    media=upload.get_json()['media_id'];_,card=activate(custom,media=media)
    import web.miniapp_api as mini
    monkeypatch.setattr(mini,'db',db);mini.app.config.update(TESTING=True,DEBUG=True)
    player=mini.app.test_client();url='/api/v1/custom/cards/'+card+'/image'
    assert player.get(url,headers={'X-Debug-User-Id':'11'}).status_code==404
    response=player.get(url,headers={'X-Debug-User-Id':'1'})
    assert response.status_code==200 and response.headers['Cache-Control']=='private, no-store';response.close()
    assert client.get('/api/custom/media/'+media).status_code==401
    assert client.put('/api/cards/'+card,json={}).status_code==403
    post(custom,'remove_image',{'card_id':card})
    assert player.get(url,headers={'X-Debug-User-Id':'1'}).status_code==404


@pytest.mark.parametrize('rounds,xp,score',[(3,10,1),(5,15,2),(10,20,3)])
@pytest.mark.parametrize('count',[4,5])
def test_custom_easy_normal_rewards_locked_context(custom,rounds,xp,score,count):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom,easy=True)
    request=api.modes.create_easy_lobby(1,-123,rounds,allow_custom_cards=True);key=request['request_id']
    with sqlite3.connect(db.db_path) as conn:
        state=api.modes.get_state(key);state['scores']={str(user):count-user for user in range(1,count+1)}
        conn.execute('UPDATE game_match_states SET state_json=? WHERE request_id=?',(json.dumps(state),key))
        freeze_in(conn,key,1,card)
        assert context_in(conn,key,'easy').allow_custom_cards
        awards={user:{'result':'win' if user==1 else 'loss','card_id':card if user==1 else 'official','easy_final':{'scores':state['scores'],'participants':list(range(1,count+1))}} for user in range(1,count+1)}
        paid=MatchRewardsSystem.award(conn,key,'easy',awards)
    assert paid['1']['xp']==(xp if count==5 else 0)
    assert paid['1']['score']==(score if count==5 else 0)
    assert all(value['hearts_lost']==0 for value in paid.values())


def player_api(custom,monkeypatch):
    import web.miniapp_api as mini
    db,api,_=custom
    monkeypatch.setattr(mini,'db',db)
    monkeypatch.setattr(mini,'quick_modes',api.modes)
    from systems.arena_registry import ArenaRegistry
    monkeypatch.setattr(mini,'arena_registry',ArenaRegistry(db))
    mini.app.config.update(TESTING=True,DEBUG=True)
    return mini,mini.app.test_client()


@pytest.mark.parametrize('outcome',['player','ai','tie'])
def test_custom_practice_real_start_snapshot_and_settle_zero(custom,monkeypatch,outcome):
    db,api,_=custom;order,card=activate(custom);enable_v2(custom)
    mini,client=player_api(custom,monkeypatch)
    response=client.post('/api/v1/solo/start',json={'player_card_id':card,'difficulty':'easy'},headers={'X-Debug-User-Id':'1'})
    assert response.status_code==200,response.get_json()
    fight=response.get_json();fight_id=fight['fight_id']
    before=db.get_or_create_player(1)
    frozen=match_card(db,'solo:'+fight_id,1,card)
    changed={'name':'Edited','rarity':'normal','power':99,'speed':99,'iq':99,'popularity':99,'abilities':[],'traits':['different'],'hidden_stats':{'funny':99}}
    assert post(custom,'edit',{'order_id':order,'card_id':card,'card':changed}).status_code==200
    assert post(custom,'revoke',{'card_id':card,'users':[1]}).status_code==200
    assert match_card(db,'solo:'+fight_id,1,card).power==frozen.power==5
    status=client.get('/api/v1/solo/fights/'+fight_id,headers={'X-Debug-User-Id':'1'})
    assert status.status_code==200,status.get_json()
    assert client.post('/api/v1/solo/start',json={'player_card_id':card},headers={'X-Debug-User-Id':'1'}).status_code==400
    from systems.ai_opponent import AsoAI
    with sqlite3.connect(db.db_path) as conn:
        conn.row_factory=sqlite3.Row
        paid=mini._finalize_solo_fight(1,fight_id,outcome,AsoAI('easy'),frozen,db.get_card_by_id('official'),conn)
        again=MatchRewardsSystem.award(conn,'solo:'+fight_id,'solo',{1:{'result':'win','card_id':card,'opponent_card_id':'official'}})
    assert paid['xp_gained']==paid['score_gained']==paid['tier_points_change']==paid['hearts_lost']==0
    assert again['1']['xp']==0
    after=db.get_or_create_player(1)
    assert (after.coins,after.hearts,after.total_score)==(before.coins,before.hearts,before.total_score)


def test_custom_practice_v2_off_is_rejected_without_fight(custom,monkeypatch):
    db=custom[0];_,card=activate(custom)
    _,client=player_api(custom,monkeypatch)
    response=client.post('/api/v1/solo/start',json={'player_card_id':card},headers={'X-Debug-User-Id':'1'})
    assert response.status_code==400
    with sqlite3.connect(db.db_path) as conn:assert conn.execute('SELECT COUNT(*) FROM solo_fights').fetchone()[0]==0


@pytest.mark.parametrize('allow',[False,True])
def test_easy_picker_origin_context_lock_and_frozen_metrics(custom,monkeypatch,allow):
    db,api,_=custom;order,card=activate(custom);enable_v2(custom,easy=True)
    monkeypatch.setattr(api.modes,'_choose_easy_question',lambda players,previous_id=None:{'id':'fixture','title':'test','attribute':'funny'})
    request=api.modes.create_easy_lobby(1,-123,3,allow_custom_cards=allow);key=request['request_id']
    api.modes.join_easy_lobby(key,2);assert api.modes.start_easy_match(key)[0]
    choices=api.modes.get_easy_options(key,1)
    assert (card in {c.card_id for c in choices})==allow
    from dataclasses import replace
    from systems.shared_foundation import bind_context
    with sqlite3.connect(db.db_path) as conn:
        context=context_in(conn,key,'easy')
        with pytest.raises(ValueError,match='match_context_conflict'):bind_context(conn,key,replace(context,allow_custom_cards=not allow))
    ok,reason,_=api.modes.select_easy_card(key,1,card)
    assert ok==allow,(ok,reason)
    if allow:
        assert post(custom,'status',{'card_id':card,'status':'suspended'}).status_code==200
        assert api.modes._hidden_stat_value(match_card(db,key,1,card),'funny')==20


def test_direct_ungranted_player_and_callback_cannot_select(custom,monkeypatch):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom)
    request=api.modes.create_invite(1,'quick','friendly');key=request['request_id']
    api.modes.accept_request(key,11);api.modes.start_quick_match(key)
    with pytest.raises(ValueError):api.modes.select_quick_card(key,11,card)
    _,client=player_api(custom,monkeypatch)
    info=client.get('/api/v1/quick/invites/'+request['invite_token'],headers={'X-Debug-User-Id':'11'})
    assert info.status_code==200 and info.get_json()['variant']=='friendly'
    assert 'card_id' not in info.get_json()
    response=client.post('/api/v1/quick/matches/'+key+'/card',json={'card_id':card,'allow_custom_cards':True},headers={'X-Debug-User-Id':'11'})
    assert response.status_code in (400,409),response.get_json()
    assert client.get('/api/v1/cards/'+card,headers={'X-Debug-User-Id':'11'}).status_code==404
    assert not api.modes.get_state(key)['cards']


def test_private_upload_rejects_invalid_size_and_public_root(custom,monkeypatch):
    db,api,client=custom;headers={'X-Admin-Token':'synthetic-test-admin'}
    assert client.post('/api/custom/media',data={'image':(BytesIO(b'not an image'),'evil.png')},headers=headers).status_code==400
    response=client.post('/api/custom/media',data={'image':(BytesIO(b'x'*(8*1024*1024+1)),'large.png')},headers=headers)
    try:
        assert response.status_code in (400,413)
    finally:
        response.request.environ['wsgi.input'].close()
        response.close()
    from systems.custom_cards import media_root
    from pathlib import Path
    monkeypatch.setenv('TELBATTLE_CUSTOM_MEDIA_ROOT',str(Path(__file__).resolve().parents[1]/'assets/private'))
    with pytest.raises(ValueError,match='private_media_root_required'):media_root(db)


def test_verified_supplementary_order_grants_without_clone_and_conflicting_retry_fails(custom):
    db=custom[0];_,card=activate(custom)
    order=post(custom,'order',{'buyer_id':1,'card_id':card,'recipients':[11],'rarity':'normal','amount':'50','currency':'TEST'}).get_json()['order_id']
    assert post(custom,'grant',{'order_id':order,'card_id':card,'users':[11]}).status_code==400
    post(custom,'payment',{'order_id':order})
    assert post(custom,'grant',{'order_id':order,'card_id':card,'users':[11]},'extra-grant').status_code==200
    assert post(custom,'revoke',{'card_id':card,'users':[11]},'extra-grant').status_code==400
    assert db.get_card_by_id_for_player(card,11)
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM custom_definitions').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM custom_audit WHERE action=\'grant\'').fetchone()[0]==2


def test_custom_never_cached_as_public_inline_sticker(custom):
    import asyncio
    from bot.handlers.battle import BattleHandlersMixin
    from types import SimpleNamespace
    _,card=activate(custom)
    owner=SimpleNamespace(db=custom[0])
    assert asyncio.run(BattleHandlersMixin._get_inline_card_sticker_file_id(owner,None,1,custom[0].get_card_by_id_for_player(card,1))) is None


def test_friendly_forfeit_after_start_heart_once_and_queue_separation(custom):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom)
    competitive=api.modes.matchmake_random(1,'quick','normal')[1]
    friendly=api.modes.matchmake_random(2,'quick','friendly')[1]
    assert friendly['request_id']!=competitive['request_id']
    joined=api.modes.matchmake_random(3,'quick','friendly')[1]
    assert joined['request_id']==friendly['request_id']
    key=friendly['request_id'];api.modes.start_quick_match(key)
    api.modes.select_quick_card(key,2,card);api.modes.select_quick_card(key,3,'official')
    hearts=db.get_or_create_player(3).hearts
    report=api.modes.forfeit_quick(key,[3])
    assert report['rewards']['3']['hearts_lost']==1
    assert report['rewards']['3']['xp']==0
    assert api.modes.forfeit_quick(key,[3])==report
    assert db.get_or_create_player(3).hearts==hearts-1


def test_custom_economy_and_official_missions_cannot_be_spoofed_by_name(custom):
    db,api,_=custom;_,card=activate(custom);enable_v2(custom,easy=True)
    from systems.progression_economy import ProgressionEconomy
    from systems.progression_config import config_in
    from systems.card_inventory_system import CardInventorySystem
    from systems.progression_missions import ProgressionMissions
    economy=ProgressionEconomy(db)
    assert not economy.preview_upgrade(1,card,'epic')['ok']
    assert not economy.sell_preview(1,card,'normal')['ok']
    assert CardInventorySystem(db).counts(1,card)=={}
    with sqlite3.connect(db.db_path) as conn:
        config=config_in(conn)[1]
        for kind in ('daily','silver'):assert card not in economy.pool(conn,config,kind)
        assert conn.execute('SELECT COUNT(*) FROM card_variants WHERE card_id=?',(card,)).fetchone()[0]==0
        request=api.modes.create_easy_lobby(1,-123,3,allow_custom_cards=True);key=request['request_id']
        scores={str(user):5-user for user in range(1,6)}
        freeze_in(conn,key,1,card)
        awards={user:{'result':'win' if user==1 else 'loss','card_id':card if user==1 else 'official','easy_final':{'scores':scores,'participants':list(range(1,6))}} for user in range(1,6)}
        MatchRewardsSystem.award(conn,key,'easy',awards)
        base={'mission_id':'test','title':'Test','description':'Test','start':None,'end':None,'status':'active','type':'easy_games','target':1,'filters':{},'eligibility':{},'xp_reward':0,'coin_reward':0,'repeat_policy':'once'}
        assert ProgressionMissions.progress_in(conn,1,base,config)['current_progress']==1
        assert ProgressionMissions.progress_in(conn,1,{**base,'type':'character_games','filters':{'card_id':'official'}},config)['current_progress']==0
        assert ProgressionMissions.progress_in(conn,1,{**base,'eligibility':{'official_card_id':card}},config)['visible'] is False
