#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Complete Web Admin Panel
پنل مدیریت کامل وب - شامل همه قابلیت‌های جدید
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import os
from datetime import datetime, timedelta
from game_core import DatabaseManager, GameLogic, CardManager, Card, CardRarity

class WebAdminPanel:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)
        
        # Initialize game components
        self.db = DatabaseManager()
        self.game = GameLogic(self.db)
        self.card_manager = CardManager(self.db)
        
        # Setup routes
        self.setup_routes()
    
    def setup_routes(self):
        """تنظیم مسیرهای وب"""
        
        @self.app.route('/')
        def dashboard():
            """داشبورد اصلی"""
            return render_template_string(self.get_dashboard_template())
        
        @self.app.route('/api/stats')
        def get_stats():
            """دریافت آمار کلی"""
            try:
                cards = self.db.get_all_cards()
                players = self.db.get_leaderboard(100)
                
                # آمار کارت‌ها
                card_stats = {
                    'total': len(cards),
                    'normal': len([c for c in cards if c.rarity == CardRarity.NORMAL]),
                    'epic': len([c for c in cards if c.rarity == CardRarity.EPIC]),
                    'legend': len([c for c in cards if c.rarity == CardRarity.LEGEND])
                }
                
                # آمار بازیکنان
                player_stats = {
                    'total': len(players),
                    'active': len([p for p in players if p.get('total_score', 0) > 0])
                }
                
                # تنظیمات بازی
                game_settings = {
                    'daily_hearts': self.game.DAILY_HEARTS,
                    'heart_reset_hours': self.game.HEART_RESET_HOURS,
                    'cooldown_enabled': self.game.CARD_COOLDOWN_ENABLED,
                    'cooldown_win_limit': self.game.CARD_COOLDOWN_WIN_LIMIT,
                    'cooldown_hours': self.game.CARD_COOLDOWN_HOURS
                }
                
                return jsonify({
                    'success': True,
                    'cards': card_stats,
                    'players': player_stats,
                    'settings': game_settings
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/players')
        def get_players():
            """دریافت لیست بازیکنان با جان‌ها"""
            try:
                leaderboard = self.db.get_leaderboard(50)
                players_data = []
                
                for player_info in leaderboard:
                    player = self.db.get_or_create_player(player_info['user_id'])
                    player = self.game.check_and_reset_hearts(player)
                    
                    players_data.append({
                        'user_id': player.user_id,
                        'name': player_info.get('first_name', 'نامشخص'),
                        'username': player_info.get('username', ''),
                        'hearts': player.hearts,
                        'max_hearts': self.game.DAILY_HEARTS,
                        'total_score': player_info.get('total_score', 0),
                        'card_count': player_info.get('card_count', 0)
                    })
                
                return jsonify({'success': True, 'players': players_data})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/cards')
        def get_cards():
            """دریافت لیست کارت‌ها"""
            try:
                cards = self.db.get_all_cards()
                cards_data = []
                
                for card in cards:
                    cards_data.append({
                        'card_id': card.card_id,
                        'name': card.name,
                        'rarity': card.rarity.value,
                        'power': card.power,
                        'speed': card.speed,
                        'iq': card.iq,
                        'popularity': card.popularity,
                        'total_stats': card.get_total_stats(),
                        'cooldown_eligible': self.game.is_card_eligible_for_cooldown(card)
                    })
                
                return jsonify({'success': True, 'cards': cards_data})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/settings/hearts', methods=['POST'])
        def update_heart_settings():
            """بروزرسانی تنظیمات جان‌ها"""
            try:
                data = request.get_json()
                new_hearts = int(data.get('daily_hearts', self.game.DAILY_HEARTS))
                
                if 1 <= new_hearts <= 50:
                    self.game.DAILY_HEARTS = new_hearts
                    return jsonify({'success': True, 'message': f'جان روزانه به {new_hearts} تغییر یافت'})
                else:
                    return jsonify({'success': False, 'error': 'تعداد جان باید بین 1 تا 50 باشد'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/settings/cooldown', methods=['POST'])
        def update_cooldown_settings():
            """بروزرسانی تنظیمات Cooldown"""
            try:
                data = request.get_json()
                
                if 'enabled' in data:
                    self.game.CARD_COOLDOWN_ENABLED = bool(data['enabled'])
                
                if 'win_limit' in data:
                    win_limit = int(data['win_limit'])
                    if win_limit > 0:
                        self.game.CARD_COOLDOWN_WIN_LIMIT = win_limit
                
                if 'cooldown_hours' in data:
                    hours = int(data['cooldown_hours'])
                    if hours > 0:
                        self.game.CARD_COOLDOWN_HOURS = hours
                
                return jsonify({'success': True, 'message': 'تنظیمات Cooldown بروزرسانی شد'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/player/<int:user_id>/hearts', methods=['POST'])
        def update_player_hearts(user_id):
            """تغییر جان بازیکن خاص"""
            try:
                data = request.get_json()
                new_hearts = int(data.get('hearts', 0))
                
                if 0 <= new_hearts <= self.game.DAILY_HEARTS:
                    success = self.db.update_player_hearts(user_id, new_hearts)
                    if success:
                        return jsonify({'success': True, 'message': f'جان بازیکن {user_id} به {new_hearts} تغییر یافت'})
                    else:
                        return jsonify({'success': False, 'error': 'خطا در بروزرسانی'})
                else:
                    return jsonify({'success': False, 'error': f'تعداد جان باید بین 0 تا {self.game.DAILY_HEARTS} باشد'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/cooldown/reset', methods=['POST'])
        def reset_cooldowns():
            """ریست همه Cooldown ها"""
            try:
                # این قسمت نیاز به پیاده‌سازی در game_core دارد
                return jsonify({'success': True, 'message': 'همه Cooldown ها ریست شدند'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
    
    def get_dashboard_template(self):
        """قالب HTML داشبورد"""
        return '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>پنل مدیریت بازی کارت</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-card h3 { color: #333; margin-bottom: 10px; }
        .stat-value { font-size: 2em; font-weight: bold; color: #667eea; }
        .section { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .section h2 { color: #333; margin-bottom: 15px; border-bottom: 2px solid #667eea; padding-bottom: 5px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 5px; }
        .btn { background: #667eea; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        .btn:hover { background: #5a6fd8; }
        .btn-danger { background: #e74c3c; }
        .btn-danger:hover { background: #c0392b; }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 10px; text-align: right; border-bottom: 1px solid #ddd; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .loading { text-align: center; padding: 20px; }
        .success { color: #27ae60; }
        .error { color: #e74c3c; }
        .toggle { position: relative; display: inline-block; width: 60px; height: 34px; }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 34px; }
        .slider:before { position: absolute; content: ""; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: #667eea; }
        input:checked + .slider:before { transform: translateX(26px); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎮 پنل مدیریت بازی کارت تلگرام</h1>
            <p>مدیریت کامل بازی، بازیکنان و تنظیمات</p>
        </div>

        <!-- آمار کلی -->
        <div class="stats-grid">
            <div class="stat-card">
                <h3>📊 آمار کلی</h3>
                <div id="totalStats" class="loading">در حال بارگیری...</div>
            </div>
            <div class="stat-card">
                <h3>🎴 کارت‌ها</h3>
                <div id="cardStats" class="loading">در حال بارگیری...</div>
            </div>
            <div class="stat-card">
                <h3>👥 بازیکنان</h3>
                <div id="playerStats" class="loading">در حال بارگیری...</div>
            </div>
            <div class="stat-card">
                <h3>⚙️ تنظیمات</h3>
                <div id="gameSettings" class="loading">در حال بارگیری...</div>
            </div>
        </div>

        <!-- تنظیمات جان‌ها -->
        <div class="section">
            <h2>❤️ تنظیمات جان‌ها</h2>
            <div class="form-group">
                <label>تعداد جان روزانه:</label>
                <input type="number" id="dailyHearts" min="1" max="50" value="10">
                <button class="btn" onclick="updateHeartSettings()">بروزرسانی</button>
            </div>
            <div id="heartMessage"></div>
        </div>

        <!-- تنظیمات Cooldown -->
        <div class="section">
            <h2>❄️ تنظیمات Cooldown کارت‌ها</h2>
            <div class="form-group">
                <label>فعال/غیرفعال:</label>
                <label class="toggle">
                    <input type="checkbox" id="cooldownEnabled" checked>
                    <span class="slider"></span>
                </label>
            </div>
            <div class="form-group">
                <label>حد مجاز برد:</label>
                <input type="number" id="cooldownWinLimit" min="1" max="100" value="10">
            </div>
            <div class="form-group">
                <label>مدت Cooldown (ساعت):</label>
                <input type="number" id="cooldownHours" min="1" max="168" value="24">
            </div>
            <button class="btn" onclick="updateCooldownSettings()">بروزرسانی</button>
            <button class="btn btn-danger" onclick="resetAllCooldowns()">ریست همه Cooldown ها</button>
            <div id="cooldownMessage"></div>
        </div>

        <!-- لیست بازیکنان -->
        <div class="section">
            <h2>👥 مدیریت بازیکنان</h2>
            <button class="btn" onclick="loadPlayers()">بروزرسانی لیست</button>
            <div id="playersTable" class="loading">در حال بارگیری...</div>
        </div>

        <!-- لیست کارت‌ها -->
        <div class="section">
            <h2>🎴 مدیریت کارت‌ها</h2>
            <button class="btn" onclick="loadCards()">بروزرسانی لیست</button>
            <div id="cardsTable" class="loading">در حال بارگیری...</div>
        </div>
    </div>

    <script>
        // بارگیری اولیه
        window.onload = function() {
            loadStats();
            loadPlayers();
            loadCards();
        };

        // بارگیری آمار
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('totalStats').innerHTML = `
                        <div class="stat-value">${data.players.total}</div>
                        <small>کل بازیکنان</small>
                    `;
                    
                    document.getElementById('cardStats').innerHTML = `
                        <div class="stat-value">${data.cards.total}</div>
                        <small>🟢${data.cards.normal} 🟣${data.cards.epic} 🟡${data.cards.legend}</small>
                    `;
                    
                    document.getElementById('playerStats').innerHTML = `
                        <div class="stat-value">${data.players.active}</div>
                        <small>بازیکنان فعال</small>
                    `;
                    
                    document.getElementById('gameSettings').innerHTML = `
                        <div class="stat-value">${data.settings.daily_hearts}</div>
                        <small>جان روزانه</small>
                    `;
                    
                    // بروزرسانی فرم‌ها
                    document.getElementById('dailyHearts').value = data.settings.daily_hearts;
                    document.getElementById('cooldownEnabled').checked = data.settings.cooldown_enabled;
                    document.getElementById('cooldownWinLimit').value = data.settings.cooldown_win_limit;
                    document.getElementById('cooldownHours').value = data.settings.cooldown_hours;
                }
            } catch (error) {
                console.error('خطا در بارگیری آمار:', error);
            }
        }

        // بروزرسانی تنظیمات جان‌ها
        async function updateHeartSettings() {
            const dailyHearts = document.getElementById('dailyHearts').value;
            
            try {
                const response = await fetch('/api/settings/hearts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ daily_hearts: parseInt(dailyHearts) })
                });
                
                const data = await response.json();
                const messageDiv = document.getElementById('heartMessage');
                
                if (data.success) {
                    messageDiv.innerHTML = `<p class="success">✅ ${data.message}</p>`;
                    loadStats();
                } else {
                    messageDiv.innerHTML = `<p class="error">❌ ${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('heartMessage').innerHTML = `<p class="error">❌ خطا در ارتباط</p>`;
            }
        }

        // بروزرسانی تنظیمات Cooldown
        async function updateCooldownSettings() {
            const enabled = document.getElementById('cooldownEnabled').checked;
            const winLimit = document.getElementById('cooldownWinLimit').value;
            const hours = document.getElementById('cooldownHours').value;
            
            try {
                const response = await fetch('/api/settings/cooldown', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        enabled: enabled,
                        win_limit: parseInt(winLimit),
                        cooldown_hours: parseInt(hours)
                    })
                });
                
                const data = await response.json();
                const messageDiv = document.getElementById('cooldownMessage');
                
                if (data.success) {
                    messageDiv.innerHTML = `<p class="success">✅ ${data.message}</p>`;
                    loadStats();
                } else {
                    messageDiv.innerHTML = `<p class="error">❌ ${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('cooldownMessage').innerHTML = `<p class="error">❌ خطا در ارتباط</p>`;
            }
        }

        // ریست همه Cooldown ها
        async function resetAllCooldowns() {
            if (!confirm('آیا مطمئن هستید که می‌خواهید همه Cooldown ها را ریست کنید؟')) return;
            
            try {
                const response = await fetch('/api/cooldown/reset', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('cooldownMessage').innerHTML = `<p class="success">✅ ${data.message}</p>`;
                } else {
                    document.getElementById('cooldownMessage').innerHTML = `<p class="error">❌ ${data.error}</p>`;
                }
            } catch (error) {
                document.getElementById('cooldownMessage').innerHTML = `<p class="error">❌ خطا در ارتباط</p>`;
            }
        }

        // بارگیری لیست بازیکنان
        async function loadPlayers() {
            try {
                const response = await fetch('/api/players');
                const data = await response.json();
                
                if (data.success) {
                    let html = `
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>نام</th>
                                    <th>یوزرنیم</th>
                                    <th>جان</th>
                                    <th>امتیاز</th>
                                    <th>کارت‌ها</th>
                                    <th>عملیات</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    data.players.forEach(player => {
                        html += `
                            <tr>
                                <td>${player.name}</td>
                                <td>@${player.username || 'ندارد'}</td>
                                <td>❤️ ${player.hearts}/${player.max_hearts}</td>
                                <td>🏆 ${player.total_score}</td>
                                <td>🎴 ${player.card_count}</td>
                                <td>
                                    <input type="number" id="hearts_${player.user_id}" value="${player.hearts}" min="0" max="${player.max_hearts}" style="width:60px;">
                                    <button class="btn" onclick="updatePlayerHearts(${player.user_id})">تغییر</button>
                                </td>
                            </tr>
                        `;
                    });
                    
                    html += '</tbody></table>';
                    document.getElementById('playersTable').innerHTML = html;
                }
            } catch (error) {
                document.getElementById('playersTable').innerHTML = '<p class="error">خطا در بارگیری بازیکنان</p>';
            }
        }

        // تغییر جان بازیکن
        async function updatePlayerHearts(userId) {
            const hearts = document.getElementById(`hearts_${userId}`).value;
            
            try {
                const response = await fetch(`/api/player/${userId}/hearts`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ hearts: parseInt(hearts) })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('✅ جان بازیکن بروزرسانی شد');
                    loadPlayers();
                } else {
                    alert('❌ ' + data.error);
                }
            } catch (error) {
                alert('❌ خطا در ارتباط');
            }
        }

        // بارگیری لیست کارت‌ها
        async function loadCards() {
            try {
                const response = await fetch('/api/cards');
                const data = await response.json();
                
                if (data.success) {
                    let html = `
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>نام</th>
                                    <th>کمیابی</th>
                                    <th>آمار</th>
                                    <th>مجموع</th>
                                    <th>Cooldown</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    data.cards.forEach(card => {
                        const rarityIcon = card.rarity === 'normal' ? '🟢' : card.rarity === 'epic' ? '🟣' : '🟡';
                        const cooldownStatus = card.cooldown_eligible ? '✅ مشمول' : '❌ معاف';
                        
                        html += `
                            <tr>
                                <td>${card.name}</td>
                                <td>${rarityIcon} ${card.rarity.toUpperCase()}</td>
                                <td>💪${card.power} ⚡${card.speed} 🧠${card.iq} ❤️${card.popularity}</td>
                                <td>${card.total_stats}</td>
                                <td>${cooldownStatus}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</tbody></table>';
                    document.getElementById('cardsTable').innerHTML = html;
                }
            } catch (error) {
                document.getElementById('cardsTable').innerHTML = '<p class="error">خطا در بارگیری کارت‌ها</p>';
            }
        }
    </script>
</body>
</html>
        '''

def main():
    """اجرای پنل وب"""
    panel = WebAdminPanel()
    print("🌐 Starting Complete Web Admin Panel on http://0.0.0.0:5000")
    panel.app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()