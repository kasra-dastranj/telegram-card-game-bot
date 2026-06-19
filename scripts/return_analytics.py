#!/usr/bin/env python3
"""
اسکریپت آنالیتیکس بازگشت بازیکنان
"""

import sqlite3
from datetime import datetime, timedelta

def get_return_analytics():
    """آنالیتیکس بازگشت بازیکنان"""
    
    try:
        conn = sqlite3.connect('game_bot.db')
        cursor = conn.cursor()
        
        print("=" * 50)
        print("📊 آنالیتیکس بازگشت بازیکنان")
        print("=" * 50)
        
        # تعداد کل بازیکنان
        cursor.execute("SELECT COUNT(*) FROM players")
        total_players = cursor.fetchone()[0]
        print(f"👥 تعداد کل بازیکنان: {total_players:,}")
        
        # بازیکنان جدید امروز
        cursor.execute("SELECT COUNT(*) FROM players WHERE DATE(created_at) = DATE('now')")
        new_today = cursor.fetchone()[0]
        print(f"🆕 عضو جدید امروز: {new_today:,}")
        
        # بازیکنان جدید 7 روز گذشته
        cursor.execute("SELECT COUNT(*) FROM players WHERE created_at >= datetime('now', '-7 days')")
        new_week = cursor.fetchone()[0]
        print(f"🆕 عضو جدید هفته: {new_week:,}")
        
        # بازیکنان جدید 30 روز گذشته
        cursor.execute("SELECT COUNT(*) FROM players WHERE created_at >= datetime('now', '-30 days')")
        new_month = cursor.fetchone()[0]
        print(f"🆕 عضو جدید ماه: {new_month:,}")
        
        # آخرین بازیکنان عضو شده
        print("\n🔄 آخرین بازیکنان عضو شده:")
        cursor.execute("""
            SELECT username, first_name, created_at 
            FROM players 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        
        recent_players = cursor.fetchall()
        if recent_players:
            for i, (username, first_name, created_at) in enumerate(recent_players, 1):
                name = first_name or username or "نامشخص"
                print(f"   {i}. {name} - {created_at}")
        
        # چک کردن جدول fights برای فعالیت
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fights'")
        if cursor.fetchone():
            print("\n⚔️ آمار فایت‌ها (نشانه فعالیت):")
            
            # فایت‌های امروز
            cursor.execute("SELECT COUNT(*) FROM fights WHERE DATE(created_at) = DATE('now')")
            fights_today = cursor.fetchone()[0]
            print(f"🥊 فایت امروز: {fights_today:,}")
            
            # فایت‌های هفته
            cursor.execute("SELECT COUNT(*) FROM fights WHERE created_at >= datetime('now', '-7 days')")
            fights_week = cursor.fetchone()[0]
            print(f"🥊 فایت هفته: {fights_week:,}")
            
            # فایت‌های ماه
            cursor.execute("SELECT COUNT(*) FROM fights WHERE created_at >= datetime('now', '-30 days')")
            fights_month = cursor.fetchone()[0]
            print(f"🥊 فایت ماه: {fights_month:,}")
            
            # بازیکنان فعال بر اساس فایت (هفته گذشته)
            cursor.execute("""
                SELECT COUNT(DISTINCT CASE WHEN p1.id IS NOT NULL THEN p1.id END) +
                       COUNT(DISTINCT CASE WHEN p2.id IS NOT NULL THEN p2.id END) as active_fighters
                FROM fights f
                LEFT JOIN players p1 ON f.player1_id = p1.user_id
                LEFT JOIN players p2 ON f.player2_id = p2.user_id
                WHERE f.created_at >= datetime('now', '-7 days')
            """)
            
            active_fighters = cursor.fetchone()[0] or 0
            print(f"👤 بازیکنان فعال (بر اساس فایت هفته): {active_fighters:,}")
            
            if total_players > 0:
                activity_rate = (active_fighters / total_players) * 100
                print(f"📈 نرخ فعالیت هفتگی: {activity_rate:.1f}%")
            
            # فعال‌ترین بازیکنان
            print("\n🏆 فعال‌ترین بازیکنان (بر اساس فایت هفته):")
            cursor.execute("""
                SELECT p.username, p.first_name, COUNT(*) as fight_count
                FROM (
                    SELECT player1_id as player_id FROM fights WHERE created_at >= datetime('now', '-7 days')
                    UNION ALL
                    SELECT player2_id as player_id FROM fights WHERE created_at >= datetime('now', '-7 days')
                ) f
                JOIN players p ON f.player_id = p.user_id
                GROUP BY p.user_id
                ORDER BY fight_count DESC
                LIMIT 10
            """)
            
            top_fighters = cursor.fetchall()
            if top_fighters:
                for i, (username, first_name, fight_count) in enumerate(top_fighters, 1):
                    name = first_name or username or "نامشخص"
                    print(f"   {i}. {name} - {fight_count} فایت")
            else:
                print("   هیچ فایتی در هفته گذشته انجام نشده")
        
        # چک کردن جدول player_cards برای فعالیت claim
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='player_cards'")
        if cursor.fetchone():
            print("\n🎴 آمار کارت‌ها:")
            
            # کل کارت‌های داده شده
            cursor.execute("SELECT COUNT(*) FROM player_cards")
            total_cards = cursor.fetchone()[0]
            print(f"🎴 کل کارت‌های داده شده: {total_cards:,}")
            
            # میانگین کارت به ازای هر بازیکن
            if total_players > 0:
                avg_cards = total_cards / total_players
                print(f"📊 میانگین کارت به ازای بازیکن: {avg_cards:.1f}")
        
        # آمار امتیازات
        print("\n🏆 آمار امتیازات:")
        cursor.execute("SELECT AVG(total_score), MAX(total_score), MIN(total_score) FROM players")
        avg_score, max_score, min_score = cursor.fetchone()
        
        print(f"📊 میانگین امتیاز: {avg_score:.1f}")
        print(f"🥇 بالاترین امتیاز: {max_score:,}")
        print(f"🥉 کمترین امتیاز: {min_score:,}")
        
        # برترین بازیکنان
        print("\n🏆 برترین بازیکنان:")
        cursor.execute("""
            SELECT username, first_name, total_score 
            FROM players 
            ORDER BY total_score DESC 
            LIMIT 10
        """)
        
        top_players = cursor.fetchall()
        for i, (username, first_name, score) in enumerate(top_players, 1):
            name = first_name or username or "نامشخص"
            print(f"   {i}. {name} - {score:,} امتیاز")
        
        print("=" * 50)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ خطا: {e}")

if __name__ == "__main__":
    get_return_analytics()