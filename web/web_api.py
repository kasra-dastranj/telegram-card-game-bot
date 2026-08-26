#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Complete Web API for Card Management with Individual Cooldown
API وب کامل برای مدیریت کارت‌ها با Cooldown جداگانه
"""

import os
import re
import sys
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from game_core import DatabaseManager, Card, CardRarity, CardManager, GameLogic
from systems.game_mode_system import CORE_STATS, QUICK_ARENAS, GameModeSystem

class WebAPI:
    def __init__(self, db_manager: DatabaseManager):
        self.app = Flask(__name__)
        self.app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
        CORS(self.app)
        
        self.db = db_manager
        self.card_manager = CardManager(db_manager)
        self.game_logic = GameLogic(db_manager)
        self.modes = GameModeSystem(db_manager)
        
        self.setup_routes()

    @staticmethod
    def _string_list(value, field_name):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            value = [part.strip() for part in value.split(',')]
        if not isinstance(value, list):
            raise ValueError(f'فیلد {field_name} باید لیست باشد')
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    def _validate_card_payload(self, data, existing_card=None):
        if not isinstance(data, dict):
            raise ValueError('بدنه درخواست باید JSON باشد')
        required = ('name', 'rarity', 'power', 'speed', 'iq', 'popularity')
        missing = [field for field in required if data.get(field) in (None, '')]
        if missing:
            raise ValueError('فیلدهای الزامی: ' + '، '.join(missing))

        name = str(data['name']).strip()
        if not name or len(name) > 100:
            raise ValueError('نام کارت باید بین ۱ تا ۱۰۰ کاراکتر باشد')
        try:
            rarity = CardRarity(str(data['rarity']).strip().lower())
        except ValueError as exc:
            raise ValueError('کمیابی کارت نامعتبر است') from exc

        stats = {}
        for stat in CORE_STATS:
            try:
                value = int(data[stat])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'مقدار {stat} باید عدد باشد') from exc
            if not 1 <= value <= 100:
                raise ValueError(f'مقدار {stat} باید بین ۱ تا ۱۰۰ باشد')
            stats[stat] = value

        card_type = str(data.get('card_type') or 'POWER_TYPE').strip().upper()
        allowed_types = {'POWER_TYPE', 'SPEED_TYPE', 'IQ_TYPE', 'POPULARITY_TYPE'}
        if card_type not in allowed_types:
            raise ValueError('نوع اصلی کارت نامعتبر است')

        hidden_stats = data.get('hidden_stats') or {}
        if not isinstance(hidden_stats, dict):
            raise ValueError('Hidden Stats باید یک object باشد')
        clean_hidden = {}
        for key, raw_value in hidden_stats.items():
            key = str(key).strip()
            if not key or raw_value in (None, ''):
                continue
            try:
                value = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Hidden Stat {key} باید عدد باشد') from exc
            if not 1 <= value <= 100:
                raise ValueError(f'Hidden Stat {key} باید بین ۱ تا ۱۰۰ باشد')
            clean_hidden[key] = value

        passive = data.get('passive') or {}
        if not isinstance(passive, dict):
            raise ValueError('Passive باید یک object باشد')
        if passive:
            effect = passive.get('effect') or {}
            condition = passive.get('condition') or {}
            if not isinstance(condition, dict):
                raise ValueError('شرط Passive باید یک object باشد')
            allowed_conditions = {'arena', 'opponent_name', 'opponent_trait'}
            unknown_conditions = set(condition) - allowed_conditions
            clean_condition = {
                key: str(value).strip()
                for key, value in condition.items()
                if key in allowed_conditions and str(value).strip()
            }
            if unknown_conditions or len(clean_condition) != 1:
                raise ValueError('Passive باید دقیقاً یک شرط معتبر داشته باشد')
            if clean_condition.get('arena') not in (
                None,
                *(arena['id'] for arena in QUICK_ARENAS),
            ):
                raise ValueError('میدان Passive نامعتبر است')
            if effect.get('stat') not in CORE_STATS:
                raise ValueError('Passive باید یکی از چهار Stat اصلی را تغییر دهد')
            try:
                effect['delta'] = int(effect.get('delta', 0))
            except (TypeError, ValueError) as exc:
                raise ValueError('مقدار Passive باید عدد باشد') from exc
            if not -100 <= effect['delta'] <= 100:
                raise ValueError('مقدار Passive باید بین ۱۰۰- تا ۱۰۰ باشد')
            passive = {
                'name': str(passive.get('name') or 'Passive').strip(),
                'condition': clean_condition,
                'effect': {'stat': effect['stat'], 'delta': effect['delta']},
            }

        created_at = existing_card.created_at if existing_card else datetime.now()
        card_id = existing_card.card_id if existing_card else str(uuid.uuid4())
        return {
            'card': Card(
                card_id=card_id,
                name=name,
                rarity=rarity,
                power=stats['power'],
                speed=stats['speed'],
                iq=stats['iq'],
                popularity=stats['popularity'],
                abilities=self._string_list(data.get('abilities'), 'abilities'),
                card_effects=self._string_list(data.get('card_effects'), 'card_effects'),
                dialogs=self._string_list(data.get('dialogs'), 'dialogs'),
                biography=str(data.get('biography') or '').strip(),
                image_path=str(data.get('image_path') or '').strip(),
                card_type=card_type,
                created_at=created_at,
            ),
            'metadata': {
                'traits': self._string_list(data.get('traits'), 'traits'),
                'series': str(data.get('series') or '').strip() or None,
                'hidden_stats': clean_hidden,
                'passive': passive,
            },
            'media': {
                'photo': str(data.get('photo_file_id') or '').strip(),
                'sticker': str(data.get('sticker_file_id') or '').strip(),
            },
        }

    def _save_card_extras(self, card_id, payload):
        metadata = payload['metadata']
        self.modes.set_card_metadata(card_id, **metadata)
        for kind, file_id in payload['media'].items():
            if file_id:
                self.db.set_card_media_file_id(card_id, file_id, kind)
            else:
                self.db.clear_card_media_file_id(card_id, kind)

    def _serialize_card(self, card):
        metadata = self.modes.get_card_metadata(card.card_id)
        return {
            'id': card.card_id,
            'name': card.name,
            'rarity': card.rarity.value,
            'power': card.power,
            'speed': card.speed,
            'iq': card.iq,
            'popularity': card.popularity,
            'card_type': card.card_type,
            'abilities': card.abilities,
            'card_effects': card.card_effects,
            'biography': card.biography,
            'dialogs': card.dialogs,
            'image_path': card.image_path,
            'traits': metadata['traits'],
            'series': metadata['series'] or '',
            'hidden_stats': metadata['hidden_stats'],
            'passive': metadata['passive'],
            'photo_file_id': self.db.get_card_media_file_id(card.card_id, 'photo') or '',
            'sticker_file_id': self.db.get_card_media_file_id(card.card_id, 'sticker') or '',
            'variants': self.db.get_card_variants(card.card_id),
            'created_at': card.created_at.isoformat(),
        }
    
    def setup_routes(self):
        """تنظیم مسیرهای API"""
        
        @self.app.route('/')
        def serve_frontend():
            """صفحه اصلی مدیریت کارت‌ها."""
            return send_from_directory(str(WEB_ROOT), 'card_management.html')

        @self.app.route('/legacy')
        def serve_legacy_frontend():
            """نسخه قدیمی پنل برای دسترسی موقت به ابزارهای جانبی."""
            return send_from_directory(str(WEB_ROOT), 'admin_panel_full.html')
        
        @self.app.route('/simple')
        def serve_simple():
            """پنل ساده"""
            return send_from_directory(str(WEB_ROOT), 'card_management.html')
        
        @self.app.route('/test')
        def serve_test():
            """صفحه تست API"""
            return jsonify({'success': True, 'service': 'TelBattle Card Admin API'})
        
        # ==================== EXISTING CARD APIs ====================
        
        @self.app.route('/api/cards', methods=['GET'])
        def get_all_cards():
            """دریافت تمام کارت‌ها"""
            try:
                cards = self.db.get_all_cards()
                cards_data = [self._serialize_card(card) for card in cards]
                
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
                data = request.get_json(silent=True) or {}
                payload = self._validate_card_payload(data)
                card = payload['card']
                
                existing_card = self.db.get_card_by_name(card.name)
                if existing_card:
                    return jsonify({
                        'success': False,
                        'error': 'کارت با این نام قبلاً وجود دارد'
                    }), 409
                
                if self.db.add_card(card):
                    self._save_card_extras(card.card_id, payload)
                    self.db.save_card_variant(
                        card.card_id,
                        card.rarity.value,
                        {
                            'power': card.power,
                            'speed': card.speed,
                            'iq': card.iq,
                            'popularity': card.popularity,
                            'abilities': card.abilities,
                            'card_effects': card.card_effects,
                            'image_path': card.image_path,
                            'card_type': card.card_type,
                            'passive': payload['metadata']['passive'],
                            'photo_file_id': payload['media'].get('photo', ''),
                            'sticker_file_id': payload['media'].get('sticker', ''),
                        },
                    )
                    return jsonify({
                        'success': True,
                        'message': f'کارت {card.name} با موفقیت اضافه شد',
                        'card': self._serialize_card(card),
                    }), 201
                else:
                    return jsonify({
                        'success': False,
                        'error': 'خطا در ذخیره کارت'
                    }), 500
                    
            except ValueError as e:
                return jsonify({'success': False, 'error': str(e)}), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/cards/<card_id>', methods=['PUT'])
        def update_card(card_id):
            """ویرایش تعریف اصلی و متادیتای مودهای جدید کارت."""
            try:
                existing = self.db.get_card_by_id(card_id)
                if not existing:
                    return jsonify({'success': False, 'error': 'کارت یافت نشد'}), 404
                payload = self._validate_card_payload(request.get_json(silent=True) or {}, existing)
                duplicate = self.db.get_card_by_name(payload['card'].name)
                if duplicate and duplicate.card_id != card_id:
                    return jsonify({'success': False, 'error': 'کارت دیگری با این نام وجود دارد'}), 409
                if not self.db.update_card(payload['card']):
                    return jsonify({'success': False, 'error': 'خطا در ویرایش کارت'}), 500
                self._save_card_extras(card_id, payload)
                return jsonify({
                    'success': True,
                    'message': f"کارت {payload['card'].name} به‌روزرسانی شد",
                    'card': self._serialize_card(payload['card']),
                })
            except ValueError as e:
                return jsonify({'success': False, 'error': str(e)}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/cards/<card_id>/variants/<rarity>', methods=['PUT'])
        def update_card_variant(card_id, rarity):
            """Save shared character details and exactly one Normal/Epic/Legend form."""
            try:
                existing = self.db.get_card_by_id(card_id)
                if not existing:
                    return jsonify({'success': False, 'error': 'کارت یافت نشد'}), 404
                if rarity not in {'normal', 'epic', 'legend'}:
                    return jsonify({'success': False, 'error': 'فرم کارت نامعتبر است'}), 400
                raw_data = request.get_json(silent=True) or {}
                payload = self._validate_card_payload(raw_data, existing)
                duplicate = self.db.get_card_by_name(payload['card'].name)
                if duplicate and duplicate.card_id != card_id:
                    return jsonify({'success': False, 'error': 'کارت دیگری با این نام وجود دارد'}), 409

                # متن، Trait، Series و Hidden Stats شخصیت‌محورند؛ اما مشخصات
                # جنگی و مدیا فقط به فرمی که کاربر انتخاب کرده تعلق دارد.
                shared = existing
                incoming = payload['card']
                shared.name = incoming.name
                shared.biography = incoming.biography
                shared.dialogs = incoming.dialogs
                if rarity == existing.rarity.value:
                    shared.power = incoming.power
                    shared.speed = incoming.speed
                    shared.iq = incoming.iq
                    shared.popularity = incoming.popularity
                    shared.abilities = incoming.abilities
                    shared.card_effects = incoming.card_effects
                    shared.image_path = incoming.image_path
                    shared.card_type = incoming.card_type
                if not self.db.update_card(shared):
                    return jsonify({'success': False, 'error': 'خطا در ویرایش کارت'}), 500

                old_metadata = self.modes.get_card_metadata(card_id)
                self.modes.set_card_metadata(
                    card_id,
                    traits=payload['metadata']['traits'],
                    series=payload['metadata']['series'],
                    hidden_stats=payload['metadata']['hidden_stats'],
                    passive=old_metadata.get('passive') or {},
                )
                variant = self.db.save_card_variant(
                    card_id,
                    rarity,
                    {
                        'power': incoming.power,
                        'speed': incoming.speed,
                        'iq': incoming.iq,
                        'popularity': incoming.popularity,
                        'abilities': incoming.abilities,
                        'card_effects': incoming.card_effects,
                        'image_path': incoming.image_path,
                        'card_type': incoming.card_type,
                        'passive': payload['metadata']['passive'],
                        'photo_file_id': payload['media'].get('photo', ''),
                        'sticker_file_id': payload['media'].get('sticker', ''),
                    },
                )
                fresh = self.db.get_card_by_id(card_id)
                return jsonify({
                    'success': True,
                    'message': f"فرم {rarity} کارت {fresh.name} به‌روزرسانی شد",
                    'card': self._serialize_card(fresh),
                    'variant': variant,
                })
            except ValueError as exc:
                return jsonify({'success': False, 'error': str(exc)}), 400
            except Exception as exc:
                return jsonify({'success': False, 'error': str(exc)}), 500
        
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
                
                rarity_stats = {rarity.value: 0 for rarity in CardRarity}
                for card in cards:
                    rarity_stats[card.rarity.value] = rarity_stats.get(card.rarity.value, 0) + 1
                
                # آمار PvP
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                # تعداد کل فایت‌ها
                try:
                    cursor.execute("SELECT COUNT(*) FROM fight_history WHERE fight_type = 'pvp'")
                    total_pvp_fights = cursor.fetchone()[0]
                except:
                    total_pvp_fights = 0
                
                # فایت‌های امروز
                try:
                    today = datetime.now().date().isoformat()
                    cursor.execute("SELECT COUNT(*) FROM fight_history WHERE fight_type = 'pvp' AND DATE(fought_at) = ?", (today,))
                    today_fights = cursor.fetchone()[0]
                except:
                    today_fights = 0
                
                # فایت‌های فعال
                try:
                    cursor.execute("SELECT COUNT(*) FROM active_fights WHERE status != 'completed'")
                    active_fights = cursor.fetchone()[0]
                except:
                    active_fights = 0
                
                conn.close()
                
                return jsonify({
                    'success': True,
                    'stats': {
                        'total_cards': len(cards),
                        'total_players': len(players),
                        'rarity_distribution': rarity_stats,
                        'avg_stats': self._calculate_avg_stats(cards) if cards else {},
                        'pvp_stats': {
                            'total_fights': total_pvp_fights,
                            'today_fights': today_fights,
                            'active_fights': active_fights
                        }
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
            return send_from_directory(str(PROJECT_ROOT / 'assets' / 'card_images'), filename)
            
        @self.app.route('/api/upload_image', methods=['POST'])
        def upload_image():
            """Upload PNG/JPG image for card preview"""
            try:
                if 'image' not in request.files:
                    return jsonify({'success': False, 'message': '', 'error': 'No image file provided.'}), 400

                file = request.files['image']
                card_name = request.form.get('card_name', '').strip()
                rarity = request.form.get('rarity', '').strip().lower()

                if not file or file.filename == '':
                    return jsonify({'success': False, 'message': '', 'error': 'No selected file.'}), 400
                if not card_name:
                    return jsonify({'success': False, 'message': '', 'error': 'card_name is required.'}), 400

                filename = secure_filename(file.filename)
                ext = os.path.splitext(filename)[1].lower()
                allowed_exts = {'.png', '.jpg', '.jpeg', '.webp'}
                if ext not in allowed_exts:
                    return jsonify({'success': False, 'message': '', 'error': 'Invalid file type. PNG, JPG or WebP expected.'}), 400

                images_dir = PROJECT_ROOT / 'assets' / 'card_images'
                images_dir.mkdir(parents=True, exist_ok=True)

                card_slug = secure_filename(card_name) or uuid.uuid5(uuid.NAMESPACE_DNS, card_name).hex[:12]
                if rarity in {'normal', 'epic', 'legend'}:
                    card_slug = f'{card_slug}_{rarity}'
                save_name = f"{card_slug}{ext}"
                file_path = images_dir / save_name
                file.save(file_path)

                return jsonify({
                    'success': True,
                    'message': 'Image uploaded successfully.',
                    'image_path': f'assets/card_images/{save_name}',
                    'preview_url': f'/card_images/{save_name}',
                    'error': '',
                }), 200

            except Exception as e:
                return jsonify({'success': False, 'message': '', 'error': str(e)}), 500

        @self.app.route('/api/upload_sticker', methods=['POST'])
        def upload_sticker():
            """Upload WebP sticker"""
            try:
                if 'sticker' not in request.files:
                    return jsonify({'success': False, 'message': 'No sticker file provided.'}), 400

                file = request.files['sticker']
                card_name = request.form.get('card_name', '').strip()
                rarity = request.form.get('rarity', '').strip().lower()
                if not file or file.filename == '':
                    return jsonify({'success': False, 'message': 'No selected file.'}), 400
                if not card_name:
                    return jsonify({'success': False, 'message': 'card_name is required.'}), 400

                original_name = secure_filename(file.filename)
                ext = os.path.splitext(original_name)[1].lower()
                if ext != '.webp':
                    return jsonify({'success': False, 'message': 'Sticker must be a WebP file.'}), 400

                stickers_dir = PROJECT_ROOT / 'assets' / 'stickers'
                stickers_dir.mkdir(parents=True, exist_ok=True)

                # Keep the saved asset discoverable by the battle media resolver.
                card_stem = card_name.upper().replace('-', '_').replace(' ', '_')
                card_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', card_stem).strip(' ._')
                if not card_stem:
                    card_stem = uuid.uuid5(uuid.NAMESPACE_DNS, card_name).hex[:12]
                if rarity in {'normal', 'epic', 'legend'}:
                    card_stem = f'{card_stem}_{rarity.upper()}'
                filename = f'{card_stem}.webp'
                save_path = stickers_dir / filename
                file.save(save_path)

                return jsonify({
                    'success': True,
                    'message': 'Sticker uploaded successfully',
                    'filename': filename,
                    'sticker_path': f'assets/stickers/{filename}',
                }), 200

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        # ==================== PLAYER MANAGEMENT APIs ====================
        
        @self.app.route('/api/players', methods=['GET'])
        def get_all_players():
            """دریافت لیست تمام بازیکنان"""
            try:
                limit = request.args.get('limit', 100, type=int)
                players = self.db.get_leaderboard(limit)
                
                players_data = []
                for player in players:
                    # دریافت آمار بازیکن
                    stats = self.db.get_player_stats(player.user_id)
                    card_count = len(self.db.get_player_cards(player.user_id))
                    
                    players_data.append({
                        'user_id': player.user_id,
                        'username': player.username or 'Unknown',
                        'first_name': player.first_name or 'Player',
                        'total_score': player.total_score,
                        'hearts': player.hearts,
                        'card_count': card_count,
                        'stats': stats.get('total', {})
                    })
                
                return jsonify({
                    'success': True,
                    'players': players_data,
                    'count': len(players_data)
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/players/<int:user_id>', methods=['GET'])
        def get_player_details(user_id):
            """دریافت جزئیات یک بازیکن"""
            try:
                player = self.db.get_or_create_player(user_id)
                if not player:
                    return jsonify({
                        'success': False,
                        'error': 'بازیکن یافت نشد'
                    }), 404
                
                cards = self.db.get_player_cards(user_id)
                stats = self.db.get_player_stats(user_id)
                rank = self.db.get_player_rank(user_id)
                
                return jsonify({
                    'success': True,
                    'player': {
                        'user_id': player.user_id,
                        'username': player.username,
                        'first_name': player.first_name,
                        'total_score': player.total_score,
                        'hearts': player.hearts,
                        'rank': rank,
                        'card_count': len(cards),
                        'cards': [{'id': c.card_id, 'name': c.name, 'rarity': c.rarity.value} for c in cards],
                        'stats': stats
                    }
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/players/<int:user_id>/reset-hearts', methods=['POST'])
        def reset_player_hearts(user_id):
            """ریست کردن جان‌های یک بازیکن"""
            try:
                player = self.db.get_or_create_player(user_id)
                if not player:
                    return jsonify({
                        'success': False,
                        'error': 'بازیکن یافت نشد'
                    }), 404
                
                player.hearts = self.game_logic.DAILY_HEARTS
                self.db.update_player(player)
                
                return jsonify({
                    'success': True,
                    'message': f'جان‌های بازیکن {player.first_name} ریست شد'
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # ==================== PVP MANAGEMENT APIs ====================
        
        @self.app.route('/api/pvp/active-fights', methods=['GET'])
        def get_active_fights():
            """دریافت لیست فایت‌های فعال"""
            try:
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT fight_id, challenger_id, opponent_id, chat_id, status, created_at
                    FROM active_fights
                    WHERE status != 'completed'
                    ORDER BY created_at DESC
                ''')
                
                fights = []
                for row in cursor.fetchall():
                    fights.append({
                        'fight_id': row[0],
                        'challenger_id': row[1],
                        'opponent_id': row[2],
                        'chat_id': row[3],
                        'status': row[4],
                        'created_at': row[5]
                    })
                
                conn.close()
                
                return jsonify({
                    'success': True,
                    'fights': fights,
                    'count': len(fights)
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/pvp/history', methods=['GET'])
        def get_pvp_history():
            """دریافت تاریخچه فایت‌های PvP"""
            try:
                limit = request.args.get('limit', 50, type=int)
                
                conn = sqlite3.connect(self.db.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT user_id, opponent_user_id, result, score_gained, hearts_lost, fought_at
                    FROM fight_history
                    WHERE fight_type = 'pvp'
                    ORDER BY fought_at DESC
                    LIMIT ?
                ''', (limit,))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        'user_id': row[0],
                        'opponent_id': row[1],
                        'result': row[2],
                        'score_gained': row[3],
                        'hearts_lost': row[4],
                        'fought_at': row[5]
                    })
                
                conn.close()
                
                return jsonify({
                    'success': True,
                    'history': history,
                    'count': len(history)
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/pvp/cleanup', methods=['POST'])
        def cleanup_expired_fights():
            """پاکسازی فایت‌های منقضی شده"""
            try:
                minutes = request.args.get('minutes', 15, type=int)
                deleted_count = self.db.cleanup_expired_fights(minutes)
                
                return jsonify({
                    'success': True,
                    'message': f'{deleted_count} فایت منقضی شده پاک شد',
                    'deleted_count': deleted_count
                })
                
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
    
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
    
    def run(self, host='127.0.0.1', port=5000, debug=False):
        """اجرای سرور وب"""
        print(f"🌐 Starting Complete Web Management Panel on http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug, use_reloader=False)

def main():
    """اجرای سرور مدیریت وب"""
    db = DatabaseManager()
    api = WebAPI(db)
    host = os.getenv('ADMIN_PANEL_HOST', '127.0.0.1')
    port = int(os.getenv('ADMIN_PANEL_PORT', '5000'))
    api.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()
