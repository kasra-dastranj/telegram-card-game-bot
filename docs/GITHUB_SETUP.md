# 🚀 راهنمای آماده‌سازی برای GitHub

این راهنما قدم به قدم نحوه آماده‌سازی و آپلود پروژه به GitHub رو توضیح میده.

---

## ✅ مرحله 1: بررسی فایل‌های حساس

قبل از آپلود، مطمئن شو این فایل‌ها در `.gitignore` هستن:

```bash
# بررسی .gitignore
cat .gitignore
```

باید این‌ها رو ببینی:
- ✅ `game_config.json`
- ✅ `game_bot.db`
- ✅ `*.log`
- ✅ `.venv/`
- ✅ `__pycache__/`

---

## 🔐 مرحله 2: پاک کردن اطلاعات حساس

### حذف توکن از تاریخچه Git (اگه قبلاً commit کردی):

```bash
# نصب BFG Repo-Cleaner
# Windows: دانلود از https://rtyley.github.io/bfg-repo-cleaner/
# Linux/Mac:
brew install bfg  # Mac
sudo apt install bfg  # Ubuntu

# پاک کردن فایل از تاریخچه
bfg --delete-files game_config.json
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

یا استفاده از git-filter-repo:
```bash
pip install git-filter-repo
git filter-repo --path game_config.json --invert-paths
```

---

## 📝 مرحله 3: بررسی فایل‌های ضروری

مطمئن شو این فایل‌ها وجود دارن:

```bash
ls -la
```

باید ببینی:
- ✅ `.gitignore`
- ✅ `README.md`
- ✅ `LICENSE`
- ✅ `CONTRIBUTING.md`
- ✅ `requirements.txt`
- ✅ `config.example.json`
- ✅ `.env.example`
- ✅ `docs/SETUP.md`

---

## 🎯 مرحله 4: ساخت Repository در GitHub

### روش 1: از طریق وب

1. برو به [github.com](https://github.com)
2. کلیک روی `+` > `New repository`
3. نام repository: `telegram-card-game-bot`
4. توضیحات: `🎮 Telegram Card Game Bot with PvP - بات تلگرام بازی کارت با قابلیت PvP`
5. انتخاب: **Public** یا **Private**
6. **نزن** روی "Initialize with README" (چون خودت داری)
7. کلیک روی `Create repository`

### روش 2: از طریق GitHub CLI

```bash
# نصب GitHub CLI
# Windows: winget install GitHub.cli
# Mac: brew install gh
# Linux: sudo apt install gh

# لاگین
gh auth login

# ساخت repo
gh repo create kasra-dastranj/telegram-card-game-bot --public --source=. --remote=origin
```

---

## 🔧 مرحله 5: Initialize Git (اگه قبلاً نکردی)

```bash
# Initialize git
git init

# تنظیم branch اصلی به main
git branch -M main

# اضافه کردن remote
git remote add origin https://github.com/kasra-dastranj/telegram-card-game-bot.git
```

---

## 📦 مرحله 6: اولین Commit

```bash
# بررسی فایل‌هایی که add می‌شن
git status

# اضافه کردن همه فایل‌ها (به جز موارد .gitignore)
git add .

# بررسی دوباره
git status

# مطمئن شو game_config.json و game_bot.db در لیست نیستن!

# Commit
git commit -m "Initial commit: Telegram card game bot with PvP features

- Complete bot implementation with PvP system
- Card management with rarity system
- Leaderboard (global and group)
- Web admin panel
- Cooldown system for cards
- Daily claim system
- Full documentation"

# Push به GitHub
git push -u origin main
```

---

## 🌿 مرحله 7: ساخت Branch Structure

```bash
# ساخت branch dev
git checkout -b dev
git push -u origin dev

# برگشت به main
git checkout main

