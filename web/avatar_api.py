"""Authenticated player/avatar assets and existing-admin cosmetic catalog."""
import sqlite3
from contextlib import closing
from io import BytesIO
from pathlib import Path

from flask import g, jsonify, request, send_file, send_from_directory
from PIL import Image

from systems import avatar_cosmetics as cosmetics, card_avatars as faces


def png(image):
    if image.mode == 'L':
        alpha = image
        image = Image.new('RGBA', image.size, 'white')
        image.putalpha(alpha)
    output = BytesIO()
    image.save(output, 'PNG', optimize=True)
    return output.getvalue()


def image_response(raw):
    response = send_file(BytesIO(raw), mimetype='image/png', max_age=0)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def register_player_avatars(app, db_provider, auth):
    @app.route('/api/v1/avatar', methods=['GET','PUT'])
    @auth
    def player_avatar():
        db = db_provider()
        try:
            return jsonify(cosmetics.save_style(db,g.user_id,request.get_json(silent=True)) if request.method=='PUT'
                           else cosmetics.catalog(db,g.user_id))
        except ValueError as error:
            return jsonify(error=str(error)),409

    @app.route('/api/v1/avatar/render')
    @app.route('/api/v1/avatar/generic')
    @app.route('/api/v1/avatar/item/<item_id>/<kind>')
    @app.route('/api/v1/avatar/face/<card_id>/<rarity>')
    @app.route('/api/v1/avatar/free-face/<free_id>')
    @auth
    def avatar_image(item_id=None,kind=None,card_id=None,rarity=None,free_id=None):
        db=db_provider()
        try:
            if free_id:
                with closing(sqlite3.connect(db.db_path)) as conn:
                    face=cosmetics.free_face_in(conn,free_id)
                if not face or not face['enabled'] or not cosmetics.free_face_ready(db,face):return jsonify(error='image_not_found'),404
                image=cosmetics.file_image(db,face['filename']) if face['filename'] else cosmetics.generic_portrait(512)
                return image_response(png(image))
            if item_id:
                with closing(sqlite3.connect(db.db_path)) as conn:
                    conn.row_factory=sqlite3.Row
                    item=cosmetics.item_in(conn,item_id)
                if kind not in ('image','mask') or not item or not item['enabled'] or not cosmetics.ready(db,item):
                    return jsonify(error='image_not_found'),404
                return image_response(png(cosmetics.item_art(db,item,mask=kind=='mask',size=512)))
            if card_id:
                with closing(sqlite3.connect(db.db_path)) as conn:
                    conn.row_factory=sqlite3.Row
                    meta=cosmetics.face_meta_in(conn,card_id,rarity)
                    if not meta['enabled'] or not faces._owned_card_in(db,conn,g.user_id,card_id,rarity):
                        return jsonify(error='face_not_owned'),404
                path=faces.path_for(db,card_id,rarity)
                if not path:return jsonify(error='image_not_found'),404
                return image_response(path.read_bytes())
            if request.path.endswith('/generic'):
                return image_response(png(cosmetics.generic_portrait(512)))
            return image_response(cosmetics.render(db,g.user_id,request.args.get('slot','profile')))
        except (ValueError,OSError):
            return jsonify(error='image_not_found'),404


