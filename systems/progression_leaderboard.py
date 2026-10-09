"""Calendar leaderboards with atomic shared-rank weekly/monthly settlement."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from systems.progression_config import config_in, period_bounds, enabled_in
from systems.progression_match_rewards import shared_ranks
from systems.reward_ledger import apply_in


def leaderboard_in(conn,start=None,end=None):
    if start is None:
        rows=conn.execute("SELECT user_id,total_score FROM players WHERE total_score>0 ORDER BY total_score DESC,user_id").fetchall()
    else:
        # Legacy history is retained in the first v2 calendar window, not copied or reset.
        rows=conn.execute("SELECT user_id,SUM(score_gained) FROM fight_history WHERE score_gained>0 AND julianday(fought_at)>=julianday(?) AND julianday(fought_at)<julianday(?) GROUP BY user_id HAVING SUM(score_gained)>0 ORDER BY SUM(score_gained) DESC,user_id",(start.isoformat(),end.isoformat())).fetchall()
    ranks=shared_ranks(dict(rows));result=[]
    for user,score in rows:
        player=conn.execute('SELECT username,first_name,total_score FROM players WHERE user_id=?',(user,)).fetchone()
        count=conn.execute('SELECT COUNT(*) FROM player_cards WHERE user_id=?',(user,)).fetchone()[0]
        result.append({'user_id':user,'username':player[0],'first_name':player[1],'total_score':player[2],'period_score':score,'card_count':count,'rank':ranks[user]})
    return result


class ProgressionLeaderboard:
    def __init__(self,db):self.db=db
    def view(self,period='weekly',limit=10):
        with closing(sqlite3.connect(self.db.db_path)) as conn:
            _,config=config_in(conn);start,end,_=period_bounds(config,period)
            return [item for item in leaderboard_in(conn,start,end) if item['rank']<=limit]

    def settle(self,period,now=None):
        if period not in ('weekly','monthly'):raise ValueError('period_not_payable')
        now=now or datetime.now(timezone.utc)
        with closing(sqlite3.connect(self.db.db_path,timeout=30)) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            if not enabled_in(conn):raise ValueError('progression_v2_disabled')
            version,config=config_in(conn)
            current_start,_,_=period_bounds(config,period,now)
            start,end,key=period_bounds(config,period,current_start-timedelta(seconds=1))
            prior=conn.execute('SELECT receipt_json FROM leaderboard_settlements WHERE period_type=? AND period_key=?',(period,key)).fetchone()
            if prior:return []
            legacy=conn.execute("SELECT 1 FROM sqlite_master WHERE name='weekly_reward_batches'").fetchone()
            if period=='weekly' and legacy and conn.execute('SELECT 1 FROM weekly_reward_batches WHERE period_key=?',(key,)).fetchone():
                conn.execute('INSERT INTO leaderboard_settlements VALUES(?,?,?,?)',(period,key,'[]',version));return []
            rows=leaderboard_in(conn,start,end);awards=[]
            rule=config['leaderboard'][period]
            for item in rows:
                rank=item['rank'];user=item['user_id']
                if rank>len(rule['coins']):continue
                coins=rule['coins'][rank-1];xp=rule['xp'][rank-1]
                apply_in(conn,'leaderboard:'+period+':'+key,user,'leaderboard',period+'_award',version,payload={'period':period,'period_key':key,'rank':rank},xp=xp,coins=coins)
                awards.append((rank,user,coins))
            conn.execute('INSERT INTO leaderboard_settlements VALUES(?,?,?,?)',(period,key,json.dumps(awards),version))
            if period=='weekly':
                conn.execute('CREATE TABLE IF NOT EXISTS weekly_reward_batches(period_key TEXT PRIMARY KEY,awards_json TEXT NOT NULL,awarded_at TEXT NOT NULL)')
                conn.execute('INSERT INTO weekly_reward_batches VALUES(?,?,?)',(key,json.dumps(awards),now.isoformat()))
            return awards
