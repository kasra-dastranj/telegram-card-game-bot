# 🤝 راهنمای مشارکت در پروژه

> **همکار مستقیمِ دعوت‌شده به همین مخزن:** ابتدا [COLLABORATOR_START_HERE.md](COLLABORATOR_START_HERE.md) را بخوان. راهنمای Fork و شاخهٔ `dev` در ادامه برای مشارکت‌کننده‌های بیرونی است؛ همکار مستقیم از `main` شاخهٔ شخصی `collab/<username>` می‌سازد و Pull Request را به `main` می‌فرستد.

ممنون که می‌خوای در پروژه TelBattle مشارکت کنی! این راهنما به تو کمک می‌کنه تا به بهترین شکل مشارکت کنی.

## 🔄 فرآیند مشارکت

### 1️⃣ Fork و Clone
```bash
# Fork کردن پروژه از GitHub
# سپس clone کردن fork خودت
git clone https://github.com/YOUR_USERNAME/telegram-card-game-bot.git
cd telegram-card-game-bot

# اضافه کردن upstream
git remote add upstream https://github.com/kasra-dastranj/telegram-card-game-bot.git
```

### 2️⃣ ساخت Branch جدید
```bash
# همیشه از branch dev شروع کن
git checkout dev
git pull origin dev

# ساخت branch جدید برای فیچر یا باگ‌فیکس
git checkout -b feature/your-feature-name
# یا
git checkout -b bugfix/bug-description
```

### 3️⃣ انجام تغییرات
- کد خودت رو بنویس
- از استاندارد PEP 8 پیروی کن
- کامنت‌های فارسی برای توضیح منطق بنویس
- نام متغیرها و توابع به انگلیسی باشه

### 4️⃣ Test کردن
```bash
# مطمئن شو که بات کار می‌کنه
python telegram_bot.py

# اگه تست نوشتی، اجراشون کن
pytest tests/
```

### 5️⃣ Commit کردن
```bash
git add .
git commit -m "feat: add new card rarity system"
```

### 6️⃣ Push و Pull Request
```bash
git push origin feature/your-feature-name
```
بعد برو GitHub و یه Pull Request به branch `dev` بساز.

---

## 📋 استاندارد Branch

```
main (production)
  ├── dev (development)
  │   ├── feature/new-cards
  │   ├── feature/leaderboard-improvements
  │   ├── bugfix/claim-cooldown
  │   └── bugfix/pvp-timeout
  └── hotfix/critical-security-fix
```

### نام‌گذاری Branch:
- `feature/` - فیچر جدید
- `bugfix/` - رفع باگ
- `hotfix/` - رفع مشکل فوری در production
- `docs/` - بروزرسانی مستندات
- `refactor/` - بازنویسی کد بدون تغییر عملکرد

---

## ✍️ استاندارد Commit Message

از Conventional Commits استفاده کن:

```
<type>: <description>

[optional body]
[optional footer]
```

### انواع Type:
- `feat:` - فیچر جدید
- `fix:` - رفع باگ
- `docs:` - تغییر در مستندات
- `style:` - تغییرات فرمت کد (فاصله، نقطه‌ویرگول و...)
- `refactor:` - بازنویسی کد
- `test:` - اضافه کردن تست
- `chore:` - تغییرات کوچک (dependency update و...)
- `perf:` - بهبود performance

### مثال‌ها:
```bash
git commit -m "feat: add legendary card cooldown system"
git commit -m "fix: resolve claim cooldown not resetting"
git commit -m "docs: update README with new features"
git commit -m "refactor: optimize database queries for leaderboard"
```

---

## 🧪 قبل از Pull Request

### ✅ Checklist:
- [ ] کد رو test کردم و کار می‌کنه
- [ ] از PEP 8 پیروی کردم
- [ ] کامنت‌های مناسب نوشتم
- [ ] مستندات رو بروزرسانی کردم (اگه لازم بود)
- [ ] هیچ اطلاعات حساسی (توکن، پسورد) commit نکردم
- [ ] تغییراتم با branch `dev` conflict نداره

### 🔍 خودت رو بررسی کن:
```bash
# بررسی syntax errors
python -m py_compile telegram_bot.py game_core.py

# بررسی PEP 8
flake8 telegram_bot.py game_core.py --max-line-length=120

# اجرای تست‌ها
pytest tests/ -v
```

---

## 📝 استاندارد کدنویسی

### Python Style:
```python
# ✅ خوب
def calculate_fight_score(card_rarity: CardRarity, opponent_rarity: CardRarity) -> int:
    """محاسبه امتیاز بر اساس کمیابی کارت‌ها"""
    if card_rarity == CardRarity.LEGEND:
        return 50
    return 10

# ❌ بد
def calc(c,o):
    if c=="legend":
        return 50
    return 10
```

### کامنت‌گذاری:
```python
# ✅ کامنت فارسی برای توضیح منطق
def check_cooldown(user_id: int, card_id: str) -> bool:
    """بررسی اینکه آیا کارت در cooldown هست یا نه"""
    # دریافت آخرین زمان استفاده از کارت
    last_use = self.db.get_last_card_use(user_id, card_id)
    
    # اگه 24 ساعت گذشته باشه، cooldown تموم شده
    if datetime.now() - last_use > timedelta(hours=24):
        return False
    
    return True
```

### نام‌گذاری:
```python
# ✅ خوب - واضح و معنادار
player_total_score = calculate_total_score(player_id)
is_card_available = check_card_cooldown(card_id)

# ❌ بد - مبهم
pts = calc(p)
avail = chk(c)
```

---

## 🐛 گزارش باگ

اگه باگی پیدا کردی:

1. **بررسی کن** که قبلاً گزارش نشده باشه
2. **Issue جدید** بساز با این اطلاعات:
   - توضیح واضح از باگ
   - مراحل بازتولید باگ
   - رفتار مورد انتظار
   - رفتار واقعی
   - اسکرین‌شات (اگه ممکنه)
   - نسخه Python و کتابخانه‌ها

### مثال Issue:
```markdown
**توضیح باگ:**
وقتی کاربر /claim می‌زنه، cooldown درست چک نمی‌شه

**مراحل بازتولید:**
1. /claim بزن
2. بلافاصله دوباره /claim بزن
3. کارت دوباره میده

**رفتار مورد انتظار:**
باید پیام "باید 24 ساعت صبر کنی" نشون بده

**رفتار واقعی:**
کارت جدید میده

**محیط:**
- Python 3.11
- python-telegram-bot 20.7
```

---

## 💡 پیشنهاد فیچر جدید

برای پیشنهاد فیچر:

1. **Issue بساز** با برچسب `enhancement`
2. **توضیح بده**:
   - چرا این فیچر مفیده؟
   - چطور باید کار کنه؟
   - آیا با فیچرهای فعلی conflict داره؟

---

## 🔐 امنیت

اگه مشکل امنیتی پیدا کردی:

- ⚠️ **هیچ‌وقت** به صورت عمومی گزارش نده
- 📧 مستقیماً به maintainer ایمیل بزن
- 🔒 جزئیات رو خصوصی نگه دار تا fix بشه

---

## 📞 سوال داری؟

- 💬 تو Discussions بپرس
- 📱 تو گروه تلگرام بپرس
- 📧 به maintainer ایمیل بزن

---

## 🎉 تشکر!

هر مشارکتی، کوچیک یا بزرگ، ارزشمنده! ممنون که به بهتر شدن TelBattle کمک می‌کنی! ❤️

---

**ساخته شده با ❤️ برای جامعه تلگرام ایران**
