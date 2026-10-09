"""Atomic Phase 2 rewards. Callers own BEGIN IMMEDIATE and the commit."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from systems.progression_config import config_in


def receipt_in(conn,operation,user,payload=None):
    row=conn.execute("SELECT payload_json,receipt_json FROM reward_ledger WHERE operation_id=? AND user_id=?",(operation,user)).fetchone()
    if not row: return None
    if payload is not None and json.loads(row[0])!=payload: raise ValueError("idempotency_conflict")
    return {**json.loads(row[1]),"replayed":True}


def items_in(conn,user,item,delta=0):
    conn.execute("INSERT OR IGNORE INTO player_economy_items VALUES(?,?,0)",(user,item))
    row=conn.execute("SELECT quantity FROM player_economy_items WHERE user_id=? AND item=?",(user,item)).fetchone()
    amount=int(row[0])+delta
    if amount<0: raise ValueError("insufficient_"+item)
    if delta: conn.execute("UPDATE player_economy_items SET quantity=? WHERE user_id=? AND item=?",(amount,user,item))
    return amount


def capacities_in(conn,user,config):
    row=conn.execute("SELECT * FROM progression_capacities WHERE user_id=?",(user,)).fetchone()
    if row is None:
        player=conn.execute("SELECT max_hearts FROM players WHERE user_id=?",(user,)).fetchone()
        if not player: raise ValueError("player_not_found")
        # Existing accounts never silently lose capacity or receive retrospective prizes.
        decks=conn.execute("SELECT COUNT(*) FROM player_decks WHERE player_id=?",(user,)).fetchone()[0]
        conn.execute("INSERT INTO progression_capacities(user_id,base_hearts,base_slots,legacy) VALUES(?,?,?,1)",
                     (user,int(player[0] or config["hearts"]["base"]),max(50,decks)))
        row=conn.execute("SELECT * FROM progression_capacities WHERE user_id=?",(user,)).fetchone()
    values=dict(zip(("user_id","base_hearts","base_slots","level_hearts","level_slots","purchased_hearts","purchased_slots","legacy"),row))
    values["max_hearts"]=min(config["hearts"]["cap"],values["base_hearts"]+values["level_hearts"]+values["purchased_hearts"])
    values["slots"]=values["base_slots"]+values["level_slots"]+values["purchased_slots"]
    return values


def new_account_in(conn,user,config):
    conn.execute("INSERT OR IGNORE INTO progression_capacities(user_id,base_hearts,base_slots) VALUES(?,?,?)",
                 (user,config["hearts"]["base"],config["slots"]["base"]))
    conn.execute("UPDATE players SET hearts=?,max_hearts=? WHERE user_id=?",(config["hearts"]["base"],config["hearts"]["base"],user))


def level_from_xp(config,xp):
    return max(index+1 for index,threshold in enumerate(config["level_thresholds"]) if xp>=threshold)


def record_in(conn,operation,user,source,event_type,payload,receipt,version,*,xp=0,score=0,coins=0,hearts=0,inventory=None,now=None):
    conn.execute("""INSERT INTO reward_ledger(operation_id,user_id,source,event_type,xp,score,coins,hearts,inventory_json,payload_json,receipt_json,config_version,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(operation,user,source,event_type,xp,score,coins,hearts,
        json.dumps(inventory or {},sort_keys=True),json.dumps(payload,sort_keys=True),json.dumps(receipt,sort_keys=True),version,
        (now or datetime.now(timezone.utc)).isoformat()))


def apply_in(conn,operation,user,source,event_type,version,*,payload=None,xp=0,score=0,coins=0,hearts=0,inventory=None,extra=None,now=None):
    payload=payload or {}
    prior=receipt_in(conn,operation,user,payload)
    if prior: return prior
    if any(type(v) is not int for v in (xp,score,coins,hearts)) or xp<0 or score<0: raise ValueError("invalid_reward")
    _,config=config_in(conn,version)
    if conn.execute("UPDATE players SET coins=coins+?,total_score=total_score+?,hearts=MAX(0,hearts+?) WHERE user_id=? AND coins+?>=0",(coins,score,hearts,user,coins)).rowcount!=1:
        raise ValueError("insufficient_coins_or_player_missing")
    conn.execute("INSERT OR IGNORE INTO player_progression(user_id) VALUES(?)",(user,))
    old_level,total_xp=conn.execute("SELECT level,total_xp FROM player_progression WHERE user_id=?",(user,)).fetchone()
    total_xp=int(total_xp or 0)+xp
    new_level=level_from_xp(config,total_xp)
    # Config edits may recompute displayed level, but awards have their own immutable ledger.
    conn.execute("UPDATE player_progression SET total_xp=?,level=?,last_played_at=? WHERE user_id=?",(total_xp,new_level,(now or datetime.now(timezone.utc)).isoformat(),user))
    capacity=capacities_in(conn,user,config)
    level_coins=0
    if not capacity["legacy"]:
        for level in range(int(old_level)+1,new_level+1):
            rule=config["level_rewards"].get(str(level),{})
            if conn.execute("INSERT OR IGNORE INTO level_component_awards VALUES(?,?,?)",(user,level,json.dumps(rule))).rowcount:
                amount=rule.get("coins",0)
                if conn.execute("INSERT OR IGNORE INTO player_level_coin_awards(user_id,level,coins,awarded_at) VALUES(?,?,?,?)",(user,level,amount,(now or datetime.now(timezone.utc)).isoformat())).rowcount:
                    conn.execute("UPDATE players SET coins=coins+? WHERE user_id=?",(amount,user)); level_coins+=amount
                else:
                    amount=0
                conn.execute("UPDATE progression_capacities SET level_slots=level_slots+?,level_hearts=level_hearts+? WHERE user_id=?",(rule.get("slots",0),rule.get("hearts",0),user))
                items_in(conn,user,"free_silver_claim",rule.get("silver_claims",0))
                record_in(conn,"level:"+str(level),user,"level","level_up",{},rule,version,coins=amount,inventory={"deck_slots":rule.get("slots",0),"free_silver_claim":rule.get("silver_claims",0),"max_hearts":rule.get("hearts",0)},now=now)
    capacity=capacities_in(conn,user,config)
    conn.execute("UPDATE players SET max_hearts=? WHERE user_id=?",(capacity["max_hearts"],user))
    result={"ok":True,"xp":xp,"score":score,"coins":coins,"hearts_lost":max(0,-hearts),"tp_delta":0,
            "old_level":int(old_level),"new_level":new_level,"level_coins":level_coins,**(extra or {})}
    record_in(conn,operation,user,source,event_type,payload,result,version,xp=xp,score=score,coins=coins,hearts=hearts,inventory=inventory,now=now)
    return result
