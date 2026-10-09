import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.progression_config import config_in, save_config_in, seed_config, validate_config, period_bounds
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import apply_in, items_in, capacities_in
from systems.shared_foundation import bind_new_context
from systems.match_rewards_system import MatchRewardsSystem
from systems.card_inventory_system import CardInventorySystem


@pytest.fixture
def game(tmp_path):
    db=DatabaseManager(str(tmp_path/'game.db'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    for user in range(1,7):db.get_or_create_player(user)
    card=Card(card_id='deadpool',name='Deadpool',rarity=CardRarity.NORMAL,power=5,speed=5,iq=5,popularity=5,abilities=['hero'])
    db.add_card(card)
    with sqlite3.connect(db.db_path) as conn:
        # Real official variant stats, never synthesized by economic operations.
        for rarity in ('epic','legend'):
            now=datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE card_variants SET power=7,speed=7,iq=7,popularity=7,updated_at=? WHERE card_id='deadpool' AND rarity=?",(now,rarity))
        for user in range(1,7):CardInventorySystem.grant_in(conn,user,'deadpool','normal',12)
        conn.execute("INSERT INTO economy_character_rules VALUES('deadpool','A')")
    return db


def rows(db,sql,args=()):
    with sqlite3.connect(db.db_path) as conn:return conn.execute(sql,args).fetchall()


def test_admin_rare_supply_preserves_issued_and_audits(game):
    import subprocess,sys
    from systems.rare_cards_system import RareCardsSystem,create_rare_cards_tables
    create_rare_cards_tables(game.db_path)
    rare=RareCardsSystem(game)
    assert rare.create_rare_card('admin-rare','Rare',5,5,5,5,[],limited_quantity=2)
    with sqlite3.connect(game.db_path) as conn:
        conn.execute("UPDATE rare_cards_info SET total_issued=1 WHERE card_id='admin-rare'")
    assert not rare.create_rare_card('admin-rare','Rare',5,5,5,5,[],limited_quantity=2)
    command=[sys.executable,'scripts/economy_admin.py','--database',game.db_path,'--actor','test-owner','--rare-supply','admin-rare']
    assert subprocess.run(command+['0'],capture_output=True).returncode!=0
    assert subprocess.run(command+['3'],capture_output=True).returncode==0
    assert rows(game,"SELECT limited_quantity,total_issued FROM rare_cards_info WHERE card_id='admin-rare'")==[(3,1)]
    assert rows(game,"SELECT action,actor FROM economy_admin_audit")==[('rare_supply','test-owner')]


def test_admin_explicit_level_cap_extension():
    config=seed_config()
    config['max_level']=31
    config['level_thresholds'].append(24750)
    config['level_rewards']['31']={'coins':50,'slots':1,'silver_claims':0,'hearts':0}
    assert validate_config(config)['max_level']==31
    del config['level_rewards']['31']
    with pytest.raises(ValueError):validate_config(config)


def test_risk_escrow_raise_call_payout_audited_once(game):
    from systems.risk_mode_system import RiskModeSystem, RiskTable, RiskAction, create_risk_tables
    create_risk_tables(game.db_path)
    for card_id in ('risk-two','risk-three'):
        game.add_card(Card(card_id=card_id,name=card_id,rarity=CardRarity.NORMAL,power=5,speed=5,iq=5,popularity=5,abilities=[]))
    with sqlite3.connect(game.db_path) as conn:
        conn.execute('UPDATE players SET coins=1000 WHERE user_id IN (1,2)')
        conn.execute('UPDATE player_progression SET level=7,total_xp=1350 WHERE user_id IN (1,2)')
    risk=RiskModeSystem(game)
    created=risk.create_risk_match(1,2,RiskTable.TABLE_50)
    assert created['success']
    key=created['match_id']
    with sqlite3.connect(game.db_path) as conn:
        conn.execute("UPDATE risk_matches SET bluff_phase='waiting' WHERE match_id=?",(key,))
    assert risk.make_action(key,1,RiskAction.RAISE,50)['success']
    assert risk.make_action(key,2,RiskAction.CALL)['success']
    assert risk.make_action(key,2,RiskAction.FOLD)['success']
    assert not risk.make_action(key,2,RiskAction.FOLD)['success']
    assert rows(game,'SELECT coins FROM players WHERE user_id IN (1,2) ORDER BY user_id')==[(1100,),(900,)]
    assert rows(game,"SELECT user_id,SUM(coins) FROM reward_ledger WHERE source='risk' GROUP BY user_id ORDER BY user_id")==[(1,100),(2,-100)]
    assert rows(game,"SELECT COUNT(*) FROM reward_ledger WHERE event_type='risk_cash'")==[(5,)]


@pytest.mark.parametrize('mode,values',[('quick',(10,3,1,1)),('three_round',(15,5,3,3)),('deck',(15,5,3,3)),('practice',(0,0,0,0)),('risk',(25,0,5,0))])
@pytest.mark.parametrize('outcome',['win','tie','loss'])
def test_match_matrix_restart_retry_snapshot(game,mode,values,outcome):
    with sqlite3.connect(game.db_path) as conn:
        bind_new_context(conn,'test',mode)
        version,config=config_in(conn)
        config['match']['quick']['win']=99
        save_config_in(conn,config,'admin')
        award={1:{'result':outcome,'xp':999,'score':999,'hearts_lost':1,'tp_delta':99,'card_id':'deadpool'}}
        first=MatchRewardsSystem.award(conn,'test',mode,award)
    db=DatabaseManager(game.db_path)
    with sqlite3.connect(db.db_path) as conn:second=MatchRewardsSystem.award(conn,'test',mode,award)
    assert first['1']['xp']==values[['win','tie','loss'].index(outcome)]
    assert first['1']['score']==(values[3] if outcome=='win' else 0)
    assert second['1']['xp']==first['1']['xp']
    assert rows(game,"SELECT COUNT(*) FROM reward_ledger WHERE event_type='match'")==[(1,)]
    assert rows(game,'SELECT tier_points FROM player_progression WHERE user_id=1')==[(0,)]
    assert rows(game,'SELECT hearts FROM players WHERE user_id=1')==[(7 if outcome=='loss' and mode not in ('practice',) else 8,)]


@pytest.mark.parametrize('rounds,xps,score',[(3,[10,5,3],1),(5,[15,10,8],2),(10,[20,15,13],3),(1,[0,0,0],0)])
@pytest.mark.parametrize('count',[4,5])
def test_easy_threshold_shared_rank_partial_attendance(game,rounds,xps,score,count):
    from systems.game_mode_system import GameModeSystem
    GameModeSystem(game)
    with sqlite3.connect(game.db_path) as conn:
        bind_new_context(conn,'easytest','easy')
        scores={str(user):count-user for user in range(1,count+1)}
        scores['2']=scores['1'] # competition ranks 1,1,3
        state={'rounds':rounds,'scores':scores,'round_history':[]}
        conn.execute('INSERT INTO game_match_states VALUES(?,?,?)',('easytest',json.dumps(state),datetime.now(timezone.utc).isoformat()))
        awards={user:{'result':'win' if user<=2 else 'loss','card_id':'deadpool','easy_final':{'scores':scores,'participants':list(range(1,count+1))}} for user in range(1,count+1)}
        result=MatchRewardsSystem.award(conn,'easytest','easy',awards)
    assert result['1']['xp']==(xps[0] if count>=5 else 0)
    assert result['2']['xp']==result['1']['xp']
    assert result['3']['xp']==(xps[2] if count>=5 else 0)
    assert result['1']['score']==(score if count>=5 else 0)
    assert rows(game,'SELECT DISTINCT hearts FROM players')==[(8,)]


def test_level_jump_all_components_exactly_once(game):
    with sqlite3.connect(game.db_path) as conn:
        version,config=config_in(conn)
        paid=apply_in(conn,'jump',1,'mission','mission_claim',version,xp=23200)
        again=apply_in(conn,'jump',1,'mission','mission_claim',version,xp=23200)
        assert paid['new_level']==30 and again['replayed']
        assert capacities_in(conn,1,config)['slots']==32
        assert capacities_in(conn,1,config)['max_hearts']==10
        assert items_in(conn,1,'free_silver_claim')==2
    assert rows(game,'SELECT coins FROM players WHERE user_id=1')==[(1450,)]
    assert rows(game,'SELECT total_xp FROM player_progression WHERE user_id=1')==[(23200,)]
    assert rows(game,'SELECT COUNT(*) FROM level_component_awards WHERE user_id=1')==[(29,)]


def test_old_account_frozen_wallet_and_capacity(game):
    with sqlite3.connect(game.db_path) as conn:
        conn.execute('DELETE FROM progression_capacities WHERE user_id=1')
        conn.execute('UPDATE players SET max_hearts=13,coins=300 WHERE user_id=1')
        version,config=config_in(conn)
        apply_in(conn,'old-jump',1,'mission','mission_claim',version,xp=23200)
        assert capacities_in(conn,1,config)['slots']==50
        assert capacities_in(conn,1,config)['max_hearts']==13
    assert rows(game,'SELECT coins FROM players WHERE user_id=1')==[(300,)]
    assert rows(game,'SELECT COUNT(*) FROM level_component_awards WHERE user_id=1')==[(0,)]


@pytest.mark.parametrize('ticket',[False,True])
def test_daily_atomic_ability_duplicate_and_retry(game,monkeypatch,ticket):
    monkeypatch.setattr('systems.progression_economy.random.random',lambda:0 if ticket else 0.99)
    economy=ProgressionEconomy(game)
    first=economy.claim(1,request_key='dailyrequest')
    assert first['ok'] and first['ability']
    assert first['reward_type']==('silver_ticket' if ticket else 'card')
    assert economy.claim(1,request_key='dailyrequest')['replayed']
    assert not economy.claim(1)['ok']
    assert rows(game,'SELECT SUM(quantity) FROM player_ability_inventory WHERE user_id=1')==[(1,)]
    assert rows(game,"SELECT quantity FROM player_card_stacks WHERE user_id=1 AND rarity='normal'")==[(12 if ticket else 13,)]


def test_silver_only_epic_tickets_atomic_empty_pool(game):
    economy=ProgressionEconomy(game)
    with sqlite3.connect(game.db_path) as conn:items_in(conn,1,'silver_ticket',6)
    first=economy.claim(1,'silver','silver1')
    assert first['ok'] and first['rarity']=='epic'
    assert economy.claim(1,'silver','silver1')['replayed']
    with sqlite3.connect(game.db_path) as conn:
        version,config=config_in(conn);config['claim']['silver_pool']=['missing'];save_config_in(conn,config,'admin')
    assert economy.claim(1,'silver','silver2')['error_code']=='empty_pool'
    assert rows(game,"SELECT quantity FROM player_economy_items WHERE user_id=1 AND item='silver_ticket'")==[(3,)]


def test_independent_claim_weights_halved_once(game,monkeypatch):
    captured=[]
    monkeypatch.setattr('systems.progression_economy.random.choices',lambda pool,weights,k:captured.append(weights) or [pool[0]])
    with sqlite3.connect(game.db_path) as conn:
        _,config=config_in(conn)
        for kind in ('daily','silver'):
            conn.execute('INSERT INTO claim_receipts VALUES(?,?,?,?)',(1,kind,'deadpool',3 if kind=='daily' else 2))
            ProgressionEconomy.select_claim(conn,1,config,kind)
        conn.execute("UPDATE claim_receipts SET received=30 WHERE claim_type='daily'")
        ProgressionEconomy.select_claim(conn,1,config,'daily')
    assert captured==[[0.5],[1],[0.5]]


@pytest.mark.parametrize('tier,copies,coins',[('A',2,250),('B',3,350)])
def test_upgrade_recipe_sell_rollback_idempotency(game,tier,copies,coins):
    economy=ProgressionEconomy(game)
    first=economy.upgrade(1,'deadpool','epic','up1')
    assert first['xp']==50 and economy.upgrade(1,'deadpool','epic','up1')['replayed']
    with sqlite3.connect(game.db_path) as conn:
        conn.execute('UPDATE economy_character_rules SET legend_recipe_tier=?',(tier,))
        CardInventorySystem.grant_in(conn,1,'deadpool','epic',copies-1)
    assert economy.upgrade(1,'deadpool','legend','up2')['error_code']=='insufficient_upgrade_card'
    assert CardInventorySystem(game).counts(1,'deadpool')['epic']==copies
    with sqlite3.connect(game.db_path) as conn:items_in(conn,1,'upgrade_card',1)
    result=economy.upgrade(1,'deadpool','legend','up2')
    assert result['xp']==200 and 'epic' not in CardInventorySystem(game).counts(1,'deadpool')
    sold=economy.sell(1,'deadpool','legend','sell1')
    assert sold['coins']==coins and economy.sell(1,'deadpool','legend','sell1')['replayed']
    assert economy.sell(1,'deadpool','legend','sell2')['error_code']=='insufficient_copies'


@pytest.mark.parametrize('item',['silver_ticket','refill','permanent_heart','deck_slot','upgrade_card'])
def test_shop_quotes_price_escalation_concurrency(game,item):
    economy=ProgressionEconomy(game)
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET coins=10000,hearts=1 WHERE user_id=1')
    quote=economy.quote(1,item);assert quote['ok']
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:economy.purchase(1,quote['quote_id']),range(2)))
    assert all(result['ok'] for result in results)
    assert sum(bool(result.get('replayed')) for result in results)==1
    assert rows(game,"SELECT COUNT(*) FROM reward_ledger WHERE source='shop'")==[(1,)]
    if item=='refill':
        assert economy.quote(1,item)['error_code']=='hearts_full'
        with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET hearts=1 WHERE user_id=1')
    quote2=economy.quote(1,item)
    assert quote2['price']==quote['price']*(2 if item in ('silver_ticket','refill','permanent_heart') else 1)
    with sqlite3.connect(game.db_path) as conn:
        _,config=config_in(conn);save_config_in(conn,config,'edit')
    assert economy.purchase(1,quote2['quote_id'])['error_code']=='price_changed'


