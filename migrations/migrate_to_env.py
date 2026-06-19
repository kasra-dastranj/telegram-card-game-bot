#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت مهاجرت از config.json به .env
"""

import json
import os
import shutil
from datetime import datetime

def backup_old_configs():
    """بکاپ گرفتن از فایل‌های قدیمی"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups = []
    
    for config_file in ["config.json", "game_config.json"]:
        if os.path.exists(config_file):
            backup_name = f"{config_file}.backup_{timestamp}"
            shutil.copy2(config_file, backup_name)
            backups.append(backup_name)
            print(f"✅ بکاپ: {config_file} -> {backup_name}")
    
    return backups

def extract_from_config(config_path):
    """استخراج تنظیمات از فایل config"""
    if not os.path.exists(config_path):
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def create_env_file():
    """ایجاد فایل .env از تنظیمات موجود"""
    
    # خواندن از هر دو فایل (اولویت با game_config.json)
    game_config = extract_from_config("game_config.json")
    config = extract_from_config("config.json")
    
    # انتخاب config اصلی
    main_config = game_config or config
    
    if not main_config:
        print("❌ هیچ فایل config یافت نشد!")
        return False
    
    # استخراج مقادیر
    bot_token = main_config.get("bot_settings", {}).get("token", "YOUR_BOT_TOKEN_HERE")
    admin_ids = main_config.get("bot_settings", {}).get("admin_user_ids", [])
    
    # اگر config.json هم داره، admin IDs رو merge کن
    if config and config != main_config:
        extra_admins = config.get("bot_settings", {}).get("admin_user_ids", [])
        admin_ids = list(set(admin_ids + extra_admins))
    
    game_settings = main_config.get("game_settings", {})
    db_settings = main_config.get("database", {})
    image_settings = main_config.get("image_settings", {})
    
    # تنظیمات کانال (فقط در config.json)
    channel_settings = {}
    if config:
        channel_settings = config.get("channel_settings", {})
    
    # ساخت محتوای .env
    env_content = f"""# Telegram Bot Configuration
BOT_TOKEN={bot_token}

# Admin User IDs (comma-separated)
ADMIN_USER_IDS={','.join(map(str, admin_ids))}

# Channel Settings
REQUIRED_CHANNEL={channel_settings.get('required_channel', '@YourChannel')}
CHANNEL_ID={channel_settings.get('channel_id', '')}

# Database Settings
DB_PATH={db_settings.get('path', 'game_bot.db')}
AUTO_BACKUP={str(db_settings.get('auto_backup', True)).lower()}
BACKUP_INTERVAL_HOURS={db_settings.get('backup_interval_hours', 24)}

# Game Settings
DAILY_HEARTS={game_settings.get('daily_hearts', 10)}
HEART_RESET_HOURS={game_settings.get('heart_reset_hours', 24)}
CLAIM_COOLDOWN_HOURS={game_settings.get('claim_cooldown_hours', 24)}
ABILITY_COOLDOWN_HOURS={game_settings.get('ability_cooldown_hours', 24)}
MAX_CARDS_PER_PAGE={game_settings.get('max_cards_per_page', 8)}

# Card Drop Rates (must sum to 100)
DROP_RATE_NORMAL={game_settings.get('card_drop_rates', {}).get('normal', 65)}
DROP_RATE_EPIC={game_settings.get('card_drop_rates', {}).get('epic', 25)}
DROP_RATE_LEGEND={game_settings.get('card_drop_rates', {}).get('legend', 10)}

# Image Settings
CARD_IMAGES_PATH={image_settings.get('card_images_path', 'card_images/')}
DEFAULT_CARD_IMAGE={image_settings.get('default_card_image', 'card_images/default.png')}
ENABLE_IMAGES={str(image_settings.get('enable_images', True)).lower()}
MAX_IMAGE_SIZE_MB={image_settings.get('max_size_mb', 5)}

# Webhook Settings (optional)
WEBHOOK_URL=
WEBHOOK_PORT={main_config.get('bot_settings', {}).get('webhook_port', 8443)}
"""
    
    # نوشتن فایل .env
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("✅ فایل .env ایجاد شد")
    return True

def verify_migration():
    """بررسی صحت مهاجرت"""
    try:
        from config_loader import load_config
        config = load_config()
        
        print("\n✅ تست بارگذاری تنظیمات:")
        print(f"  - Bot Token: {config['bot_settings']['token'][:20]}...")
        print(f"  - Admins: {len(config['bot_settings']['admin_user_ids'])} نفر")
        print(f"  - Daily Hearts: {config['game_settings']['daily_hearts']}")
        print(f"  - Database: {config['database']['path']}")
        
        return True
    except Exception as e:
        print(f"\n❌ خطا در تست: {e}")
        return False

def main():
    print("=" * 60)
    print("🔒 مهاجرت امنیتی: انتقال به .env")
    print("=" * 60)
    print()
    
    # بررسی وجود .env
    if os.path.exists('.env'):
        response = input("⚠️  فایل .env از قبل وجود دارد. بازنویسی شود؟ (y/n): ")
        if response.lower() != 'y':
            print("❌ عملیات لغو شد")
            return
    
    # مرحله 1: بکاپ
    print("\n📦 مرحله 1: بکاپ گرفتن از فایل‌های قدیمی...")
    backups = backup_old_configs()
    
    # مرحله 2: ایجاد .env
    print("\n🔧 مرحله 2: ایجاد فایل .env...")
    if not create_env_file():
        print("❌ مهاجرت ناموفق بود")
        return
    
    # مرحله 3: تست
    print("\n🧪 مرحله 3: تست تنظیمات جدید...")
    if not verify_migration():
        print("❌ تست ناموفق بود")
        return
    
    # مرحله 4: راهنمایی
    print("\n" + "=" * 60)
    print("✅ مهاجرت با موفقیت انجام شد!")
    print("=" * 60)
    print("\n📝 مراحل بعدی:")
    print("  1. نصب وابستگی: pip install python-dotenv")
    print("  2. تست ربات: python telegram_bot.py")
    print("  3. بررسی SECURITY_MIGRATION.md برای جزئیات بیشتر")
    print("\n⚠️  مهم:")
    print("  - فایل .env را هرگز commit نکنید!")
    print("  - فایل‌های بکاپ را نگه دارید:")
    for backup in backups:
        print(f"    • {backup}")
    print()

if __name__ == "__main__":
    main()
