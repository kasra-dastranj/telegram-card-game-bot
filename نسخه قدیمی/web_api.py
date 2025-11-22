#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Web API for Card Management
API وب برای مدیریت کارت‌ها - فقط برای ادمین
"""

from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import json
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename

from game_core import DatabaseManager, Card, CardRarity, CardManager

class WebAPI:
    def __init__(self, db_manager: DatabaseManager):
        self.app = Flask(__name__)
        CORS(self.app)  # اجازه دسترسی از دامنه‌های مختلف
        
        self.db = db_manager
        self.card_manager = CardManager(db_manager)
        
        # تنظیم route های API
        self.setup_routes()
    
    def setup_routes(self):
        """تنظیم مسیرهای API"""
        
        @self.app.route('/')
        def serve_frontend():
            """صفحه اصلی مدیریت"""
            return send_from_directory('.', 'card_management.html')
        
        @self.app.route('/api/cards', methods=['GET'])
        def get_all_cards():
            """دریافت تمام کارت‌ها"""
            try:
                cards = self.db.get_all_cards()
                cards_data = []
                
                for card in cards:
                    dialogs_struct = self._get_card_dialogs_struct(card.name)
                    
                    # Fix for cards without biography
                    card_biography = getattr(card, 'biography', None)
                    if not card_biography or card_biography in ['', 'Biography not available.', None]:
                        # Try to get from dialogs file first
                        struct_bio = dialogs_struct.get('biography', '')
                        if struct_bio and struct_bio.strip():
                            card_biography = struct_bio
                        else:
                            # Generate default biography based on card name
                            card_biography = f"شخصیت {card.name} - یکی از شخصیت‌های قدرتمند این بازی با توانایی‌های منحصر به فرد."
                    # Merge dialogs from DB and file (victory_lines)
                    db_dialogs = getattr(card, 'dialogs', []) or []
                    file_dialogs = dialogs_struct.get('victory_lines', []) or []
                    merged_dialogs = list(dict.fromkeys([*db_dialogs, *file_dialogs]))
                    
                    card_dict = {
                        'id': card.card_id,
                        'name': card.name,
                        'rarity': card.rarity.value,
                        'power': card.power,
                        'speed': card.speed,
                        'iq': card.iq,
                        'popularity': card.popularity,
                        'abilities': card.abilities,
                        'biography': card_biography,
                        'dialogs': merged_dialogs,
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
                
                # اعتبارسنجی داده‌ها
                required_fields = ['name', 'rarity', 'power', 'speed', 'iq', 'popularity']
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'success': False,
                            'error': f'فیلد {field} الزامی است'
                        }), 400
                
                # بررسی تکراری نبودن نام
                existing_card = self.db.get_card_by_name(data['name'])
                if existing_card:
                    return jsonify({
                        'success': False,
                        'error': 'کارت با این نام قبلاً وجود دارد'
                    }), 409
                
                # Prepare dialogs with backward compatibility for single 'dialog'
                dialogs_input = data.get('dialogs', []) or []
                if isinstance(dialogs_input, str):
                    dialogs_input = [dialogs_input]
                single_dialog = data.get('dialog')
                if isinstance(single_dialog, str) and single_dialog.strip():
                    dialogs_input.append(single_dialog.strip())
                # Deduplicate while preserving order
                dialogs_input = list(dict.fromkeys(dialogs_input))

                # ایجاد کارت جدید
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
                    # Persist dialogs + biography to the dialogs file using the new structure
                    if ('dialogs' in data) or ('dialog' in data) or ('biography' in data):
                        self._save_card_dialogs_struct(card.name, dialogs_input, data.get('biography', ''))
                    
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
                    
            except ValueError as e:
                return jsonify({
                    'success': False,
                    'error': f'خطا در داده‌ها: {str(e)}'
                }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/cards/<card_id>', methods=['PUT'])
        def update_card(card_id):
            """بروزرسانی کارت موجود"""
            try:
                data = request.get_json()
                
                # پیدا کردن کارت
                card = self.db.get_card_by_id(card_id)
                if not card:
                    return jsonify({
                        'success': False,
                        'error': 'کارت یافت نشد'
                    }), 404
                
                # بروزرسانی اطلاعات کارت با نگاشت دقیق نام ستون‌های دیتابیس
                db_update = {}
                if 'name' in data:
                    db_update['name'] = data['name']
                if 'rarity' in data:
                    db_update['rarity'] = CardRarity(data['rarity']).value
                if 'power' in data:
                    db_update['power'] = int(data['power'])
                if 'speed' in data:
                    db_update['speed'] = int(data['speed'])
                if 'iq' in data:
                    db_update['iq'] = int(data['iq'])
                if 'popularity' in data:
                    db_update['popularity'] = int(data['popularity'])
                if 'abilities' in data:
                    db_update['abilities'] = data['abilities']
                if 'biography' in data:
                    db_update['biography'] = data['biography']
                # dialogs support with backward compatibility
                dialogs_payload = None
                has_dialogs = ('dialogs' in data) or ('dialog' in data)
                if has_dialogs:
                    base_dialogs = card.dialogs or []
                    if 'dialogs' in data:
                        incoming = data.get('dialogs') or []
                        if isinstance(incoming, str):
                            incoming = [incoming]
                        base_dialogs = incoming
                    single_dialog = data.get('dialog')
                    if isinstance(single_dialog, str) and single_dialog.strip():
                        base_dialogs = [*base_dialogs, single_dialog.strip()]
                    # dedup
                    dialogs_payload = list(dict.fromkeys(base_dialogs))
                    db_update['dialogs'] = dialogs_payload

                if self.db.update_card(card_id, **db_update):
                    new_name = data.get('name', card.name)
                    old_name = card.name
                    if new_name != old_name:
                        try:
                            self._rename_card_dialogs_entry(old_name, new_name)
                        except Exception:
                            pass
                    
                    if ('dialogs' in data) or ('dialog' in data) or ('biography' in data):
                        existing_struct = self._get_card_dialogs_struct(new_name)
                        victory_lines = dialogs_payload if dialogs_payload is not None else existing_struct.get('victory_lines', [])
                        biography = data.get('biography', card.biography or existing_struct.get('biography', ''))
                        self._save_card_dialogs_struct(new_name, victory_lines, biography)
                    
                    return jsonify({
                        'success': True,
                        'message': f'کارت بروزرسانی شد'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'خطا در ذخیره تغییرات'
                    }), 500
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500

        @self.app.route('/api/cards/<card_id>', methods=['GET'])
        def get_card(card_id):
            """دریافت اطلاعات یک کارت"""
            try:
                card = self.db.get_card_by_id(card_id)
                if not card:
                    return jsonify({'success': False, 'error': 'کارت یافت نشد'}), 404
                dialogs_struct = self._get_card_dialogs_struct(card.name)
                # biography with fallback
                card_biography = getattr(card, 'biography', None)
                if not card_biography or card_biography in ['', 'Biography not available.', None]:
                    struct_bio = dialogs_struct.get('biography', '')
                    if struct_bio and struct_bio.strip():
                        card_biography = struct_bio
                # dialogs merge
                db_dialogs = getattr(card, 'dialogs', []) or []
                file_dialogs = dialogs_struct.get('victory_lines', []) or []
                merged_dialogs = list(dict.fromkeys([*db_dialogs, *file_dialogs]))
                return jsonify({
                    'success': True,
                    'card': {
                        'id': card.card_id,
                        'name': card.name,
                        'rarity': card.rarity.value,
                        'power': card.power,
                        'speed': card.speed,
                        'iq': card.iq,
                        'popularity': card.popularity,
                        'abilities': card.abilities,
                        'biography': card_biography,
                        'dialogs': merged_dialogs,
                        'created_at': card.created_at.isoformat()
                    }
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
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
                    # After deleting DB record, remove related files on disk
                    try:
                        slug = (card.name or '').lower().replace(' ', '_')
                        possible_files = [
                            os.path.join('card_images', f'{slug}.png'),
                            os.path.join('card_images', f'{slug}.jpg'),
                            os.path.join('card_images', f'{slug}.jpeg'),
                            os.path.join('webp_cards', f'{slug}.webp'),
                        ]
                        for fp in possible_files:
                            try:
                                if os.path.exists(fp):
                                    os.remove(fp)
                                    print(f"🗑️ Deleted file: {fp}")
                            except Exception as rem_err:
                                print(f"⚠️ Failed to delete file {fp}: {rem_err}")
                    except Exception as cleanup_err:
                        print(f"⚠️ Cleanup error after deleting card {card.name}: {cleanup_err}")

                    return jsonify({
                        'success': True,
                        'message': 'Card and linked files deleted successfully.'
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
        
        @self.app.route('/api/stats', methods=['GET'])
        def get_stats():
            """دریافت آمار کلی سیستم"""
            try:
                cards = self.db.get_all_cards()
                players = self.db.get_leaderboard(1000)
                
                # آمار کارت‌ها بر اساس کمیابی
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
            """Upload PNG/JPG image for card preview (no auto-conversion)."""
            try:
                if 'image' not in request.files:
                    return jsonify({'success': False, 'message': '', 'error': 'No image file provided.'}), 400

                file = request.files['image']
                card_name = request.form.get('card_name', '').strip()

                if not file or file.filename == '':
                    return jsonify({'success': False, 'message': '', 'error': 'No selected file.'}), 400
                if not card_name:
                    return jsonify({'success': False, 'message': '', 'error': 'card_name is required.'}), 400

                # Validate extension
                filename = secure_filename(file.filename)
                ext = os.path.splitext(filename)[1].lower()
                allowed_exts = {'.png', '.jpg', '.jpeg'}
                if ext not in allowed_exts:
                    return jsonify({'success': False, 'message': '', 'error': 'Invalid file type. Only PNG and JPG are allowed.'}), 400

                # Ensure destination directory exists
                os.makedirs('card_images', exist_ok=True)

                # Save using card slug + original extension to avoid implicit conversion
                card_slug = card_name.lower().replace(' ', '_')
                save_name = f"{card_slug}{ext}"
                file_path = os.path.join('card_images', save_name)
                file.save(file_path)

                return jsonify({'success': True, 'message': 'Image uploaded successfully.', 'error': ''}), 200

            except Exception as e:
                return jsonify({'success': False, 'message': '', 'error': str(e)}), 500

        @self.app.route('/api/upload_sticker', methods=['POST'])
        def upload_sticker():
            """Upload sticker. Saves to stickers/ and attempts PNG/JPG -> WebP conversion."""
            try:
                if 'sticker' not in request.files:
                    return jsonify({'success': False, 'message': 'No sticker file provided.'}), 400

                file = request.files['sticker']
                if not file or file.filename == '':
                    return jsonify({'success': False, 'message': 'No selected file.'}), 400

                # Ensure destination directory exists
                stickers_dir = os.path.join(os.getcwd(), 'stickers')
                os.makedirs(stickers_dir, exist_ok=True)

                # Save original file
                filename = secure_filename(file.filename)
                save_path = os.path.join(stickers_dir, filename)
                file.save(save_path)

                # Attempt conversion for PNG/JPG to WebP
                ext = os.path.splitext(filename)[1].lower()
                return_filename = filename
                try:
                    if ext in {'.png', '.jpg', '.jpeg'}:
                        base = os.path.splitext(filename)[0]
                        webp_name = f"{base}.webp"
                        webp_path = os.path.join(stickers_dir, webp_name)
                        try:
                            import subprocess
                            subprocess.run(['cwebp', '-q', '90', save_path, '-o', webp_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            return_filename = webp_name
                        except Exception:
                            try:
                                from PIL import Image
                                im = Image.open(save_path).convert('RGBA')
                                im.save(webp_path, 'WEBP', quality=90, method=6)
                                return_filename = webp_name
                            except Exception:
                                # Conversion failed; keep original
                                pass
                    elif ext == '.webp':
                        # Already WebP; just return the same filename
                        return_filename = filename
                except Exception:
                    # Silently ignore conversion issues; upload still succeeded
                    pass

                return jsonify({'success': True, 'message': 'Sticker uploaded successfully', 'filename': return_filename}), 200

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
    
    def _read_dialogs_file(self) -> dict:
        """Read dialogs file safely and return a dict."""
        dialogs_file = "card_dialogs.json"
        if os.path.exists(dialogs_file):
            try:
                with open(dialogs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def _write_dialogs_file(self, data: dict):
        """Write dialogs data back to file."""
        dialogs_file = "card_dialogs.json"
        with open(dialogs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_card_dialogs_struct(self, card_name: str) -> dict:
        """Return {'biography': str, 'victory_lines': list} with backward compatibility."""
        data = self._read_dialogs_file()
        value = data.get(card_name)
        if isinstance(value, list):
            # Old format
            return {'biography': '', 'victory_lines': value}
        elif isinstance(value, dict):
            bio = value.get('biography', '')
            lines = value.get('victory_lines', [])
            if isinstance(lines, list):
                pass
            elif isinstance(lines, str) and lines:
                lines = [lines]
            else:
                lines = []
            return {'biography': bio, 'victory_lines': lines}
        else:
            return {'biography': '', 'victory_lines': []}

    def _get_card_victory_lines(self, card_name: str) -> list:
        struct = self._get_card_dialogs_struct(card_name)
        return struct.get('victory_lines', [])

    def _save_card_dialogs_struct(self, card_name: str, victory_lines: list, biography: str):
        """Save new structure for a card."""
        data = self._read_dialogs_file()
        data[card_name] = {
            'biography': biography or '',
            'victory_lines': victory_lines or []
        }
        self._write_dialogs_file(data)

    def _rename_card_dialogs_entry(self, old_name: str, new_name: str):
        """If the card is renamed, move its dialogs entry to the new key."""
        if not old_name or not new_name or old_name == new_name:
            return
        data = self._read_dialogs_file()
        if old_name in data:
            # If destination exists, keep destination and drop old to avoid unexpected merge
            if new_name not in data:
                data[new_name] = data[old_name]
            data.pop(old_name, None)
            self._write_dialogs_file(data)
    
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
        print(f"🌐 Starting Web Management Panel on http://{host}:{port}")
        # Disable auto-reloader to avoid duplicate processes when running in background
        self.app.run(host=host, port=port, debug=debug, use_reloader=False)

def main():
    """اجرای سرور مدیریت وب"""
    db = DatabaseManager()
    api = WebAPI(db)
    api.run(debug=False, port=5000)

if __name__ == "__main__":
    main()