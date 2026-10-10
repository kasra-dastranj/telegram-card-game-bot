"""Admin-defined missions derived from qualified, immutable reward events."""
import json
from datetime import datetime, timezone
from systems.progression_economy import ProgressionEconomy
from systems.progression_config import period_bounds, config_in
from systems.reward_ledger import receipt_in, apply_in

TYPES={'quick_games','deck_games','competitive_wins','character_games','trait_games','daily_claims','silver_claims','official_upgrades','official_sales','easy_games','period_score'}


def save_mission_in(conn,definition,actor):
    fields={'mission_id','title','description','start','end','status','type','target','filters','eligibility','xp_reward','coin_reward','repeat_policy'}
    if not isinstance(definition,dict) or set(definition)!=fields:raise ValueError('invalid_mission_fields')
    if definition['type'] not in TYPES or definition['status'] not in ('active','paused') or definition['repeat_policy'] not in ('once','daily','weekly','monthly'):raise ValueError('invalid_mission_type')
    if any(type(definition[key]) is not int or definition[key]<0 for key in ('target','xp_reward','coin_reward')) or definition['target']<1:raise ValueError('invalid_mission_reward')
    if not all(isinstance(definition[key],str) and definition[key] for key in ('mission_id','title','description')) or not actor:raise ValueError('invalid_mission_identity')
    if not isinstance(definition['filters'],dict) or set(definition['filters'])-{'card_id','trait','modes'}:raise ValueError('invalid_mission_filters')
    if not isinstance(definition['eligibility'],dict) or set(definition['eligibility'])-{'official_card_id','min_level'}:raise ValueError('invalid_mission_eligibility')
    for key in ('card_id','trait'):
        if key in definition['filters'] and (not isinstance(definition['filters'][key],str) or not definition['filters'][key]):raise ValueError('invalid_mission_filters')
    modes=definition['filters'].get('modes',[])
    if not isinstance(modes,list) or any(mode not in ('quick','legacy_pvp','three_round','deck','easy','risk') for mode in modes):raise ValueError('invalid_mission_filters')
    eligibility=definition['eligibility']
    if 'min_level' in eligibility and (type(eligibility['min_level']) is not int or not 1<=eligibility['min_level']<=config_in(conn)[1]['max_level']):raise ValueError('invalid_mission_eligibility')
    if 'official_card_id' in eligibility and (not isinstance(eligibility['official_card_id'],str) or not eligibility['official_card_id']):raise ValueError('invalid_mission_eligibility')
    for key in ('start','end'):
        if definition[key] is not None:
            moment=datetime.fromisoformat(definition[key])
            if moment.tzinfo is None:raise ValueError('mission_timezone_required')
    if definition['start'] and definition['end'] and datetime.fromisoformat(definition['start'])>=datetime.fromisoformat(definition['end']):raise ValueError('invalid_mission_time')
    now=datetime.now(timezone.utc).isoformat()
    row=conn.execute('SELECT version FROM economy_missions WHERE mission_id=?',(definition['mission_id'],)).fetchone()
    version=row[0]+1 if row else 1
    encoded=json.dumps(definition,sort_keys=True)
    conn.execute('INSERT INTO economy_missions VALUES(?,?,?,?,?) ON CONFLICT(mission_id) DO UPDATE SET definition_json=excluded.definition_json,version=excluded.version,actor=excluded.actor,updated_at=excluded.updated_at',(definition['mission_id'],encoded,version,actor,now))
    conn.execute('INSERT INTO economy_mission_audit(mission_id,definition_json,actor,created_at) VALUES(?,?,?,?)',(definition['mission_id'],encoded,actor,now))
    return version


