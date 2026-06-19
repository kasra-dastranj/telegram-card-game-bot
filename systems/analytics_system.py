#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Bot Analytics System - سیستم آنالیتیکس ربات
سیستم جداگانه برای آمارگیری و ارزش‌گذاری ربات
بدون تغییر در کد اصلی - فقط می‌خونه از دیتابیس
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

class BotAnalytics:
    def __init__(self, db_path: str = "game_bot.db"):
        self.db_path = db_path
    
    def _execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        """اجرای کوئری و برگرداندن نتایج"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        return results
    
    # ==================== آمار کاربران ====================
    
    def get_total_users(self) -> int:
        """تعداد کل کاربران ثبت شده"""
        result = self._execute_query("SELECT COUNT(*) FROM players")
        return result[0][0] if result else 0
    
    def get_active_users(self, days: int = 7) -> int:
        """کاربران فعال در N روز گذشته"""
        date_threshold = (datetime.now() - timedelta(days=days)).isoformat()
        result = self._execute_query(
            "SELECT COUNT(DISTINCT user_id) FROM fight_history WHERE fought_at >= ?",
            (date_threshold,)
        )
        return result[0][0] if result else 0
    
    def get_new_users(self, days: int = 7) -> int:
        """کاربران جدید در N روز گذشته"""
        date_threshold = (datetime.now() - timedelta(days=days)).isoformat()
        result = self._execute_query(
            "SELECT COUNT(*) FROM players WHERE created_at >= ?",
            (date_threshold,)
        )
        return result[0][0] if result else 0
    
    def get_user_growth_rate(self) -> Dict[str, Any]:
        """نرخ رشد کاربران"""
        total = self.get_total_users()
        last_week = self.get_new_users(7)
        last_month = self.get_new_users(30)
        
        return {
            'total_users': total,
            'new_last_week': last_week,
            'new_last_month': last_month,
            'weekly_growth_rate': round((last_week / total * 100), 2) if total > 0 else 0,
            'monthly_growth_rate': round((last_month / total * 100), 2) if total > 0 else 0
        }
    
    def get_user_retention(self) -> Dict[str, float]:
        """نرخ بازگشت کاربران (Retention Rate)"""
        # کاربرانی که حداقل 2 بار بازی کردند
        result = self._execute_query("""
            SELECT COUNT(DISTINCT user_id) 
            FROM (
                SELECT user_id, COUNT(*) as fight_count 
                FROM fight_history 
                GROUP BY user_id 
                HAVING fight_count >= 2
            )
        """)
        returning_users = result[0][0] if result else 0
        total_users = self.get_total_users()
        
        return {
            'returning_users': returning_users,
            'total_users': total_users,
            'retention_rate': round((returning_users / total_users * 100), 2) if total_users > 0 else 0
        }
    
    # ==================== آمار گروه‌ها ====================
    
    def get_group_stats(self) -> Dict[str, Any]:
        """آمار گروه‌ها (از fight_history استخراج می‌شود)"""
        # گروه‌های یونیک که در آنها فایت انجام شده
        result = self._execute_query("""
            SELECT COUNT(DISTINCT chat_id) 
            FROM fight_history 
            WHERE chat_id IS NOT NULL AND chat_id < 0
        """)
        unique_groups = result[0][0] if result else 0
        
        # فعال‌ترین گروه‌ها
        active_groups = self._execute_query("""
            SELECT chat_id, COUNT(*) as fight_count 
            FROM fight_history 
            WHERE chat_id IS NOT NULL AND chat_id < 0
            GROUP BY chat_id 
            ORDER BY fight_count DESC 
            LIMIT 10
        """)
        
        return {
            'total_groups': unique_groups,
            'active_groups': [
                {'chat_id': row[0], 'fight_count': row[1]} 
                for row in active_groups
            ]
        }
    
    # ==================== آمار بازی ====================
    
    def get_fight_stats(self, days: int = 30) -> Dict[str, Any]:
        """آمار فایت‌ها"""
        date_threshold = (datetime.now() - timedelta(days=days)).isoformat()
        
        # کل فایت‌ها
        total_fights = self._execute_query(
            "SELECT COUNT(*) FROM fight_history WHERE fought_at >= ?",
            (date_threshold,)
        )[0][0]
        
        # فایت‌های PvP
        pvp_fights = self._execute_query(
            "SELECT COUNT(*) FROM fight_history WHERE fight_type = 'pvp' AND fought_at >= ?",
            (date_threshold,)
        )[0][0]
        
        # میانگین فایت در روز
        avg_per_day = round(total_fights / days, 2) if days > 0 else 0
        
        return {
            'total_fights': total_fights,
            'pvp_fights': pvp_fights,
            'avg_fights_per_day': avg_per_day,
            'period_days': days
        }
    
    def get_peak_hours(self) -> List[Dict[str, Any]]:
        """ساعات پیک استفاده"""
        results = self._execute_query("""
            SELECT 
                CAST(strftime('%H', fought_at) AS INTEGER) as hour,
                COUNT(*) as fight_count
            FROM fight_history
            WHERE fought_at >= datetime('now', '-30 days')
            GROUP BY hour
            ORDER BY fight_count DESC
            LIMIT 5
        """)
        
        return [
            {'hour': row[0], 'fight_count': row[1]} 
            for row in results
        ]
    
    def get_popular_cards(self, limit: int = 10) -> List[Dict[str, Any]]:
        """محبوب‌ترین کارت‌ها"""
        results = self._execute_query("""
            SELECT c.name, c.rarity, COUNT(pc.card_id) as owner_count
            FROM cards c
            LEFT JOIN player_cards pc ON c.card_id = pc.card_id
            GROUP BY c.card_id
            ORDER BY owner_count DESC
            LIMIT ?
        """, (limit,))
        
        return [
            {'name': row[0], 'rarity': row[1], 'owner_count': row[2]} 
            for row in results
        ]
    
    # ==================== آمار تعامل ====================
    
    def get_engagement_stats(self) -> Dict[str, Any]:
        """آمار تعامل کاربران"""
        # میانگین فایت هر کاربر
        result = self._execute_query("""
            SELECT AVG(fight_count) 
            FROM (
                SELECT user_id, COUNT(*) as fight_count 
                FROM fight_history 
                GROUP BY user_id
            )
        """)
        avg_fights_per_user = round(result[0][0], 2) if result and result[0][0] else 0
        
        # میانگین کارت هر کاربر
        result = self._execute_query("""
            SELECT AVG(card_count) 
            FROM (
                SELECT user_id, COUNT(*) as card_count 
                FROM player_cards 
                GROUP BY user_id
            )
        """)
        avg_cards_per_user = round(result[0][0], 2) if result and result[0][0] else 0
        
        return {
            'avg_fights_per_user': avg_fights_per_user,
            'avg_cards_per_user': avg_cards_per_user
        }
    
    # ==================== گزارش جامع ====================
    
    def get_comprehensive_report(self) -> Dict[str, Any]:
        """گزارش جامع برای ارزش‌گذاری"""
        return {
            'timestamp': datetime.now().isoformat(),
            'user_stats': {
                'total': self.get_total_users(),
                'active_7d': self.get_active_users(7),
                'active_30d': self.get_active_users(30),
                'growth': self.get_user_growth_rate(),
                'retention': self.get_user_retention()
            },
            'group_stats': self.get_group_stats(),
            'fight_stats': {
                'last_7_days': self.get_fight_stats(7),
                'last_30_days': self.get_fight_stats(30)
            },
            'engagement': self.get_engagement_stats(),
            'peak_hours': self.get_peak_hours(),
            'popular_cards': self.get_popular_cards(5)
        }
    
    # ==================== ارزش‌گذاری ====================
    
    def calculate_bot_value(self) -> Dict[str, Any]:
        """محاسبه ارزش تقریبی ربات برای فروش"""
        report = self.get_comprehensive_report()
        
        # فاکتورهای ارزش‌گذاری
        total_users = report['user_stats']['total']
        active_users_30d = report['user_stats']['active_30d']
        retention_rate = report['user_stats']['retention']['retention_rate']
        total_groups = report['group_stats']['total_groups']
        avg_fights_per_day = report['fight_stats']['last_30_days']['avg_fights_per_day']
        
        # محاسبه امتیاز (0-100)
        user_score = min(total_users / 10, 30)  # حداکثر 30 امتیاز
        activity_score = min(active_users_30d / 5, 25)  # حداکثر 25 امتیاز
        retention_score = min(retention_rate / 4, 20)  # حداکثر 20 امتیاز
        group_score = min(total_groups * 2, 15)  # حداکثر 15 امتیاز
        engagement_score = min(avg_fights_per_day / 2, 10)  # حداکثر 10 امتیاز
        
        total_score = user_score + activity_score + retention_score + group_score + engagement_score
        
        # ارزش‌گذاری تقریبی (به دلار)
        # فرمول ساده: (کاربران فعال × 2) + (گروه‌ها × 10) + (امتیاز کلی × 5)
        estimated_value = (active_users_30d * 2) + (total_groups * 10) + (total_score * 5)
        
        # رتبه‌بندی
        if total_score >= 80:
            rating = "عالی - آماده فروش با قیمت بالا"
        elif total_score >= 60:
            rating = "خوب - قابل فروش"
        elif total_score >= 40:
            rating = "متوسط - نیاز به بهبود"
        else:
            rating = "ضعیف - نیاز به رشد بیشتر"
        
        return {
            'total_score': round(total_score, 2),
            'rating': rating,
            'estimated_value_usd': round(estimated_value, 2),
            'factors': {
                'user_score': round(user_score, 2),
                'activity_score': round(activity_score, 2),
                'retention_score': round(retention_score, 2),
                'group_score': round(group_score, 2),
                'engagement_score': round(engagement_score, 2)
            },
            'recommendations': self._get_recommendations(total_score, report)
        }
    
    def _get_recommendations(self, score: float, report: Dict) -> List[str]:
        """توصیه‌ها برای بهبود ارزش ربات"""
        recommendations = []
        
        if report['user_stats']['total'] < 100:
            recommendations.append("افزایش تعداد کاربران - تبلیغات بیشتر")
        
        if report['user_stats']['retention']['retention_rate'] < 50:
            recommendations.append("بهبود نرخ بازگشت - افزودن ویژگی‌های جذاب")
        
        if report['group_stats']['total_groups'] < 5:
            recommendations.append("افزایش تعداد گروه‌ها - معرفی در گروه‌های بیشتر")
        
        if report['fight_stats']['last_30_days']['avg_fights_per_day'] < 10:
            recommendations.append("افزایش تعامل - ایونت‌ها و مسابقات")
        
        if not recommendations:
            recommendations.append("ربات در وضعیت خوبی است - ادامه دهید!")
        
        return recommendations

def main():
    """تست سیستم"""
    analytics = BotAnalytics()
    
    print("=" * 60)
    print("📊 گزارش جامع آنالیتیکس ربات")
    print("=" * 60)
    
    report = analytics.get_comprehensive_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    print("💰 ارزش‌گذاری ربات")
    print("=" * 60)
    
    valuation = analytics.calculate_bot_value()
    print(json.dumps(valuation, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