def test_heart_shop_reserves_future_level_bonus(game):
    with sqlite3.connect(game.db_path) as conn:
        conn.execute('UPDATE progression_capacities SET purchased_hearts=10 WHERE user_id=1')
        conn.execute('UPDATE players SET max_hearts=18,coins=10000 WHERE user_id=1')
    assert ProgressionEconomy(game).quote(1,'permanent_heart')['error_code']=='heart_cap'


def test_temporary_copy_migration_preserves_data(game,tmp_path):
    from migrations.migrate_progression_v2 import apply_migration
    from migrations.migrate_card_trait_registry import copy_database
    before=rows(game,'SELECT * FROM players')
    target=copy_database(game.db_path,tmp_path/'preview.db')
    apply_migration(target);apply_migration(target)
    assert rows(SimpleNamespace(db_path=str(target)),'SELECT * FROM players')==before
    assert rows(game,'PRAGMA quick_check')==[('ok',)]


def test_config_validation_and_tehran_periods():
    config=seed_config();assert validate_config(config)==config
    for key,value in [('daily_ticket_percent',101),('silver_tickets',0),('base_weight',True)]:
        bad=seed_config();bad['claim'][key]=value
        with pytest.raises(ValueError):validate_config(bad)
    start,end,key=period_bounds(config,'weekly',datetime(2026,10,9,12,tzinfo=timezone.utc))
    assert key=='2026-10-05' and end-start==timedelta(days=7)
    assert start.hour==20 and start.minute==30


