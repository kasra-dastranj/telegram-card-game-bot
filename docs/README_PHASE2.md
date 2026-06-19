# 🎮 TelBattle - Phase 2 Implementation

**نسخه**: 2.0  
**تاریخ**: 2026-02-25  
**وضعیت**: Production Ready ✅

---

## 📖 درباره فاز ۲

فاز ۲ TelBattle شامل سیستم‌های پیشرفت و ارتقای کارت است که تجربه بازی را عمیق‌تر و جذاب‌تر می‌کند.

### 🎯 اهداف فاز ۲

1. **پیشرفت بازیکن** - سیستم Level و Tier برای انگیزه بلندمدت
2. **ارتقای کارت** - Fusion برای ساخت کارت‌های قوی‌تر
3. **اقتصاد بازی** - Pool Management و Claim System جدید
4. **تعادل بازی** - Decay System برای جلوگیری از تسلط بازیکنان غیرفعال

---

## ✨ فیچرهای جدید

### 1. Level System (1-30)
- پیشرفت بازیکن بر اساس XP
- فرمول: `100 + (level-2) * 50` XP برای هر level
- نمایش XP bar در profile
- پیام Level Up در PV

### 2. XP Sources
| منبع | XP |
|------|-----|
| Normal Win | 10 |
| Normal Loss | 3 |
| Risk Win | 25 |
| Risk Loss | 5 |
| Card Upgrade Epic | 15 |
| Card Upgrade Legend | 30 |

### 3. Tier System
| Tier | TP Range | Badge |
|------|----------|-------|
| Bronze | 0-499 | 🥉 |
| Silver | 500-999 | 🥈 |
| Gold | 1000-1499 | 🥇 |
| Diamond | 1500-1999 | 💎 |
| Elite | 2000+ | 👑 |

### 4. TP (Tier Points)
- محاسبه پویا بر اساس tier difference
- Base gain: 15 (normal) / 25 (risk)
- Tier multiplier: ±5 per tier difference
- پیام Tier Change در PV

### 5. Decay System
- حفاظت بر اساس tier:
  - Elite: 7 روز
  - Diamond: 5 روز
  - Gold: 3 روز
  - Silver: 2 روز
  - Bronze: 1 روز
- Daily decay: 30 TP
- Max decay: 50% of current TP

### 6. Claim System (جدید)
- همیشه Normal می‌دهد
- احتمال برابر برای همه کارت‌های pool
- کارت‌های Epic/Legend از pool خارج می‌شوند
- هرگز ناموفق نمی‌شود
- Cooldown: 24 ساعت

### 7. Fusion System
#### Normal → Epic
- انتخاب 3 کارت Normal
- بازیکن انتخاب می‌کند کدام Epic شود
- 2 کارت دیگر به pool بازمی‌گردند
- همیشه موفق (100%)

#### Epic → Legend
- انتخاب 3 کارت Epic
- بازیکن انتخاب می‌کند کدام Legend شود
- همیشه موفق (100%)

---

## 📁 ساختار فایل‌ها

### کدهای اصلی
```
fusion_system.py          # سیستم Fusion
claim_system.py           # سیستم Claim جدید
phase2_systems.py         # Level, XP, Tier, TP, Decay
phase2_migration.py       # اسکریپت Migration
config_loader.py          # بارگذاری تنظیمات
game_core.py              # یکپارچگی با فاز ۲
telegram_bot.py           # نمایش Level/Tier
```

### تست‌ها
```
test_claim_system.py      # تست Claim System
test_phase2_systems.py    # تست Phase2 Systems
test_bot_profile.py       # تست Profile و Rewards
test_migration.py         # تست Migration
setup_test_environment.py # راه‌اندازی محیط تست
run_all_tests.py          # اجرای همه تست‌ها
```

### مستندات
```
SESSION_SUMMARY.md        # خلاصه سشن
QUICK_START.md            # راهنمای سریع
FINAL_CHECKLIST.md        # چک‌لیست نهایی
CLAIM_SYSTEM_SUMMARY.md   # خلاصه Claim System
PROGRESS_REPORT.md        # گزارش پیشرفت
PHASE2_IMPLEMENTATION_PLAN.md  # نقشه پیاده‌سازی
SECURITY_MIGRATION.md     # راهنمای امنیتی
TEST_SETUP_GUIDE.md       # راهنمای تست
README_PHASE2.md          # این فایل
```

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
```bash
pip install python-dotenv
```

### تنظیمات
1. کپی کردن `.env.example` به `.env`
2. تنظیم `BOT_TOKEN` و سایر تنظیمات
3. برای تست، `.env.test` را تنظیم کنید

### Migration
```bash
# اجرای migration روی دیتابیس تست
python phase2_migration.py
```

### تست
```bash
# اجرای همه تست‌ها
python run_all_tests.py

# یا تک تک
python test_claim_system.py
python test_phase2_systems.py
python test_bot_profile.py
```

### اجرای ربات
```bash
# ربات تست
python run_test_bot.py

# ربات production
python telegram_bot.py
```

---

## 📊 تغییرات دیتابیس

### جداول جدید
- `player_progression` - Level, XP, Tier, TP
- `fusion_log` - تاریخچه Fusion
- `card_missions` - ماموریت‌های کارت (آینده)

### ستون‌های جدید
- `cards.card_type` - نوع کارت (POWER_TYPE, SPEED_TYPE, IQ_TYPE, POPULARITY_TYPE)
- `players.coins` - سکه‌های بازیکن (آینده)
- `players.weekly_score` - امتیاز هفتگی (آینده)
- `players.max_hearts` - حداکثر جان (آینده)

