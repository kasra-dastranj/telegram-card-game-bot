"""Versioned, validated economy configuration; no production credentials."""
from __future__ import annotations

import copy
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def seed_config():
    return {
        "timezone": "Asia/Tehran", "week_start": 0, "settlement_hour": 0,
        "settlement_minute": 15,
        "max_level": 30,
        "level_thresholds": [25*(level-1)*level+50*(level-1) for level in range(1,31)],
        "level_rewards": {str(level): {"coins":50,"slots":1,
            "silver_claims":int(level in (3,10)), "hearts":int(level in (8,10))}
            for level in range(2,31)},
        "mode_levels":{"quick":1,"three_round":1,"mini_three_round":1,"legacy_pvp":1,
                       "practice":1,"solo":1,"easy":5,"deck":5,"risk":7},
        "match":{"quick":{"win":10,"tie":3,"loss":1,"score":1,"loss_hearts":1},
                 "three_round":{"win":15,"tie":5,"loss":3,"score":3,"loss_hearts":1},
                 "deck":{"win":15,"tie":5,"loss":3,"score":3,"loss_hearts":1},
                 "risk":{"win":25,"tie":0,"loss":5,"score":0}},
        "easy":{"min_players":5,"rounds":{"3":{"xp":[10,5,3],"score":1},
                    "5":{"xp":[15,10,8],"score":2},"10":{"xp":[20,15,13],"score":3}}},
        "hearts":{"base":8,"cap":20,"reserve_future_level_bonus":True},
        "slots":{"base":3},
        "claim":{"daily_ticket_percent":20,"silver_tickets":3,"duplicate_threshold":3,
                 "duplicate_factor":0.5,"base_weight":1,"weights":{},"daily_pool":[],"silver_pool":[]},
        "upgrade":{"epic":{"copies":3,"xp":50,"items":0},
                   "legend_A":{"copies":2,"xp":200,"items":1},
                   "legend_B":{"copies":3,"xp":200,"items":1}},
        "sell":{"normal":10,"epic":60,"legend_A":250,"legend_B":350},
        "shop":{"upgrade_card":{"price":200,"factor":1,"window":"none","enabled":True,"stock":None},
                "silver_ticket":{"price":100,"factor":2,"window":"weekly","enabled":True,"stock":None},
                "deck_slot":{"price":200,"factor":1,"window":"none","enabled":True,"stock":None},
                "refill":{"price":100,"factor":2,"window":"daily","enabled":True,"stock":None},
                "permanent_heart":{"price":100,"factor":2,"window":"none","enabled":True,"stock":None}},
        "leaderboard":{"weekly":{"coins":[100,50,30]+[10]*7,"xp":[100,50,30]+[0]*7},
                       "monthly":{"coins":[300,200,100]+[50]*7,"xp":[300,200,100]+[50]*7}},
        "migration":{"legacy_user_policy":"preserve_freeze_rewards"},
        "wheel":{"enabled":False,"price":None,"pool":[]},
    }


