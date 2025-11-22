#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎁 اسکریپت اعطای کارت‌های شروعی
این اسکریپت کارت‌های شروعی را به همه بازیکنان موجود می‌دهد
"""

import sys
import os
from datetime import datetime

# اضافه کردن مسیر پروژه
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from game_core import DatabaseManager, CardManager

def main():
    """اجرای اصلی اسکریپت"""
    print("🎁 اسکریپت اعطای کارت‌های شروعی")
    print("=" * 50)
    
    try:
        # ایجاد مدیر دیتابیس و کارت‌ها
        db = DatabaseManager()
        card_manager = CardManager(db)
        
        print("📊 بررسی وضعیت فعلی...")
        
        # نمایش آمار قبل از اعطا
        all_players = db.get_leaderboard(1000)  # همه بازیکنان
        print(f"👥 تعداد بازیکنان: {len(all_players)}")
        
        starter_cards = ["John Wick", "Heisenberg", "Rehi"]
        print(f"🎴 کارت‌های شروعی: {', '.join(starter_cards)}")
        
        # تأیید از کاربر
        print("\n⚠️ این عملیات کارت‌های شروعی را به همه بازیکنان موجود می‌دهد.")
        print("فقط بازیکنانی که این کارت‌ها را ندارند، دریافت خواهند کرد.")
        
        confirm = input("\nآیا ادامه می‌دهید؟ (yes/no): ").strip().lower()
        
        if confirm not in ['yes', 'y', 'بله']:
            print("❌ عملیات لغو شد!")
            return
        
        print("\n🔄 در حال اعطای کارت‌های شروعی...")
        print("-" * 30)
        
        # اعطای کارت‌ها
        granted_count = card_manager.grant_starter_cards_to_all()
        
        print("-" * 30)
        
        if granted_count > 0:
            print(f"🎉 عملیات موفق!")
            print(f"📈 {granted_count} کارت به بازیکنان اعطا شد.")
        else:
            print("📝 همه بازیکنان قبلاً کارت‌های شروعی را دارند.")
            print("هیچ کارت جدیدی اعطا نشد.")
        
        print(f"\n✅ عملیات در {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} تکمیل شد.")
        
    except Exception as e:
        print(f"❌ خطا در اجرای اسکریپت: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)