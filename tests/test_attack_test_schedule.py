"""Scoped scheduling tests: real SQLite, fake time, no Telegram or production data."""
import asyncio
import sqlite3
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from systems.attack_catalog import defaults,example,catalog_in,read,write,remove,records,save_in
from systems.group_attacks import now_utc,GroupAttacks
from systems.progression_config import config_in,period_bounds
from tests.test_group_attacks import scene,play,scalar


def prepare(scene,now,count=3):
    db,engine=scene
    config=defaults()
    config['test_schedule']={'chat_id':-100,'until':(now+timedelta(hours=1)).isoformat()}
    for index in range(count):
        attack=example();attack.update(id='npc-'+str(index),enabled=True,death_after=0,duration_minutes=5)
        config['attacks'].append(attack)
    with sqlite3.connect(db.db_path) as conn:save_in(conn,config,'test-admin')
    return db,engine


def current(db,chat=-100):
    with sqlite3.connect(db.db_path) as conn:
        key=read(conn,'open:'+str(chat))
        return read(conn,'event:'+key) if key else None


def delivered(db):
    # Model successful outbox delivery so scheduling isn't paused by a full queue.
    with sqlite3.connect(db.db_path) as conn:
        for key,_ in records(conn,'notice:'):remove(conn,key)


@pytest.mark.parametrize('outcome',['win','loss','tie','expiry','cancel'])
def test_one_minute_starts_at_finish_for_every_outcome(scene,monkeypatch,outcome):
    now=now_utc();db,engine=prepare(scene,now)
    clock=[now];monkeypatch.setattr('systems.group_attacks.now_utc',lambda:clock[0])
    engine.tick(now);event=current(db)
    assert event and event['participants']=={}
    clock[0]=now+timedelta(minutes=4)
    if outcome=='expiry':
        clock[0]=now+timedelta(minutes=5);engine.tick(clock[0]);result=engine.get(event['id'])
    elif outcome=='cancel':result=engine.cancel(event['id'])
    else:result=play(engine,event,0,1,{'win':'strong','loss':'weak','tie':'equal'}[outcome])
    result=engine.get(event['id'])
    assert result['status']==({'expiry':'void','cancel':'void'}.get(outcome,outcome))
    assert result['finished_at']==clock[0].isoformat()
    delivered(db)
    engine.tick(clock[0]+timedelta(seconds=59));assert current(db) is None
    engine.tick(clock[0]+timedelta(seconds=60));next_event=current(db)
    assert next_event and next_event['attack']['id']!=event['attack']['id']
    with sqlite3.connect(db.db_path) as conn:
        assert not read(conn,'open:-200')


def test_repeated_expirations_ignore_test_event_quotas_but_never_repeat_type(scene,monkeypatch):
    now=now_utc();db,engine=prepare(scene,now)
    seen=[];pools=[]
    def pick(candidates,weights,k):
        pools.append(([a['id'] for a in candidates],weights,k))
        return [candidates[0]]
    monkeypatch.setattr('systems.group_attacks.random.choices',pick)
    for index in range(6):
        start=now+timedelta(minutes=index*6)
        engine=GroupAttacks(db,engine.modes)  # Restart does not discard previous-type state.
        engine.tick(start);event=current(db);assert event
        seen.append(event['attack']['id']);delivered(db)
        engine.tick(start+timedelta(minutes=5));assert current(db) is None
        delivered(db)
    assert seen==['npc-0','npc-1','npc-0','npc-1','npc-0','npc-1']
    assert pools[0]==(['npc-0','npc-1','npc-2'],[1,1,1],1)
    assert pools[1][0]==['npc-1','npc-2']
    assert scalar(db,'SELECT MIN(coins) FROM players')==1000


def test_disabled_and_dead_templates_excluded_and_only_previous_type_waits(scene):
    now=now_utc();db,engine=prepare(scene,now)
    with sqlite3.connect(db.db_path) as conn:
        config=catalog_in(conn);config['attacks'][1]['enabled']=False;save_in(conn,config,'admin')
        write(conn,'progress:-100:npc-2',{'wins':3,'dead':True})
    engine.tick(now);event=current(db);assert event['attack']['id']=='npc-0'
    delivered(db);engine.tick(now+timedelta(minutes=5));delivered(db)
    engine.tick(now+timedelta(minutes=6));assert current(db) is None
    with sqlite3.connect(db.db_path) as conn:
        config=catalog_in(conn);config['attacks'][1]['enabled']=True;save_in(conn,config,'admin')
    engine.tick(now+timedelta(minutes=7));assert current(db)['attack']['id']=='npc-1'


