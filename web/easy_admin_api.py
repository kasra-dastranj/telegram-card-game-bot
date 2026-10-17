"""Easy question editing behind the existing server admin authentication."""
import sqlite3
from contextlib import closing
from pathlib import Path
from flask import jsonify, request, send_from_directory
from systems.easy_questions import catalog_in, save_catalog_in, CatalogConflict


def register_easy_admin(api):
    @api.app.route('/easy-questions')
    def easy_page():
        return send_from_directory(str(Path(__file__).resolve().parent), 'easy_questions.html')

    @api.app.route('/api/easy/catalog', methods=['GET', 'PUT'])
    def easy_catalog():
        try:
            actor = api._arena_admin_actor('read' if request.method == 'GET' else 'write')
            with closing(sqlite3.connect(api.db.db_path, timeout=15)) as conn, conn:
                if request.method == 'GET':
                    data = catalog_in(conn)
                else:
                    api._arena_rate_limit('easy_catalog_write', 30)
                    conn.execute('BEGIN IMMEDIATE')
                    data = save_catalog_in(conn, request.get_json(silent=True), actor)
            response = jsonify(success=True, catalog=data)
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        except PermissionError:
            return jsonify(success=False, error='دسترسی مدیریت لازم است.'), 403
        except CatalogConflict as exc:
            return jsonify(success=False, error=str(exc)), 409
        except ValueError as exc:
            return jsonify(success=False, error=str(exc)), 400
