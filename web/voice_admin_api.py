"""Audio authoring uses the corresponding existing card/attack admin authority."""
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import closing
from io import BytesIO
from pathlib import Path
from flask import jsonify, request, send_file, send_from_directory
from systems import victory_voices as voices


def register_voice_admin(api):
    def actor(custom=False):
        if not custom:
            return api._arena_admin_actor('write')
        expected = os.getenv('ADMIN_API_TOKEN') or os.getenv('ARENA_ADMIN_TOKEN')
        if not expected or not hmac.compare_digest(request.headers.get('X-Admin-Token', ''), expected):
            raise PermissionError('unauthorized_admin')
        return os.getenv('ARENA_ADMIN_ACTOR') or 'token-admin:' + hashlib.sha256(expected.encode()).hexdigest()[:10]

    @api.app.after_request
    def private_voice_responses(response):
        if request.path.startswith(('/api/voices/', '/api/custom/voices/')):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @api.app.route('/victory-voices')
    def voice_page():
        return send_from_directory(str(Path(__file__).parent), 'victory_voices.html')

    @api.app.route('/api/voices/cards')
    def voice_cards():
        try:
            custom = request.args.get('kind') == 'custom'
            actor(custom)
            api._arena_rate_limit('voice_cards', 30)
            with closing(sqlite3.connect(api.db.db_path)) as conn:
                rows = conn.execute('''SELECT c.card_id,c.name,d.payload_json FROM cards c
                    LEFT JOIN custom_definitions d ON d.card_id=c.card_id WHERE c.origin=? AND
                    (c.rarity='legend' OR (c.origin='official' AND EXISTS
                    (SELECT 1 FROM card_variants v WHERE v.card_id=c.card_id AND v.rarity='legend')))
                    ORDER BY c.name''', ('custom' if custom else 'official',)).fetchall()
            return jsonify(cards=[{'card_id': r[0], 'name': json.loads(r[2]).get('name',r[1]) if r[2] else r[1]} for r in rows])
        except PermissionError:
            return jsonify(error='توکن مدیریت معتبر لازم است.'), 403
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @api.app.route('/api/voices/card/<card_id>', methods=['GET', 'PUT', 'POST'])
    @api.app.route('/api/custom/voices/<card_id>', methods=['GET', 'PUT', 'POST'])
    def card_voice_settings(card_id):
        try:
            # Authenticate before revealing card existence or origin.
            custom = request.path.startswith('/api/custom/voices/')
            who = actor(custom)
            with closing(sqlite3.connect(api.db.db_path)) as conn:
                origin = voices.card_scope(conn, card_id)
                if (origin == 'custom') != custom:
                    raise PermissionError('wrong_admin_scope')
                value = voices.card_settings_in(conn, card_id)
            api._arena_rate_limit('voice_card_' + request.method, 30 if request.method == 'GET' else 10)
            if request.method == 'PUT':
                value = voices.save_card(api.db, card_id, request.get_json(silent=True), who)
            elif request.method == 'POST':
                file = request.files.get('voice')
                if not file:
                    raise ValueError('فایل ویس را انتخاب کن.')
                try:
                    raw = file.read(voices.MAX_BYTES + 1)
                finally:
                    file.close()
                key = voices.upload(api.db, raw, 'card:' + card_id, who)
                return jsonify(media_id=key), 201
            return jsonify(settings=value)
        except PermissionError:
            return jsonify(error='دسترسی مدیریت همین نوع کارت لازم است.'), 403
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @api.app.route('/api/voices/attack', methods=['POST'])
    def attack_voice_upload():
        try:
            who = actor()
            api._arena_rate_limit('voice_attack_upload', 10)
            file = request.files.get('voice')
            if not file:
                raise ValueError('فایل ویس را انتخاب کن.')
            try:
                raw = file.read(voices.MAX_BYTES + 1)
            finally:
                file.close()
            return jsonify(media_id=voices.upload(api.db, raw, 'attack', who)), 201
        except PermissionError:
            return jsonify(error='دسترسی مدیریت لازم است.'), 403
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @api.app.route('/api/voices/preview/<media_id>')
    def voice_preview(media_id):
        try:
            custom = request.args.get('kind') == 'custom'
            actor(custom)
            with closing(sqlite3.connect(api.db.db_path)) as conn:
                value = voices.asset_in(conn, media_id)
                if not value:
                    return jsonify(error='ویس پیدا نشد.'), 404
                scope = value['scope']
                if scope.startswith('card:'):
                    if (voices.card_scope(conn, scope[5:]) == 'custom') != custom:
                        raise PermissionError('wrong_admin_scope')
                elif custom:
                    raise PermissionError('wrong_admin_scope')
            raw = voices.audio_bytes(api.db, media_id, scope)
            return send_file(BytesIO(raw), mimetype='audio/ogg', max_age=0)
        except PermissionError:
            return jsonify(error='دسترسی مدیریت لازم است.'), 403
        except (ValueError, OSError) as exc:
            return jsonify(error='ویس در دسترس نیست.'), 400