def test_monthly_weekly_shared_rank_and_retry(game):
    from systems.progression_leaderboard import ProgressionLeaderboard
    now=datetime(2026,11,2,12,tzinfo=timezone.utc)
    with sqlite3.connect(game.db_path) as conn:
        for user in range(1,7):
            conn.execute("INSERT INTO fight_history(user_id,result,score_gained,fought_at,fight_type) VALUES(?,'win',?,?,'quick')",(user,10 if user<3 else 8-user,'2026-10-29T12:00:00+00:00'))
    service=ProgressionLeaderboard(game)
    awards=service.settle('weekly',now)
    assert awards[:3]==[(1,1,100),(1,2,100),(3,3,30)]
    assert service.settle('weekly',now)==[]
    assert service.settle('monthly',now)[:3]==[(1,1,300),(1,2,300),(3,3,100)]
    assert service.settle('monthly',now)==[]


def test_mission_qualification_official_ownership_admin_edit(game):
    from systems.progression_missions import save_mission_in, ProgressionMissions
    mission={'mission_id':'deadpool-wins','title':'Deadpool','description':'سه برد رسمی','start':None,'end':None,'status':'active','type':'competitive_wins','target':3,'filters':{'card_id':'deadpool'},'eligibility':{'official_card_id':'deadpool'},'xp_reward':20,'coin_reward':15,'repeat_policy':'once'}
    with sqlite3.connect(game.db_path) as conn:
        save_mission_in(conn,mission,'admin')
        for index in range(3):
            bind_new_context(conn,'mission'+str(index),'quick')
            MatchRewardsSystem.award(conn,'mission'+str(index),'quick',{1:{'result':'win','card_id':'deadpool'}})
        bind_new_context(conn,'practice','practice')
        MatchRewardsSystem.award(conn,'practice','practice',{1:{'result':'win','card_id':'deadpool'}})
        mission['coin_reward']=40;save_mission_in(conn,mission,'edit')
    service=ProgressionMissions(game)
    assert service.list(1)[0]['current_progress']==3
    first=service.claim(1,'deadpool-wins');assert first['coins']==40 and first['xp']==20
    assert service.claim(1,'deadpool-wins')['replayed']


