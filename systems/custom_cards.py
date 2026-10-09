"""Manual admin fulfillment and private entitlements, separate from game currency."""
from __future__ import annotations
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from core.models import Card


def now():
    return datetime.now(timezone.utc).isoformat()


def ensure_custom_schema(conn):
    statements=[
        "CREATE TABLE IF NOT EXISTS custom_orders(order_id TEXT PRIMARY KEY,buyer_id INTEGER NOT NULL,rarity TEXT NOT NULL,recipients_json TEXT NOT NULL,amount TEXT NOT NULL,currency TEXT NOT NULL,notes TEXT NOT NULL,payment_status TEXT NOT NULL DEFAULT 'payment_pending',card_id TEXT,actor TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS custom_definitions(card_id TEXT PRIMARY KEY,order_id TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',media_id TEXT,actor TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS custom_grants(card_id TEXT NOT NULL,user_id INTEGER NOT NULL,active INTEGER NOT NULL,order_id TEXT NOT NULL,actor TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(card_id,user_id))",
        "CREATE TABLE IF NOT EXISTS custom_operations(actor TEXT NOT NULL,operation_id TEXT NOT NULL,payload_json TEXT NOT NULL,receipt_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(actor,operation_id))",
        "CREATE TABLE IF NOT EXISTS custom_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS custom_media(media_id TEXT PRIMARY KEY,filename TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS custom_match_cards(match_key TEXT NOT NULL,user_id INTEGER NOT NULL,card_id TEXT NOT NULL,snapshot_json TEXT NOT NULL,PRIMARY KEY(match_key,user_id,card_id))",
    ]
    for statement in statements:conn.execute(statement)
    conn.execute("INSERT OR IGNORE INTO foundation_settings VALUES('custom_card_orders_enabled','false')")
    conn.execute("INSERT OR IGNORE INTO foundation_settings VALUES('custom_admin_contact','null')")


def access_in(conn,user,card):
    return bool(conn.execute("SELECT 1 FROM custom_grants g JOIN custom_definitions d USING(card_id) JOIN foundation_settings f ON f.key='custom_cards_enabled' WHERE g.card_id=? AND g.user_id=? AND g.active=1 AND d.status='active' AND f.value_json='true'",(card,user)).fetchone())


def display_card_in(conn,card):
    row=conn.execute('SELECT payload_json FROM custom_definitions WHERE card_id=?',(card.card_id,)).fetchone()
    if row:card.name=json.loads(row[0])['name']
    return card


def user_cards(db,user):
    with closing(sqlite3.connect(db.db_path)) as conn:
        ids=[row[0] for row in conn.execute('SELECT card_id FROM custom_grants WHERE user_id=? AND active=1',(user,)) if access_in(conn,user,row[0])]
    return [card for card in (db.get_card_by_id_for_player(key,user) for key in ids) if card]


def user_card_in(db,conn,user,card_id):
    if not access_in(conn,user,card_id):return None
    raw=db.get_card_by_id(card_id)
    if not raw:return None
    card=Card.from_dict(raw.to_dict())
    media=conn.execute('SELECT m.filename FROM custom_definitions d JOIN custom_media m USING(media_id) WHERE d.card_id=? AND m.removed=0',(card_id,)).fetchone()
    if media:card.image_path=str(media_root(db)/media[0])
    return card


def snapshot_in(conn,key,user,card_id):
    row=conn.execute('SELECT snapshot_json FROM custom_match_cards WHERE match_key=? AND user_id=? AND card_id=?',(key,user,card_id)).fetchone()
    return json.loads(row[0]) if row else None


def freeze_in(conn,key,user,card_id):
    row=conn.execute('SELECT * FROM cards WHERE card_id=?',(card_id,)).fetchone()
    columns=[item[1] for item in conn.execute('PRAGMA table_info(cards)')]
    if not row or dict(zip(columns,row))['origin']!='custom':return
    if snapshot_in(conn,key,user,card_id):return
    if not access_in(conn,user,card_id):raise ValueError('custom_access_denied')
    data=dict(zip(columns,row))
    card=display_card_in(conn,Card.from_dict(data))
    metadata=conn.execute('SELECT traits,series,hidden_stats,passive FROM card_mode_metadata WHERE card_id=?',(card_id,)).fetchone()
    data=card.to_dict()
    data['_metadata']={'traits':json.loads(metadata[0]),'series':metadata[1],'hidden_stats':json.loads(metadata[2]),'passive':json.loads(metadata[3])} if metadata else {}
    conn.execute('INSERT INTO custom_match_cards VALUES(?,?,?,?)',(key,user,card_id,json.dumps(data)))


def match_card(db,key,user,card_id):
    with closing(sqlite3.connect(db.db_path)) as conn:data=snapshot_in(conn,key,user,card_id)
    card=Card.from_dict(data) if data else db.get_card_by_id_for_player(card_id,user) or db.get_card_by_id(card_id)
    if data and card:card.snapshot_metadata=data['_metadata']
    return card


