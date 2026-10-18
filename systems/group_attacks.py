"""Persistent Quick NPC encounters; no startup migration or in-memory busy flag."""
from __future__ import annotations

import copy
import json
import random
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

from systems.attack_catalog import STATS,read,write,remove,records,catalog_in,validate_reward
from systems.attack_rewards import reserve_in,escrow_in,settle_user_in
from systems.progression_config import config_in,enabled_in,period_bounds


def now_utc():return datetime.now(timezone.utc)


def date(value):return datetime.fromisoformat(value).astimezone(timezone.utc)


def test_chat(settings,chat,now):
    schedule=settings.get('test_schedule',{})
    return bool(schedule.get('chat_id')==chat and schedule.get('until') and now<date(schedule['until']))


def active_player_in(conn,user):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='foundation_settings'").fetchone():return False
    lock=read(conn,'player:'+str(user))
    return bool(lock and date(lock['deadline'])>now_utc())


def group_for_match(conn,key):
    tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'game_requests' in tables:
        row=conn.execute('SELECT origin_chat_id FROM game_requests WHERE request_id=?',(key,)).fetchone()
        if row and row[0] and row[0]<0:return row[0]
    if key.startswith('fight:') and 'active_fights' in tables:
        row=conn.execute('SELECT chat_id FROM active_fights WHERE fight_id=?',(key[6:],)).fetchone()
        if row and row[0] and row[0]<0:return row[0]
    return None


def record_activity_in(conn,key,mode,awards):
    if mode in ('practice','solo','risk'):return
    group=group_for_match(conn,key)
    if group is None:return
    config=config_in(conn)[1];start,end,day=period_bounds(config,'daily')
    users=set(read(conn,'activity:'+day+':'+str(group),[]))
    final=next(iter(awards.values()),{}).get('easy_final')
    for user,item in awards.items():
        paid=conn.execute('SELECT awarded_at FROM match_reward_events WHERE request_id=? AND user_id=?',(key,user)).fetchone()
        stamp=datetime.fromisoformat(paid[0]) if paid else None
        if stamp and stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        if user>0 and stamp and start<=stamp<end and item.get('valid',True) and (mode!='easy' or final and user in final['participants']):users.add(user)
    if users:
        write(conn,'activity:'+day+':'+str(group),sorted(users))


def referenced_card_in(conn,card_id):
    attacks=list(catalog_in(conn)['attacks'])
    for _,event_id in records(conn,'open:'):
        event=read(conn,'event:'+event_id)
        if event:attacks.append(event['attack'])
    return any(enemy['card_id']==card_id for a in attacks for enemy in a['enemies']) or any(
        c['card_id']==card_id for a in attacks for reward in (a['win'],a['death_reward']) for c in reward['cards'])


def card_in(conn,card_id,rarity=None,user=None):
    row=conn.execute('SELECT name,rarity,origin,power,speed,iq,popularity,card_type,image_path FROM cards WHERE card_id=?',(card_id,)).fetchone()
    if not row or row[2]!='official':raise ValueError('attack_official_card_required')
    name,base,_,*_=row
    if user is not None:
        owned=conn.execute('SELECT rarity_override FROM player_cards WHERE user_id=? AND card_id=?',(user,card_id)).fetchone()
        if not owned:raise ValueError('card_not_owned')
        rarity=owned[0] or base
        if not conn.execute('SELECT 1 FROM player_card_stacks WHERE user_id=? AND card_id=? AND rarity=? AND quantity>0',(user,card_id,rarity)).fetchone():raise ValueError('card_not_owned')
    rarity=rarity or base
    variant=conn.execute('SELECT variant_id,power,speed,iq,popularity,card_type,image_path,passive FROM card_variants WHERE card_id=? AND rarity=?',(card_id,rarity)).fetchone()
    if not variant and rarity!=base:raise ValueError('variant_unavailable')
    values=variant[1:5] if variant else row[3:7]
    metadata=conn.execute('SELECT traits,passive FROM card_mode_metadata WHERE card_id=?',(card_id,)).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_mode_metadata'").fetchone() else None
    from systems.card_trait_registry import variant_traits
    traits=variant_traits(conn,card_id,rarity)
    passive=json.loads((variant[7] if variant else metadata[1] if metadata else '{}') or '{}')
    media=conn.execute("SELECT file_id FROM card_variant_media_cache WHERE variant_id=? AND media_kind='sticker'",(variant[0],)).fetchone() if variant else conn.execute("SELECT file_id FROM card_media_cache WHERE card_id=? AND media_kind='sticker'",(card_id,)).fetchone()
    return {'card_id':card_id,'rarity':rarity,'name':name,'stats':{s:max(1,min(100,int(v))) for s,v in zip(STATS,values)},
            'card_type':variant[5] if variant else row[7],'image_path':variant[6] if variant else row[8],
            'sticker_file_id':media[0] if media else '', 'traits':traits,'passive':passive}