### تغییرات آمار
- آمار کارت‌ها از 0-100 به 0-10 تبدیل شدند
- همه کارت‌ها به Normal تبدیل شدند
- Card Type به همه کارت‌ها تخصیص یافت

---

## 🎮 راهنمای بازی

### برای بازیکنان

#### دریافت کارت روزانه
```
/start → 🎴 دریافت کارت روزانه
```
- هر روز یک کارت Normal دریافت کنید
- کارت‌هایی که در Epic/Legend دارید از pool خارج می‌شوند

#### مشاهده پروفایل
```
/profile
```
- Level و XP bar
- Tier و TP
- آمار کارت‌ها (Normal/Epic/Legend)
- آمار بازی‌ها

#### PvP Fight
```
در گروه: /fight
```
- پاداش XP و TP بعد از هر بازی
- پیام Level Up در صورت ارتقا
- پیام Tier Change در صورت تغییر tier

#### Fusion (آینده)
```
# UI هنوز پیاده نشده
# فقط backend آماده است
```

---

## 🔧 تنظیمات

### فایل .env
```env
# Bot Settings
BOT_TOKEN=your_bot_token_here
ADMIN_USER_IDS=123456789,987654321

# Game Settings
DAILY_HEARTS=10
HEART_RESET_HOURS=24
CLAIM_COOLDOWN_HOURS=24

# Database
DB_PATH=game_bot.db
AUTO_BACKUP=true
```

### تنظیمات پیشرفته
برای تغییر XP sources, TP calculation, یا Decay settings، فایل `phase2_systems.py` را ویرایش کنید.

---

## 📈 مانیتورینگ

### لاگ‌ها
```bash
# مشاهده لاگ‌های اخیر
tail -100 bot.log

# جستجو در لاگ‌ها
grep "ERROR" bot.log
grep "Level Up" bot.log
grep "Tier Change" bot.log
```

### دیتابیس
```bash
sqlite3 game_bot.db

# آمار بازیکنان
SELECT COUNT(*) FROM player_progression;

# توزیع Level
SELECT level, COUNT(*) FROM player_progression GROUP BY level;

# توزیع Tier
SELECT current_tier, COUNT(*) FROM player_progression GROUP BY current_tier;
```

---

## 🐛 عیب‌یابی

### مشکلات رایج

#### خطا: "No module named 'dotenv'"
```bash
pip install python-dotenv
```

#### خطا: "توکن ربات یافت نشد"
بررسی کنید فایل `.env` وجود دارد و `BOT_TOKEN` تنظیم شده است.

#### خطا: "Database is locked"
ربات production را متوقف کنید یا از دیتابیس تست استفاده کنید.

#### Migration ناموفق
از بکاپ بازگردانید:
```bash
cp game_bot.db.backup_phase2_XXXXXX game_bot.db
```

### لاگ‌های مفید
```bash
# خطاهای critical
grep "ERROR" bot.log | tail -20

# Level Up ها
grep "Level Up" bot.log | tail -10

# Tier Change ها
grep "Tier Change" bot.log | tail -10

# Fusion ها
grep "Fusion" bot.log | tail -10
```

---

## 🔐 امنیت

### نکات مهم
- ✅ `.env` را هرگز commit نکنید
- ✅ `.env.test` را هرگز commit نکنید
- ✅ قبل از هر تغییر بکاپ بگیرید
- ✅ توکن production را در `.env` نگه دارید
- ✅ دسترسی به سرور را محدود کنید

### بکاپ
```bash
# بکاپ دستی
cp game_bot.db game_bot.db.backup_$(date +%Y%m%d_%H%M%S)

# بکاپ خودکار (در .env)
AUTO_BACKUP=true
BACKUP_INTERVAL_HOURS=24
```

---

## 📞 پشتیبانی

### مستندات
- `QUICK_START.md` - راهنمای سریع
- `FINAL_CHECKLIST.md` - چک‌لیست کامل
- `SESSION_SUMMARY.md` - خلاصه سشن

### لاگ‌ها
- `bot.log` - لاگ‌های ربات
- `migration_log_*.txt` - لاگ‌های migration

### تست
```bash
# اجرای همه تست‌ها
python run_all_tests.py
```

---

## 🎯 مراحل بعدی

### فاز 2.5: Fusion UI
- پیاده‌سازی UI در telegram_bot.py
- لیست کارت‌ها با pagination
- انتخاب 3 کارت
- انتخاب کارت ارتقایافته
- تأیید نهایی

### فاز 3: Economy
- Coin System
- Shop System
- Heart Increase
- Skins

### فاز 4: Advanced Features
- Risk Mode (کامل)
- 3-Round Battle
- Arena System
- Weekly Leaderboard

---

## 📜 تاریخچه نسخه‌ها

### v2.0 (2026-02-25)
- ✅ Level System (1-30)
- ✅ XP System
- ✅ Tier System (Bronze → Elite)
- ✅ TP System
- ✅ Decay System
- ✅ Claim System (جدید)
- ✅ Fusion System (backend)
- ✅ Migration از فاز ۱

### v1.0 (قبلی)
- PvP Fight System
- Card Collection
- Basic Profile
- Cooldown System

---

## 🙏 تشکر

از همه کسانی که در توسعه این پروژه مشارکت داشتند، تشکر می‌کنیم!

---

## 📄 لایسنس

این پروژه تحت لایسنس MIT منتشر شده است.

---

**ساخته شده با ❤️ برای جامعه TelBattle**

🎮 **بازی کنید، لذت ببرید، پیشرفت کنید!** 🚀
