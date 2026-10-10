"""Atomic limited official Rare issuance contract; no new event, wheel or auction UI."""
from datetime import datetime, timezone
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import apply_in, receipt_in
from systems.card_inventory_system import CardInventorySystem


def issue(db,user,card,source,request_key):
    if not request_key or source not in ('event','wheel','leaderboard'):
        return {'success':False,'error':'approved_source_and_request_key_required'}
    try:request_key=ProgressionEconomy.operation_key('rare',request_key)
    except ValueError:return {'success':False,'error':'invalid_request_key'}
    def action(conn,version,config):
        payload={'card_id':card,'source':source}
        prior=receipt_in(conn,request_key,user,payload)
        if prior:return prior
        ProgressionEconomy.official(conn,card)
        if not conn.execute("SELECT 1 FROM cards WHERE card_id=? AND rarity='rare'",(card,)).fetchone():raise ValueError('rare_required')
        if source=='wheel' and not config['wheel']['enabled']:raise ValueError('wheel_disabled')
        info=conn.execute('SELECT limited_quantity,total_issued FROM rare_cards_info WHERE card_id=?',(card,)).fetchone()
        if not info or info[1]>=info[0]:raise ValueError('rare_supply_empty')
        serial=info[1]+1
        if conn.execute('UPDATE rare_cards_info SET total_issued=total_issued+1 WHERE card_id=? AND total_issued<?',(card,info[0])).rowcount!=1:raise ValueError('rare_supply_empty')
        conn.execute('INSERT INTO rare_card_instances VALUES(?,?,?,?,?,?)',(card,serial,user,request_key,source,datetime.now(timezone.utc).isoformat()))
        CardInventorySystem.grant_in(conn,user,card,'rare')
        return apply_in(conn,request_key,user,'rare','rare_issue',version,payload=payload,inventory={card+':rare':1},extra={'serial':serial,'card_id':card})
    result=ProgressionEconomy(db).run(action)
    return {**result,'success':result['ok']}