@pytest.mark.parametrize('item',['silver_ticket','upgrade_card','refill','deck_slot','permanent_heart'])
def test_insufficient_coins_rolls_back_delivery_and_quote(game,item):
    economy=ProgressionEconomy(game)
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET hearts=1 WHERE user_id=1')
    before=economy.inventory(1)
    quote=economy.quote(1,item)
    result=economy.purchase(1,quote['quote_id'])
    assert result['error_code']=='insufficient_coins_or_player_missing'
    after=economy.inventory(1)
    assert before['items']==after['items'] and before['capacity']==after['capacity']
    assert rows(game,'SELECT used FROM shop_quotes WHERE quote_id=?',(quote['quote_id'],))==[(0,)]
    assert rows(game,"SELECT COUNT(*) FROM reward_ledger WHERE source='shop'")==[(0,)]


@pytest.mark.parametrize('mode,min_level',[('easy',5),('deck',5),('risk',7),('quick',1),('mini_three_round',1)])
def test_mode_unlocks(game,mode,min_level):
    from systems.mode_access_system import ModeAccessSystem
    system=ModeAccessSystem(game)
    assert system.min_level(mode)==min_level
    assert system.check(1,mode)[0]==(min_level<=1)
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE player_progression SET level=? WHERE user_id=1',(min_level,))
    assert system.check(1,mode)[0]


