#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Final System Test & Quick Setup Checker
ابزار تست نهایی و بررسی سریع سیستم
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

class SystemChecker:
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.passed_checks = 0
        self.total_checks = 0
    
    def check_python_version(self):
        """بررسی نسخه Python"""
        self.total_checks += 1
        version = sys.version_info
        
        if version >= (3, 8):
            print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
            self.passed_checks += 1
        else:
            print(f"❌ Python {version.major}.{version.minor} - نیاز به 3.8+")
            self.issues.append("Python version too old")
    
    def check_dependencies(self):
        """بررسی dependencies"""
        self.total_checks += 1
        missing = []
        
        try:
            import telegram
            print("✅ python-telegram-bot")
        except ImportError:
            missing.append("python-telegram-bot")
        
        try:
            from PIL import Image
            print("✅ Pillow")
        except ImportError:
            missing.append("Pillow")
        
        if not missing:
            self.passed_checks += 1
        else:
            print(f"❌ Missing: {', '.join(missing)}")
            self.issues.append(f"Missing packages: {', '.join(missing)}")
    
    def check_main_files(self):
        """بررسی فایل‌های اصلی"""
        required_files = [
            "game_core.py",
            "telegram_bot.py", 
            "admin_setup.py",
            "requirements.txt"
        ]
        
        self.total_checks += 1
        missing_files = []
        
        for file in required_files:
            if os.path.exists(file):
                print(f"✅ {file}")
            else:
                print(f"❌ {file} - یافت نشد")
                missing_files.append(file)
        
        if not missing_files:
            self.passed_checks += 1
        else:
            self.issues.append(f"Missing files: {', '.join(missing_files)}")
    
    def check_config_file(self):
        """بررسی فایل تنظیمات"""
        self.total_checks += 1
        
        if not os.path.exists("game_config.json"):
            print("❌ game_config.json - یافت نشد")
            self.issues.append("Configuration file missing")
            return
        
        try:
            with open("game_config.json", 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # بررسی توکن
            token = config.get('bot_settings', {}).get('token', '')
            if token and token != 'YOUR_BOT_TOKEN_HERE':
                print("✅ Bot token configured")
            else:
                print("⚠️ Bot token not set")
                self.warnings.append("Bot token needs to be configured")
            
            # بررسی admin IDs  
            admin_ids = config.get('bot_settings', {}).get('admin_user_ids', [])
            if admin_ids and admin_ids != [123456789]:
                print(f"✅ Admin IDs: {len(admin_ids)}")
            else:
                print("⚠️ Admin IDs not configured")
                self.warnings.append("Admin user IDs need to be set")
            
            print("✅ Configuration file valid")
            self.passed_checks += 1
            
        except json.JSONDecodeError:
            print("❌ Configuration file corrupted")
            self.issues.append("Invalid configuration file")
        except Exception as e:
            print(f"❌ Configuration error: {e}")
            self.issues.append(f"Configuration error: {e}")
    
    def check_database(self):
        """بررسی دیتابیس"""
        self.total_checks += 1
        
        db_path = "game_bot.db"
        
        if not os.path.exists(db_path):
            print("⚠️ Database not found - will be created on first run")
            self.warnings.append("Database will be created automatically")
            self.passed_checks += 1
            return
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # بررسی جدول کارت‌ها
            cursor.execute("SELECT COUNT(*) FROM cards")
            card_count = cursor.fetchone()[0]
            
            # بررسی جدول بازیکنان
            cursor.execute("SELECT COUNT(*) FROM players")
            player_count = cursor.fetchone()[0]
            
            conn.close()
            
            print(f"✅ Database: {card_count} cards, {player_count} players")
            self.passed_checks += 1
            
        except sqlite3.Error as e:
            print(f"❌ Database error: {e}")
            self.issues.append(f"Database error: {e}")
    
    def check_images_directory(self):
        """بررسی پوشه عکس‌ها"""
        self.total_checks += 1
        images_dir = "card_images"
        
        if not os.path.exists(images_dir):
            print("⚠️ Images directory not found")
            self.warnings.append("Images directory missing - will be created")
            try:
                os.makedirs(images_dir, exist_ok=True)
                print("✅ Images directory created")
                self.passed_checks += 1
            except Exception as e:
                print(f"❌ Cannot create images directory: {e}")
                self.issues.append(f"Cannot create images directory: {e}")
        else:
            # شمارش عکس‌ها
            image_files = [f for f in os.listdir(images_dir) 
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            print(f"✅ Images directory: {len(image_files)} images")
            if len(image_files) == 0:
                self.warnings.append("No card images found - bot will work without images")
            self.passed_checks += 1
    
    def test_imports(self):
        """تست import کردن ماژول‌های اصلی"""
        self.total_checks += 1
        
        try:
            from game_core import DatabaseManager, GameLogic, CardManager
            print("✅ Core modules import successful")
            
            # تست ساده
            db = DatabaseManager()
            print("✅ Database connection works")
            
            self.passed_checks += 1
            
        except ImportError as e:
            print(f"❌ Import error: {e}")
            self.issues.append(f"Cannot import core modules: {e}")
        except Exception as e:
            print(f"❌ Core system error: {e}")
            self.issues.append(f"Core system error: {e}")
    
    def run_full_check(self):
        """اجرای تست کامل"""
        print("🔧 System Health Check")
        print("=" * 50)
        
        self.check_python_version()
        self.check_dependencies()
        self.check_main_files()
        self.check_config_file()
        self.check_database()
        self.check_images_directory()
        self.test_imports()
        
        print(f"\n📊 Results: {self.passed_checks}/{self.total_checks} checks passed")
        
        # خلاصه مشکلات
        if self.issues:
            print(f"\n❌ Critical Issues ({len(self.issues)}):")
            for issue in self.issues:
                print(f"   • {issue}")
        
        if self.warnings:
            print(f"\n⚠️ Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        # نتیجه کلی
        if not self.issues:
            if not self.warnings:
                print(f"\n🎉 Perfect! System is ready to run!")
                return "perfect"
            else:
                print(f"\n✅ Good! System is ready with minor warnings.")
                return "good"
        else:
            print(f"\n💔 Issues found. Please fix them before running the bot.")
            return "issues"

def create_quick_start_script():
    """ایجاد اسکریپت شروع سریع"""
    script_content = '''#!/usr/bin/env python3
# Quick Start Script - Auto-generated
import subprocess
import sys
import os

def main():
    print("🚀 Quick Start - Telegram Card Game Bot")
    
    if not os.path.exists("game_config.json"):
        print("⚠️  Configuration needed. Running setup...")
        subprocess.run([sys.executable, "admin_setup.py"])
    else:
        print("🤖 Starting bot...")
        subprocess.run([sys.executable, "telegram_bot.py"])

if __name__ == "__main__":
    main()
'''
    
    with open("start.py", "w", encoding="utf-8") as f:
        f.write(script_content)
    
    print("✅ Quick start script created: start.py")

def show_next_steps(status):
    """نمایش گام‌های بعدی"""
    print(f"\n📋 Next Steps:")
    
    if status == "issues":
        print("1. ❌ Fix the critical issues listed above")
        print("2. 🔄 Run this checker again: python system_check.py")
        print("3. 📖 Check the setup guide for help")
        
    elif status == "good":
        print("1. 🔧 Fix warnings if needed")
        print("2. 🤖 Get bot token from @BotFather")
        print("3. ⚙️ Configure game_config.json")
        print("4. 🚀 Run: python telegram_bot.py")
        
    elif status == "perfect":
        print("1. 🤖 Make sure bot token is set")
        print("2. 🚀 Run: python telegram_bot.py")
        print("3. 💬 Test bot with /start in Telegram")
        print("4. 🎉 Enjoy your card game bot!")
    
    print(f"\n🆘 Need help? Check README.md or run: python admin_setup.py")

def main():
    """Main function"""
    checker = SystemChecker()
    status = checker.run_full_check()
    
    if status in ["good", "perfect"]:
        create_quick_start_script()
    
    show_next_steps(status)

if __name__ == "__main__":
    main()

# ============================================================
# 📋 FINAL CHECKLIST - نهایی چک‌لیست راه‌اندازی
# ============================================================

"""
🎯 FINAL SETUP CHECKLIST - چک‌لیست نهایی راه‌اندازی

□ 1. Python 3.8+ نصب شده
□ 2. فایل‌های اصلی دانلود شده (5 فایل)
□ 3. Dependencies نصب شده: pip install -r requirements.txt  
□ 4. توکن ربات از @BotFather دریافت شده
□ 5. User ID خودتان از @userinfobot دریافت شده
□ 6. فایل game_config.json ویرایش شده (توکن + User ID)
□ 7. پوشه card_images/ ایجاد شده
□ 8. عکس‌های کارت‌ها اضافه شده (اختیاری)
□ 9. تست سیستم: python system_check.py
□ 10. اجرای ربات: python telegram_bot.py

🚨 اگر مشکلی دارید:
• python system_check.py
• python admin_setup.py (گزینه 7: تست سیستم)
• بررسی فایل bot.log
• مراجعه به بخش "مشکلات متداول" در راهنما

🎉 اگر همه چیز کار کرد:
• ربات را در تلگرام پیدا کنید
• /start بزنید
• کارت دریافت کنید
• فایت کنید!

خوش بگذره! 🎮
"""