"""Atomic limited official Rare issuance contract; no new event, wheel or auction UI."""
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import apply_in, receipt_in


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
        from systems.rare_delivery import issue_in
        serial=issue_in(conn,user,card,request_key,source)
        return apply_in(conn,request_key,user,'rare','rare_issue',version,payload=payload,inventory={card+':rare':1},extra={'serial':serial,'card_id':card})
    result=ProgressionEconomy(db).run(action)
    return {**result,'success':result['ok']}
