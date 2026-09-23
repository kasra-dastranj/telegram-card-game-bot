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
python web/web_api.py
# http://localhost:5000
```

## Arena Registry (زمین‌های نسخه‌دار)

پنل زمین‌ها در `/arenas` قرار دارد. اجرای معمول `DatabaseManager` جدول‌های جدید را
به‌صورت additive می‌سازد و ده زمین فعلی را بدون تغییر Balance seed می‌کند. برای اجرای
صریح migration نیز می‌توان از دستور زیر استفاده کرد:

```bash
python migrations/migrate_arena_registry.py game_bot.db
```

تنظیمات Production مهم:

- `ARENA_ADMIN_TOKEN` — توکن پایه و اجباری پنل برای خواندن و ویرایش Draft؛ فقط روی سرور تنظیم شود.
- `ARENA_ADMIN_PUBLISH_TOKEN` — توکن مستقل انتشار (اختیاری ولی توصیه‌شده)؛ در نبود آن توکن پایه استفاده می‌شود.
- `ARENA_ADMIN_ARCHIVE_TOKEN` — توکن مستقل آرشیو (اختیاری ولی توصیه‌شده)؛ در نبود آن توکن انتشار/پایه استفاده می‌شود.
- `ARENA_ADMIN_ACTOR`، `ARENA_ADMIN_PUBLISH_ACTOR` و `ARENA_ADMIN_ARCHIVE_ACTOR` — شناسه ثابت عامل برای Audit Log.
- `ADMIN_CORS_ORIGINS` — فهرست comma-separated مبداهای مجاز پنل؛ اگر خالی باشد CORS برای API فعال نمی‌شود.
- `ARENA_ADMIN_LOCAL_DEV=1` — فقط برای توسعه محلی روی loopback و بدون توکن؛ هرگز در Production فعال نشود.
- `ARENA_REGISTRY_READS=0` — Rollback خواندن Runtime به ثابت‌های قدیمی، بدون حذف داده‌ها.
- `ARENA_REGISTRY_FALLBACK_SEED=0` — جلوگیری از fallback به زمین‌های seed در Mini App وقتی هیچ زمین فعالی نیست.
- `MINIAPP_ARENA_MEDIA_DIR` — مسیر پایدار پس‌زمینه‌های نسخه‌دار Mini App؛ پیش‌فرض `media/arena-backgrounds` است و API آن را پیش از فایل‌های Build سرو می‌کند.

در Production قبل از migration از SQLite backup بگیرید. زمین Published حذف نمی‌شود؛ برای
تغییر آن از «ساخت Draft از نسخه منتشرشده» استفاده کنید. Matchهای تازه Snapshot Arena را
می‌گیرند و Publish بعدی روی Match فعال اثر نمی‌گذارد.

## تنظیمات

فایل `game_config.json` را ویرایش کنید:
- `bot_settings.token` — توکن ربات از BotFather
- `bot_settings.admin_user_ids` — آیدی عددی ادمین‌ها
- `channel_settings.required_channel` — کانال اجباری برای استفاده از ربات
