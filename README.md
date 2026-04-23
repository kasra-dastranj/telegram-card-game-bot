# TelBattle - بازی کارت تلگرامی

بازی کارت PvP برای تلگرام با پشتیبانی از گروه‌ها.

## ساختار پروژه

```
├── telegram_bot.py        # ربات اصلی تلگرام
├── game_core.py           # هسته بازی و دیتابیس
├── web_api.py             # REST API پنل ادمین
├── web_admin_panel.py     # پنل مدیریت وب (ساده)
├── admin_panel_full.html  # رابط کاربری پنل ادمین
├── card_management.html   # مدیریت کارت‌ها
│
├── claim_system.py        # سیستم کلیم روزانه
├── arena_system.py        # زمین‌های بازی
├── battle_system_3rounds.py  # مبارزه ۳ راوندی
├── economy_system.py      # سیستم سکه و اقتصاد
├── fusion_system.py       # ادغام کارت‌ها
├── phase2_systems.py      # Level/XP/Tier
├── risk_mode_system.py    # حالت ریسک
├── skins_system.py        # اسکین کارت‌ها
├── rare_cards_system.py   # کارت‌های نادر
├── card_missions_system.py # ماموریت‌ها
├── tier_decay_system.py   # سیستم Decay
│
├── game_config.json       # تنظیمات اصلی
├── card_dialogs.json      # دیالوگ‌های کارت‌ها
├── game_bot.db            # دیتابیس
│
├── card_images/           # تصاویر PNG کارت‌ها
└── stickers/              # استیکرهای WebP تلگرام
```

## راه‌اندازی

```bash
pip install -r requirements.txt
python telegram_bot.py
```

## پنل ادمین

```bash
python web_api.py
# http://localhost:5000
```

## تنظیمات

فایل `game_config.json` را ویرایش کنید:
- `bot_settings.token` — توکن ربات از BotFather
- `bot_settings.admin_user_ids` — آیدی عددی ادمین‌ها
- `channel_settings.required_channel` — کانال اجباری برای استفاده از ربات
