"""Whole-match v2 settlement; immutable config snapshot and legacy ledger identity."""
import json
from datetime import datetime, timezone
from systems.progression_config import config_in
from systems.reward_ledger import apply_in
from systems.shared_foundation import require_card_in


def shared_ranks(scores):
    """Competition ranking: 1, 1, 3. Every tied player receives the same award."""
    return {user:1+sum(other>score for other in scores.values()) for user,score in scores.items()}


def award_in(conn,key,mode,context,awards):
    snapshot=conn.execute("SELECT config_version FROM match_economy_snapshots WHERE match_key=?",(key,)).fetchone()
    if not snapshot: raise ValueError("future_policy_not_live")
    version,config=config_in(conn,snapshot[0])
    conn.execute("""CREATE TABLE IF NOT EXISTS match_reward_events(request_id TEXT NOT NULL,user_id INTEGER NOT NULL,mode TEXT NOT NULL,xp INTEGER NOT NULL,score INTEGER NOT NULL,hearts_lost INTEGER NOT NULL DEFAULT 0,tp_delta INTEGER NOT NULL DEFAULT 0,awarded_at TEXT NOT NULL,PRIMARY KEY(request_id,user_id))""")
    columns = {row[1] for row in conn.execute('PRAGMA table_info(match_reward_events)')}
    for column in ('hearts_lost', 'tp_delta'):
        if column not in columns:
            conn.execute('ALTER TABLE match_reward_events ADD COLUMN ' + column + ' INTEGER NOT NULL DEFAULT 0')
    easy_scores={}
    rounds=0
    if context.mode=="easy":
        state=json.loads(conn.execute("SELECT state_json FROM game_match_states WHERE request_id=?",(key,)).fetchone()[0])
        # Qualifies after at least one server-validated round. A missed round earns no points.
        participants={int(entry['user_id']) for round_item in state['round_history'] for entry in round_item['entries']}
        easy_scores={user:int(state['scores'].get(str(user),0)) for user in participants}
        # Final round is not persisted yet; creators pass the final validated report separately.
        rounds=int(state['rounds'])
        final=next(iter(awards.values()),{}).get('easy_final')
        if final:
            easy_scores={int(user):int(score) for user,score in final['scores'].items() if int(user) in final['participants']}
    ranks=shared_ranks(easy_scores)
    result={}
    now=datetime.now(timezone.utc)
    has_metadata=conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_mode_metadata' AND type='table'").fetchone()
    for user,item in awards.items():
        prior=conn.execute("SELECT xp,score,hearts_lost,tp_delta FROM match_reward_events WHERE request_id=? AND user_id=?",(key,user)).fetchone()
        if prior:
            result[str(user)]={"xp":prior[0],"score":prior[1],"hearts_lost":prior[2],"tp_delta":prior[3]}; continue
        outcome=item.get('result')
        if outcome not in ('win','loss','tie','draw'): raise ValueError('invalid_match_result')
        valid=item.get('valid',True) is True
        for card in (item.get('card_id'),item.get('opponent_card_id')):
            if card: require_card_in(conn,card,context,user if card==item.get("card_id") and context.mode!="risk" else item.get("opponent_id"),key)
        xp=score=hearts=0
        qualified=False
        if valid and context.mode not in ('practice',) and context.variant!='friendly':
            if context.mode=='easy':
                rule=config['easy']['rounds'].get(str(rounds))
                qualified=len(easy_scores)>=config['easy']['min_players'] and rule is not None
                rank=ranks.get(user,0)
                if qualified and rank:
                    xp=rule['xp'][rank-1] if rank<=len(rule['xp']) else 0
                    score=rule['score'] if rank==1 else 0
            else:
                canonical='quick' if context.mode=='legacy_pvp' else context.mode
                rule=config['match'][canonical]
                xp=rule['tie' if outcome=='draw' else outcome]
                score=rule['score'] if outcome=='win' else 0
                hearts=rule.get('loss_hearts',int(item.get('hearts_lost',0))) if outcome=='loss' else 0
                qualified=context.mode!='risk'
        elif valid and context.variant=='friendly': hearts=context.friendly_loss_hearts if outcome=='loss' else 0
        payload={'mode':context.mode,'result':outcome,'card_id':item.get('card_id'),'qualified':qualified,
                 'rank':ranks.get(user),'rounds':rounds,'variant':context.variant}
        metadata=conn.execute('SELECT traits FROM card_mode_metadata WHERE card_id=?',(item.get('card_id'),)).fetchone() if has_metadata else None
        # Record the traits used at settlement; later card edits cannot rewrite mission progress.
        payload['traits']=json.loads(metadata[0] or '[]') if metadata else []
        paid=apply_in(conn,'match:'+key,user,context.mode,'match',version,payload=payload,xp=xp,score=score,hearts=-hearts,extra={'ranked_progress':qualified})
        conn.execute("INSERT INTO match_reward_events(request_id,user_id,mode,xp,score,hearts_lost,tp_delta,awarded_at) VALUES(?,?,?,?,?,?,0,?)",(key,user,mode,xp,score,hearts,now.isoformat()))
        conn.execute("""INSERT INTO fight_history(user_id,user_card_id,opponent_card_id,stat_used,result,score_gained,hearts_lost,fought_at,fight_type,opponent_user_id,xp_gained) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (user,item.get('card_id'),item.get('opponent_card_id'),item.get('stat_used'),outcome,score,hearts,now.isoformat(),"quick_friendly" if context.variant=="friendly" else mode,item.get('opponent_id'),xp))
        result[str(user)]=paid
    return result