class ProgressionMissions:
    def __init__(self,db):self.economy=ProgressionEconomy(db)

    @staticmethod
    def progress_in(conn,user,mission,config,now=None):
        now=now or datetime.now(timezone.utc)
        start=datetime.fromisoformat(mission['start']) if mission['start'] else datetime.min.replace(tzinfo=timezone.utc)
        end=datetime.fromisoformat(mission['end']) if mission['end'] else datetime.max.replace(tzinfo=timezone.utc)
        visible=mission['status']=='active' and start<=now<end
        repeat=mission['repeat_policy']
        window='once'
        if repeat!='once':
            period_start,period_end,window=period_bounds(config,repeat,now)
            start=max(start,period_start);end=min(end,period_end)
        eligibility=mission['eligibility']
        card=eligibility.get('official_card_id')
        if card and not conn.execute("SELECT 1 FROM player_card_stacks p JOIN cards c USING(card_id) WHERE p.user_id=? AND p.card_id=? AND c.origin='official' AND p.quantity>0",(user,card)).fetchone():visible=False
        level=conn.execute('SELECT level FROM player_progression WHERE user_id=?',(user,)).fetchone()
        if eligibility.get('min_level',1)>(level[0] if level else 1):visible=False
        progress=0
        rows=conn.execute('SELECT source,event_type,payload_json,score FROM reward_ledger WHERE user_id=? AND created_at>=? AND created_at<?',(user,start.isoformat(),end.isoformat())).fetchall()
        for source,event_type,encoded,score in rows:
            payload=json.loads(encoded)
            filters=mission['filters'];mode=payload.get('mode')
            if filters.get('modes') and mode not in filters['modes']:continue
            if filters.get('card_id') and payload.get('card_id')!=filters['card_id']:continue
            if filters.get('trait'):
                row=conn.execute('SELECT abilities FROM cards WHERE card_id=? AND origin=\'official\'',(payload.get('card_id'),)).fetchone()
                if not row or filters['trait'] not in json.loads(row[0] or '[]'):continue
            kind=mission['type'];eligible=False
            if event_type=='match' and payload.get('qualified'):
                eligible=(kind=='quick_games' and mode in ('quick','legacy_pvp') or kind=='deck_games' and mode in ('deck','three_round') or kind=='competitive_wins' and payload.get('result')=='win' or kind in ('character_games','trait_games') or kind=='easy_games' and mode=='easy')
                if kind=='period_score':progress+=score
            elif kind=='daily_claims':eligible=event_type=='daily_claim'
            elif kind=='silver_claims':eligible=event_type=='silver_claim'
            elif kind=='official_upgrades':eligible=event_type=='official_upgrade'
            elif kind=='official_sales':eligible=event_type=='official_sell'
            if eligible:progress+=1
        operation='mission:'+mission['mission_id']+':'+window
        claimed=receipt_in(conn,operation,user) is not None
        return {'mission_id':mission['mission_id'],'card_id':card,'card_name':mission['title'],'name':mission['title'],'description':mission['description'],
                'mission_type':mission['type'],'target':mission['target'],'current_progress':min(progress,mission['target']),
                'progress_percent':min(100,progress*100//mission['target']),'completed':progress>=mission['target'],'reward_claimed':claimed,
                'can_claim':visible and progress>=mission['target'] and not claimed,'visible':visible,'operation':operation,
                'xp_reward':mission['xp_reward'],'coin_reward':mission['coin_reward']}

    def list(self,user):
        def action(conn,version,config):
            result=[]
            for row in conn.execute('SELECT definition_json FROM economy_missions ORDER BY mission_id'):
                item=self.progress_in(conn,user,json.loads(row[0]),config)
                if item['visible']:result.append(item)
            return result
        result=self.economy.run(action)
        return result if isinstance(result,list) else []

    def claim(self,user,mission_id):
        def action(conn,version,config):
            row=conn.execute('SELECT definition_json,version FROM economy_missions WHERE mission_id=?',(mission_id,)).fetchone()
            if not row:raise ValueError('mission_not_found')
            definition=json.loads(row[0]);status=self.progress_in(conn,user,definition,config)
            if status['reward_claimed']:return receipt_in(conn,status['operation'],user)
            if not status['can_claim']:raise ValueError('mission_incomplete_or_ineligible')
            return apply_in(conn,status['operation'],user,'mission','mission_claim',version,payload={'mission_id':mission_id,'mission_version':row[1]},xp=definition['xp_reward'],coins=definition['coin_reward'],extra={'mission_id':mission_id,'card_id':definition['eligibility'].get('official_card_id'),'xp_gained':definition['xp_reward']})
        return self.economy.run(action)
