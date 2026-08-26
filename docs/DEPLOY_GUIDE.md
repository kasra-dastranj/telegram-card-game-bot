# 🚀 راهنمای آپلود و اجرای پروژه روی سرور

## ✅ تغییرات انجام شده

### 1. پاک کردن فایل‌های اضافی
- ✅ فایل‌های HTML تکراری به پوشه `archive_html/` منتقل شدند
- ✅ فقط 2 فایل HTML باقی ماند:
  - `admin_panel_offline.html` - پنل ادمین اصلی (کاملاً آفلاین)
  - `simple_test.html` - صفحه تست

### 2. تغییر فایل اصلی پنل
- ✅ `web_api.py` اصلاح شد تا `admin_panel_offline.html` را serve کند
- ✅ پنل بدون هیچ وابستگی خارجی (CDN) کار می‌کند

## 📤 دستورات آپلود به سرور

> احراز هویت production فقط با کلید اختصاصی خارج از repository انجام می‌شود:
> `%USERPROFILE%\.ssh\telbattle_deploy_ed25519`. رمز، token یا private key را
> هرگز داخل فایل‌های پروژه ثبت نکنید.

### مرحله 1: آپلود فایل‌های اصلی
```powershell
# آپلود web_api.py (تغییر کرده)
scp -i "$env:USERPROFILE\.ssh\telbattle_deploy_ed25519" "C:\Users\lenovo\Desktop\card game\web_api.py" root@89.106.206.220:"/root/card game/"

# آپلود پنل ادمین جدید
scp -i "$env:USERPROFILE\.ssh\telbattle_deploy_ed25519" "C:\Users\lenovo\Desktop\card game\admin_panel_offline.html" root@89.106.206.220:"/root/card game/"

# آپلود telegram_bot.py (در صورت تغییر)
scp -i "$env:USERPROFILE\.ssh\telbattle_deploy_ed25519" "C:\Users\lenovo\Desktop\card game\telegram_bot.py" root@89.106.206.220:"/root/card game/"

# آپلود game_core.py (در صورت تغییر)
scp -i "$env:USERPROFILE\.ssh\telbattle_deploy_ed25519" "C:\Users\lenovo\Desktop\card game\game_core.py" root@89.106.206.220:"/root/card game/"
```

### مرحله 2: اتصال به سرور
```powershell
ssh -i "$env:USERPROFILE\.ssh\telbattle_deploy_ed25519" root@89.106.206.220
# Authentication: dedicated SSH key (private key is stored outside the repository)
```

### مرحله 3: رفتن به پوشه پروژه
```bash
cd "/root/card game"
```

### مرحله 4: متوقف کردن سرویس‌های قبلی
```bash
# متوقف کردن ربات تلگرام
pkill -9 -f telegram_bot.py

# متوقف کردن Web API
pkill -9 -f web_api.py

# بررسی که همه متوقف شدند
ps aux | grep -E "telegram_bot|web_api"
```

### مرحله 5: اجرای سرویس‌ها در پس‌زمینه
```bash
# اجرای Web API
nohup python3 web_api.py > web_api.log 2>&1 &

# صبر 2 ثانیه
sleep 2

# اجرای ربات تلگرام
nohup python3 telegram_bot.py > bot.log 2>&1 &

# بررسی وضعیت
ps aux | grep -E "telegram_bot|web_api"
```

### مرحله 6: تست سرویس‌ها
```bash
# تست Web API
curl http://localhost:5000/api/stats

# مشاهده لاگ‌ها
tail -f web_api.log
# یا
tail -f bot.log

# خروج از tail: Ctrl+C
```

## 🌐 دسترسی به پنل ادمین

**آدرس سرور**: https://89-106-206-220.nip.io

### ویژگی‌های پنل:
- ⚙️ **تنظیمات بازی**: تغییر تعداد جان روزانه
- ❄️ **مدیریت Cooldown**: تنظیمات کارت‌های Epic/Legend
- 📊 **آمار سیستم**: مشاهده آمار کلی

## 🔧 عیب‌یابی

### اگر پنل صفحه سفید نشان داد:
```bash
# بررسی لاگ web_api
tail -20 web_api.log

# بررسی اینکه فایل HTML موجود است
ls -lh admin_panel_offline.html

# ریستارت web_api
pkill -9 -f web_api.py
nohup python3 web_api.py > web_api.log 2>&1 &
```

### اگر API خطا داد:
```bash
# بررسی دیتابیس
python3 check_db.py

# تست API ها
curl http://localhost:5000/api/stats
curl http://localhost:5000/api/game-settings
curl http://localhost:5000/api/cards/cooldown-settings
```

### اگر ربات کار نکرد:
```bash
# بررسی لاگ
tail -50 bot.log

# بررسی توکن در game_config.json
cat game_config.json | grep token

# ریستارت ربات
pkill -9 -f telegram_bot.py
nohup python3 telegram_bot.py > bot.log 2>&1 &
```

## 📝 نکات مهم

1. **پورت 5000** باید در فایروال سرور باز باشد
2. **توکن ربات** را از `game_config.json` محرمانه نگه دارید
3. **بکاپ دیتابیس** قبل از هر تغییر مهم:
   ```bash
   cp game_bot.db game_bot.db.backup_$(date +%Y%m%d_%H%M%S)
   ```

## ✅ چک‌لیست نهایی

- [ ] فایل‌ها آپلود شدند
- [ ] سرویس‌های قدیمی متوقف شدند
- [ ] Web API اجرا شد
- [ ] ربات تلگرام اجرا شد
- [ ] پنل ادمین در مرورگر باز می‌شود
- [ ] API ها پاسخ می‌دهند
- [ ] ربات در تلگرام پاسخ می‌دهد

---
**🎉 موفق باشید!**