# تنظیم dev به عنوان default branch در GitHub:
# Settings > Branches > Default branch > dev
```

---

## 📋 مرحله 8: تنظیمات Repository در GitHub

### 1️⃣ About Section
- Description: `🎮 Telegram Card Game Bot with PvP - بات تلگرام بازی کارت`
- Website: لینک دمو (اگه داری)
- Topics: `telegram-bot`, `python`, `game`, `pvp`, `card-game`, `persian`

### 2️⃣ Settings
- ✅ Issues فعال باشه
- ✅ Discussions فعال کن (برای سوالات)
- ✅ Wiki غیرفعال کن (اگه نمی‌خوای)

### 3️⃣ Branch Protection (اختیاری)
Settings > Branches > Add rule:
- Branch name: `main`
- ✅ Require pull request reviews before merging
- ✅ Require status checks to pass

---

## 🏷️ مرحله 9: ساخت Release اول

```bash
# تگ کردن نسخه اول
git tag -a v1.0.0 -m "Release v1.0.0 - Initial public release"
git push origin v1.0.0
```

یا از GitHub:
1. برو به Releases
2. کلیک روی "Create a new release"
3. Tag: `v1.0.0`
4. Title: `🎉 v1.0.0 - Initial Release`
5. توضیحات:
```markdown
## 🎮 اولین نسخه عمومی TelBattle

### ✨ ویژگی‌ها
- سیستم کارت‌های جمع‌آوری (Normal, Epic, Legend)
- مبارزه PvP در گروه‌ها
- لیدربورد جهانی و گروهی
- پنل مدیریت وب
- سیستم کولدان کارت‌ها
- کلیم روزانه

### 📦 نصب
مستندات کامل در [SETUP.md](docs/SETUP.md)

### 🐛 مشکلات شناخته شده
- هیچ

### 🙏 تشکر
از همه کسانی که در توسعه این پروژه کمک کردن!
```

---

## 📄 مرحله 10: ساخت README Badge ها

به `README.md` اضافه کن:

```markdown
![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Stars](https://img.shields.io/github/stars/YOUR_USERNAME/telegram-card-game-bot)
![Issues](https://img.shields.io/github/issues/YOUR_USERNAME/telegram-card-game-bot)
```

---

## 🔄 مرحله 11: Workflow برای تیمی کار کردن

### برای تو (Owner):
```bash
# دریافت تغییرات
git checkout dev
git pull origin dev

# بررسی Pull Requests در GitHub
# Merge کردن بعد از review
```

### برای همکاران:
```bash
# Fork کردن پروژه
# Clone کردن fork
git clone https://github.com/THEIR_USERNAME/telegram-card-game-bot.git

# اضافه کردن upstream
git remote add upstream https://github.com/kasra-dastranj/telegram-card-game-bot.git

# ساخت branch جدید
git checkout -b feature/new-feature

# کار کردن و commit
git add .
git commit -m "feat: add new feature"

# Push به fork خودشون
git push origin feature/new-feature

# ساخت Pull Request در GitHub
```

---

## 🛡️ مرحله 12: امنیت

### GitHub Secrets (برای CI/CD):
Settings > Secrets and variables > Actions > New repository secret

اضافه کن:
- `BOT_TOKEN` - توکن بات (برای تست خودکار)
- `ADMIN_ID` - ID ادمین

### Security Policy:
ساخت `SECURITY.md`:
```markdown
# Security Policy

## Reporting a Vulnerability

اگه مشکل امنیتی پیدا کردی، لطفاً:
- به صورت عمومی گزارش نده
- ایمیل بزن به: your-email@example.com
- جزئیات کامل بده

ما ظرف 48 ساعت پاسخ می‌دیم.
```

---

## ✅ Checklist نهایی

قبل از اعلام عمومی پروژه:

- [ ] همه فایل‌های حساس در `.gitignore` هستن
- [ ] `README.md` کامل و واضح هست
- [ ] `CONTRIBUTING.md` موجود هست
- [ ] `LICENSE` اضافه شده
- [ ] `docs/SETUP.md` کامل هست
- [ ] `config.example.json` بدون اطلاعات حساس هست
- [ ] تست کردم که بات با config.example کار می‌کنه
- [ ] Issues و Discussions فعال هستن
- [ ] Release اول ساخته شده
- [ ] README badges اضافه شدن

---

## 🎉 تبریک!

پروژه‌ت آماده‌ست! حالا می‌تونی:
- لینک رو با دوستات share کنی
- در گروه‌های تلگرام معرفی کنی
- در Reddit یا سایت‌های دیگه پست کنی

---

## 📞 کمک بیشتر

اگه سوالی داری:
- [GitHub Docs](https://docs.github.com)
- [Git Handbook](https://guides.github.com/introduction/git-handbook/)

**موفق باشی! 🚀**
