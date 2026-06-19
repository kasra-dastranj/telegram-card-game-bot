#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Analytics Web Panel - پنل وب آنالیتیکس
پنل جداگانه برای مشاهده آمار و ارزش‌گذاری ربات
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from systems.analytics_system import BotAnalytics

app = Flask(__name__)
CORS(app)

analytics = BotAnalytics()

@app.route('/')
def dashboard():
    """داشبورد اصلی"""
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/report')
def get_report():
    """API گزارش جامع"""
    try:
        report = analytics.get_comprehensive_report()
        return jsonify({'success': True, 'data': report})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/valuation')
def get_valuation():
    """API ارزش‌گذاری"""
    try:
        valuation = analytics.calculate_bot_value()
        return jsonify({'success': True, 'data': valuation})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/users')
def get_users():
    """API آمار کاربران"""
    try:
        data = {
            'total': analytics.get_total_users(),
            'active_7d': analytics.get_active_users(7),
            'active_30d': analytics.get_active_users(30),
            'growth': analytics.get_user_growth_rate(),
            'retention': analytics.get_user_retention()
        }
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups')
def get_groups():
    """API آمار گروه‌ها"""
    try:
        data = analytics.get_group_stats()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fights')
def get_fights():
    """API آمار فایت‌ها"""
    try:
        data = {
            'last_7_days': analytics.get_fight_stats(7),
            'last_30_days': analytics.get_fight_stats(30),
            'peak_hours': analytics.get_peak_hours()
        }
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# HTML Template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 پنل آنالیتیکس ربات</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
            text-align: center;
        }
        .header h1 { color: #667eea; font-size: 2.5em; margin-bottom: 10px; }
        .header p { color: #666; font-size: 1.1em; }
        
        .grid { display: grid; gap: 20px; margin-bottom: 30px; }
        .grid-2 { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
        .grid-3 { grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }
        .grid-4 { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
        
        .card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        .card:hover { transform: translateY(-5px); }
        
        .card h3 { color: #333; margin-bottom: 15px; font-size: 1.2em; }
        .card .value { font-size: 2.5em; font-weight: bold; color: #667eea; margin: 10px 0; }
        .card .label { color: #666; font-size: 0.9em; }
        .card .sub-value { color: #888; font-size: 0.9em; margin-top: 10px; }
        
        .valuation-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .valuation-card h2 { font-size: 2em; margin-bottom: 20px; }
        .valuation-card .score { font-size: 4em; font-weight: bold; margin: 20px 0; }
        .valuation-card .rating { font-size: 1.3em; margin: 15px 0; opacity: 0.9; }
        .valuation-card .price { font-size: 2.5em; margin: 20px 0; }
        
        .recommendations {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }
        .recommendations h4 { color: #856404; margin-bottom: 10px; }
        .recommendations ul { list-style: none; }
        .recommendations li { padding: 5px 0; color: #856404; }
        .recommendations li:before { content: "💡 "; }
        
        .chart-container {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        
        .progress-bar {
            background: #e0e0e0;
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            height: 100%;
            transition: width 0.5s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .loading {
            text-align: center;
            padding: 50px;
            font-size: 1.5em;
            color: white;
        }
        
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 25px;
            font-size: 1em;
            cursor: pointer;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            transition: all 0.3s;
        }
        .refresh-btn:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 7px 20px rgba(0,0,0,0.3);
        }
        
        .badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            margin: 5px;
        }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-danger { background: #f8d7da; color: #721c24; }
        .badge-info { background: #d1ecf1; color: #0c5460; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 پنل آنالیتیکس و ارزش‌گذاری ربات</h1>
            <p>آمار جامع برای تصمیم‌گیری هوشمندانه</p>
            <button class="refresh-btn" onclick="loadAllData()">🔄 بروزرسانی داده‌ها</button>
        </div>

        <div id="loading" class="loading">⏳ در حال بارگیری داده‌ها...</div>
        
        <div id="content" style="display: none;">
            <!-- ارزش‌گذاری -->
            <div class="valuation-card" id="valuationCard">
                <h2>💰 ارزش‌گذاری ربات</h2>
                <div class="score" id="totalScore">-</div>
                <div class="rating" id="rating">-</div>
                <div class="price" id="estimatedValue">-</div>
                <div class="recommendations" id="recommendations"></div>
            </div>

            <!-- آمار کلیدی -->
            <div class="grid grid-4" style="margin-top: 30px;">
                <div class="card">
                    <h3>👥 کل کاربران</h3>
                    <div class="value" id="totalUsers">-</div>
                    <div class="sub-value">
                        <span id="newUsers7d">-</span> کاربر جدید (7 روز)
                    </div>
                </div>
                <div class="card">
                    <h3>🔥 کاربران فعال</h3>
                    <div class="value" id="activeUsers30d">-</div>
                    <div class="sub-value">
                        در 30 روز گذشته
                    </div>
                </div>
                <div class="card">
                    <h3>🏢 تعداد گروه‌ها</h3>
                    <div class="value" id="totalGroups">-</div>
                    <div class="sub-value">
                        گروه‌های فعال
                    </div>
                </div>
                <div class="card">
                    <h3>⚔️ فایت‌ها</h3>
                    <div class="value" id="totalFights">-</div>
                    <div class="sub-value">
                        در 30 روز گذشته
                    </div>
                </div>
            </div>

            <!-- نرخ رشد و بازگشت -->
            <div class="grid grid-2">
                <div class="card">
                    <h3>📈 نرخ رشد کاربران</h3>
                    <div class="label">رشد هفتگی</div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="weeklyGrowth" style="width: 0%">0%</div>
                    </div>
                    <div class="label" style="margin-top: 15px;">رشد ماهانه</div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="monthlyGrowth" style="width: 0%">0%</div>
                    </div>
                </div>
                <div class="card">
                    <h3>🔄 نرخ بازگشت کاربران</h3>
                    <div class="value" id="retentionRate">-</div>
                    <div class="sub-value">
                        <span id="returningUsers">-</span> از <span id="totalUsersRetention">-</span> کاربر
                    </div>
                </div>
            </div>

            <!-- فاکتورهای ارزش‌گذاری -->
            <div class="chart-container">
                <h3>📊 فاکتورهای ارزش‌گذاری</h3>
                <div id="factorsChart"></div>
            </div>

            <!-- ساعات پیک -->
            <div class="grid grid-2" style="margin-top: 30px;">
                <div class="card">
                    <h3>⏰ ساعات پیک استفاده</h3>
                    <div id="peakHours"></div>
                </div>
                <div class="card">
                    <h3>🎴 محبوب‌ترین کارت‌ها</h3>
                    <div id="popularCards"></div>
                </div>
            </div>

            <!-- گروه‌های فعال -->
            <div class="card" style="margin-top: 30px;">
                <h3>🏢 فعال‌ترین گروه‌ها</h3>
                <div id="activeGroups"></div>
            </div>
        </div>
    </div>

    <script>
        async function loadAllData() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('content').style.display = 'none';

            try {
                // بارگیری داده‌ها
                const reportResponse = await fetch('/api/analytics/report');
                const report = await reportResponse.json();
                
                const valuationResponse = await fetch('/api/analytics/valuation');
                const valuation = await valuationResponse.json();
                
                // استفاده از داده‌های report
                if (!report.success || !report.data) {
                    throw new Error('خطا در دریافت گزارش');
                }
                
                const users = { success: true, data: report.data.user_stats };
                const groups = { success: true, data: report.data.group_stats };
                const fights = { success: true, data: report.data.fight_stats };

                // نمایش ارزش‌گذاری
                if (valuation.success) {
                    const v = valuation.data;
                    document.getElementById('totalScore').textContent = v.total_score + ' / 100';
                    document.getElementById('rating').textContent = v.rating;
                    document.getElementById('estimatedValue').textContent = '$' + v.estimated_value_usd.toLocaleString();
                    
                    // توصیه‌ها
                    const recsHTML = '<h4>💡 توصیه‌ها برای افزایش ارزش:</h4><ul>' +
                        v.recommendations.map(r => '<li>' + r + '</li>').join('') +
                        '</ul>';
                    document.getElementById('recommendations').innerHTML = recsHTML;

                    // فاکتورها
                    renderFactors(v.factors);
                }

                // نمایش آمار کاربران
                if (users.success) {
                    const u = users.data;
                    document.getElementById('totalUsers').textContent = u.total.toLocaleString();
                    document.getElementById('newUsers7d').textContent = u.growth.new_last_week;
                    document.getElementById('activeUsers30d').textContent = u.active_30d.toLocaleString();
                    
                    document.getElementById('weeklyGrowth').style.width = Math.min(u.growth.weekly_growth_rate, 100) + '%';
                    document.getElementById('weeklyGrowth').textContent = u.growth.weekly_growth_rate + '%';
                    
                    document.getElementById('monthlyGrowth').style.width = Math.min(u.growth.monthly_growth_rate, 100) + '%';
                    document.getElementById('monthlyGrowth').textContent = u.growth.monthly_growth_rate + '%';
                    
                    document.getElementById('retentionRate').textContent = u.retention.retention_rate + '%';
                    document.getElementById('returningUsers').textContent = u.retention.returning_users;
                    document.getElementById('totalUsersRetention').textContent = u.retention.total_users;
                }

                // نمایش آمار گروه‌ها
                if (groups.success) {
                    document.getElementById('totalGroups').textContent = groups.data.total_groups.toLocaleString();
                    
                    const groupsHTML = groups.data.active_groups.map(g => 
                        '<div style="padding: 10px; border-bottom: 1px solid #eee;">' +
                        '<strong>گروه ' + g.chat_id + '</strong>: ' + g.fight_count + ' فایت' +
                        '</div>'
                    ).join('');
                    document.getElementById('activeGroups').innerHTML = groupsHTML || '<p>هنوز گروهی ثبت نشده</p>';
                }

                // نمایش آمار فایت‌ها
                if (fights.success) {
                    document.getElementById('totalFights').textContent = fights.data.last_30_days.total_fights.toLocaleString();
                    
                    // ساعات پیک
                    const peakHTML = fights.data.peak_hours.map(h => 
                        '<div style="padding: 8px; border-bottom: 1px solid #eee;">' +
                        '<strong>ساعت ' + h.hour + ':00</strong>: ' + h.fight_count + ' فایت' +
                        '</div>'
                    ).join('');
                    document.getElementById('peakHours').innerHTML = peakHTML || '<p>داده‌ای موجود نیست</p>';
                }

                // کارت‌های محبوب
                if (report.success && report.data.popular_cards) {
                    const cardsHTML = report.data.popular_cards.map(c => 
                        '<div style="padding: 8px; border-bottom: 1px solid #eee;">' +
                        '<strong>' + c.name + '</strong> ' +
                        '<span class="badge badge-info">' + c.rarity + '</span>: ' +
                        c.owner_count + ' مالک' +
                        '</div>'
                    ).join('');
                    document.getElementById('popularCards').innerHTML = cardsHTML || '<p>داده‌ای موجود نیست</p>';
                }

                document.getElementById('loading').style.display = 'none';
                document.getElementById('content').style.display = 'block';

            } catch (error) {
                console.error('Error loading data:', error);
                document.getElementById('loading').innerHTML = '❌ خطا در بارگیری داده‌ها';
            }
        }

        function renderFactors(factors) {
            const factorsHTML = Object.entries(factors).map(([key, value]) => {
                const labels = {
                    'user_score': 'امتیاز کاربران',
                    'activity_score': 'امتیاز فعالیت',
                    'retention_score': 'امتیاز بازگشت',
                    'group_score': 'امتیاز گروه‌ها',
                    'engagement_score': 'امتیاز تعامل'
                };
                const maxScores = {
                    'user_score': 30,
                    'activity_score': 25,
                    'retention_score': 20,
                    'group_score': 15,
                    'engagement_score': 10
                };
                const percentage = (value / maxScores[key] * 100).toFixed(1);
                return `
                    <div style="margin: 15px 0;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                            <span>${labels[key]}</span>
                            <span><strong>${value}</strong> / ${maxScores[key]}</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${percentage}%">${percentage}%</div>
                        </div>
                    </div>
                `;
            }).join('');
            document.getElementById('factorsChart').innerHTML = factorsHTML;
        }

        // بارگیری اولیه
        loadAllData();

        // بروزرسانی خودکار هر 5 دقیقه
        setInterval(loadAllData, 5 * 60 * 1000);
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("📊 Starting Analytics Panel on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
