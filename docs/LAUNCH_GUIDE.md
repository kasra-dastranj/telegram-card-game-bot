# 🚀 Phase 2 Launch Guide

## راهنمای راه‌اندازی Phase 2

---

## ⚠️ قبل از Launch

### 1. Backup دیتابیس
```bash
# Backup دیتابیس فعلی
cp game_bot.db game_bot.db.backup_$(date +%Y%m%d_%H%M%S)

# بررسی backup
ls -lh game_bot.db.backup_*
```

### 2. بررسی Environment
```bash
# بررسی .env
cat .env

# بررسی توکن ربات
# بررسی مسیر دیتابیس
# بررسی تنظیمات
```

### 3. تست Migration
```bash
# تست روی دیتابیس تست
python phase2_migration.py

# بررسی نتیجه
# اگر موفق بود، ادامه بده
```

---

## 🔧 مراحل راه‌اندازی

### مرحله 1: Migration دیتابیس

```bash
# 1. اجرای Migration اصلی
python phase2_migration.py
# پاسخ: yes

# 2. اجرای Migration Battle
python migrate_3round_battle.py
# پاسخ: yes

# 3. اجرای Migration Economy
python migrate_economy.py
# پاسخ: yes
```

**بررسی موفقیت:**
```bash
# بررسی جداول جدید
sqlite3 game_bot.db "SELECT name FROM sqlite_master WHERE type='table';"

# باید این جداول را ببینید:
# - player_progression
# - fusion_log
# - battle_states
# - round_history
```

---

### مرحله 2: تست سیستم‌ها

```bash
# 1. تست Phase 2 Systems
python test_phase2_systems.py

# 2. تست Claim System
python test_claim_system.py

# 3. تست Fusion
python test_fusion_ui.py

# 4. تست Economy
python test_economy.py

# 5. تست Battle
python test_3round_simulation.py

# 6. تست Profile
python test_bot_profile.py
```

**همه تست‌ها باید موفق باشند (✅)**

---

### مرحله 3: راه‌اندازی ربات

```bash
# 1. توقف ربات فعلی (اگر در حال اجرا است)
# Ctrl+C یا kill process

# 2. راه‌اندازی ربات جدید
python telegram_bot.py

# 3. بررسی لاگ
tail -f bot.log
```

**بررسی موفقیت:**
- ربات باید بدون خطا start شود
- لاگ باید "✅ ربات آماده شد" را نشان دهد
- دستور `/start` در تلگرام باید کار کند

---

### مرحله 4: تست در تلگرام

#### تست 1: منوی اصلی
```
/start
```
**انتظار:**
- دکمه "🎴 کارت‌های من"
- دکمه "⚔️ چالش PvP"
- دکمه "🎁 کلیم روزانه"
- دکمه "🔮 Fusion کارت‌ها"
- دکمه "💰 اقتصاد و شاپ"

#### تست 2: پروفایل
```
/profile
```
**انتظار:**
- نمایش Level و XP
- نمایش Tier و TP
- نمایش تعداد کارت‌ها
- نمایش آمار

#### تست 3: Claim
```
/claim
```
**انتظار:**
- دریافت کارت Normal
- پیام موفقیت

#### تست 4: Fusion
```
کلیک روی "🔮 Fusion کارت‌ها"
```
**انتظار:**
- نمایش منوی Fusion
- نمایش تعداد کارت‌های موجود
- امکان انتخاب نوع Fusion

#### تست 5: Economy
```
کلیک روی "💰 اقتصاد و شاپ"
```
**انتظار:**
- نمایش موجودی سکه
- نمایش ماینینگ روزانه
- دکمه‌های: ماینینگ، تبدیل، شاپ

#### تست 6: بازی PvP
```
/fight در گروه
```
**انتظار:**
- نمایش پنل چالش
- امکان قبول چالش
- بازی 3 راوندی
- نمایش نتیجه هر راوند

---

## 📢 اطلاع‌رسانی به کاربران

### پیام 1: اعلام به‌روزرسانی (قبل از Launch)
```
📢 اطلاعیه مهم!

🔄 به‌روزرسانی بزرگ Phase 2 در راه است!

⏰ زمان: [تاریخ و ساعت]
⏱️ مدت توقف: حدود 10 دقیقه

✨ ویژگی‌های جدید:
• سیستم Level و Tier
• Fusion کارت‌ها
• اقتصاد سکه و ماینینگ
• بازی 3 راوندی
• شاپ و خرید آیتم‌ها

📋 تغییرات مهم:
• همه کارت‌ها به Normal تبدیل می‌شوند
• آمار کارت‌ها تغییر می‌کند (0-10)
• سیستم Claim جدید

🎁 هدیه راه‌اندازی:
• 100 سکه رایگان
• 1 کارت Epic رایگان

منتظر باشید! 🚀
```