def register_avatar_admin(api):
    @api.app.route('/avatar-items')
    def avatar_admin_page():
        return send_from_directory(str(Path(__file__).parent),'avatar_items.html')

    @api.app.route('/api/avatar-admin/catalog',methods=['GET','POST'])
    @api.app.route('/api/avatar-admin/defaults',methods=['PUT'])
    @api.app.route('/api/avatar-admin/media',methods=['POST'])
    @api.app.route('/api/avatar-admin/media/<filename>')
    @api.app.route('/api/avatar-admin/face/<card_id>/<rarity>',methods=['GET','PUT'])
    @api.app.route('/api/avatar-admin/preview',methods=['POST'])
    @api.app.route('/api/avatar-admin/free-faces',methods=['POST'])
    @api.app.route('/api/avatar-admin/free-face/<free_id>')
    def avatar_admin_action(filename=None,card_id=None,rarity=None,free_id=None):
        try:
            actor=api._arena_admin_actor()
            api._arena_rate_limit('avatar:'+request.method,120 if request.method=='GET' else 60)
            if filename:
                return image_response(png(cosmetics.file_image(api.db,filename)))
            body=request.get_json(silent=True) or {}
            if not isinstance(body,dict):raise ValueError('فرم معتبر نیست.')
            if free_id:
                with closing(sqlite3.connect(api.db.db_path)) as conn:
                    face=cosmetics.free_face_in(conn,free_id)
                if not face or not cosmetics.free_face_ready(api.db,face):return jsonify(error='image_not_found'),404
                return image_response(png(cosmetics.file_image(api.db,face['filename']) if face['filename'] else cosmetics.generic_portrait(512)))
            if request.path.endswith('/free-faces'):
                return jsonify(face=cosmetics.save_free_face(api.db,actor,body))
            if card_id:
                if request.method=='PUT':
                    cosmetics.configure_face(api.db,actor,card_id,rarity,body)
                    return jsonify(ok=True)
                path=faces.path_for(api.db,card_id,rarity)
                if not path:return jsonify(error='image_not_found'),404
                return image_response(path.read_bytes())
            if request.path.endswith('/media'):
                file=request.files.get('file')
                if not file:raise ValueError('فایل تصویر را انتخاب کن.')
                kind=request.form.get('kind')
                if kind not in ('frame','background','mask','portrait'):raise ValueError('نوع تصویر معتبر نیست.')
                return jsonify(filename=cosmetics.upload(api.db,file.read(faces.MAX_UPLOAD+1),mask=kind=='mask',transparent=kind in ('frame','portrait')))
            if request.path.endswith('/defaults'):
                cosmetics.set_defaults(api.db,actor,body)
                return jsonify(ok=True)
            if request.path.endswith('/preview'):
                with closing(sqlite3.connect(api.db.db_path)) as conn:
                    conn.row_factory=sqlite3.Row
                    frame=cosmetics.item_in(conn,body.get('frame_id','silver'))
                    bg=cosmetics.item_in(conn,body.get('background_id','red'))
                    if not frame or frame['kind']!='frame' or not bg or bg['kind']!='background':
                        raise ValueError('قاب و پس‌زمینه را انتخاب کن.')
                    face=dict(card_id=None,rarity=None,filename=None,kind='portrait',scale=1,offset_x=0,offset_y=0)
                    if body.get('free_face_id'):
                        free=cosmetics.free_face_in(conn,body['free_face_id'])
                        if not free or not cosmetics.free_face_ready(api.db,free):raise ValueError('چهرهٔ رایگان آماده نیست.')
                        face=cosmetics.free_face_value(free)
                    if body.get('card_id'):
                        path=faces.path_for(api.db,body['card_id'],body.get('rarity'))
                        if path:face=dict(card_id=body['card_id'],rarity=body['rarity'],filename=path.name,
                                          **cosmetics.face_meta_in(conn,body['card_id'],body['rarity']))
                return image_response(cosmetics.compose(api.db,dict(face=face,frame=frame,background=bg)))
            if request.method=='POST':
                return jsonify(item=cosmetics.save_item(api.db,actor,body))
            with closing(sqlite3.connect(api.db.db_path)) as conn:
                conn.row_factory=sqlite3.Row
                items=[dict(row,ready=cosmetics.ready(api.db,dict(row))) for row in conn.execute('SELECT * FROM avatar_cosmetics ORDER BY kind,sort_order,item_id')]
                portraits=[dict(row,**cosmetics.face_meta_in(conn,row['card_id'],row['rarity'])) for row in conn.execute('''
                    SELECT a.card_id,a.rarity,c.name FROM card_avatars a JOIN cards c USING(card_id) ORDER BY c.name''')]
                defaults=dict(conn.execute('SELECT key,value FROM avatar_settings'))
                free_faces=[dict(row,ready=cosmetics.free_face_ready(api.db,dict(row))) for row in conn.execute('SELECT * FROM avatar_free_faces ORDER BY sort_order,face_id')]
            return jsonify(items=items,faces=portraits,free_faces=free_faces,defaults=defaults)
        except PermissionError:
            return jsonify(error='توکن مدیریت معتبر لازم است.'),403
        except (ValueError,sqlite3.IntegrityError) as error:
            return jsonify(error=str(error)),400
        except OSError:
            return jsonify(error='تصویر در دسترس نیست.'),404