def media_root(db):
    # Never put user images in a public assets directory or a release package.
    root = Path(os.environ.get('TELBATTLE_CUSTOM_MEDIA_ROOT') or (Path(db.db_path).resolve().parent/'private_custom_media')).resolve()
    project = Path(__file__).resolve().parents[1]
    for public in (project/'assets', project/'frontend/game/public', project/'frontend/game/dist', project/'web'):
        if root == public.resolve() or public.resolve() in root.parents:
            raise ValueError('private_media_root_required')
    return root


class CustomCards:
    def __init__(self,db):self.db=db

    def mutate(self,actor,key,action,payload,validator=None):
        if not isinstance(actor,str) or not actor or not isinstance(key,str) or not 1<=len(key)<=128:raise ValueError('admin_and_request_key_required')
        encoded=json.dumps({'action':action,'payload':payload},sort_keys=True)
        with closing(sqlite3.connect(self.db.db_path,timeout=30)) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            prior=conn.execute('SELECT payload_json,receipt_json FROM custom_operations WHERE actor=? AND operation_id=?',(actor,key)).fetchone()
            if prior:
                if prior[0]!=encoded:raise ValueError('idempotency_conflict')
                return {**json.loads(prior[1]),'replayed':True}
            result=self._action(conn,actor,action,payload,validator)
            conn.execute('INSERT INTO custom_operations VALUES(?,?,?,?,?)',(actor,key,encoded,json.dumps(result),now()))
            conn.execute('INSERT INTO custom_audit(actor,action,payload_json,created_at) VALUES(?,?,?,?)',(actor,action,encoded,now()))
        self.db.card_cache.clear()
        return result

    @staticmethod
    def users_in(conn,users):
        if not isinstance(users,list) or not users or len(users)!=len(set(users)) or any(type(user) is not int or user<=0 for user in users):raise ValueError('invalid_recipients')
        if any(not conn.execute('SELECT 1 FROM players WHERE user_id=?',(user,)).fetchone() for user in users):raise ValueError('unknown_recipient')
        return users

    def _action(self,conn,actor,action,data,validator):
        if not isinstance(data,dict):raise ValueError('invalid_payload')
        if action=='settings':
            allowed={'custom_cards_enabled','quick_friendly_enabled','easy_custom_cards_enabled','custom_card_orders_enabled','custom_admin_contact','balance_approved'}
            if set(data)-allowed:raise ValueError('invalid_custom_settings')
            if data.get('easy_custom_cards_enabled') is True and data.get('balance_approved') is not True:raise ValueError('easy_balance_approval_required')
            for key,value in data.items():
                if key=='balance_approved':continue
                if key=='custom_admin_contact':
                    if value is not None and (not isinstance(value,str) or not re.fullmatch(r'https://t\.me/[A-Za-z][A-Za-z0-9_]{4,31}',value)):raise ValueError('invalid_admin_contact')
                elif type(value) is not bool:raise ValueError('invalid_flag')
                conn.execute('UPDATE foundation_settings SET value_json=? WHERE key=?',(json.dumps(value),key))
            return {'settings':data}
        if action=='order':
            buyer=data.get('buyer_id');recipients=self.users_in(conn,data.get('recipients'))
            self.users_in(conn,[buyer])
            rarity=data.get('rarity')
            if rarity not in ('normal','epic','legend'):raise ValueError('invalid_custom_rarity')
            try:amount=Decimal(str(data.get('amount')))
            except InvalidOperation:raise ValueError('agreed_amount_required')
            currency=data.get('currency');notes=data.get('notes','')
            if not amount.is_finite() or amount<0 or len(str(amount))>40 or not isinstance(currency,str) or not 1<=len(currency)<=20 or not isinstance(notes,str) or len(notes)>2000:raise ValueError('invalid_order')
            card=data.get('card_id')
            if card and not conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='custom' AND rarity=?",(card,rarity)).fetchone():raise ValueError('invalid_custom_card')
            order=uuid.uuid4().hex
            conn.execute('INSERT INTO custom_orders(order_id,buyer_id,rarity,recipients_json,amount,currency,notes,card_id,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(order,buyer,rarity,json.dumps(recipients),str(amount),currency,notes,card,actor,now()))
            return {'order_id':order,'payment_status':'payment_pending'}
        if action=='payment':
            order=data.get('order_id')
            if conn.execute("UPDATE custom_orders SET payment_status='verified' WHERE order_id=?",(order,)).rowcount!=1:raise ValueError('order_not_found')
            return {'order_id':order,'payment_status':'verified'}
        if action in ('create','edit'):
            order=conn.execute('SELECT rarity,card_id FROM custom_orders WHERE order_id=?',(data.get('order_id'),)).fetchone()
            if not order:raise ValueError('order_not_found')
            raw=data.get('card')
            if not isinstance(raw,dict) or raw.get('rarity')!=order[0] or raw.get('image_path') or raw.get('photo_file_id') or raw.get('sticker_file_id'):raise ValueError('invalid_custom_definition')
            if not validator:raise ValueError('validator_required')
            if any(type(raw.get(stat)) is not int for stat in ('power','speed','iq','popularity')):raise ValueError('invalid_stats')
            validated=validator(raw)
            card=validated['card'];card_id=data.get('card_id') if action=='edit' else 'cc-'+uuid.uuid4().hex[:20]
            if action=='create' and order[1]:raise ValueError('order_already_has_card')
            if action=='edit' and order[1]!=card_id:raise ValueError('definition_order_mismatch')
            card.card_id=card_id;card.origin='custom';display_name=card.name;card.name='__custom:'+card_id
            values=card.to_dict();keys=list(values)
            if action=='create':
                conn.execute('INSERT INTO cards('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(values.values()))
            else:
                conn.execute('UPDATE cards SET '+','.join(key+'=?' for key in keys if key!='card_id')+' WHERE card_id=?',tuple(value for key,value in values.items() if key!='card_id')+(card_id,))
            media=data.get('media_id')
            if media and not conn.execute('SELECT 1 FROM custom_media WHERE media_id=? AND removed=0',(media,)).fetchone():raise ValueError('invalid_private_media')
            metadata=validated['metadata']
            conn.execute('INSERT INTO card_mode_metadata VALUES(?,?,?,?,?) ON CONFLICT(card_id) DO UPDATE SET traits=excluded.traits,series=excluded.series,hidden_stats=excluded.hidden_stats,passive=excluded.passive',(card_id,json.dumps(metadata['traits']),metadata['series'],json.dumps(metadata['hidden_stats']),json.dumps(metadata['passive'])))
            payload={**raw,'name':display_name,'metadata':metadata}
            conn.execute("INSERT INTO custom_definitions VALUES(?,?,?,'draft',?,?,?,?) ON CONFLICT(card_id) DO UPDATE SET payload_json=excluded.payload_json,status='pending_review',media_id=excluded.media_id,actor=excluded.actor,updated_at=excluded.updated_at",(card_id,data['order_id'],json.dumps(payload),media,actor,now(),now()))
            conn.execute('UPDATE custom_orders SET card_id=? WHERE order_id=?',(card_id,data['order_id']))
            return {'card_id':card_id,'status':'draft' if action=='create' else 'pending_review'}
        card=data.get('card_id')
        definition=conn.execute('SELECT order_id,status,media_id FROM custom_definitions WHERE card_id=?',(card,)).fetchone()
        if not definition:raise ValueError('custom_card_not_found')
        if action=='status':
            status=data.get('status')
            if status not in ('draft','pending_review','active','suspended'):raise ValueError('invalid_status')
            if status=='active':
                if data.get('review_confirmed') is not True or not conn.execute("SELECT 1 FROM custom_orders WHERE order_id=? AND payment_status='verified'",(definition[0],)).fetchone():raise ValueError('review_and_payment_required')
            conn.execute('UPDATE custom_definitions SET status=?,actor=?,updated_at=? WHERE card_id=?',(status,actor,now(),card))
            return {'card_id':card,'status':status}
        if action=='grant':
            users=self.users_in(conn,data.get('users'))
            order=conn.execute("SELECT recipients_json FROM custom_orders WHERE order_id=? AND card_id=? AND payment_status='verified'",(data.get('order_id'),card)).fetchone()
            if definition[1]!='active' or not order or any(user not in json.loads(order[0]) for user in users):raise ValueError('verified_recipient_order_required')
            for user in users:
                conn.execute('INSERT INTO custom_grants VALUES(?,?,1,?,?,?) ON CONFLICT(card_id,user_id) DO UPDATE SET active=1,order_id=excluded.order_id,actor=excluded.actor,updated_at=excluded.updated_at',(card,user,data['order_id'],actor,now()))
            return {'card_id':card,'users':users}
        if action=='revoke':
            users=self.users_in(conn,data.get('users'))
            for user in users:conn.execute('UPDATE custom_grants SET active=0,actor=?,updated_at=? WHERE card_id=? AND user_id=?',(actor,now(),card,user))
            return {'card_id':card,'users':users,'active':False}
        if action=='remove_image':
            # Logical removal is immediate; physical cleanup only after retention review.
            conn.execute('UPDATE custom_definitions SET media_id=NULL,status=\'suspended\',updated_at=? WHERE card_id=?',(now(),card))
            if definition[2]:conn.execute('UPDATE custom_media SET removed=1 WHERE media_id=?',(definition[2],))
            return {'card_id':card,'image_removed':True}
        raise ValueError('invalid_custom_action')
