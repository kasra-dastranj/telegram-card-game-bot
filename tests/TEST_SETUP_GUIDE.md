# 🧪 راهنمای راه‌اندازی محیط تست

## چرا محیط تست؟

ربات production شما در حال اجراست و نباید روی آن تست کنیم. محیط تست به شما اجازه می‌دهد:
- تمام فیچرهای جدید را تست کنید
- Migration را بدون خطر امتحان کنید
- باگ‌ها را قبل از production پیدا کنید

---

## مراحل راه‌اندازی

### ۱. ساخت ربات تست

```
1. به @BotFather در تلگرام بروید
2. دستور /newbot را بزنید
3. نام ربات: TelBattle Test Bot (یا هر نام دیگری)
4. Username: TelBattleTest_bot (باید با _bot تمام شود)
5. توکن دریافتی را کپی کنید
```

### ۲. ساخت کانال تست

```
1. یک کانال عمومی بسازید
2. نام: TelBattle Test
3. Username: @TelBattleTest (یا هر نام دیگری)
4. ربات تست را به عنوان ادمین اضافه کنید
```

### ۳. دریافت User ID

```
1. به @userinfobot بروید
2. /start را بزنید
3. User ID خود را کپی کنید
```

### ۴. تنظیم .env.test

فایل `.env.test` را باز کنید و این مقادیر را جایگزین کنید:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # توکن ربات تست
ADMIN_USER_IDS=123456789  # User ID شما
REQUIRED_CHANNEL=@TelBattleTest  # کانال تست
```

### ۵. راه‌اندازی محیط

```bash
python setup_test_environment.py
```

این اسکریپت:
- بررسی می‌کند .env.test درست تنظیم شده
- یک کپی از دیتابیس production می‌سازد (game_bot_test.db)
- اسکریپت‌های لازم را ایجاد می‌کند

---

## اجرای ربات تست

```bash
python run_test_bot.py
```

این ربات:
- از توکن تست استفاده می‌کند
- به دیتابیس تست متصل می‌شود
- هیچ تأثیری روی ربات production ندارد

---

## تست Migration

```bash
# ۱. اجرای migration روی دیتابیس تست
python phase2_migration.py

# ۲. اجرای ربات تست برای بررسی
python run_test_bot.py

# ۳. تست فیچرهای جدید در تلگرام
```

---

## ساختار فایل‌ها

```
📁 پروژه
├── 🔴 Production (دست نزنید!)
│   ├── .env                    # تنظیمات production
│   ├── game_bot.db             # دیتابیس production
│   └── telegram_bot.py         # کد اصلی
│
├── 🟢 Test (برای تست)
│   ├── .env.test               # تنظیمات تست
│   ├── game_bot_test.db        # دیتابیس تست
│   ├── run_test_bot.py         # اجرای ربات تست
│   └── setup_test_environment.py
│
└── 🔧 Development
    ├── phase2_migration.py     # اسکریپت migration
    ├── test_migration.py       # تست migration
    └── game_core.py            # کد اصلی بازی
```

---

## چک‌لیست قبل از Production

قبل از اعمال تغییرات روی ربات اصلی:

- [ ] ربات تست ساخته شد
- [ ] .env.test تنظیم شد
- [ ] محیط تست راه‌اندازی شد
- [ ] Migration روی دیتابیس تست اجرا شد
- [ ] ربات تست بدون مشکل اجرا می‌شود
- [ ] تمام فیچرهای جدید تست شدند
- [ ] هیچ باگ critical وجود ندارد
- [ ] بکاپ کامل از production گرفته شد

---

## عیب‌یابی

### خطا: "توکن نامعتبر"
```
بررسی کنید:
- توکن در .env.test درست کپی شده
- فضای خالی اضافی وجود ندارد
- از توکن ربات تست استفاده می‌کنید (نه production)
```

### خطا: "دیتابیس قفل است"
```
ربات production را متوقف کنید یا:
- از دیتابیس تست استفاده کنید
- فایل game_bot.db.lock را پاک کنید
```

### ربات پاسخ نمی‌دهد
```
بررسی کنید:
- ربات در کانال تست ادمین است
- User ID شما در ADMIN_USER_IDS است
- ربات با /start شروع شده
```

---

## نکات امنیتی

✅ **انجام دهید:**
- از ربات و کانال جداگانه برای تست استفاده کنید
- .env.test را در .gitignore قرار دهید
- قبل از هر تغییر بکاپ بگیرید

❌ **انجام ندهید:**
- توکن production را در .env.test نگذارید
- روی دیتابیس production تست نکنید
- تغییرات تست نشده را مستقیم deploy نکنید

---

## پشتیبانی

اگر مشکلی داشتید:
1. لاگ‌های bot.log را بررسی کنید
2. دستور python setup_test_environment.py را دوباره اجرا کنید
3. مطمئن شوید تمام dependencies نصب شده‌اند

```bash
pip install -r requirements.txt
```
