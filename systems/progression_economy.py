"""Shared v2 Claim, upgrade, sell, shop and heart operations for Bot and Mini App."""
from __future__ import annotations
import json
import random
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from systems.progression_config import enabled_in, config_in, period_bounds
from systems.reward_ledger import apply_in, receipt_in, items_in, capacities_in
from systems.card_inventory_system import CardInventorySystem as Inventory


class ProgressionEconomy:
    def __init__(self,db): self.db=db

    @staticmethod
    def operation_key(kind,request_key):
        if not isinstance(request_key,str) or not request_key.strip() or len(request_key)>128:
            raise ValueError('invalid_request_key')
        return kind+':'+request_key

    def run(self,action):
        with closing(sqlite3.connect(self.db.db_path,timeout=30)) as conn:
            try:
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    if not enabled_in(conn): raise ValueError('progression_v2_disabled')
                    version,config=config_in(conn)
                    return action(conn,version,config)
            except ValueError as error:
                code = str(error)
                messages = {
                    'empty_pool':'کارت آماده‌ای در فهرست دریافت نیست؛ نوبت یا Ticket مصرف نشد.',
                    'already_claimed':'پاداش امروز دریافت شده است؛ بعد از نیمه‌شب دوباره بیا.',
                    'legend_recipe_unset':'روش ارتقای Legend این شخصیت هنوز توسط ادمین مشخص نشده است.',
                    'variant_unavailable':'فرم مقصد این کارت هنوز آماده نیست.',
                    'insufficient_copies':'تعداد نسخه‌های کارت کافی نیست.',
                    'insufficient_upgrade_card':'کارت ارتقا کافی نیست؛ آن را از فروشگاه بگیر.',
                    'insufficient_silver_ticket':'Silver Ticket کافی نیست.',
                    'insufficient_coins_or_player_missing':'سکه کافی نیست یا حساب پیدا نشد.',
                    'price_changed':'قیمت یا شرایط تغییر کرده؛ دوباره پیش‌نمایش بگیر.',
                    'quote_expired':'پیش‌نمایش منقضی شده؛ دوباره قیمت را بگیر.',
                    'quote_not_found':'پیش‌نمایش خرید پیدا نشد؛ دوباره قیمت را بگیر.',
                    'hearts_full':'قلب‌ها پر هستند؛ هزینه‌ای پرداخت نشد.',
                    'heart_cap':'ظرفیت قلب با احتساب جوایز آینده به سقف رسیده است.',
                    'stock_empty':'موجودی این کالا تمام شده است.',
                    'active_match':'تا پایان مسابقه نمی‌توانی کارت را تغییر بدهی.',
                    'card_ineligible':'این کارت برای این عملیات مجاز نیست.',
                    'rarity_not_sellable':'این فرم کارت قابل فروش نیست.',
                    'progression_v2_disabled':'اقتصاد جدید هنوز فعال نیست.',
                    'already_owned':'این پوسته را قبلاً گرفته‌ای.',
                    'item_unavailable':'این کالا فعلاً در دسترس نیست.',
                    'mission_incomplete_or_ineligible':'شرایط مأموریت هنوز تکمیل نشده است.',
                }
                return {'ok':False,'error_code':code,'error':messages.get(code,'عملیات انجام نشد؛ شرایط را دوباره بررسی کن.')}

    @staticmethod
    def active_guard(conn,user):
        from systems.card_upgrade_system import CardUpgradeSystem
        if CardUpgradeSystem._active_match(conn,user): raise ValueError('active_match')
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='game_match_states'").fetchone():
            for encoded, in conn.execute('SELECT state_json FROM game_match_states'):
                state=json.loads(encoded)
                if user in state.get('players',[]) and state.get('phase') not in ('completed','finished','cancelled','expired'):
                    raise ValueError('active_match')

    @staticmethod
    def official(conn,card):
        if not conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='official'",(card,)).fetchone(): raise ValueError('card_ineligible')

    @staticmethod
    def recipe(conn,config,card,target):
        if target=='epic': return 'normal',config['upgrade']['epic']
        if target!='legend': raise ValueError('invalid_target')
        tier=conn.execute('SELECT legend_recipe_tier FROM economy_character_rules WHERE card_id=?',(card,)).fetchone()
        if not tier: raise ValueError('legend_recipe_unset')
        return 'epic',config['upgrade']['legend_'+tier[0]]

    def inventory(self,user):
        def action(conn,version,config):
            return {'ok':True,'config_version':version,'items':dict(conn.execute('SELECT item,quantity FROM player_economy_items WHERE user_id=?',(user,))),
                    'capacity':capacities_in(conn,user,config),
                    'shop':{key:rule for key,rule in config['shop'].items() if rule['enabled']},
                    'daily_ticket_percent':config['claim']['daily_ticket_percent'], 'silver_claim_tickets':config['claim']['silver_tickets']}
        return self.run(action)

    @staticmethod
    def claim_status_in(conn,user,config,now=None):
        start,end,key=period_bounds(config,'daily',now)
        row=conn.execute('SELECT last_claim FROM players WHERE user_id=?',(user,)).fetchone()
        if not row: raise ValueError('player_not_found')
        claimed=None
        if row[0]:
            claimed=datetime.fromisoformat(row[0]); claimed=claimed.replace(tzinfo=timezone.utc) if claimed.tzinfo is None else claimed
        return {'can_claim':not(claimed and start<=claimed<end),'remaining_seconds':max(0,int((end-(now or datetime.now(timezone.utc))).total_seconds())),'day':key}

    def claim_status(self,user):
        return self.run(lambda conn,version,config:{**self.claim_status_in(conn,user,config),'pool_count':len(self.pool(conn,config,'daily')),'pool_exhausted':not self.pool(conn,config,'daily')})

    @staticmethod
    def pool(conn,config,kind):
        rarity='normal' if kind=='daily' else 'epic'
        rows=conn.execute("""SELECT c.card_id FROM cards c WHERE c.origin='official' AND
            (c.rarity=? OR EXISTS(SELECT 1 FROM card_variants v WHERE v.card_id=c.card_id AND v.rarity=?)) ORDER BY c.card_id""",(rarity,rarity)).fetchall()
        configured=config['claim'][kind+'_pool']
        return [row[0] for row in rows if not configured or row[0] in configured]

    @staticmethod
    def select_claim(conn,user,config,kind):
        pool=ProgressionEconomy.pool(conn,config,kind)
        if not pool: raise ValueError('empty_pool')
        counts=dict(conn.execute('SELECT card_id,received FROM claim_receipts WHERE user_id=? AND claim_type=?',(user,kind)))
        rule=config['claim']
        weights=[rule['weights'].get(card,rule['base_weight'])*(rule['duplicate_factor'] if counts.get(card,0)>=rule['duplicate_threshold'] else 1) for card in pool]
        return random.choices(pool,weights=weights,k=1)[0]

    def claim(self,user,kind='daily',request_key=None):
        if kind not in ('daily','silver'): return {'ok':False,'error_code':'invalid_claim','error':'invalid_claim'}
        try:
            operation=self.operation_key('claim:'+kind,request_key or uuid.uuid4().hex)
        except ValueError:
            return {'ok':False,'error_code':'invalid_request_key','error':'شناسهٔ درخواست نامعتبر است.'}
        def action(conn,version,config):
            payload={'kind':kind}
            prior=receipt_in(conn,operation,user,payload)
            if prior: return prior
            now=datetime.now(timezone.utc)
            spent_items={}
            if kind=='daily':
                status=self.claim_status_in(conn,user,config,now)
                if not status['can_claim']: raise ValueError('already_claimed')
                operation_id='daily:'+status['day']
                if receipt_in(conn,operation_id,user): raise ValueError('already_claimed')
                # Validate Normal pool even when Ticket wins: unavailable daily contents never burn a claim.
                if not self.pool(conn,config,'daily'): raise ValueError('empty_pool')
                ticket=random.random()*100<config['claim']['daily_ticket_percent']
            else:
                operation_id=operation; ticket=False
                if items_in(conn,user,'free_silver_claim')>0:
                    items_in(conn,user,'free_silver_claim',-1);spent_items['free_silver_claim']=-1
                else:
                    items_in(conn,user,'silver_ticket',-config['claim']['silver_tickets']);spent_items['silver_ticket']=-config['claim']['silver_tickets']
            card=None; quantity=None
            inventory=dict(spent_items)
            if ticket:
                quantity=items_in(conn,user,'silver_ticket',1); inventory['silver_ticket']=1
            else:
                card=self.select_claim(conn,user,config,kind)
                rarity='normal' if kind=='daily' else 'epic'
                quantity=Inventory.grant_in(conn,user,card,rarity)
                conn.execute("INSERT INTO claim_receipts VALUES(?,?,?,1) ON CONFLICT(user_id,claim_type,card_id) DO UPDATE SET received=received+1",(user,kind,card))
                inventory[card+':'+rarity]=1
            ability=None
            if kind=='daily':
                from systems.game_mode_system import ABILITY_DEFINITIONS
                ability_key=random.choice(tuple(ABILITY_DEFINITIONS))
                conn.execute("INSERT INTO player_ability_inventory VALUES(?,?,1) ON CONFLICT(user_id,ability_key) DO UPDATE SET quantity=quantity+1",(user,ability_key))
                ability={'key':ability_key,'title':ABILITY_DEFINITIONS[ability_key]['title']}
                inventory['ability:'+ability_key]=1
                conn.execute('UPDATE players SET last_claim=? WHERE user_id=?',(now.isoformat(),user))
            extra={'card_id':card,'rarity':None if ticket else 'normal' if kind=='daily' else 'epic','reward_type':'silver_ticket' if ticket else 'card','quantity':quantity,'ability':ability}
            result=apply_in(conn,operation_id,user,'claim',kind+'_claim',version,payload=payload,inventory=inventory,extra=extra)
            if operation!=operation_id:
                from systems.reward_ledger import record_in
                record_in(conn,operation,user,'retry','claim_receipt',payload,result,version)
            return result
        return self.run(action)

    def preview_upgrade(self,user,card,target):
        def action(conn,version,config):
            self.official(conn,card)
            source,rule=self.recipe(conn,config,card,target)
            if not conn.execute('SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?',(card,target)).fetchone(): raise ValueError('variant_unavailable')
            count=Inventory.counts_in(conn,user,card).get(source,0)
            return {'ok':count>=rule['copies'] and items_in(conn,user,'upgrade_card')>=rule['items'],'card_id':card,'from_rarity':source,'to_rarity':target,'owned':count,'required':rule['copies'],'upgrade_cards_required':rule['items'],'xp':rule['xp'],'config_version':version,'error':None if count>=rule['copies'] else 'نسخهٔ کافی نیست'}
        return self.run(action)

    def upgrade(self,user,card,target,request_key,expected_version=None):
        try:request_key=self.operation_key('upgrade',request_key)
        except ValueError:return {'ok':False,'error_code':'invalid_request_key','error':'شناسهٔ درخواست نامعتبر است.'}
        def action(conn,version,config):
            payload={'card_id':card,'target':target}
            prior=receipt_in(conn,request_key,user,payload)
            if prior:return prior
            if expected_version is not None and expected_version!=version:raise ValueError('price_changed')
            self.active_guard(conn,user);self.official(conn,card)
            source,rule=self.recipe(conn,config,card,target)
            if not conn.execute('SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?',(card,target)).fetchone():raise ValueError('variant_unavailable')
            if not Inventory.consume_in(conn,user,card,source,rule['copies']):raise ValueError('insufficient_copies')
            items_in(conn,user,'upgrade_card',-rule['items'])
            Inventory.grant_in(conn,user,card,target)
            Inventory.reconcile_active_in(conn,user,card)
            return apply_in(conn,request_key,user,'upgrade','official_upgrade',version,payload=payload,xp=rule['xp'],inventory={card+':'+source:-rule['copies'],card+':'+target:1,'upgrade_card':-rule['items']},extra={'card_id':card,'target':target,'xp_gained':rule['xp']})
        if not request_key:return {'ok':False,'error_code':'request_key_required','error':'request_key_required'}
        return self.run(action)

    def sell(self,user,card,rarity,request_key,expected_version=None):
        try:request_key=self.operation_key('sell',request_key)
        except ValueError:return {'ok':False,'error_code':'invalid_request_key','error':'شناسهٔ درخواست نامعتبر است.'}
        def action(conn,version,config):
            payload={'card_id':card,'rarity':rarity}
            prior=receipt_in(conn,request_key,user,payload)
            if prior:return prior
            if expected_version is not None and expected_version!=version:raise ValueError('price_changed')
            self.active_guard(conn,user);self.official(conn,card)
            key=rarity
            if rarity=='legend':
                tier=conn.execute('SELECT legend_recipe_tier FROM economy_character_rules WHERE card_id=?',(card,)).fetchone()
                if not tier:raise ValueError('legend_recipe_unset')
                key+='_'+tier[0]
            if key not in config['sell']:raise ValueError('rarity_not_sellable')
            if not Inventory.consume_in(conn,user,card,rarity):raise ValueError('insufficient_copies')
            Inventory.reconcile_active_in(conn,user,card)
            return apply_in(conn,request_key,user,'sell','official_sell',version,payload=payload,coins=config['sell'][key],inventory={card+':'+rarity:-1},extra={'card_id':card,'rarity':rarity})
        if not request_key:return {'ok':False,'error_code':'request_key_required','error':'request_key_required'}
        return self.run(action)

    def sell_preview(self,user,card,rarity):
        def action(conn,version,config):
            self.official(conn,card)
            key=rarity
            if rarity=='legend':
                row=conn.execute('SELECT legend_recipe_tier FROM economy_character_rules WHERE card_id=?',(card,)).fetchone()
                if not row:raise ValueError('legend_recipe_unset')
                key+='_'+row[0]
            if key not in config['sell']:raise ValueError('rarity_not_sellable')
            if Inventory.counts_in(conn,user,card).get(rarity,0)<1:raise ValueError('insufficient_copies')
            return {'ok':True,'card_id':card,'rarity':rarity,'price':config['sell'][key],'config_version':version}
        return self.run(action)

    @staticmethod
    def counter(conn,user,item,window_key):
        return conn.execute("SELECT COUNT(*) FROM reward_ledger WHERE user_id=? AND source='shop' AND json_extract(payload_json,'$.item')=? AND json_extract(payload_json,'$.window_key')=?",(user,item,window_key)).fetchone()[0]

    @staticmethod
    def price_in(conn,user,item,config):
        if item.startswith('skin:'):
            row=conn.execute('SELECT price FROM skins WHERE skin_id=?',(item[5:],)).fetchone()
            if not row or type(row[0]) is not int or row[0]<0:raise ValueError('invalid_skin_price')
            return row[0],0,'lifetime'
        rule=config['shop'].get(item)
        if not rule or not rule['enabled']:raise ValueError('item_unavailable')
        window_key=period_bounds(config,rule['window'])[2] if rule['window']!='none' else 'lifetime'
        count=ProgressionEconomy.counter(conn,user,item,window_key)
        if count>60:raise ValueError('price_limit')
        price=rule['price']*rule['factor']**count
        if price>2**62:raise ValueError('price_limit')
        return price,count,window_key

    def quote(self,user,item):
        def action(conn,version,config):
            self.refresh_hearts_in(conn,user,config)
            price,count,window=self.price_in(conn,user,item,config)
            self.shop_eligible(conn,user,item,config)
            key=uuid.uuid4().hex
            conn.execute('INSERT INTO shop_quotes VALUES(?,?,?,?,?,?,?,?,0)',(key,user,item,price,version,count,window,(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()))
            return {'ok':True,'quote_id':key,'item':item,'price':price,'config_version':version}
        return self.run(action)

    @staticmethod
    def shop_eligible(conn,user,item,config):
        if item.startswith('skin:'):
            skin_id=item[5:]
            row=conn.execute('SELECT card_id,is_seasonal,season_end FROM skins WHERE skin_id=?',(skin_id,)).fetchone()
            if not row or not conn.execute('SELECT 1 FROM player_cards WHERE user_id=? AND card_id=?',(user,row[0])).fetchone():raise ValueError('skin_not_accessible')
            if conn.execute('SELECT 1 FROM player_skins WHERE user_id=? AND skin_id=?',(user,skin_id)).fetchone():raise ValueError('already_owned')
            if row[1] and row[2]:
                end=datetime.fromisoformat(row[2]);end=end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
                if end<datetime.now(timezone.utc):raise ValueError('skin_expired')
            return
        capacity=capacities_in(conn,user,config)
        current=conn.execute('SELECT hearts FROM players WHERE user_id=?',(user,)).fetchone()[0]
        if item=='refill' and current>=capacity['max_hearts']:raise ValueError('hearts_full')
        if item=='permanent_heart':
            reserve=config['hearts']['reserve_future_level_bonus']
            if reserve is None:raise ValueError('heart_policy_unset')
            pending=max(0,sum(rule['hearts'] for rule in config['level_rewards'].values())-capacity['level_hearts']) if reserve and not capacity['legacy'] else 0
            if capacity['max_hearts']+pending>=config['hearts']['cap']:raise ValueError('heart_cap')
        stock=config['shop'][item]['stock']
        if stock is not None:
            sold=conn.execute("SELECT COUNT(*) FROM reward_ledger WHERE source='shop' AND json_extract(payload_json,'$.item')=?",(item,)).fetchone()[0]
            if sold>=stock:raise ValueError('stock_empty')

    def purchase(self,user,quote_id):
        operation='shop:'+quote_id
        def action(conn,version,config):
            prior=receipt_in(conn,operation,user)
            if prior:return prior
            row=conn.execute('SELECT item,price,config_version,counter,window_key,expires_at,used FROM shop_quotes WHERE quote_id=? AND user_id=?',(quote_id,user)).fetchone()
            if not row:raise ValueError('quote_not_found')
            item,price,quoted_version,count,window,expiry,used=row
            if used or datetime.fromisoformat(expiry)<datetime.now(timezone.utc):raise ValueError('quote_expired')
            self.refresh_hearts_in(conn,user,config)
            if quoted_version!=version or (price,count,window)!=self.price_in(conn,user,item,config):raise ValueError('price_changed')
            self.shop_eligible(conn,user,item,config)
            inventory={item:1};heart_delta=0
            if item in ('upgrade_card','silver_ticket'):items_in(conn,user,item,1)
            elif item=='deck_slot':conn.execute('UPDATE progression_capacities SET purchased_slots=purchased_slots+1 WHERE user_id=?',(user,))
            elif item=='permanent_heart':
                conn.execute('UPDATE progression_capacities SET purchased_hearts=purchased_hearts+1 WHERE user_id=?',(user,));heart_delta=1
            elif item=='refill':
                capacity=capacities_in(conn,user,config)
                current=conn.execute('SELECT hearts FROM players WHERE user_id=?',(user,)).fetchone()[0]
                heart_delta=capacity['max_hearts']-current
            elif item.startswith('skin:'):
                conn.execute('INSERT INTO player_skins(user_id,skin_id,unlocked_at) VALUES(?,?,?)',(user,item[5:],datetime.now(timezone.utc).isoformat()))
            result=apply_in(conn,operation,user,'shop','shop_purchase',version,payload={'item':item,'window_key':window},coins=-price,hearts=heart_delta,inventory=inventory,extra={'item':item,'coins_spent':price})
            conn.execute('UPDATE shop_quotes SET used=1 WHERE quote_id=?',(quote_id,))
            return result
        return self.run(action)

    @staticmethod
    def refresh_hearts_in(conn,user,config,now=None):
        capacity=capacities_in(conn,user,config)
        start,end,key=period_bounds(config,'daily',now)
        row=conn.execute('SELECT last_heart_reset FROM players WHERE user_id=?',(user,)).fetchone()
        previous=datetime.fromisoformat(row[0]) if row and row[0] else None
        if previous and previous.tzinfo is None:previous=previous.replace(tzinfo=timezone.utc)
        if previous is None or previous<start:
            conn.execute('UPDATE players SET hearts=?,max_hearts=?,last_heart_reset=? WHERE user_id=?',(capacity['max_hearts'],capacity['max_hearts'],(now or datetime.now(timezone.utc)).isoformat(),user))
        return end

    def refresh_hearts(self,user):
        return self.run(lambda conn,version,config:{'ok':True,'next_reset':self.refresh_hearts_in(conn,user,config).isoformat()})