def validate_config(value):
    """Reject unknown keys, bool numbers, negative amounts and malformed recipes."""
    defaults = seed_config()
    def shape(item, template, path):
        if isinstance(template, dict):
            if not isinstance(item, dict): raise ValueError("invalid_config:"+path)
            if not template: return  # explicitly extensible pool weights
            if set(item) != set(template): raise ValueError("config_keys:"+path)
            for key in template: shape(item[key],template[key],path+"."+key)
        elif isinstance(template,list):
            if not isinstance(item,list): raise ValueError("invalid_config:"+path)
            if template:
                for entry in item: shape(entry,template[0],path)
        elif type(template) is bool:
            if type(item) is not bool: raise ValueError("invalid_config:"+path)
        elif type(template) is int:
            if type(item) is not int or item<0: raise ValueError("invalid_config:"+path)
        elif type(template) is float:
            if type(item) not in (int,float) or not 0<item<=1: raise ValueError("invalid_config:"+path)
        elif isinstance(template,str):
            if not isinstance(item,str): raise ValueError("invalid_config:"+path)
    # Level counts may change; require explicit rules for every new level.
    defaults['level_rewards']={}
    shape(value,defaults,"config")
    ZoneInfo(value["timezone"])
    if not 0<=value["week_start"]<=6 or value["settlement_hour"]>23 or value["settlement_minute"]>59:
        raise ValueError("invalid_time_window")
    thresholds=value["level_thresholds"]
    if value["max_level"]<1 or len(thresholds)!=value["max_level"] or thresholds[0]!=0 or any(a>=b for a,b in zip(thresholds,thresholds[1:])):
        raise ValueError("invalid_level_curve")
    if set(value['level_rewards'])!={str(level) for level in range(2,value['max_level']+1)}:raise ValueError('invalid_level_rewards')
    for rule in value['level_rewards'].values():
        if not isinstance(rule,dict) or set(rule)!={'coins','slots','silver_claims','hearts'} or any(type(amount) is not int or amount<0 for amount in rule.values()):raise ValueError('invalid_level_rewards')
    if value["easy"]["min_players"]<5 or value["hearts"]["base"]<1 or value["hearts"]["cap"]<value["hearts"]["base"]:
        raise ValueError("invalid_capacity")
    if value['hearts']['cap']>20 or value['slots']['base']<1 or any(not 1<=level<=value['max_level'] for level in value['mode_levels'].values()):
        raise ValueError('invalid_capacity_or_unlock')
    for rule in value['easy']['rounds'].values():
        if len(rule['xp'])!=3:raise ValueError('invalid_easy_ranks')
    for rule in value['leaderboard'].values():
        if not rule['coins'] or len(rule['coins'])!=len(rule['xp']) or len(rule['coins'])>100:raise ValueError('invalid_leaderboard_ranks')
    claim=value["claim"]
    if claim["daily_ticket_percent"]>100 or claim["silver_tickets"]<1 or claim["duplicate_threshold"]<1 or claim["base_weight"]<1:
        raise ValueError("invalid_claim_config")
    for pool in (claim["daily_pool"],claim["silver_pool"]):
        if any(not isinstance(key,str) or not key for key in pool) or len(pool)!=len(set(pool)): raise ValueError("invalid_claim_pool")
    if any(not isinstance(key,str) or type(weight) not in (int,float) or weight<=0 for key,weight in claim["weights"].items()): raise ValueError("invalid_claim_weight")
    try:
        if not math.isfinite(sum(float(weight) for weight in [claim['base_weight'], *claim['weights'].values()])):
            raise ValueError('invalid_claim_weight')
    except OverflowError:
        raise ValueError('invalid_claim_weight') from None
    for rule in value["upgrade"].values():
        if rule["copies"]<1: raise ValueError("invalid_recipe")
    for rule in value["shop"].values():
        if rule["factor"]<1 or rule["window"] not in ("none","daily","weekly") or (rule["stock"] is not None and (type(rule["stock"]) is not int or rule["stock"]<0)):
            raise ValueError("invalid_shop_rule")
    if value["hearts"]["reserve_future_level_bonus"] not in (None,True,False): raise ValueError("invalid_heart_migration")
    if value["migration"]["legacy_user_policy"] not in (None,"preserve_freeze_rewards"): raise ValueError("unsupported_user_migration")
    if value["wheel"]["enabled"]: raise ValueError("wheel_requires_product_approval")
    return copy.deepcopy(value)


