# ⏰ راه‌اندازی Cron Job برای Tier Decay

## 📋 نیازمندی‌ها

سیستم Tier Decay نیاز به اجرای روزانه دارد تا بازیکنان غیرفعال Decay دریافت کنند.

## 🔧 راه‌اندازی در Linux/Mac

### 1. تست دستی

ابتدا اسکریپت را به صورت دستی تست کنید:

```bash
python daily_tier_decay.py game_bot.db
```

خروجی باید شامل آمار Decay باشد.

### 2. اضافه کردن به Crontab

برای اجرای روزانه در ساعت 00:00:

```bash
crontab -e
```

سپس این خط را اضافه کنید:

```
0 0 * * * cd /path/to/card_game && /path/to/python daily_tier_decay.py game_bot.db >> tier_decay_cron.log 2>&1
```

**نکات:**
- `/path/to/card_game` را با مسیر واقعی پروژه جایگزین کنید
- `/path/to/python` را با مسیر Python environment خود جایگزین کنید (معمولاً `.venv/bin/python`)

### 3. بررسی Cron Jobs فعال

```bash
crontab -l
```

### 4. مشاهده لاگ‌ها

```bash
tail -f tier_decay_cron.log
```

## 🪟 راه‌اندازی در Windows

### روش 1: Task Scheduler

1. باز کردن Task Scheduler
2. Create Basic Task
3. نام: "TelBattle Tier Decay"
4. Trigger: Daily در ساعت 00:00
5. Action: Start a program
   - Program: `C:\path\to\.venv\Scripts\python.exe`
   - Arguments: `daily_tier_decay.py game_bot.db`
   - Start in: `C:\path\to\card_game`

### روش 2: Python Schedule

اگر می‌خواهید از Python استفاده کنید:

```python
import schedule
import time
from tier_decay_system import TierDecaySystem
from game_core import DatabaseManager

def run_decay():
    db = DatabaseManager('game_bot.db')
    tier_decay = TierDecaySystem(db)
    stats = tier_decay.apply_decay_to_all_players()
    print(f"Decay applied: {stats}")

# اجرای روزانه در ساعت 00:00
schedule.every().day.at("00:00").do(run_decay)

while True:
    schedule.run_pending()
    time.sleep(60)
```

نصب schedule:
```bash
pip install schedule
```

## 📊 مانیتورینگ

### بررسی آخرین اجرا

```bash
tail -20 tier_decay.log
```

### بررسی تعداد بازیکنان Decay شده

```sql
SELECT COUNT(*) FROM player_progression 
WHERE last_played_at < datetime('now', '-1 day');
```

## 🔍 عیب‌یابی

### مشکل: Cron اجرا نمی‌شود

1. بررسی مجوزها:
```bash
chmod +x daily_tier_decay.py
```

2. بررسی لاگ سیستم:
```bash
grep CRON /var/log/syslog
```

3. تست با مسیر کامل:
```bash
/full/path/to/python /full/path/to/daily_tier_decay.py /full/path/to/game_bot.db
```

### مشکل: خطای Import

مطمئن شوید که Python environment صحیح استفاده می‌شود:

```bash
which python  # باید مسیر .venv را نشان دهد
```

### مشکل: دیتابیس قفل است

اگر ربات در حال اجراست، ممکن است دیتابیس قفل باشد. راه‌حل:

1. Cron را در زمانی اجرا کنید که ترافیک کم است (مثلاً 3 صبح)
2. از WAL mode استفاده کنید:

```python
conn = sqlite3.connect('game_bot.db')
conn.execute('PRAGMA journal_mode=WAL')
```

## ⚙️ تنظیمات پیشرفته

### تغییر زمان اجرا

برای اجرا در ساعت 3 صبح:

```
0 3 * * * cd /path/to/card_game && python daily_tier_decay.py game_bot.db
```

### اجرای هفتگی

برای اجرا فقط یکشنبه‌ها:

```
0 0 * * 0 cd /path/to/card_game && python daily_tier_decay.py game_bot.db
```

### ارسال نوتیفیکیشن

برای دریافت ایمیل در صورت خطا:

```bash
0 0 * * * cd /path/to/card_game && python daily_tier_decay.py game_bot.db || echo "Tier Decay failed!" | mail -s "TelBattle Error" admin@example.com
```

## 📝 نکات مهم

1. **Backup**: قبل از اولین اجرا، از دیتابیس backup بگیرید
2. **Test Database**: ابتدا روی test database تست کنید
3. **Monitoring**: لاگ‌ها را به طور منظم بررسی کنید
4. **Timezone**: مطمئن شوید timezone سرور صحیح است

## ✅ چک‌لیست راه‌اندازی

- [ ] اسکریپت به صورت دستی تست شد
- [ ] Cron job اضافه شد
- [ ] لاگ‌ها قابل دسترسی هستند
- [ ] Backup از دیتابیس گرفته شد
- [ ] اولین اجرای خودکار موفق بود
- [ ] مانیتورینگ راه‌اندازی شد

## 🆘 پشتیبانی

اگر مشکلی داشتید:

1. لاگ‌ها را بررسی کنید
2. اسکریپت را دستی اجرا کنید
3. مجوزها را چک کنید
4. مسیرها را بررسی کنید
