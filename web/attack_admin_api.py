"""Attack authoring behind the existing owner admin authentication."""
import sqlite3
from contextlib import closing
from pathlib import Path
from flask import jsonify,request,send_from_directory
from systems.attack_catalog import PREFIX,catalog_in,save_in,validate,example,records,read,write,CatalogConflict
from systems.group_attacks import GroupAttacks,now_utc


def register_attack_admin(api):
    @api.app.route('/group-attacks')
    def attack_page():
        return send_from_directory(str(Path(__file__).resolve().parent),'group_attacks.html')

    @api.app.route('/api/attacks/catalog',methods=['GET','PUT'])
    def attack_catalog():
        try:
            actor=api._arena_admin_actor('read' if request.method=='GET' else 'write')
            with closing(sqlite3.connect(api.db.db_path,timeout=15)) as conn,conn:
                if request.method=='GET':value=catalog_in(conn)
                else:
                    api._arena_rate_limit('attack_catalog',20)
                    conn.execute('BEGIN IMMEDIATE')
                    value=save_in(conn,request.get_json(silent=True),actor)
            response=jsonify(success=True,catalog=value)
            response.headers['Cache-Control']='private, no-store'
            return response
        except PermissionError:return jsonify(success=False,error='دسترسی مدیریت لازم است.'),403
        except CatalogConflict as exc:return jsonify(success=False,error=str(exc)),409
        except ValueError as exc:return jsonify(success=False,error=str(exc)),400

    @api.app.route('/api/attacks/options')
    def attack_options():
        try:
            api._arena_admin_actor('read')
            api._arena_rate_limit('attack_options',30)
            cards=[]
            for card in api.db.get_all_cards():
                rarities=[v['rarity'] for v in api.db.get_card_variants(card.card_id)]
                if card.rarity.value not in rarities:rarities.append(card.rarity.value)
                cards.append({'id':card.card_id,'name':card.name,'rarities':rarities})
            return jsonify(success=True,cards=cards,example=example()),200,{'Cache-Control':'private, no-store'}
        except PermissionError:return jsonify(success=False,error='دسترسی مدیریت لازم است.'),403
        except ValueError as exc:return jsonify(success=False,error=str(exc)),400

    @api.app.route('/api/attacks/preview',methods=['POST'])
    def attack_preview():
        try:
            api._arena_admin_actor('read');api._arena_rate_limit('attack_preview',30)
            with closing(sqlite3.connect(api.db.db_path)) as conn:value=validate(conn,request.get_json(silent=True))
            return jsonify(success=True,message='ساختار معتبره؛ هیچ حمله یا پرداختی ایجاد نشد.',attacks=len(value['attacks']))
        except PermissionError:return jsonify(success=False,error='دسترسی مدیریت لازم است.'),403
        except ValueError as exc:return jsonify(success=False,error=str(exc)),400

    @api.app.route('/api/attacks/events')
    def attack_events():
        try:
            api._arena_admin_actor('read');api._arena_rate_limit('attack_events',30)
            with closing(sqlite3.connect(api.db.db_path)) as conn:
                prefix=PREFIX+'history:'
                keys=conn.execute('SELECT value_json FROM foundation_settings WHERE key>=? AND key<? ORDER BY key DESC LIMIT 50',(prefix,prefix+'\uffff')).fetchall()
                import json
                events=[read(conn,'event:'+json.loads(row[0])) for row in keys]
                warnings=[{'chat_id':key.split(':')[1],**value} for key,value in records(conn,'health:')][-50:]
            events=sorted(events,key=lambda e:e['created_at'],reverse=True)[:50]
            return jsonify(success=True,events=[{k:e.get(k) for k in ('id','chat_id','status','created_at','deadline','progress','attack','participants','receipts')} for e in events],warnings=warnings),200,{'Cache-Control':'private, no-store'}
        except PermissionError:return jsonify(success=False,error='دسترسی مدیریت لازم است.'),403
        except ValueError as exc:return jsonify(success=False,error=str(exc)),400

    @api.app.route('/api/attacks/events/<event_id>/cancel',methods=['POST'])
    def attack_cancel(event_id):
        try:
            actor=api._arena_admin_actor('write');api._arena_rate_limit('attack_cancel',10)
            system=GroupAttacks(api.db,api.modes)
            def action(conn):
                event=read(conn,'event:'+event_id)
                if not event:raise ValueError('حمله پیدا نشد.')
                system._finish(conn,event,'void')
                write(conn,'cancel-audit:'+event_id,{'actor':actor,'at':now_utc().isoformat()})
                return event
            event=system.run(action)
            return jsonify(success=True,status=event['status'])
        except PermissionError:return jsonify(success=False,error='دسترسی مدیریت لازم است.'),403
        except ValueError as exc:return jsonify(success=False,error=str(exc)),400
