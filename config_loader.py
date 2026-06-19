#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Loader - بارگذاری تنظیمات از .env
"""

import os
from typing import Dict, List, Any
from dotenv import load_dotenv

class ConfigLoader:
    """کلاس بارگذاری تنظیمات از .env"""
    
    def __init__(self, env_path: str = ".env"):
        """
        بارگذاری تنظیمات از فایل .env
        
        Args:
            env_path: مسیر فایل .env
        """
        # بارگذاری متغیرهای محیطی
        load_dotenv(env_path)
        
        # بررسی وجود توکن
        if not os.getenv("BOT_TOKEN"):
            raise ValueError(
                "⚠️ توکن ربات یافت نشد!\n"
                "لطفاً فایل .env را ایجاد کنید و BOT_TOKEN را تنظیم کنید.\n"
                "می‌توانید از .env.example به عنوان الگو استفاده کنید."
            )
    
    def get_config(self) -> Dict[str, Any]:
        """
        دریافت تمام تنظیمات به صورت dictionary
        
        Returns:
            Dict حاوی تمام تنظیمات
        """
        return {
            "bot_settings": self.get_bot_settings(),
            "game_settings": self.get_game_settings(),
            "database": self.get_database_settings(),
            "image_settings": self.get_image_settings(),
            "channel_settings": self.get_channel_settings()
        }
    
    def get_bot_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات ربات"""
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        
        return {
            "token": os.getenv("BOT_TOKEN"),
            "admin_user_ids": admin_ids,
            "webhook_url": os.getenv("WEBHOOK_URL") or None,
            "webhook_port": int(os.getenv("WEBHOOK_PORT", "8443"))
        }
    
    def get_game_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات بازی"""
        return {
            "daily_hearts": int(os.getenv("DAILY_HEARTS", "10")),
            "heart_reset_hours": int(os.getenv("HEART_RESET_HOURS", "24")),
            "claim_cooldown_hours": int(os.getenv("CLAIM_COOLDOWN_HOURS", "24")),
            "ability_cooldown_hours": int(os.getenv("ABILITY_COOLDOWN_HOURS", "24")),
            "max_cards_per_page": int(os.getenv("MAX_CARDS_PER_PAGE", "8")),
            "card_drop_rates": {
                "normal": int(os.getenv("DROP_RATE_NORMAL", "65")),
                "epic": int(os.getenv("DROP_RATE_EPIC", "25")),
                "legend": int(os.getenv("DROP_RATE_LEGEND", "10"))
            }
        }
    
    def get_database_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات دیتابیس"""
        return {
            "path": os.getenv("DB_PATH", "game_bot.db"),
            "backup_interval_hours": int(os.getenv("BACKUP_INTERVAL_HOURS", "24")),
            "auto_backup": os.getenv("AUTO_BACKUP", "true").lower() == "true"
        }
    
    def get_image_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات تصاویر"""
        return {
            "card_images_path": os.getenv("CARD_IMAGES_PATH", "card_images/"),
            "default_card_image": os.getenv("DEFAULT_CARD_IMAGE", "card_images/default.png"),
            "enable_images": os.getenv("ENABLE_IMAGES", "true").lower() == "true",
            "max_size_mb": int(os.getenv("MAX_IMAGE_SIZE_MB", "5")),
            "allowed_formats": ["png", "jpg", "jpeg", "gif"]
        }
    
    def get_channel_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات کانال"""
        channel_id_str = os.getenv("CHANNEL_ID", "")
        channel_id = int(channel_id_str) if channel_id_str else None
        
        return {
            "required_channel": os.getenv("REQUIRED_CHANNEL"),
            "channel_id": channel_id
        }
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> List[str]:
        """
        اعتبارسنجی تنظیمات
        
        Args:
            config: تنظیمات برای بررسی
            
        Returns:
            لیست خطاها (خالی اگر همه چیز درست باشد)
        """
        errors = []
        
        # بررسی توکن
        if not config["bot_settings"]["token"]:
            errors.append("توکن ربات تنظیم نشده است")
        
        # بررسی admin IDs
        if not config["bot_settings"]["admin_user_ids"]:
            errors.append("هیچ ادمینی تنظیم نشده است")
        
        # بررسی drop rates
        drop_rates = config["game_settings"]["card_drop_rates"]
        total_rate = sum(drop_rates.values())
        if total_rate != 100:
            errors.append(f"مجموع drop rates باید 100 باشد (فعلی: {total_rate})")
        
        return errors


# تابع کمکی برای استفاده آسان
def load_config(env_path: str = ".env") -> Dict[str, Any]:
    """
    بارگذاری تنظیمات از .env
    
    Args:
        env_path: مسیر فایل .env
        
    Returns:
        Dict حاوی تمام تنظیمات
        
    Raises:
        ValueError: اگر تنظیمات معتبر نباشند
    """
    loader = ConfigLoader(env_path)
    config = loader.get_config()
    
    # اعتبارسنجی
    errors = ConfigLoader.validate_config(config)
    if errors:
        raise ValueError(
            "⚠️ خطا در تنظیمات:\n" + "\n".join(f"  - {error}" for error in errors)
        )
    
    return config


if __name__ == "__main__":
    # تست بارگذاری تنظیمات
    try:
        config = load_config()
        print("✅ تنظیمات با موفقیت بارگذاری شد:")
        print(f"  - Bot Token: {config['bot_settings']['token'][:20]}...")
        print(f"  - Admins: {len(config['bot_settings']['admin_user_ids'])} نفر")
        print(f"  - Daily Hearts: {config['game_settings']['daily_hearts']}")
        print(f"  - Database: {config['database']['path']}")
    except Exception as e:
        print(f"❌ خطا: {e}")