def ensure_progression_schema(conn):
    statements = [
        "CREATE TABLE IF NOT EXISTS economy_config_versions(version INTEGER PRIMARY KEY AUTOINCREMENT,config_json TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS economy_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS match_economy_snapshots(match_key TEXT PRIMARY KEY,config_version INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS reward_ledger(operation_id TEXT NOT NULL,user_id INTEGER NOT NULL,source TEXT NOT NULL,event_type TEXT NOT NULL,xp INTEGER NOT NULL DEFAULT 0,score INTEGER NOT NULL DEFAULT 0,coins INTEGER NOT NULL DEFAULT 0,hearts INTEGER NOT NULL DEFAULT 0,inventory_json TEXT NOT NULL DEFAULT '{}',payload_json TEXT NOT NULL,receipt_json TEXT NOT NULL,config_version INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(operation_id,user_id))",
        "CREATE INDEX IF NOT EXISTS reward_score_time ON reward_ledger(created_at,user_id) WHERE score>0",
        "CREATE TABLE IF NOT EXISTS progression_capacities(user_id INTEGER PRIMARY KEY,base_hearts INTEGER NOT NULL,base_slots INTEGER NOT NULL,level_hearts INTEGER NOT NULL DEFAULT 0,level_slots INTEGER NOT NULL DEFAULT 0,purchased_hearts INTEGER NOT NULL DEFAULT 0,purchased_slots INTEGER NOT NULL DEFAULT 0,legacy INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS level_component_awards(user_id INTEGER NOT NULL,level INTEGER NOT NULL,receipt_json TEXT NOT NULL,PRIMARY KEY(user_id,level))",
        "CREATE TABLE IF NOT EXISTS player_economy_items(user_id INTEGER NOT NULL,item TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>=0),PRIMARY KEY(user_id,item))",
        "CREATE TABLE IF NOT EXISTS claim_receipts(user_id INTEGER NOT NULL,claim_type TEXT NOT NULL,card_id TEXT NOT NULL,received INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,claim_type,card_id))",
        "CREATE TABLE IF NOT EXISTS shop_quotes(quote_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,item TEXT NOT NULL,price INTEGER NOT NULL,config_version INTEGER NOT NULL,counter INTEGER NOT NULL,window_key TEXT NOT NULL,expires_at TEXT NOT NULL,used INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS economy_character_rules(card_id TEXT PRIMARY KEY,legend_recipe_tier TEXT NOT NULL CHECK(legend_recipe_tier IN ('A','B')))",
        "CREATE TABLE IF NOT EXISTS rare_card_instances(card_id TEXT NOT NULL,serial INTEGER NOT NULL,user_id INTEGER NOT NULL,operation_id TEXT NOT NULL UNIQUE,source TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(card_id,serial))",
        "CREATE TABLE IF NOT EXISTS economy_missions(mission_id TEXT PRIMARY KEY,definition_json TEXT NOT NULL,version INTEGER NOT NULL,actor TEXT NOT NULL,updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS economy_mission_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,mission_id TEXT NOT NULL,definition_json TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS economy_admin_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,details_json TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS leaderboard_settlements(period_type TEXT NOT NULL,period_key TEXT NOT NULL,receipt_json TEXT NOT NULL,config_version INTEGER NOT NULL,PRIMARY KEY(period_type,period_key))",
        "CREATE TABLE IF NOT EXISTS player_ability_inventory(user_id INTEGER NOT NULL,ability_key TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,ability_key))",
    ]
    for statement in statements: conn.execute(statement)
    if not conn.execute("SELECT 1 FROM economy_config_versions").fetchone():
        cursor=conn.execute("INSERT INTO economy_config_versions(config_json,actor,created_at) VALUES(?,?,?)",
            (json.dumps(seed_config(),sort_keys=True),"seed",datetime.now(timezone.utc).isoformat()))
        conn.execute("INSERT OR IGNORE INTO economy_state VALUES('config_version',?)",(str(cursor.lastrowid),))
        conn.execute("INSERT OR IGNORE INTO economy_state VALUES('schema_created_at',?)",(datetime.now(timezone.utc).isoformat(),))


def enabled_in(conn):
    row=conn.execute("SELECT value_json FROM foundation_settings WHERE key='progression_v2_enabled'").fetchone()
    return bool(row and json.loads(row[0]) is True)


def enabled(db):
    if not getattr(db,"db_path",None): return False
    with closing(sqlite3.connect(db.db_path)) as conn: return enabled_in(conn)


def config_in(conn,version=None):
    if version is None:
        version=int(conn.execute("SELECT value FROM economy_state WHERE key='config_version'").fetchone()[0])
    row=conn.execute("SELECT config_json FROM economy_config_versions WHERE version=?",(version,)).fetchone()
    if not row: raise ValueError("config_version_missing")
    return int(version),json.loads(row[0])


def save_config_in(conn,value,actor):
    validate_config(value)
    if enabled_in(conn):
        _, current = config_in(conn)
        if any(current[key] != value[key] for key in ('timezone', 'week_start')):
            raise ValueError('calendar_change_requires_reviewed_migration')
    if not isinstance(actor,str) or not actor.strip(): raise ValueError("admin_actor_required")
    cursor=conn.execute("INSERT INTO economy_config_versions(config_json,actor,created_at) VALUES(?,?,?)",
        (json.dumps(value,sort_keys=True),actor,datetime.now(timezone.utc).isoformat()))
    conn.execute("UPDATE economy_state SET value=? WHERE key='config_version'",(str(cursor.lastrowid),))
    return cursor.lastrowid


def period_bounds(config,period,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None: now=now.replace(tzinfo=timezone.utc)
    local=now.astimezone(ZoneInfo(config["timezone"]))
    start=local.replace(hour=0,minute=0,second=0,microsecond=0)
    if period=="daily": end=start+timedelta(days=1)
    elif period=="weekly":
        start-=timedelta(days=(local.weekday()-config["week_start"])%7); end=start+timedelta(days=7)
    elif period=="monthly":
        start=start.replace(day=1)
        end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    elif period=="all": return None,None,"all"
    else: raise ValueError("invalid_period")
    return start.astimezone(timezone.utc),end.astimezone(timezone.utc),start.date().isoformat()