### پیام 2: اعلام راه‌اندازی (بعد از Launch)
```
🎉 Phase 2 راه‌اندازی شد!

✅ ربات دوباره فعال است!

🆕 چه چیزی جدید است؟

1️⃣ سیستم Level (1-30)
   • با بازی XP کسب کنید
   • Level بالاتر = امکانات بیشتر

2️⃣ سیستم Tier (Bronze → Elite)
   • با برد TP کسب کنید
   • Tier بالاتر = پاداش بیشتر

3️⃣ Fusion کارت‌ها
   • 3 Normal → 1 Epic
   • 3 Epic → 1 Legend
   • شما انتخاب می‌کنید کدام کارت ارتقا یابد!

4️⃣ اقتصاد سکه
   • ماینینگ روزانه (هر 5 کارت = 1 سکه)
   • تبدیل امتیاز به سکه
   • خرید از شاپ

5️⃣ بازی 3 راوندی
   • Best of 3
   • Stat Locking (هر stat فقط یکبار)
   • استراتژی بیشتر!

🎁 هدیه شما:
/start بزنید و هدیه‌تان را دریافت کنید!

📖 راهنما: /help
💬 پشتیبانی: @KhasteNewsGap

بازی را شروع کنید: /start
```

---

## 🎁 اعطای هدیه راه‌اندازی

### روش 1: دستی (برای تعداد کم)
```python
# در Python shell یا script
from economy_system import EconomySystem
from game_core import DatabaseManager

db = DatabaseManager()
economy = EconomySystem(db)

# لیست user_id ها
user_ids = [123456, 789012, ...]

for user_id in user_ids:
    # 100 سکه
    economy.add_coins(user_id, 100, "launch_gift")
    
    # 1 کارت Epic (باید دستی اضافه شود)
    # ...
```

### روش 2: خودکار (برای همه)
```python
# اسکریپت اعطای هدیه
import sqlite3

conn = sqlite3.connect('game_bot.db')
cursor = conn.cursor()

# 100 سکه به همه
cursor.execute('UPDATE players SET coins = coins + 100')

conn.commit()
conn.close()

print("✅ هدیه به همه اعطا شد!")
```

---

## 📊 مانیتورینگ بعد از Launch

### 1. بررسی لاگ‌ها
```bash
# لاگ‌های اخیر
tail -f bot.log

# جستجوی خطاها
grep ERROR bot.log

# جستجوی Fusion
grep "Fusion" bot.log
```

### 2. بررسی دیتابیس
```bash
# تعداد بازیکنان
sqlite3 game_bot.db "SELECT COUNT(*) FROM players;"

# تعداد Fusion ها
sqlite3 game_bot.db "SELECT COUNT(*) FROM fusion_log;"

# توزیع Tier
sqlite3 game_bot.db "SELECT current_tier, COUNT(*) FROM player_progression GROUP BY current_tier;"

# موجودی سکه
sqlite3 game_bot.db "SELECT AVG(coins), MAX(coins), MIN(coins) FROM players;"
```

### 3. آمار روزانه
```python
# اسکریپت آمار
python return_analytics.py
```

---

## 🐛 عیب‌یابی

### مشکل 1: ربات start نمی‌شود
**راه‌حل:**
```bash
# بررسی لاگ
tail -n 50 bot.log

# بررسی توکن
cat .env | grep BOT_TOKEN

# بررسی دیتابیس
sqlite3 game_bot.db "PRAGMA integrity_check;"
```

### مشکل 2: Migration ناموفق
**راه‌حل:**
```bash
# Restore از backup
cp game_bot.db.backup_XXXXXX game_bot.db

# اجرای مجدد migration
python phase2_migration.py
```

### مشکل 3: Fusion کار نمی‌کند
**راه‌حل:**
```bash
# بررسی جدول fusion_log
sqlite3 game_bot.db "SELECT * FROM fusion_log LIMIT 5;"

# تست Fusion
python test_fusion_ui.py
```

### مشکل 4: Economy کار نمی‌کند
**راه‌حل:**
```bash
# بررسی ستون coins
sqlite3 game_bot.db "PRAGMA table_info(players);"

# تست Economy
python test_economy.py
```

---

## 🔄 Rollback (در صورت نیاز)

### مرحله 1: توقف ربات
```bash
# Ctrl+C یا kill process
```

### مرحله 2: Restore دیتابیس
```bash
# Restore از backup
cp game_bot.db.backup_XXXXXX game_bot.db
```

### مرحله 3: راه‌اندازی نسخه قبلی
```bash
# Checkout نسخه قبلی (اگر از Git استفاده می‌کنید)
git checkout <commit-before-phase2>

# راه‌اندازی ربات
python telegram_bot.py
```

---

## ✅ Checklist نهایی

قبل از Launch:
- [ ] Backup دیتابیس گرفته شد
- [ ] Migration ها تست شدند
- [ ] همه تست‌ها موفق بودند
- [ ] پیام اطلاع‌رسانی آماده است
- [ ] هدیه راه‌اندازی آماده است

بعد از Launch:
- [ ] ربات بدون خطا start شد
- [ ] تست‌های دستی در تلگرام موفق بودند
- [ ] پیام اطلاع‌رسانی ارسال شد
- [ ] هدیه‌ها اعطا شدند
- [ ] مانیتورینگ فعال است

---

## 📞 پشتیبانی

در صورت بروز مشکل:
1. بررسی این راهنما
2. بررسی `PHASE2_FINAL_SUMMARY.md`
3. بررسی لاگ‌ها
4. تماس با توسعه‌دهنده

---

**موفق باشید! 🚀**

تاریخ: 25 فوریه 2026
