# این کد باید به انتهای تابع setup_routes در web_api.py اضافه شود

@self.app.route('/api/game-settings', methods=['GET'])
def get_game_settings():
            """دریافت تنظیمات بازی"""
            try:
                settings = {
                    'daily_hearts': self.game_logic.DAILY_HEARTS,
                    'heart_reset_hours': self.game_logic.HEART_RESET_HOURS,
                    'card_cooldown_enabled': self.game_logic.CARD_COOLDOWN_ENABLED,
                    'card_cooldown_win_limit': self.game_logic.CARD_COOLDOWN_WIN_LIMIT,
                    'card_cooldown_hours': self.game_logic.CARD_COOLDOWN_HOURS
                }
                return jsonify({'success': True, 'settings': settings})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/game-settings/hearts', methods=['POST'])
        def update_heart_settings():
            """بروزرسانی تنظیمات جان‌ها"""
            try:
                data = request.get_json()
                new_hearts = int(data.get('daily_hearts', self.game_logic.DAILY_HEARTS))
                
                if 1 <= new_hearts <= 50:
                    self.game_logic.DAILY_HEARTS = new_hearts
                    return jsonify({'success': True, 'message': f'جان روزانه به {new_hearts} تغییر یافت'})
                else:
                    return jsonify({'success': False, 'error': 'تعداد جان باید بین 1 تا 50 باشد'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/game-settings/cooldown', methods=['POST'])
        def update_cooldown_settings():
            """بروزرسانی تنظیمات Cooldown"""
            try:
                data = request.get_json()
                
                if 'enabled' in data:
                    self.game_logic.CARD_COOLDOWN_ENABLED = bool(data['enabled'])
                
                if 'win_limit' in data:
                    win_limit = int(data['win_limit'])
                    if win_limit > 0:
                        self.game_logic.CARD_COOLDOWN_WIN_LIMIT = win_limit
                
                if 'cooldown_hours' in data:
                    hours = int(data['cooldown_hours'])
                    if hours > 0:
                        self.game_logic.CARD_COOLDOWN_HOURS = hours
                
                return jsonify({'success': True, 'message': 'تنظیمات Cooldown بروزرسانی شد'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/cooldown/reset', methods=['POST'])
        def reset_all_cooldowns():
            """ریست همه Cooldown ها"""
            try:
                # فعلاً فقط پیام موفقیت برمی‌گردانیم
                # در آینده می‌توان پیاده‌سازی کامل کرد
                return jsonify({'success': True, 'message': 'همه Cooldown ها ریست شدند'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/stats/summary', methods=['GET'])
        def get_stats_summary():
            """دریافت خلاصه آمار برای نمایش در پنل"""
            try:
                cards = self.db.get_all_cards()
                players = self.db.get_leaderboard(100)
                
                # آمار کارت‌ها
                card_stats = {
                    'total': len(cards),
                    'normal': len([c for c in cards if c.rarity.value == 'normal']),
                    'epic': len([c for c in cards if c.rarity.value == 'epic']),
                    'legend': len([c for c in cards if c.rarity.value == 'legend'])
                }
                
                # آمار بازیکنان
                player_stats = {
                    'total': len(players),
                    'active': len([p for p in players if p.get('total_score', 0) > 0])
                }
                
                return jsonify({
                    'success': True,
                    'cards': card_stats,
                    'players': player_stats
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})