@pytest.mark.parametrize('stop',['disabled','expired'])
def test_stop_restores_normal_rules_without_touching_current_encounter(scene,stop):
    now=now_utc();db,engine=prepare(scene,now)
    engine.tick(now);event=current(db)
    with sqlite3.connect(db.db_path) as conn:
        config=catalog_in(conn)
        config['test_schedule']=({'chat_id':0,'until':''} if stop=='disabled' else
                                 {'chat_id':-100,'until':(now-timedelta(seconds=1)).isoformat()})
        save_in(conn,config,'admin')
    engine.tick(now+timedelta(seconds=30));assert current(db)['id']==event['id']
    delivered(db);engine.tick(now+timedelta(minutes=5));delivered(db)
    engine.tick(now+timedelta(minutes=6));assert current(db) is None


@pytest.mark.parametrize('active',[3,4])
def test_other_group_obeys_hours_and_minimum_activity(scene,active):
    now=now_utc();db,engine=prepare(scene,now)
    with sqlite3.connect(db.db_path) as conn:
        day=period_bounds(config_in(conn)[1],'daily',now)[2]
        write(conn,'activity:'+day+':-200',list(range(1,active+1)))
        hour=now.astimezone(ZoneInfo(config_in(conn)[1]['timezone'])).hour
        start=(hour+1)%24
        config=catalog_in(conn);config.update(start_hour=start,end_hour=start+1);save_in(conn,config,'admin')
    engine.tick(now);assert current(db)
    assert current(db,-200) is None


def test_normal_group_also_never_repeats_only_available_type(scene,monkeypatch):
    now=now_utc();db,engine=prepare(scene,now,count=1)
    monkeypatch.setattr('systems.group_attacks.now_utc',lambda:now)
    with sqlite3.connect(db.db_path) as conn:
        config=catalog_in(conn);config.update(start_hour=0,end_hour=24)
        config['test_schedule']={'chat_id':0,'until':''};save_in(conn,config,'admin')
        day=period_bounds(config_in(conn)[1],'daily',now)[2]
        write(conn,'activity:'+day+':-200',[1,2,3,4])
    engine.tick(now);event=current(db,-200);assert event
    play(engine,event,0,1);delivered(db)
    engine.tick(now+timedelta(hours=4));assert current(db,-200) is None


def test_test_group_keeps_account_daily_limit(scene,monkeypatch):
    now=now_utc();db,engine=prepare(scene,now)
    monkeypatch.setattr('systems.group_attacks.now_utc',lambda:now)
    engine.tick(now);event=current(db)
    with sqlite3.connect(db.db_path) as conn:
        day=period_bounds(config_in(conn)[1],'daily',now)[2]
        write(conn,'limit:'+day+':1',4)
    with pytest.raises(ValueError,match='attack_daily_limit'):engine.join(event['id'],0,1,-100)
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1000


def test_old_catalog_gets_disabled_test_defaults_without_database_write(scene):
    db,_=scene
    with sqlite3.connect(db.db_path) as conn:
        old=defaults();old.pop('test_schedule');write(conn,'catalog',old)
        assert catalog_in(conn)['test_schedule']=={'chat_id':0,'until':''}
        assert 'test_schedule' not in read(conn,'catalog')
        assert save_in(conn,catalog_in(conn),'admin')['revision']==1


@pytest.mark.parametrize('value',[
    {'chat_id':True,'until':''},{'chat_id':123,'until':''},
    {'chat_id':-100,'until':'tomorrow'}, {'chat_id':-100,'until':'2026-01-01T10:00:00'},
    {'chat_id':-100,'until':None},{'chat_id':0,'until':'2026-01-01T10:00:00+00:00'},
])
def test_invalid_test_settings_rejected(scene,value):
    db,_=scene
    with sqlite3.connect(db.db_path) as conn:
        config=defaults();config['test_schedule']=value
        with pytest.raises(ValueError):save_in(conn,config,'admin')
        assert read(conn,'catalog') is None


def test_test_window_cannot_exceed_one_day(scene):
    db,_=scene
    with sqlite3.connect(db.db_path) as conn:
        config=defaults();config['test_schedule']={'chat_id':-100,'until':(now_utc()+timedelta(days=2)).isoformat()}
        with pytest.raises(ValueError):save_in(conn,config,'admin')


@pytest.mark.parametrize('chat_type',['supergroup','group','private'])
def test_chat_id_command_is_read_only_and_group_scoped(chat_type):
    from bot.group_attacks import chat_id_command
    reply=AsyncMock();update=NS(effective_chat=NS(id=-1001234567890,type=chat_type),effective_message=NS(reply_text=reply))
    asyncio.run(chat_id_command(update,NS()))
    text=reply.call_args.args[0]
    if chat_type=='private':assert '/chatid' in text and '-1001234567890' not in text
    else:assert '-1001234567890' in text
