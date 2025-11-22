#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Web API Cooldown Update
بروزرسانی web_api.py برای مدیریت Cooldown جداگانه هر کارت
"""

# این API ها باید به web_api.py اضافه شوند:

API_ADDITIONS = '''
        @self.app.route('/api/cards/<card_id>/cooldown', methods=['GET'])
        def get_card_cooldown(card_id):
            """دریافت تنظیمات cooldown کارت خاص"""
            try:
                card = self.db.get_card_by_id(card_id)
                if not card:
                    return jsonify({'success': False, 'error': 'کارت یافت نشد'}), 404
                
                settings = self.db.get_card_cooldown_settings(card_id)
                
                return jsonify({
                    'success': True,
                    'card': {
                        'id': card.card_id,
                        'name': card.name,
                        'rarity': card.rarity.value
                    },
                    'cooldown_settings': settings
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/cards/<card_id>/cooldown', methods=['POST'])
        def update_card_cooldown(card_id):
            """بروزرسانی تنظیمات cooldown کارت خاص"""
            try:
                card = self.db.get_card_by_id(card_id)
                if not card:
                    return jsonify({'success': False, 'error': 'کارت یافت نشد'}), 404
                
                data = request.get_json()
                
                win_limit = None
                cooldown_hours = None
                enabled = None
                
                if 'win_limit' in data:
                    win_limit = int(data['win_limit'])
                    if win_limit < 1 or win_limit > 100:
                        return jsonify({'success': False, 'error': 'حد مجاز برد باید بین 1 تا 100 باشد'}), 400
                
                if 'cooldown_hours' in data:
                    cooldown_hours = int(data['cooldown_hours'])
                    if cooldown_hours < 1 or cooldown_hours > 168:  # حداکثر یک هفته
                        return jsonify({'success': False, 'error': 'مدت cooldown باید بین 1 تا 168 ساعت باشد'}), 400
                
                if 'enabled' in data:
                    enabled = bool(data['enabled'])
                
                success = self.db.set_card_cooldown_settings(card_id, win_limit, cooldown_hours, enabled)
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': f'تنظیمات cooldown کارت {card.name} بروزرسانی شد'
                    })
                else:
                    return jsonify({'success': False, 'error': 'خطا در ذخیره تنظیمات'}), 500
                    
            except ValueError as e:
                return jsonify({'success': False, 'error': 'داده‌های ورودی نامعتبر'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/cards/cooldown-settings', methods=['GET'])
        def get_all_cooldown_settings():
            """دریافت تنظیمات cooldown همه کارت‌ها"""
            try:
                settings = self.db.get_all_card_cooldown_settings()
                
                return jsonify({
                    'success': True,
                    'cards': settings,
                    'count': len(settings)
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/cards/cooldown-settings/bulk', methods=['POST'])
        def bulk_update_cooldown_settings():
            """بروزرسانی دسته‌ای تنظیمات cooldown"""
            try:
                data = request.get_json()
                
                if 'cards' not in data or not isinstance(data['cards'], list):
                    return jsonify({'success': False, 'error': 'فرمت داده نامعتبر'}), 400
                
                updated_count = 0
                errors = []
                
                for card_data in data['cards']:
                    try:
                        card_id = card_data.get('card_id')
                        if not card_id:
                            continue
                        
                        win_limit = card_data.get('win_limit')
                        cooldown_hours = card_data.get('cooldown_hours')
                        enabled = card_data.get('enabled')
                        
                        success = self.db.set_card_cooldown_settings(card_id, win_limit, cooldown_hours, enabled)
                        if success:
                            updated_count += 1
                        else:
                            errors.append(f'خطا در بروزرسانی کارت {card_id}')
                            
                    except Exception as e:
                        errors.append(f'خطا در پردازش کارت {card_data.get("card_id", "نامشخص")}: {str(e)}')
                
                return jsonify({
                    'success': True,
                    'message': f'{updated_count} کارت بروزرسانی شد',
                    'updated_count': updated_count,
                    'errors': errors
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/cards/cooldown-settings/reset', methods=['POST'])
        def reset_all_cooldowns():
            """ریست همه cooldown های فعال"""
            try:
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                # ریست همه cooldown های فعال
                cursor.execute('''
                    UPDATE card_cooldowns 
                    SET is_in_cooldown = 0, cooldown_until = NULL, wins_count = 0
                    WHERE is_in_cooldown = 1
                ''')
                
                reset_count = cursor.rowcount
                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'message': f'{reset_count} cooldown ریست شد',
                    'reset_count': reset_count
                })
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
'''

print("✅ فایل web_api_cooldown_update.py آماده شد!")
print("این فایل شامل API های جدید:")
print("- GET /api/cards/{card_id}/cooldown - دریافت تنظیمات کارت")
print("- POST /api/cards/{card_id}/cooldown - تغییر تنظیمات کارت")
print("- GET /api/cards/cooldown-settings - همه تنظیمات")
print("- POST /api/cards/cooldown-settings/bulk - بروزرسانی دسته‌ای")
print("- POST /api/cards/cooldown-settings/reset - ریست همه cooldown ها")