def effective(card,opponent,arena):
    from systems.game_mode_system import normalize_quick_card_type
    values=dict(card['stats'])
    for effect in arena.get('effects',[]):
        if effect.get('card_type')==normalize_quick_card_type(card['card_type']) and effect.get('stat') in STATS:
            values[effect['stat']]+=int(effect.get('delta',0))
    passive=card.get('passive') or {};condition=passive.get('condition') or {};effect=passive.get('effect') or {}
    if arena.get('passives_enabled',True) and condition and effect.get('stat') in STATS:
        matches=(not condition.get('arena') or condition['arena']==arena.get('arena_id',arena.get('id')))
        matches=matches and (not condition.get('opponent_name') or condition['opponent_name'].casefold()==opponent['name'].casefold())
        matches=matches and (not condition.get('opponent_trait') or condition['opponent_trait'].casefold() in {t.casefold() for t in opponent.get('traits',[])})
        if matches:values[effect['stat']]+=int(effect.get('delta',0))
    return values


class GroupAttacks:
    def __init__(self,db,modes=None):self.db,self.modes=db,modes

    def run(self,action):
        with closing(sqlite3.connect(self.db.db_path,timeout=30)) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            return action(conn)

    def get(self,event_id):
        with closing(sqlite3.connect(self.db.db_path)) as conn:return read(conn,'event:'+event_id)

    def _arena(self,exclude=None):
        if self.modes is None:
            from systems.game_mode_system import GameModeSystem
            self.modes=GameModeSystem(self.db)
        arena=copy.deepcopy(self.modes._random_arena(exclude))
        if exclude and arena.get('arena_id',arena.get('id'))==exclude:raise ValueError('no_alternative_arena')
        return arena

    @staticmethod
    def _save(conn,event):
        event['revision']+=1
        write(conn,'event:'+event['id'],event)
        write(conn,'notice:'+event['id'],True)

    def _finish(self,conn,event,outcome,now=None):
        if event['status']!='open':return
        progress_key='progress:'+str(event['chat_id'])+':'+event['attack']['id']
        progress=read(conn,progress_key,{'wins':0,'dead':False})
        killed=False
        if outcome=='win':
            progress['wins']+=1
            killed=bool(event['attack']['death_after'] and progress['wins']>=event['attack']['death_after'])
            progress['dead']=killed
            write(conn,progress_key,progress)
        event.update(status=outcome,killed=killed,progress=progress,receipts={},finished_at=(now or now_utc()).isoformat())
        for slot in event['slots']:
            if slot['status'] in ('open','playing'):slot.update(status='cancelled',reason='team_'+outcome)
        for user in event['participants']:
            event['receipts'][user]=settle_user_in(conn,event,int(user),outcome,killed)
            lock=read(conn,'player:'+user)
            if lock and lock['event']==event['id']:remove(conn,'player:'+user)
        remove(conn,'reserve:'+event['id'])
        if read(conn,'open:'+str(event['chat_id']))==event['id']:remove(conn,'open:'+str(event['chat_id']))
        self._save(conn,event)

    def _advance(self,conn,event,now):
        if event['status']!='open':return
        for slot in event['slots']:
            if slot['status']=='playing' and date(slot['deadline'])<=now:
                slot.update(status='loss',reason='timeout')
                lock=read(conn,'player:'+str(slot['user']))
                if lock and lock['event']==event['id']:remove(conn,'player:'+str(slot['user']))
                self._save(conn,event)
        wins=sum(s['status']=='win' for s in event['slots']);losses=sum(s['status']=='loss' for s in event['slots']);size=len(event['slots'])
        complete=all(s['status'] in ('win','loss','tie') for s in event['slots'])
        if losses>size//2:self._finish(conn,event,'loss',now)
        elif complete:self._finish(conn,event,'win' if wins>losses else 'loss' if losses>wins else 'tie',now)
        elif date(event['deadline'])<=now:self._finish(conn,event,'void',now)

    def _spawn(self,conn,chat,users,settings,now):
        if read(conn,'open:'+str(chat)):return None
        _,config=config_in(conn);day=period_bounds(config,'daily',now)[2]
        testing=test_chat(settings,chat,now)
        local=now.astimezone(ZoneInfo(config['timezone']))
        if not testing and not settings['start_hour']<=local.hour<settings['end_hour']:return None
        quota=max((r['max_events'] for r in settings['frequency'] if len(users)>=r['min_active']),default=0)
        previous=read(conn,'group:'+str(chat),{})
        if testing:
            prior=read(conn,'event:'+previous.get('last',''),{})
            closed=prior.get('finished_at') or previous.get('at')
            if closed and date(closed)+timedelta(seconds=60)>now:return None
        elif previous.get('day')==day:
            if previous.get('count',0)>=quota:return None
            prior=read(conn,'event:'+previous.get('last',''),{})
            if prior and not prior.get('participants'):return None  # No repeated unattended attacks today.
        if not testing and previous.get('at') and date(previous['at'])+timedelta(minutes=settings['gap_minutes'])>now:return None
        candidates=[]
        for attack in settings['attacks']:
            if not attack['enabled']:continue
            if not testing and (len(users)<attack['min_active'] or attack['max_active'] and len(users)>attack['max_active']):continue
            if read(conn,'progress:'+str(chat)+':'+attack['id'],{}).get('dead'):continue
            if attack['id']==previous.get('attack'):continue
            candidates.append(attack)
        if (not testing and not quota) or not candidates:return None
        attack=copy.deepcopy(random.choices(candidates,weights=[a['weight'] for a in candidates],k=1)[0])
        for enemy in attack['enemies']:
            if enemy['card_id']:
                snapshot=card_in(conn,enemy['card_id'],enemy['rarity'])
                if enemy['use_custom_stats']:
                    snapshot['stats']=dict(enemy['stats']);snapshot['card_type']=enemy['card_type']
                if enemy['name']:snapshot['name']=enemy['name']
                if enemy['sticker_file_id']:snapshot['sticker_file_id']=enemy['sticker_file_id']
                enemy.clear();enemy.update(snapshot)
            else:enemy.update(traits=[],passive={},image_path='')
        validate_reward(conn,attack['win']);validate_reward(conn,attack['death_reward'])
        for reward in (attack['win'],attack['death_reward']):
            for item in reward['cards']:
                item['name']=conn.execute('SELECT name FROM cards WHERE card_id=?',(item['card_id'],)).fetchone()[0]
        progress=read(conn,'progress:'+str(chat)+':'+attack['id'],{'wins':0,'dead':False})
        event={'id':uuid.uuid4().hex,'chat_id':chat,'attack':attack,'settings':settings,
               'day':day,'config_version':config_in(conn)[0],'status':'open','revision':0,
               'created_at':now.isoformat(),'deadline':(now+timedelta(minutes=attack['duration_minutes'])).isoformat(),
               'slots':[{'status':'open'} for _ in attack['enemies']], 'participants':{},
               'kill_possible':bool(attack['death_after'] and progress['wins']+1>=attack['death_after']),
               'delivery':{},'progress':progress}
        # The event needs only the timing/limits snapshot, not another full catalog.
        event['settings']={key:settings[key] for key in ('choice_seconds','user_daily_limit')}
        event['settings']['timezone']=config['timezone']
        reserve_in(conn,event)
        write(conn,'open:'+str(chat),event['id'])
        write(conn,'history:'+now.isoformat()+':'+event['id'],event['id'])
        write(conn,'group:'+str(chat),{'day':day,'count':(previous.get('count',0) if previous.get('day')==day else 0)+1,'at':now.isoformat(),'last':event['id'],'attack':attack['id']})
        self._save(conn,event)
        return event

    def tick(self,now=None):
        now=now or now_utc()
        def action(conn):
            heartbeat=read(conn,'heartbeat')
            for _,event_id in records(conn,'open:'):
                event=read(conn,'event:'+event_id)
                if event:
                    interrupted=heartbeat and (now-date(heartbeat)).total_seconds()>max(120,event['settings']['choice_seconds']*2)
                    if interrupted and any(s['status']=='playing' for s in event['slots']):self._finish(conn,event,'void',now)
                    else:self._advance(conn,event,now)
            write(conn,'heartbeat',now.isoformat())
            settings=catalog_in(conn)
            if not settings['enabled'] or not enabled_in(conn):return
            start,end,day=period_bounds(config_in(conn)[1],'daily',now)
            if read(conn,'activity_warmed')!=day:
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'match_reward_events' in tables:
                    for key,user,mode in conn.execute('SELECT request_id,user_id,mode FROM match_reward_events WHERE julianday(awarded_at)>=julianday(?) AND julianday(awarded_at)<julianday(?)',(start.isoformat(),end.isoformat())).fetchall():
                        if user<=0 or mode in ('practice','solo','risk'):continue
                        group=group_for_match(conn,key)
                        if group is None:continue
                        if mode=='easy':
                            row=conn.execute('SELECT state_json FROM game_match_states WHERE request_id=?',(key,)).fetchone()
                            history=json.loads(row[0]).get('round_history',[]) if row else []
                            if not any(entry.get('user_id')==user for round_item in history for entry in round_item.get('entries',[])):continue
                        activity_key='activity:'+day+':'+str(group)
                        users=set(read(conn,activity_key,[]));users.add(user);write(conn,activity_key,sorted(users))
                write(conn,'activity_warmed',day)
            groups=records(conn,'activity:'+day+':')
            test_group=settings['test_schedule']['chat_id']
            testing=test_chat(settings,test_group,now)
            test_key='activity:'+day+':'+str(test_group)
            if testing and not any(key==test_key for key,_ in groups):groups.append((test_key,[]))
            if read(conn,'cleanup_day')!=day:
                cutoff=(now-timedelta(days=7)).date().isoformat()
                for prefix in ('activity:','limit:'):
                    for key,_ in records(conn,prefix):
                        if key.split(':')[1]<cutoff:remove(conn,key)
                write(conn,'cleanup_day',day)
            cursor=read(conn,'scheduler_cursor','')
            groups=sorted(groups,key=lambda pair:(not (testing and pair[0]==test_key),pair[0]<=cursor,pair[0]))[:64]
            ready_notices=sum(value is True or date(value['next_attempt'])<=now for _,value in records(conn,'notice:'))
            spawn_budget=max(0,4-ready_notices)
            for key,users in groups:
                if (len(users)>=4 or testing and key==test_key) and spawn_budget:
                    conn.execute('SAVEPOINT attack_spawn')
                    try:
                        event=self._spawn(conn,int(key.rsplit(':',1)[1]),users,settings,now)
                        if event:
                            remove(conn,'health:'+str(event['chat_id']));spawn_budget-=1
                    except ValueError as exc:
                        conn.execute('ROLLBACK TO attack_spawn')
                        write(conn,'health:'+key.rsplit(':',1)[1],{'reason':str(exc),'at':now.isoformat()})
                    finally:conn.execute('RELEASE attack_spawn')
            if groups:write(conn,'scheduler_cursor',groups[-1][0])
        self.run(action)

    def join(self,event_id,index,user,chat):
        # Initialize the arena provider before taking SQLite's write lock.
        arena=self._arena()
        def action(conn):
            event=read(conn,'event:'+event_id)
            if not event or event['chat_id']!=chat:raise ValueError('attack_not_found')
            if event['status']!='open' or date(event['deadline'])<=now_utc():raise ValueError('attack_closed')
            if not enabled_in(conn):raise ValueError('progression_v2_disabled')
            if type(index) is not int or not 0<=index<len(event['slots']):raise ValueError('attack_not_found')
            if event['slots'][index]['status']!='open':raise ValueError('attack_slot_taken')
            if str(user) in event['participants']:raise ValueError('attack_already_joined')
            from systems.match_activity import require_free_in
            require_free_in(conn,user)
            cards=[row[0] for row in conn.execute("SELECT DISTINCT s.card_id FROM player_card_stacks s JOIN cards c USING(card_id) WHERE s.user_id=? AND c.origin='official' AND s.quantity>0 ORDER BY s.card_id",(user,))]
            if not cards:raise ValueError('attack_no_cards')
            day=period_bounds(config_in(conn)[1],'daily')[2];limit_key='limit:'+day+':'+str(user)
            count=read(conn,limit_key,0)
            if count>=event['settings']['user_daily_limit']:raise ValueError('attack_daily_limit')
            escrow_in(conn,event,user);write(conn,limit_key,count+1)
            deadline=min(date(event['deadline']),now_utc()+timedelta(seconds=event['settings']['choice_seconds'])).isoformat()
            slot={'status':'playing','phase':'card','user':user,'cards':cards,'deadline':deadline,'arena':arena}
            event['slots'][index]=slot;event['participants'][str(user)]=index
            write(conn,'player:'+str(user),{'event':event_id,'deadline':deadline})
            self._save(conn,event)
            return event
        return self.run(action)

    @staticmethod
    def _choice(conn,event_id,index,user,phase):
        event=read(conn,'event:'+event_id)
        if not event or event['status']!='open' or type(index) is not int or not 0<=index<len(event['slots']):raise ValueError('attack_closed')
        slot=event['slots'][index]
        if slot.get('user')!=user or slot['status']!='playing' or slot['phase']!=phase:raise ValueError('attack_choice_locked')
        if date(slot['deadline'])<=now_utc() or date(event['deadline'])<=now_utc():raise ValueError('attack_choice_expired')
        return event,slot

    def _next(self,conn,event,slot,phase):
        slot['phase']=phase
        slot['deadline']=min(date(event['deadline']),now_utc()+timedelta(seconds=event['settings']['choice_seconds'])).isoformat()
        write(conn,'player:'+str(slot['user']),{'event':event['id'],'deadline':slot['deadline']})
        self._save(conn,event)

    @staticmethod
    def _npc_stat(slot,enemy):
        allowed=[s for s in STATS if s not in slot['arena'].get('disabled_stats',[]) and s!=slot.get('npc_locked')]
        if not allowed:raise ValueError('stat_not_allowed')
        values=effective(enemy,slot['card'],slot['arena'])
        best=max(values[s] for s in allowed)
        return random.choice([s for s in allowed if values[s]==best])

    def choose_card(self,event_id,index,user,card_index):
        def action(conn):
            event,slot=self._choice(conn,event_id,index,user,'card')
            if type(card_index) is not int or not 0<=card_index<len(slot['cards']):raise ValueError('card_not_owned')
            slot['card']=card_in(conn,slot['cards'][card_index],user=user)
            slot['npc_stat']=self._npc_stat(slot,event['attack']['enemies'][index])
            self._next(conn,event,slot,'ability' if slot['arena'].get('abilities_enabled',True) else 'stat')
            return event
        return self.run(action)

    def choose_ability(self,event_id,index,user,key):
        alternative=None
        if key=='reroll_arena':
            current=self.get(event_id)
            if not current or type(index) is not int or not 0<=index<len(current['slots']):raise ValueError('attack_not_found')
            old=current['slots'][index].get('arena',{})
            alternative=self._arena(old.get('arena_id',old.get('id')))
        def action(conn):
            event,slot=self._choice(conn,event_id,index,user,'ability')
            from systems.game_mode_system import ABILITY_DEFINITIONS
            if key!='skip':
                definition=ABILITY_DEFINITIONS.get(key)
                if not definition:raise ValueError('unknown_ability')
                if key=='reroll_arena':
                    old=slot['arena'].get('arena_id',slot['arena'].get('id'))
                    if alternative.get('arena_id',alternative.get('id'))==old:raise ValueError('no_alternative_arena')
                    slot['arena']=alternative
                effect=definition['effect']
                if effect['type']=='lock_stat':slot['npc_locked']=effect['stat']
                from systems.three_round_abilities import consume_ability
                consume_ability(conn,user,key)
                if slot['npc_stat'] in slot['arena'].get('disabled_stats',[]) or slot['npc_stat']==slot.get('npc_locked'):
                    slot['npc_stat']=self._npc_stat(slot,event['attack']['enemies'][index])
            slot['ability']=key
            self._next(conn,event,slot,'stat')
            return event
        return self.run(action)

    def choose_stat(self,event_id,index,user,stat):
        def action(conn):
            event,slot=self._choice(conn,event_id,index,user,'stat')
            if stat not in STATS or stat in slot['arena'].get('disabled_stats',[]):raise ValueError('stat_not_allowed')
            enemy=event['attack']['enemies'][index]
            yours=effective(slot['card'],enemy,slot['arena']);theirs=effective(enemy,slot['card'],slot['arena'])
            from systems.game_mode_system import ABILITY_DEFINITIONS
            effect=ABILITY_DEFINITIONS.get(slot.get('ability'),{}).get('effect',{})
            if effect.get('type')=='weaken_stat':theirs[effect['stat']]+=int(effect.get('delta',-2))
            chosen=[stat,slot['npc_stat']]
            score=sum(yours[s] for s in chosen);opponent_score=sum(theirs[s] for s in chosen)
            slot.update(status='win' if score>opponent_score else 'loss' if score<opponent_score else 'tie',
                        report={'stats':chosen,'player_values':yours,'npc_values':theirs,'score':score,'npc_score':opponent_score})
            remove(conn,'player:'+str(user))
            self._save(conn,event);self._advance(conn,event,now_utc())
            return event
        return self.run(action)

    def cancel(self,event_id):
        def action(conn):
            event=read(conn,'event:'+event_id)
            if not event:raise ValueError('attack_not_found')
            self._finish(conn,event,'void')
            return event
        return self.run(action)
