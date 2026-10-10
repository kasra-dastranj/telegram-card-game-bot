"""Custom fulfillment uses existing server admin auth, never player credentials."""
import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from contextlib import closing
from io import BytesIO
from functools import wraps
from flask import jsonify, request, send_file, send_from_directory
from PIL import Image, UnidentifiedImageError
from systems.custom_cards import CustomCards,media_root,now


def register_custom_admin(api):
    service=CustomCards(api.db)
    @api.app.after_request
    def private_responses(response):
        if request.path.startswith('/api/custom/'):
            response.headers['Cache-Control']='private, no-store'
            response.headers['X-Content-Type-Options']='nosniff'
        return response
    def auth(fn):
        @wraps(fn)
        def guarded(*args,**kwargs):
            token=os.environ.get('ADMIN_API_TOKEN') or os.environ.get('ARENA_ADMIN_TOKEN')
            supplied=request.headers.get('X-Admin-Token','')
            if not token or not hmac.compare_digest(token,supplied):return jsonify(error='unauthorized_admin'),401
            actor=os.environ.get('ARENA_ADMIN_ACTOR') or 'token-admin:'+hashlib.sha256(token.encode()).hexdigest()[:10]
            try:return fn(actor,*args,**kwargs)
            except (ValueError,TypeError,sqlite3.IntegrityError) as error:return jsonify(error=str(error)),400
        return guarded

    @api.app.route('/custom-cards')
    def custom_panel():
        from pathlib import Path
        return send_from_directory(str(Path(__file__).parent),'custom_card_management.html')

    @api.app.route('/api/custom/<action>',methods=['POST'])
    @auth
    def custom_action(actor,action):
        if action not in ('order','payment','create','edit','status','grant','revoke','remove_image','settings'):return jsonify(error='unknown_action'),404
        body=request.get_json(silent=True) or {}
        return jsonify(service.mutate(actor,body.get('request_key'),action,body.get('data'),api._validate_card_payload))

    @api.app.route('/api/custom/records')
    @auth
    def custom_records(actor):
        with closing(sqlite3.connect(api.db.db_path)) as conn:
            conn.row_factory=sqlite3.Row
            orders=[dict(row) for row in conn.execute('SELECT * FROM custom_orders ORDER BY created_at DESC LIMIT 100')]
            cards=[dict(row) for row in conn.execute('SELECT * FROM custom_definitions ORDER BY created_at DESC LIMIT 100')]
            grants=[dict(row) for row in conn.execute('SELECT * FROM custom_grants ORDER BY updated_at DESC LIMIT 500')]
        # Comparisons are informational; no invented paid-card balance algorithm.
        references=[{'name':card.name,'rarity':card.rarity.value,'power':card.power,'speed':card.speed,'iq':card.iq,'popularity':card.popularity} for card in api.db.get_all_cards() if card.origin=='official']
        return jsonify(orders=orders,cards=cards,grants=grants,official_references=references)

    @api.app.route('/api/custom/media',methods=['POST'])
    @auth
    def custom_upload(actor):
        api._arena_rate_limit('custom_upload',10)
        upload=request.files.get('image')
        if not upload:return jsonify(error='image_required'),400
        try:
            data=upload.read(8*1024*1024+1)
        finally:
            upload.close()
        if len(data)>8*1024*1024:raise ValueError('image_too_large')
        try:
            with Image.open(BytesIO(data)) as picture:
                if picture.format not in ('PNG','JPEG','WEBP') or picture.width*picture.height>16_000_000 or picture.width<1 or picture.height<1:raise ValueError('invalid_image')
                picture.load();clean=picture.convert('RGB')
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError):raise ValueError('invalid_image')
        key=uuid.uuid4().hex;filename=key+'.png';root=media_root(api.db);root.mkdir(parents=True,exist_ok=True)
        clean.save(root/filename,format='PNG')
        try:
            with closing(sqlite3.connect(api.db.db_path)) as conn,conn:
                conn.execute('INSERT INTO custom_media(media_id,filename,actor,created_at) VALUES(?,?,?,?)',(key,filename,actor,now()))
                conn.execute('INSERT INTO custom_audit(actor,action,payload_json,created_at) VALUES(?,?,?,?)',(actor,'upload',json.dumps({'media_id':key}),now()))
        except Exception:
            (root/filename).unlink();raise
        return jsonify(media_id=key),201

    @api.app.route('/api/custom/media/<media_id>')
    @auth
    def custom_admin_image(actor,media_id):
        with closing(sqlite3.connect(api.db.db_path)) as conn:
            row=conn.execute('SELECT filename FROM custom_media WHERE media_id=? AND removed=0',(media_id,)).fetchone()
        if not row:return jsonify(error='not_found'),404
        response=send_file(media_root(api.db)/row[0],mimetype='image/png',max_age=0)
        response.headers['Cache-Control']='private, no-store';return response

    @api.app.before_request
    def prevent_legacy_custom_edit():
        card=(request.view_args or {}).get('card_id')
        if not card and request.path.startswith('/api/cards') and request.method in ('POST','PUT','DELETE'):
            pending=[request.get_json(silent=True)]
            while pending:
                item=pending.pop()
                if isinstance(item,dict):pending.extend(item.values())
                elif isinstance(item,list):pending.extend(item)
                elif isinstance(item,str) and item.startswith('cc-'):
                    with closing(sqlite3.connect(api.db.db_path)) as conn:
                        if conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='custom'",(item,)).fetchone():return jsonify(error='use_authenticated_custom_admin'),403
        if card and not request.path.startswith('/api/custom/'):
            with closing(sqlite3.connect(api.db.db_path)) as conn:
                if conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='custom'",(card,)).fetchone():return jsonify(error='use_authenticated_custom_admin'),403
