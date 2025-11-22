#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Complete Web API for Card Management with Individual Cooldown
API وب کامل برای مدیریت کارت‌ها با Cooldown جداگانه
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import uuid
import sqlite3
from datetime import datetime
from werkzeug.utils import secure_filename

from game_core import DatabaseManager, Card, CardRarity, CardManager, GameLogic

class WebAPI:
    def __init__(self, db_manager: DatabaseManager):
        self.app = Flask(__name__)
        CORS(self.app)
        
        self.db = db_manager
        self.card_manager = CardManager(db_manager)
        self.game_logic = GameLogic(db_manager)
        
        self.setup_routes()
    
    def setup_routes(self):
        """تنظیم مسیرهای API"""
        
        @self.app.route('/')
        def serve_frontend():
            """صفحه اصلی مدیریت"""
            return send_from_directory('.', 'card_management.html')
        
        # ==================== EXISTING CARD APIs ====================
        
        @self.app.route('/api/cards', methods=['GET'])
        def get_all_cards():
            """دریافت تمام کارت‌ها"""
            try:
                cards = self.db.get_all_cards()
                cards_data = []
                
                for card in cards:
                    card_dict = {
                        'id': card.card_id,
                        'name': card.name,
                        'rarity': card.rarity.value,
                        'power': card.power,
                        'speed': card.speed,
                        'iq': card.iq,
                        'popularity': card.popularity,
                        'abilities': card.abilities,
                        'biography': getattr(card, 'biography', ''),
                        'dialogs': getattr(card, 'dialogs', []),
                        'created_at': card.created_at.isoformat()
                    }
                    cards_data.append(card_dict)
                
                return jsonify({
                    'success': True,
                    'cards': cards_data,
                    'count': len(cards_data)
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/cards', methods=['POST'])
        def create_card():
            """ایجاد کارت جدید"""
            try:
                data = request.get_json()
                
                required_fields = ['name', 'rarity', 'power', 'speed', 'iq', 'popularity']
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'success': False,
                            'error': f'فیلد {field} الزامی است'
                        }), 400
                
                existing_card = self.db.get_card_by_name(data['name'])
                if existing_card:
                    return jsonify({
                        'success': False,
                        'error': 'کارت با این نام قبلاً وجود دارد'
                    }), 409
                
                dialogs_input = data.get('dialogs', []) or []
                if isinstance(dialogs_input, str):
                    dialogs_input = [dialogs_input]
                
                card = Card(
                    card_id=str(uuid.uuid4()),
                    name=data['name'],
                    rarity=CardRarity(data['rarity']),
                    power=int(data['power']),
                    speed=int(data['speed']),
                    iq=int(data['iq']),
                    popularity=int(data['popularity']),
                    abilities=data.get('abilities', []),
                    dialogs=dialogs_input,
                    biography=data.get('biography', ''),
                    image_path=f"card_images/{data['name'].lower().replace(' ', '_')}.png"
                )
                
                if self.db.add_card(card):
                    return jsonify({
                        'success': True,
                        'message': f'کارت {card.name} با موفقیت اضافه شد',
                        'card_id': card.card_id
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'خطا در ذخیره کارت'
                    }), 500
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/cards/<card_id>', methods=['DELETE'])
        def delete_card(card_id):
            """حذف کارت"""
            try:
                card = self.db.get_card_by_id(card_id)
                if not card:
                    return jsonify({
                        'success': False,
                        'error': 'کارت یافت نشد'
                    }), 404
                
                if self.db.delete_card(card_id):
                    return jsonify({
                        'success': True,
                        'message': 'کارت با موفقیت حذف شد'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'خطا در حذف کارت'
                    }), 500
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500      
  # ==================== GAME SETTINGS APIs ====================
        
        @self.app.route('/api/game-settings', methods=['GET'])
        def get_game_settings():
            """دریافت تنظیمات بازی"""
            try:
                settings = {
                    'daily_hearts': self.game_logic.DAILY_HEARTS,
                    'card_cooldown_enabled': self.game_logic.CARD_COOLDOWN_ENABLED,
                    'card_cooldown_win_limit': self.game_logic.CARD_COOLDOWN_WIN_LIMIT,
                    'card_cooldown_hours': self.game_logic.CARD_COOLDOWN_HOURS
                }
                return jsonify({'success': True, 'settings': settings})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/game-settings', methods=['POST'])
        def update_game_settings():
            """بروزرسانی تنظیمات بازی"""
            try:
                data = request.get_json()
                
                if 'daily_hearts' in data:
                    hearts = int(data['daily_hearts'])
                    if 1 <= hearts <= 50:
                        self.game_logic.DAILY_HEARTS = hearts
                
                if 'card_cooldown_enabled' in data:
                    self.game_logic.CARD_COOLDOWN_ENABLED = bool(data['card_cooldown_enabled'])
                
                if 'card_cooldown_win_limit' in data:
                    limit = int(data['card_cooldown_win_limit'])
                    if limit > 0:
                        self.game_logic.CARD_COOLDOWN_WIN_LIMIT = limit
                
                if 'card_cooldown_hours' in data:
                    hours = int(data['card_cooldown_hours'])
                    if hours > 0:
                        self.game_logic.CARD_COOLDOWN_HOURS = hours
                
                return jsonify({'success': True, 'message': 'تنظیمات بروزرسانی شد'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        # ==================== INDIVIDUAL CARD COOLDOWN APIs - NEW ====================
        
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
                    if cooldown_hours < 1 or cooldown_hours > 168:
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
        
        @self.app.route('/api/cards/cooldown-settings/reset', methods=['POST'])
        def reset_all_cooldowns():
            """ریست همه cooldown های فعال"""
            try:
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
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
 # ==================== STATS & UPLOAD APIs ====================
        
        @self.app.route('/api/stats', methods=['GET'])
        def get_stats():
            """دریافت آمار کلی سیستم"""
            try:
                cards = self.db.get_all_cards()
                players = self.db.get_leaderboard(1000)
                
                rarity_stats = {'normal': 0, 'epic': 0, 'legend': 0}
                for card in cards:
                    rarity_stats[card.rarity.value] += 1
                
                return jsonify({
                    'success': True,
                    'stats': {
                        'total_cards': len(cards),
                        'total_players': len(players),
                        'rarity_distribution': rarity_stats,
                        'avg_stats': self._calculate_avg_stats(cards) if cards else {}
                    }
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/card_images/<filename>')
        def serve_image(filename):
            """سرو کردن تصاویر کارت‌ها"""
            return send_from_directory('card_images', filename)
            
        @self.app.route('/api/upload_image', methods=['POST'])
        def upload_image():
            """Upload PNG/JPG image for card preview"""
            try:
                if 'image' not in request.files:
                    return jsonify({'success': False, 'message': '', 'error': 'No image file provided.'}), 400

                file = request.files['image']
                card_name = request.form.get('card_name', '').strip()

                if not file or file.filename == '':
                    return jsonify({'success': False, 'message': '', 'error': 'No selected file.'}), 400
                if not card_name:
                    return jsonify({'success': False, 'message': '', 'error': 'card_name is required.'}), 400

                filename = secure_filename(file.filename)
                ext = os.path.splitext(filename)[1].lower()
                allowed_exts = {'.png', '.jpg', '.jpeg'}
                if ext not in allowed_exts:
                    return jsonify({'success': False, 'message': '', 'error': 'Invalid file type. Only PNG and JPG are allowed.'}), 400

                os.makedirs('card_images', exist_ok=True)

                card_slug = card_name.lower().replace(' ', '_')
                save_name = f"{card_slug}{ext}"
                file_path = os.path.join('card_images', save_name)
                file.save(file_path)

                return jsonify({'success': True, 'message': 'Image uploaded successfully.', 'error': ''}), 200

            except Exception as e:
                return jsonify({'success': False, 'message': '', 'error': str(e)}), 500

        @self.app.route('/api/upload_sticker', methods=['POST'])
        def upload_sticker():
            """Upload WebP sticker"""
            try:
                if 'sticker' not in request.files:
                    return jsonify({'success': False, 'message': 'No sticker file provided.'}), 400

                file = request.files['sticker']
                if not file or file.filename == '':
                    return jsonify({'success': False, 'message': 'No selected file.'}), 400

                stickers_dir = os.path.join(os.getcwd(), 'stickers')
                os.makedirs(stickers_dir, exist_ok=True)

                filename = secure_filename(file.filename)
                save_path = os.path.join(stickers_dir, filename)
                file.save(save_path)

                return jsonify({'success': True, 'message': 'Sticker uploaded successfully', 'filename': filename}), 200

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
    
    def _calculate_avg_stats(self, cards):
        """محاسبه میانگین آمار کارت‌ها"""
        if not cards:
            return {}
        
        total_power = sum(card.power for card in cards)
        total_speed = sum(card.speed for card in cards)
        total_iq = sum(card.iq for card in cards)
        total_popularity = sum(card.popularity for card in cards)
        count = len(cards)
        
        return {
            'avg_power': round(total_power / count, 1),
            'avg_speed': round(total_speed / count, 1),
            'avg_iq': round(total_iq / count, 1),
            'avg_popularity': round(total_popularity / count, 1)
        }
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """اجرای سرور وب"""
        print(f"🌐 Starting Complete Web Management Panel on http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug, use_reloader=False)

def main():
    """اجرای سرور مدیریت وب"""
    db = DatabaseManager()
    api = WebAPI(db)
    api.run(debug=False, port=5000)

if __name__ == "__main__":
    main()