# 🚀 راهنمای نصب و راه‌اندازی کامل

این راهنما قدم به قدم نحوه نصب و راه‌اندازی بات TelBattle رو توضیح میده.

---

## 📋 پیش‌نیازها

قبل از شروع، مطمئن شو این‌ها رو داری:

### 1️⃣ نرم‌افزارها
- **Python 3.9 یا بالاتر** ([دانلود](https://www.python.org/downloads/))
- **Git** ([دانلود](https://git-scm.com/downloads))
- **یک ادیتور کد** (VS Code, PyCharm, یا هر چیز دیگه)

### 2️⃣ حساب‌های مورد نیاز
- **حساب تلگرام**
- **یک بات تلگرام** (از [@BotFather](https://t.me/BotFather) بگیر)
- **(اختیاری)** یک کانال تلگرام برای عضویت اجباری

### 3️⃣ سرور (برای Production)
- **VPS یا سرور لینوکس** (Ubuntu 20.04+ توصیه می‌شه)
- حداقل **512MB RAM** و **10GB فضا**
- دسترسی SSH

---

## 🔧 مرحله 1: دریافت کد

### روش 1: Clone از GitHub
```bash
git clone https://github.com/YOUR_USERNAME/telegram-card-game-bot.git
cd telegram-card-game-bot
```

### روش 2: دانلود ZIP
1. برو به صفحه GitHub پروژه
2. کلیک روی `Code` > `Download ZIP`
3. فایل رو Extract کن

---

## 🐍 مرحله 2: نصب Python و وابستگی‌ها

### در Windows:
```bash
# بررسی نسخه Python
python --version

# ساخت محیط مجازی
python -m venv .venv

# فعال‌سازی محیط مجازی
.venv\Scripts\activate

# نصب وابستگی‌ها
pip install -r requirements.txt
```

### در Linux/Mac:
```bash
# بررسی نسخه Python
python3 --version

# نصب pip (اگه نداری)
sudo apt update
sudo apt install python3-pip python3-venv

# ساخت محیط مجازی
python3 -m venv .venv

# فعال‌سازی محیط مجازی
source .venv/bin/activate

# نصب وابستگی‌ها
pip install -r requirements.txt
```

---

## ⚙️ مرحله 3: تنظیمات بات

### 1️⃣ ساخت بات در تلگرام

1. به [@BotFather](https://t.me/BotFather) پیام بده
2. دستور `/newbot` رو بزن
3. یه اسم برای بات انتخاب کن (مثلاً: `My Card Game Bot`)
4. یه username انتخاب کن که به `bot` ختم بشه (مثلاً: `my_card_game_bot`)
5. توکن بات رو کپی کن (مثل: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2️⃣ تنظیم دستورات بات (اختیاری)

به BotFather پیام بده:
```
/setcommands
```
انتخاب بات، سپس این دستورات رو بفرست:
```
start - شروع بازی
help - راهنمای بازی
profile - مشاهده پروفایل
cards - مشاهده کارت‌ها
claim - دریافت کارت روزانه
fight - شروع مبارزه PvP
leaderboard - لیست برترین‌ها
story - داستان بازی
```

### 3️⃣ ساخت فایل تنظیمات

```bash
# کپی کردن فایل نمونه
cp config.example.json game_config.json

# ویرایش فایل
nano game_config.json
# یا
notepad game_config.json
```

### 4️⃣ پر کردن تنظیمات

فایل `game_config.json` رو باز کن و این‌ها رو تنظیم کن:

```json
{
    "bot_settings": {
        "token": "توکن_بات_خودت_رو_اینجا_بذار",
        "admin_user_ids": [123456789],  // ID تلگرام خودت
        "webhook_url": null,
        "webhook_port": 8443
    },
    "game_settings": {
        "daily_hearts": 10,
        "heart_reset_hours": 24,
        "claim_cooldown_hours": 24,
        "ability_cooldown_hours": 24,
        "max_cards_per_page": 8,
        "card_drop_rates": {
            "normal": 65,
            "epic": 25,
            "legend": 10
        }
    },
    "database": {
        "path": "game_bot.db",
        "backup_interval_hours": 24,
        "auto_backup": true
    },
    "image_settings": {
        "card_images_path": "card_images/",
        "default_card_image": "card_images/default.png",
        "enable_images": true
    }
}
```

### 5️⃣ پیدا کردن User ID خودت

1. به [@userinfobot](https://t.me/userinfobot) پیام بده
2. ID خودت رو کپی کن
3. در `admin_user_ids` قرار بده

---

## 🎴 مرحله 4: اضافه کردن کارت‌ها

### روش 1: از طریق پنل مدیریت (توصیه می‌شه)

```bash
# اجرای پنل مدیریت
python web_api.py
```

بعد برو به `http://localhost:5000` و کارت‌ها رو اضافه کن.

### روش 2: از طریق کد Python

یه فایل `add_cards.py` بساز:

```python
from game_core import DatabaseManager, Card, CardRarity
import uuid

db = DatabaseManager()

# اضافه کردن کارت نمونه
card = Card(
    card_id=str(uuid.uuid4()),
    name="John Wick",
    rarity=CardRarity.LEGEND,
    power=95,
    speed=90,
    iq=85,
    popularity=98,
    abilities=["Headshot Master", "Gun Fu"],
    dialogs=["Yeah, I'm thinking I'm back!"],
    biography="The legendary assassin",
    image_path="card_images/john_wick.png"
)

db.add_card(card)
print(f"✅ کارت {card.name} اضافه شد!")
```

اجرا کن:
```bash
python add_cards.py
```

---

## 🖼️ مرحله 5: اضافه کردن تصاویر کارت‌ها

### ساخت پوشه تصاویر:
```bash
mkdir card_images
```

### اضافه کردن تصاویر:
1. تصاویر کارت‌ها رو با فرمت PNG یا JPG آماده کن
2. نام فایل‌ها باید با نام کارت مطابقت داشته باشه:
   - `john_wick.png`
   - `heisenberg.png`
   - `darth_vader.png`

3. فایل‌ها رو در پوشه `card_images/` قرار بده

---

## ▶️ مرحله 6: اجرای بات

### حالت Development (تست):
```bash
# فعال‌سازی محیط مجازی (اگه فعال نیست)
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# اجرای بات
python telegram_bot.py
```

اگه همه چی درست باشه، باید این پیام رو ببینی:
```
✅ ربات آماده شد با 1 ادمین
INFO - Application started
```

### تست بات:
1. بات رو در تلگرام پیدا کن
2. `/start` بزن
3. اگه منوی اصلی نمایش داده شد، همه چی درسته! 🎉

---

## 🚀 مرحله 7: استقرار در سرور (Production)

### 1️⃣ آپلود کد به سرور

```bash
# از طریق Git
ssh user@your-server-ip
git clone https://github.com/YOUR_USERNAME/telegram-card-game-bot.git
cd telegram-card-game-bot
```

### 2️⃣ نصب وابستگی‌ها در سرور

```bash
# نصب Python و pip
sudo apt update
sudo apt install python3 python3-pip python3-venv

# ساخت محیط مجازی
python3 -m venv .venv
source .venv/bin/activate

# نصب وابستگی‌ها
pip install -r requirements.txt
```

### 3️⃣ تنظیم فایل config

```bash
cp config.example.json game_config.json
nano game_config.json
# توکن و تنظیمات رو وارد کن
```

### 4️⃣ اجرا با systemd (توصیه می‌شه)

ساخت service file:
```bash
sudo nano /etc/systemd/system/telbattle.service
```

محتوای فایل:
```ini
[Unit]
Description=TelBattle Card Game Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/telegram-card-game-bot
Environment="PATH=/home/YOUR_USERNAME/telegram-card-game-bot/.venv/bin"
ExecStart=/home/YOUR_USERNAME/telegram-card-game-bot/.venv/bin/python telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

فعال‌سازی و اجرا:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telbattle
sudo systemctl start telbattle

# بررسی وضعیت
sudo systemctl status telbattle

# مشاهده لاگ‌ها
sudo journalctl -u telbattle -f
```

### 5️⃣ اجرا با screen (روش ساده‌تر)

```bash
# نصب screen
sudo apt install screen

# ساخت session جدید
screen -S telbattle

# اجرای بات
python telegram_bot.py

# جدا شدن از session: Ctrl+A سپس D

# برگشت به session
screen -r telbattle
```

---

## 🌐 مرحله 8: راه‌اندازی پنل مدیریت (اختیاری)

### اجرای پنل:
```bash
python web_api.py
```

پنل روی `http://localhost:5000` در دسترسه.

### دسترسی از بیرون (با nginx):

نصب nginx:
```bash
sudo apt install nginx
```

تنظیم nginx:
```bash
sudo nano /etc/nginx/sites-available/telbattle-admin
```

محتوا:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

فعال‌سازی:
```bash
sudo ln -s /etc/nginx/sites-available/telbattle-admin /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🔍 عیب‌یابی

### مشکل: بات پاسخ نمی‌دهد
```bash
# بررسی لاگ‌ها
tail -f bot.log

# بررسی اینکه بات در حال اجراست
ps aux | grep telegram_bot.py
```

### مشکل: خطای دیتابیس
```bash
# بررسی فایل دیتابیس
ls -lh game_bot.db

# اگه فایل نیست، بات رو یکبار اجرا کن تا بسازدش
python telegram_bot.py
```

### مشکل: تصاویر نمایش داده نمی‌شود
```bash
# بررسی وجود پوشه
ls -la card_images/

# بررسی مجوزها
chmod 755 card_images/
chmod 644 card_images/*.png
```

---

## 📊 مانیتورینگ

### مشاهده لاگ‌های زنده:
```bash
tail -f bot.log
```

### بررسی استفاده از منابع:
```bash
htop
# یا
top
```

### بررسی فضای دیسک:
```bash
df -h
du -sh game_bot.db
```

---

## 🔄 بروزرسانی

```bash
# دریافت آخرین تغییرات
git pull origin main

# نصب وابستگی‌های جدید (اگه هست)
pip install -r requirements.txt

# ریستارت بات
sudo systemctl restart telbattle
# یا اگه با screen اجرا کردی:
screen -r telbattle
# Ctrl+C برای توقف
# python telegram_bot.py برای اجرای دوباره
```

---

## 🆘 کمک بیشتر

اگه مشکلی داری:
- 📖 [مستندات کامل](../README.md)
- 💬 [Discussions در GitHub](https://github.com/YOUR_USERNAME/telegram-card-game-bot/discussions)
- 🐛 [گزارش باگ](https://github.com/YOUR_USERNAME/telegram-card-game-bot/issues)

---

**موفق باشی! 🎉**