@pytest.mark.parametrize('mode',['quick','three_round','deck','easy','practice','risk'])
def test_invalid_match_no_reward(game,mode):
    from systems.game_mode_system import GameModeSystem
    GameModeSystem(game)
    with sqlite3.connect(game.db_path) as conn:
        bind_new_context(conn,'invalid',mode)
        if mode=='easy':conn.execute('INSERT INTO game_match_states VALUES(?,?,?)',('invalid',json.dumps({'rounds':3,'scores':{},'round_history':[]}),datetime.now(timezone.utc).isoformat()))
        result=MatchRewardsSystem.award(conn,'invalid',mode,{1:{'result':'loss','valid':False}})
    assert result['1']['xp']==result['1']['score']==result['1']['hearts_lost']==0
    assert rows(game,'SELECT hearts,coins,total_score FROM players WHERE user_id=1')==[(8,0,0)]


def test_weekly_cutover_respects_paid_legacy_batch(game):
    from systems.progression_leaderboard import ProgressionLeaderboard
    with sqlite3.connect(game.db_path) as conn:
        conn.execute('CREATE TABLE weekly_reward_batches(period_key TEXT PRIMARY KEY,awards_json TEXT,awarded_at TEXT)')
        conn.execute("INSERT INTO weekly_reward_batches VALUES('2026-10-26','[]','2026-11-02')")
        conn.execute("INSERT INTO fight_history(user_id,result,score_gained,fought_at) VALUES(1,'win',5,'2026-10-29T12:00:00+00:00')")
    assert ProgressionLeaderboard(game).settle('weekly',datetime(2026,11,2,12,tzinfo=timezone.utc))==[]
    assert rows(game,'SELECT coins FROM players WHERE user_id=1')==[(0,)]


