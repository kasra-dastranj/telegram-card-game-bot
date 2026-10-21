"""Authenticated manual handoff of existing official Rare cards."""
from pathlib import Path
from flask import jsonify, request, send_from_directory
from systems import rare_delivery


ERRORS = {
    'player_not_found':'بازیکن پیدا نشد؛ باید قبلاً ربات را استارت کرده باشد.',
    'invalid_player_id':'شناسهٔ عددی معتبر بازیکن را وارد کن.',
    'rare_required':'یک کارت رسمی Rare انتخاب کن.',
    'rare_supply_empty':'نسخهٔ آزاد کافی نیست؛ موجودی یا رزرو حمله‌ها را بررسی کن.',
    'invalid_rare_supply':'تیراژ باید یک عدد صحیح بین صفر تا یک میلیون باشد.',
    'rare_supply_reserved_or_issued':'تیراژ از تعداد نسخه‌های تحویل‌شده و رزروشده کمتر نمی‌شود.',
    'supply_changed':'تیراژ تغییر کرده؛ فهرست را دوباره بارگذاری کن.',
    'idempotency_conflict':'این شناسهٔ درخواست قبلاً برای تحویل دیگری استفاده شده است.',
    'invalid_request_key':'شناسهٔ درخواست معتبر لازم است.',
    'review_required':'گیرنده و هماهنگی پرداخت خارج از پنل را تأیید کن.',
    'rate_limit_exceeded':'درخواست‌ها زیاد شده؛ یک دقیقه بعد دوباره امتحان کن.',
}


def register_rare_admin(api):
    @api.app.route('/rare-cards')
    def rare_page():
        return send_from_directory(str(Path(__file__).parent), 'rare_card_management.html')

    @api.app.after_request
    def private_rare_responses(response):
        if request.path.startswith('/api/rare/'):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @api.app.route('/api/rare/cards', methods=['GET'])
    @api.app.route('/api/rare/players', methods=['GET'])
    @api.app.route('/api/rare/deliver', methods=['POST'])
    @api.app.route('/api/rare/supply', methods=['POST'])
    def rare_action():
        try:
            actor = api._arena_admin_actor('write')
            api._arena_rate_limit('rare_'+request.path, 30 if request.method=='GET' else 10)
            if request.method == 'GET':
                if request.path.endswith('/players'):
                    from web.custom_admin_api import find_players
                    return jsonify(players=find_players(api.db, request.args.get('q','')))
                return jsonify(cards=rare_delivery.catalog(api.db))
            body = request.get_json(silent=True)
            if not isinstance(body, dict):
                raise ValueError('invalid_request')
            if request.path.endswith('/supply'):
                if 'expected_supply' not in body:
                    raise ValueError('supply_changed')
                result = rare_delivery.set_supply(api.db, actor, body.get('card_id'), body.get('total'), body['expected_supply'])
            else:
                if body.get('review_confirmed') is not True:
                    raise ValueError('review_required')
                result = rare_delivery.deliver(api.db, actor, body.get('user_id'), body.get('card_id'), body.get('request_key'))
            return jsonify(result)
        except PermissionError:
            return jsonify(error='توکن مدیریت معتبر لازم است.'), 403
        except ValueError as error:
            code = str(error)
            return jsonify(error=ERRORS.get(code, 'درخواست معتبر نیست؛ اطلاعات فرم را بررسی کن.'), error_code=code), 400
