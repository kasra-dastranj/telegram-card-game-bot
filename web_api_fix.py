#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Web API Fix - اضافه کردن API های جدید به web_api.py
"""

# این کد باید قبل از تابع run در کلاس WebAPI اضافه شود:

API_ADDITIONS = '''
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
        
        @self.app.route('/api/players-hearts', methods=['GET'])
        def get_players_hearts():
            """دریافت جان‌های بازیکنان"""
            try:
                leaderboard = self.db.get_leaderboard(50)
                players_hearts = []
                
                for player in leaderboard:
                    player_obj = self.db.get_or_create_player(player['user_id'])
                    player_obj = self.game_logic.check_and_reset_hearts(player_obj)
                    
                    players_hearts.append({
                        'user_id': player['user_id'],
                        'name': player.get('first_name', 'نامشخص'),
                        'hearts': getattr(player_obj, 'hearts', self.game_logic.DAILY_HEARTS),
                        'max_hearts': self.game_logic.DAILY_HEARTS,
                        'total_score': player.get('total_score', 0)
                    })
                
                return jsonify({'success': True, 'players': players_hearts})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
'''

print("API additions ready for manual insertion into web_api.py")
print("Insert before the 'def run(self, host=' line in the WebAPI class")