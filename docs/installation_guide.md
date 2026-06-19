# 🔧 راهنمای نصب سیستم Cooldown جداگانه

## 📁 فایل‌های آپلود شده:

1. **game_core_cooldown_update.py** - بروزرسانی منطق بازی
2. **web_api_cooldown_update.py** - API های جدید
3. **html_cooldown_section.html** - بخش HTML جدید
4. **installation_guide.md** - این راهنما

## 🚀 مراحل نصب:

### مرحله 1: بروزرسانی game_core.py

```bash
cd "/root/card game"

# بکاپ فایل فعلی
cp game_core.py game_core.py.backup_cooldown

# اضافه کردن جدول جدید به init_database
# در خط حدود 350 (بعد از جدول active_fights) اضافه کنید:
```

**کد برای اضافه کردن:**
```python
# جدول تنظیمات Cooldown هر کارت - NEW
cursor.execute('''
    CREATE TABLE IF NOT EXISTS card_cooldown_settings (
        card_id TEXT PRIMARY KEY,
        win_limit INTEGER DEFAULT 10,
        cooldown_hours INTEGER DEFAULT 24,
        enabled BOOLEAN DEFAULT 1,
        FOREIGN KEY (card_id) REFERENCES cards (card_id)
    )
''')
```

### مرحله 2: اضافه کردن توابع جدید

**در کلاس DatabaseManager، قبل از کلاس GameLogic:**

```python
# کد کامل از فایل game_core_cooldown_update.py کپی کنید
```

### مرحله 3: بروزرسانی web_api.py

```bash
# بکاپ فایل فعلی
cp web_api.py web_api.py.backup_cooldown

# اضافه کردن API های جدید قبل از توابع helper
# کد کامل از فایل web_api_cooldown_update.py کپی کنید
```

### مرحله 4: بروزرسانی card_management.html

```bash
# بکاپ فایل فعلی
cp card_management.html card_management.html.backup_cooldown

# اضافه کردن بخش JavaScript جدید
# کد کامل از فایل html_cooldown_section.html کپی کنید
```

## 🔧 دستورات سریع نصب:

```bash
# 1. رفتن به پوشه پروژه
cd "/root/card game"

# 2. متوقف کردن سرور
pkill -f web_api.py

# 3. بکاپ فایل‌ها
cp game_core.py game_core.py.backup_cooldown
cp web_api.py web_api.py.backup_cooldown
cp card_management.html card_management.html.backup_cooldown

# 4. اعمال تغییرات (دستی)
# فایل‌های بروزرسانی شده را جایگزین کنید

# 5. تست syntax
python3 -c "import game_core; print('game_core OK')"
python3 -c "import web_api; print('web_api OK')"

# 6. راه‌اندازی مجدد
nohup python3 web_api.py > web_api_cooldown.log 2>&1 &

# 7. تست API جدید
curl http://localhost:5000/api/cards/cooldown-settings
```

## 🧪 تست سیستم:

### تست API ها:

```bash
# دریافت تنظیمات همه کارت‌ها
curl http://localhost:5000/api/cards/cooldown-settings

# تغییر تنظیمات یک کارت (جایگزین CARD_ID کنید)
curl -X POST -H "Content-Type: application/json" \
  -d '{"win_limit": 15, "cooldown_hours": 48, "enabled": true}' \
  http://localhost:5000/api/cards/CARD_ID/cooldown

# ریست همه cooldown ها
curl -X POST http://localhost:5000/api/cards/cooldown-settings/reset
```

### تست پنل وب:

1. برو به http://195.248.243.122:5000/
2. دکمه "❄️ مدیریت Cooldown" را کلیک کن
3. تنظیمات کارت‌های Epic/Legend را ببین
4. یک کارت را ویرایش کن
5. تغییرات را ذخیره کن

## 🎯 ویژگی‌های جدید:

✅ **تنظیمات جداگانه برای هر کارت:**
- حد مجاز برد (1-100)
- مدت Cooldown (1-168 ساعت)
- فعال/غیرفعال کردن

✅ **پنل مدیریت وب:**
- نمایش همه کارت‌های Epic/Legend
- ویرایش آنلاین تنظیمات
- ریست دسته‌ای cooldown ها

✅ **API های کامل:**
- مدیریت تک کارت
- مدیریت دسته‌ای
- ریست سیستم

## 🔍 عیب‌یابی:

### اگر API 404 می‌دهد:
```bash
grep -n "cooldown-settings" web_api.py
# باید خطوط API را نشان دهد
```

### اگر دیتابیس خطا می‌دهد:
```bash
python3 -c "
from game_core import DatabaseManager
db = DatabaseManager()
print('Database OK')
"
```

### اگر پنل وب کار نمی‌کند:
```bash
tail -20 web_api_cooldown.log
# بررسی خطاهای JavaScript در مرورگر F12
```

## 📊 ساختار جدول جدید:

```sql
card_cooldown_settings:
├── card_id (TEXT PRIMARY KEY)
├── win_limit (INTEGER DEFAULT 10)
├── cooldown_hours (INTEGER DEFAULT 24)  
├── enabled (BOOLEAN DEFAULT 1)
└── FOREIGN KEY (card_id) → cards(card_id)
```

## 🎉 پس از نصب موفق:

1. هر کارت Epic/Legend تنظیمات جداگانه دارد
2. ادمین می‌تواند از پنل وب تنظیمات را تغییر دهد
3. سیستم cooldown بر اساس تنظیمات هر کارت کار می‌کند
4. امکان ریست دسته‌ای وجود دارد

**موفق باشید! 🚀**