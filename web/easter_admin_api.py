"""Easter-egg configuration is restricted to existing admin authority."""
import sqlite3
import hashlib
import hmac
import os
from contextlib import closing
from io import BytesIO
from pathlib import Path

from flask import jsonify, request, send_file, send_from_directory

from systems import easter_eggs as eggs, easter_media


def register_easter_admin(api):
    @api.app.route('/easter-eggs')
    def easter_page():
        return send_from_directory(str(Path(__file__).parent), 'easter_eggs.html')

    @api.app.after_request
    def easter_private(response):
        if request.path.startswith('/api/easter/'):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @api.app.route('/api/easter/catalog', methods=['GET', 'POST'])
    @api.app.route('/api/easter/rules/<rule_id>', methods=['PUT', 'DELETE'])
    @api.app.route('/api/easter/history/<rule_id>')
    @api.app.route('/api/easter/preview', methods=['POST'])
    @api.app.route('/api/easter/media', methods=['POST'])
    @api.app.route('/api/easter/media/<media_id>')
    def easter_action(rule_id=None, media_id=None):
        try:
            # This panel may assign private custom cards: use the same complete
            # admin authority as the existing custom fulfillment panel.
            expected = os.getenv('ADMIN_API_TOKEN') or os.getenv('ARENA_ADMIN_TOKEN')
            if not expected or not hmac.compare_digest(request.headers.get('X-Admin-Token', ''), expected):
                raise PermissionError('unauthorized_admin')
            actor = os.getenv('ARENA_ADMIN_ACTOR') or 'token-admin:' + hashlib.sha256(expected.encode()).hexdigest()[:10]
            api._arena_rate_limit('easter:' + request.method, 60 if request.method == 'GET' else 30)
            if media_id:
                item, raw = easter_media.read(api.db, media_id)
                return send_file(BytesIO(raw), mimetype=item['mime'], max_age=0)
            if request.path == '/api/easter/media':
                file = request.files.get('file')
                if not file:
                    raise ValueError('فایل رسانه را انتخاب کن.')
                try:
                    raw = file.read(easter_media.MAX_BYTES + 1)
                finally:
                    file.close()
                return jsonify(media_id=easter_media.upload(api.db, actor, request.form.get('kind'), raw)), 201
            if request.path.startswith('/api/easter/history/'):
                user = request.args.get('user_id')
                if user and (not user.isdecimal() or int(user) <= 0):
                    raise ValueError('شناسهٔ عددی حساب معتبر نیست.')
                return jsonify(users=eggs.history(api.db, rule_id, int(user) if user else None))
            if request.method == 'GET':
                return jsonify(eggs.catalog(api.db))
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                raise ValueError('فرم معتبر نیست.')
            if request.path == '/api/easter/preview':
                with closing(sqlite3.connect(api.db.db_path)) as conn, conn:
                    eggs.ensure_in(conn)
                    value = eggs.validate_in(conn, body.get('rule'))
                return jsonify(rule=value, notice='پیش‌نمایش تنظیمات؛ هیچ جایزه یا سهمیه‌ای تغییر نکرد.')
            if request.method == 'DELETE':
                eggs.delete(api.db, actor, rule_id, body.get('revision'))
                return jsonify(ok=True)
            value = eggs.save(api.db, actor, rule_id, body.get('revision'), body.get('rule'))
            return jsonify(rule=value)
        except PermissionError:
            return jsonify(error='توکن مدیریت معتبر لازم است.'), 403
        except (ValueError, sqlite3.IntegrityError) as error:
            return jsonify(error=str(error)), 400
        except OSError:
            return jsonify(error='فایل رسانه در دسترس نیست.'), 404
