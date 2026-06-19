#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 راه‌اندازی محیط تست برای فاز ۲
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime

def setup_test_environment():
    """ایجاد محیط تست کامل"""
    
    print("=" * 60)
    print("🧪 راه‌اندازی محیط تست TelBattle Phase 2")
    print("=" * 60)
    print()
    
    # مرحله ۱: بررسی .env.test
    print("📋 مرحله ۱: بررسی فایل تنظیمات تست...")
    if not os.path.exists('.env.test'):
        print("❌ فایل .env.test یافت نشد!")
        print("لطفاً ابتدا .env.test را با اطلاعات ربات تست پر کنید")
        return False
    
    # خواندن .env.test
    with open('.env.test', 'r', encoding='utf-8') as f:
        env_content = f.read()
    
    if 'YOUR_TEST_BOT_TOKEN_HERE' in env_content:
        print("⚠️  توکن ربات تست هنوز تنظیم نشده!")
        print()
        print("مراحل لازم:")
        print("  1. از @BotFather یک ربات تست بسازید")
        print("  2. توکن را در .env.test جایگزین کنید")
        print("  3. User ID خود را در ADMIN_USER_IDS قرار دهید")
        print("  4. یک کانال تست بسازید و آدرس آن را در REQUIRED_CHANNEL قرار دهید")
        print()
        return False
    
    print("✅ فایل .env.test آماده است")
    
    # مرحله ۲: کپی دیتابیس production برای تست
    print("\n📦 مرحله ۲: ایجاد دیتابیس تست...")
    
    if os.path.exists('game_bot.db'):
        # کپی از دیتابیس اصلی
        shutil.copy2('game_bot.db', 'game_bot_test.db')
        print("✅ دیتابیس production کپی شد به game_bot_test.db")
    else:
        print("⚠️  دیتابیس production یافت نشد")
        print("یک دیتابیس خالی برای تست ایجاد می‌شود...")
        
        # ایجاد دیتابیس خالی
        from game_core import DatabaseManager
        db = DatabaseManager(db_path='game_bot_test.db')
        print("✅ دیتابیس تست خالی ایجاد شد")
    
    # مرحله ۳: اضافه کردن داده‌های تست
    print("\n🎲 مرحله ۳: اضافه کردن داده‌های تست...")
    
    conn = sqlite3.connect('game_bot_test.db')
    cursor = conn.cursor()
    
    # بررسی تعداد کارت‌ها
    cursor.execute("SELECT COUNT(*) FROM cards")
    card_count = cursor.fetchone()[0]
    
    if card_count == 0:
        print("⚠️  هیچ کارتی در دیتابیس نیست")
        print("لطفاً ابتدا کارت‌ها را به دیتابیس اضافه کنید")
    else:
        print(f"✅ {card_count} کارت در دیتابیس موجود است")
    
    # بررسی تعداد بازیکنان
    cursor.execute("SELECT COUNT(*) FROM players")
    player_count = cursor.fetchone()[0]
    print(f"✅ {player_count} بازیکن در دیتابیس موجود است")
    
    conn.close()
    
    # مرحله ۴: ایجاد اسکریپت اجرای تست
    print("\n🚀 مرحله ۴: ایجاد اسکریپت‌های اجرا...")
    
    # اسکریپت run_test_bot.py
    with open('run_test_bot.py', 'w', encoding='utf-8') as f:
        f.write('''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 اجرای ربات تست با تنظیمات .env.test
"""

import os
import sys

# تنظیم متغیر محیطی برای استفاده از .env.test
os.environ['ENV_FILE'] = '.env.test'

# اجرای ربات
from telegram_bot import TelegramCardBot

if __name__ == "__main__":
    print("🧪 اجرای ربات تست...")
    print("📝 استفاده از: .env.test")
    print("💾 دیتابیس: game_bot_test.db")
    print()
    
    try:
        bot = TelegramCardBot(use_env=True)
        bot.run()
    except KeyboardInterrupt:
        print("\\n⏹️  ربات متوقف شد")
    except Exception as e:
        print(f"❌ خطا: {e}")
        sys.exit(1)
''')
    
    print("✅ اسکریپت run_test_bot.py ایجاد شد")
    
    # مرحله ۵: خلاصه
    print("\n" + "=" * 60)
    print("✅ محیط تست آماده است!")
    print("=" * 60)
    print()
    print("📝 فایل‌های ایجاد شده:")
    print("  • .env.test - تنظیمات ربات تست")
    print("  • game_bot_test.db - دیتابیس تست")
    print("  • run_test_bot.py - اسکریپت اجرای ربات تست")
    print()
    print("🚀 برای اجرای ربات تست:")
    print("   python run_test_bot.py")
    print()
    print("🔄 برای اجرای migration روی دیتابیس تست:")
    print("   python phase2_migration.py")
    print("   (دیتابیس game_bot_test.db را migrate می‌کند)")
    print()
    print("⚠️  نکات مهم:")
    print("  • ربات production شما تحت تأثیر قرار نمی‌گیرد")
    print("  • دیتابیس تست جداگانه است (game_bot_test.db)")
    print("  • می‌توانید هر تغییری را تست کنید")
    print()
    
    return True


if __name__ == "__main__":
    success = setup_test_environment()
    
    if not success:
        print("\n❌ راه‌اندازی ناموفق بود")
        print("لطفاً مراحل بالا را دنبال کنید")
        sys.exit(1)