def test_off_flag_old_match_keeps_snapshot_and_old_rules(game):
    with sqlite3.connect(game.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='false' WHERE key='progression_v2_enabled'")
        bind_new_context(conn,'oldmatch','quick')
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
        old=MatchRewardsSystem.award(conn,'oldmatch','quick',{1:{'result':'win','xp':17,'score':7,'card_id':'deadpool'}})
    assert old['1']=={'xp':17,'score':7}
    assert rows(game,'SELECT COUNT(*) FROM match_economy_snapshots')==[(0,)]


def test_v2_legacy_economy_writers_are_closed(game):
    from systems.economy_system import EconomySystem
    from systems.card_upgrade_system import CardUpgradeSystem
    from systems.fusion_system import FusionSystem
    assert not EconomySystem(game).claim_daily_mining(1)[0]
    assert not EconomySystem(game).convert_score_to_coins(1,100)[0]
    assert CardUpgradeSystem(game).upgrade(1,'deadpool','normal_to_epic','old')['error_code']=='coin_upgrade_removed'
    assert not FusionSystem(game).fuse_to_epic(1,['deadpool','x','y'],'deadpool','old').success


def test_last_copy_sell_invalidates_deck_with_reason(game):
    from systems.deck_system import DeckSystem
    with sqlite3.connect(game.db_path) as conn:
        conn.execute("UPDATE player_card_stacks SET quantity=1 WHERE user_id=1 AND card_id='deadpool'")
    deck=game.create_deck(1,'test','deadpool','deadpool','deadpool')
    assert ProgressionEconomy(game).sell(1,'deadpool','normal','last')['ok']
    item=DeckSystem(game).get_player_decks(1)[0]
    assert item['deck_id']==deck and not item['is_valid'] and 'کلکسیون' in item['invalid_reason']


def test_shop_window_reset_keeps_ticket_inventory(game):
    economy=ProgressionEconomy(game)
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET coins=10000 WHERE user_id=1')
    quote=economy.quote(1,'silver_ticket');assert economy.purchase(1,quote['quote_id'])['ok']
    assert economy.quote(1,'silver_ticket')['price']==200
    with sqlite3.connect(game.db_path) as conn:
        conn.execute("UPDATE reward_ledger SET payload_json=json_set(payload_json,'$.window_key','2026-01-05') WHERE source='shop'")
    assert economy.quote(1,'silver_ticket')['price']==100
    assert economy.inventory(1)['items']['silver_ticket']==1


def test_skin_quote_independent_price_edit_no_duplicate_delivery(game):
    from systems.skins_system import SkinsSystem
    SkinsSystem(game).create_skin('dp-blue','deadpool','Blue','special','existing.png',175)
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET coins=1000 WHERE user_id=1')
    economy=ProgressionEconomy(game)
    quote=economy.quote(1,'skin:dp-blue');assert quote['price']==175
    with sqlite3.connect(game.db_path) as conn:conn.execute("UPDATE skins SET price=180 WHERE skin_id='dp-blue'")
    assert economy.purchase(1,quote['quote_id'])['error_code']=='price_changed'
    quote=economy.quote(1,'skin:dp-blue')
    assert economy.purchase(1,quote['quote_id'])['coins_spent']==180
    assert economy.purchase(1,quote['quote_id'])['replayed']
    assert economy.quote(1,'skin:dp-blue')['error_code']=='already_owned'


def test_admin_json_edit_and_flags_are_persisted(game,tmp_path):
    import subprocess,sys
    exported=tmp_path/'config.json'
    result=subprocess.run([sys.executable,'scripts/economy_admin.py','--database',game.db_path,'--export',str(exported)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    value=json.loads(exported.read_text(encoding='utf8'));value['claim']['daily_ticket_percent']=30
    exported.write_text(json.dumps(value),encoding='utf8')
    result=subprocess.run([sys.executable,'scripts/economy_admin.py','--database',game.db_path,'--actor','test-owner','--import-config',str(exported)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    with sqlite3.connect(game.db_path) as conn:assert config_in(conn)[1]['claim']['daily_ticket_percent']==30


@pytest.fixture
def v2_client(game,monkeypatch):
    import web.miniapp_api as miniapp
    monkeypatch.setattr(miniapp,'db',game)
    monkeypatch.setattr(miniapp,'DB_PATH',game.db_path)
    miniapp.app.config.update(TESTING=True,DEBUG=True)
    return miniapp.app.test_client()


def test_miniapp_economy_end_to_end_offline(v2_client,game):
    headers={'X-Debug-User-Id':'1'}
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET coins=1000 WHERE user_id=1')
    profile=v2_client.get('/api/v1/profile',headers=headers).get_json()
    assert profile['progression_v2_enabled'] and profile['tier_points'] is None
    quote=v2_client.post('/api/v1/economy/quote',headers=headers,json={'item':'silver_ticket'}).get_json()
    buy=v2_client.post('/api/v1/economy/purchase',headers=headers,json={'quote_id':quote['quote_id']}).get_json()
    assert buy['profile']['coins']==900
    assert v2_client.post('/api/v1/economy/purchase',headers=headers,json={'quote_id':quote['quote_id']}).get_json()['replayed']
    version=quote['config_version']
    upgraded=v2_client.post('/api/v1/economy/cards/deadpool/upgrade',headers=headers,json={'target':'epic','request_key':'api-up','config_version':version})
    assert upgraded.status_code==200 and upgraded.get_json()['xp']==50
    preview=v2_client.post('/api/v1/economy/cards/deadpool/sell/preview',headers=headers,json={'rarity':'epic'}).get_json()
    sold=v2_client.post('/api/v1/economy/cards/deadpool/sell',headers=headers,json={'rarity':'epic','request_key':'api-sell','config_version':preview['config_version']})
    assert sold.status_code==200 and sold.get_json()['coins']==60
    assert v2_client.post('/api/v1/cards/deadpool/upgrade',headers=headers,json={'upgrade_key':'normal_to_epic','request_key':'unsafe'}).status_code==409


@pytest.mark.parametrize('difficulty',['easy','medium','hard'])
def test_practice_api_all_difficulties_no_rewards(v2_client,game,monkeypatch,difficulty):
    import web.miniapp_api as miniapp
    monkeypatch.setattr(miniapp.AsoAI,'select_card',lambda self,db:db.get_card_by_id('deadpool'))
    monkeypatch.setattr(miniapp.AsoAI,'select_stat',lambda self,available,*args:available[0])
    headers={'X-Debug-User-Id':'1'}
    started=v2_client.post('/api/v1/solo/start',headers=headers,json={'player_card_id':'deadpool','difficulty':difficulty})
    assert started.status_code==200,started.get_json()
    fight=started.get_json()['fight_id']
    for stat in ('power','speed','iq'):
        response=v2_client.post('/api/v1/solo/round',headers=headers,json={'fight_id':fight,'player_stat':stat})
        assert response.status_code==200,response.get_json()
    rewards=response.get_json()['final_result']['rewards']
    assert rewards['xp_gained']==rewards['score_gained']==rewards['tier_points_change']==rewards['hearts_lost']==0
    assert rows(game,'SELECT hearts,coins,total_score FROM players WHERE user_id=1')==[(8,0,0)]


def test_client_operation_key_cannot_poison_match_ledger(game):
    economy=ProgressionEconomy(game)
    assert economy.upgrade(1,'deadpool','epic','match:real')['ok']
    with sqlite3.connect(game.db_path) as conn:
        bind_new_context(conn,'real','quick')
        result=MatchRewardsSystem.award(conn,'real','quick',{1:{'result':'win','card_id':'deadpool'}})
    assert result['1']['xp']==10


def test_starter_cannot_be_reissued_after_selling_every_copy(game):
    from systems.starter_cards_system import grant_starter_cards
    for key in ('a','b'):game.add_card(Card(card_id=key,name=key,rarity=CardRarity.NORMAL,power=1,speed=1,iq=1,popularity=1,abilities=[]))
    game.get_or_create_player(10)
    assert len(grant_starter_cards(game,10))==3
    assert grant_starter_cards(game,10)==[]
    with sqlite3.connect(game.db_path) as conn:
        conn.execute('DELETE FROM player_cards WHERE user_id=10')
        conn.execute('DELETE FROM player_card_stacks WHERE user_id=10')
    assert grant_starter_cards(game,10)==[]


def test_rare_supply_serials_atomic_retry_and_stock(game):
    from systems.rare_cards_system import create_rare_cards_tables
    from systems.progression_rare import issue
    create_rare_cards_tables(game.db_path)
    game.add_card(Card(card_id='rare',name='Rare',rarity=CardRarity.RARE,power=9,speed=9,iq=9,popularity=9,abilities=[]))
    with sqlite3.connect(game.db_path) as conn:conn.execute('INSERT INTO rare_cards_info VALUES(?,1000,1,0)',('rare',))
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(lambda user:issue(game,user,'rare','event','event'+str(user)),(1,2)))
    assert sum(item['success'] for item in result)==1
    winner=1 if result[0]['success'] else 2
    assert issue(game,winner,'rare','event','event'+str(winner))['replayed']
    assert rows(game,'SELECT serial FROM rare_card_instances')==[(1,)]
    assert rows(game,"SELECT total_issued FROM rare_cards_info WHERE card_id='rare'")==[(1,)]


def test_telegram_shop_confirmation_uses_same_atomic_quote(game):
    import asyncio
    from bot.handlers.progression import handle
    from unittest.mock import AsyncMock
    with sqlite3.connect(game.db_path) as conn:conn.execute('UPDATE players SET coins=1000 WHERE user_id=1')
    query=SimpleNamespace(data='v2_quote_silver_ticket',from_user=SimpleNamespace(id=1),id='cb1',answer=AsyncMock(),edit_message_text=AsyncMock())
    update=SimpleNamespace(callback_query=query,effective_user=query.from_user,effective_message=SimpleNamespace(reply_text=AsyncMock()))
    context=SimpleNamespace(user_data={})
    asyncio.run(handle(SimpleNamespace(db=game),update,context))
    keyboard=query.edit_message_text.call_args.kwargs['reply_markup'].inline_keyboard
    assert '100' in query.edit_message_text.call_args.args[0]
    query.data=keyboard[0][0].callback_data
    asyncio.run(handle(SimpleNamespace(db=game),update,context))
    asyncio.run(handle(SimpleNamespace(db=game),update,context))
    assert rows(game,'SELECT coins FROM players WHERE user_id=1')==[(900,)]
    assert rows(game,"SELECT quantity FROM player_economy_items WHERE user_id=1 AND item='silver_ticket'")==[(1,)]
