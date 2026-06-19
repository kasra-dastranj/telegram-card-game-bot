#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 اجرای همه تست‌های فاز ۲ به صورت یکجا
"""

import sys
import os
import subprocess
from datetime import datetime

def print_header(title):
    """چاپ header زیبا"""
    print("\n" + "=" * 60)
    print(f"🧪 {title}")
    print("=" * 60 + "\n")

def run_test(test_file, description):
    """اجرای یک تست و نمایش نتیجه"""
    print_header(description)
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"\n✅ {description} موفق بود!")
            return True
        else:
            print(f"\n❌ {description} ناموفق بود!")
            if result.stderr:
                print(f"خطا: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"\n⏰ {description} timeout شد (بیش از 60 ثانیه)")
        return False
    except Exception as e:
        print(f"\n❌ خطا در اجرای {description}: {e}")
        return False

def main():
    """اجرای همه تست‌ها"""
    print("=" * 60)
    print("🚀 شروع اجرای همه تست‌های فاز ۲")
    print("=" * 60)
    print(f"⏰ زمان شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # لیست تست‌ها
    tests = [
        ("test_claim_system.py", "تست Claim System"),
        ("test_phase2_systems.py", "تست Phase2 Systems (Level, XP, Tier, TP, Decay)"),
        ("test_bot_profile.py", "تست Bot Profile و Match Rewards"),
    ]
    
    results = {}
    
    # اجرای تست‌ها
    for test_file, description in tests:
        if not os.path.exists(test_file):
            print(f"\n⚠️  فایل {test_file} یافت نشد - رد شد")
            results[description] = "SKIPPED"
            continue
        
        success = run_test(test_file, description)
        results[description] = "PASSED" if success else "FAILED"
    
    # خلاصه نتایج
    print("\n" + "=" * 60)
    print("📊 خلاصه نتایج تست‌ها")
    print("=" * 60 + "\n")
    
    passed = 0
    failed = 0
    skipped = 0
    
    for description, status in results.items():
        if status == "PASSED":
            emoji = "✅"
            passed += 1
        elif status == "FAILED":
            emoji = "❌"
            failed += 1
        else:  # SKIPPED
            emoji = "⚠️"
            skipped += 1
        
        print(f"{emoji} {description}: {status}")
    
    print("\n" + "-" * 60)
    print(f"✅ موفق: {passed}")
    print(f"❌ ناموفق: {failed}")
    print(f"⚠️  رد شده: {skipped}")
    print(f"📊 کل: {len(results)}")
    print("-" * 60)
    
    print(f"\n⏰ زمان پایان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # نتیجه نهایی
    if failed == 0 and passed > 0:
        print("\n" + "=" * 60)
        print("🎉 همه تست‌ها با موفقیت انجام شد!")
        print("=" * 60)
        print("\n✨ مراحل بعدی:")
        print("  1. اجرای ربات تست: python run_test_bot.py")
        print("  2. تست دستی فیچرها در تلگرام")
        print("  3. بررسی لاگ‌ها: cat bot.log")
        print("  4. آماده برای production!")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ برخی تست‌ها ناموفق بودند")
        print("=" * 60)
        print("\n🔍 مراحل عیب‌یابی:")
        print("  1. بررسی لاگ‌های بالا")
        print("  2. اجرای تست‌های ناموفق به صورت جداگانه")
        print("  3. بررسی فایل bot.log")
        print("  4. بررسی دیتابیس: sqlite3 game_bot_test.db")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  تست‌ها توسط کاربر متوقف شدند")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
