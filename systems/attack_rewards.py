"""Attack escrow and card issuance, inside the encounter's write transaction."""
from systems.attack_catalog import records,read,write,remove
from systems.card_inventory_system import CardInventorySystem
from systems.reward_ledger import apply_in,record_in,receipt_in


def rare_available_in(conn,card,exclude=None):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='rare_cards_info'").fetchone():return 0
    row=conn.execute('SELECT limited_quantity,total_issued FROM rare_cards_info WHERE card_id=?',(card,)).fetchone()
    if not row:return 0
    reserved=sum(value.get(card,0) for key,value in records(conn,'reserve:') if key!='reserve:'+str(exclude))
    return max(0,row[0]-row[1]-reserved)


def reserve_in(conn,event):
    attack=event['attack'];needed={}
    rewards=[attack['win']]
    if event['kill_possible']:rewards.append(attack['death_reward'])
    for reward in rewards:
        for item in reward['cards']:
            if item['rarity']=='rare':needed[item['card_id']]=needed.get(item['card_id'],0)+item['quantity']*len(event['slots'])
    for card,quantity in needed.items():
        if rare_available_in(conn,card)<quantity:raise ValueError('rare_supply_empty')
    if needed:write(conn,'reserve:'+event['id'],needed)


def escrow_in(conn,event,user):
    loss=event['attack']['loss'];operation='attack-stake:'+event['id']
    if conn.execute('UPDATE players SET coins=coins-?,hearts=hearts-? WHERE user_id=? AND coins>=? AND hearts>=?',
                    (loss['coins'],loss['hearts'],user,loss['coins'],loss['hearts'])).rowcount!=1:
        raise ValueError('attack_stake_shortage')
    record_in(conn,operation,user,'attack_escrow','attack_entry',{},loss,event['config_version'],
              coins=-loss['coins'],hearts=-loss['hearts'])


def grant_cards_in(conn,event,user,cards,operation):
    granted=[]
    for index,item in enumerate(cards):
        serials=[]
        if item['rarity']=='rare':
            if rare_available_in(conn,item['card_id'],event['id'])<item['quantity']:raise ValueError('rare_supply_empty')
            for unit in range(item['quantity']):
                from systems.rare_delivery import issue_in
                serial=issue_in(conn,user,item['card_id'],operation+':'+str(index)+':'+str(unit),'event',encounter=event['id'])
                serials.append(serial)
        else:
            CardInventorySystem.grant_in(conn,user,item['card_id'],item['rarity'],item['quantity'])
        name=conn.execute('SELECT name FROM cards WHERE card_id=?',(item['card_id'],)).fetchone()[0]
        granted.append({**item,'name':name,'serials':serials})
    return granted


def settle_user_in(conn,event,user,outcome,killed=False):
    operation='attack-result:'+event['id']
    prior=receipt_in(conn,operation,user)
    if prior:return prior
    loss=event['attack']['loss']
    refund=outcome!='loss'
    # Restore escrow directly, without counting it as income or XP.
    if refund:
        before=conn.execute('SELECT hearts,max_hearts FROM players WHERE user_id=?',(user,)).fetchone()
        returned_hearts=max(0,min(loss['hearts'],before[1]-before[0]))
        conn.execute('UPDATE players SET coins=coins+?,hearts=hearts+? WHERE user_id=?',(loss['coins'],returned_hearts,user))
        record_in(conn,'attack-refund:'+event['id'],user,'attack_escrow','attack_refund',{},
                  {'coins':loss['coins'],'hearts':returned_hearts},event['config_version'],coins=loss['coins'],hearts=returned_hearts)
    rewards=[event['attack']['win']] if outcome=='win' else []
    if killed:rewards.append(event['attack']['death_reward'])
    coins=sum(r['coins'] for r in rewards);xp=sum(r['xp'] for r in rewards)
    cards=grant_cards_in(conn,event,user,[card for reward in rewards for card in reward['cards']],operation+':'+str(user))
    inventory={}
    ability=event['slots'][event['participants'][str(user)]].get('ability')
    if outcome=='void' and ability and ability!='skip':
        conn.execute('INSERT INTO player_ability_inventory VALUES(?,?,1) ON CONFLICT(user_id,ability_key) DO UPDATE SET quantity=quantity+1',(user,ability))
        inventory['ability:'+ability]=1
    for card in cards:
        key=card['card_id']+':'+card['rarity'];inventory[key]=inventory.get(key,0)+card['quantity']
    return apply_in(conn,operation,user,'group_attack','attack_result',event['config_version'],
                    payload={'event_id':event['id'],'outcome':outcome,'killed':killed},
                    coins=coins,xp=xp,inventory=inventory,
                    extra={'attack_coins':coins if refund else -loss['coins'],
                           'attack_hearts_lost':0 if refund else loss['hearts'],
                           'escrow_refunded':refund,'ability_refunded':ability if outcome=='void' and ability!='skip' else None,'cards':cards})
