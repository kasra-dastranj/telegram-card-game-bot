# 🚀 راهنمای سریع شروع کار

این راهنما برای آپلود سریع پروژه به GitHub نوشته شده.

---

## ✅ مرحله 1: بررسی نهایی

```bash
# بررسی اینکه game_config.json در .gitignore هست
cat .gitignore | grep game_config.json

# بررسی اینکه game_bot.db در .gitignore هست  
cat .gitignore | grep "*.db"
```

اگه این دو خط رو دیدی، عالیه! ✅

---

## 🔧 مرحله 2: Initialize Git

```bash
# Initialize git repository
git init

# تنظیم نام و ایمیل (اگه قبلاً نکردی)
git config --global user.name "Kasra Dastranj"
git config --global user.email "kasra.dastranj80@gmail.com"

# تنظیم branch اصلی به main
git branch -M main
```

---

## 📦 مرحله 3: اولین Commit

```bash
# بررسی فایل‌هایی که add می‌شن
git status

# مطمئن شو این فایل‌ها در لیست نیستن:
# - game_config.json
# - game_bot.db
# - bot.log
# - __pycache__/

# اگه همه چی درسته، add کن
git add .

# بررسی دوباره
git status

# Commit
git commit -m "Initial commit: Complete Telegram card game bot

- Full bot implementation with PvP system
- Card management with rarity system (Normal, Epic, Legend)
- Leaderboard (global and group)
- Web admin panel with Flask
- Individual card cooldown system
- Daily claim system with 24h cooldown
- Complete documentation and setup guides
- GitHub templates and security policy
- Persian language support"
```

---

## 🌐 مرحله 4: ساخت Repository در GitHub

### روش 1: از طریق وب (ساده‌تر)

1. برو به: https://github.com/new
2. Repository name: `telegram-card-game-bot`
3. Description: `🎮 Telegram Card Game Bot with PvP - بات تلگرام بازی کارت با قابلیت مبارزه`
4. انتخاب: **Public** (یا Private اگه می‌خوای خصوصی باشه)
5. **نزن** روی "Add a README file" (چون خودت داری)
6. **نزن** روی "Add .gitignore" (چون خودت داری)
7. License: **MIT License** انتخاب کن
8. کلیک روی **Create repository**

### روش 2: از طریق GitHub CLI (پیشرفته)

```bash
# نصب GitHub CLI (اگه نداری)
# Windows: winget install GitHub.cli
# Mac: brew install gh
# Linux: sudo apt install gh

# لاگین
gh auth login

# ساخت repository
gh repo create kasra-dastranj/telegram-card-game-bot --public --source=. --remote=origin --description "🎮 Telegram Card Game Bot with PvP"
```

---

## 🚀 مرحله 5: Push به GitHub

```bash
# اضافه کردن remote (اگه از روش 1 استفاده کردی)
git remote add origin https://github.com/kasra-dastranj/telegram-card-game-bot.git

# بررسی remote
git remote -v

# Push به GitHub
git push -u origin main
```

اگه خطای authentication گرفتی:
```bash
# استفاده از Personal Access Token
# برو به: https://github.com/settings/tokens
# Generate new token (classic)
# انتخاب scope: repo
# کپی کردن token
# وقتی git push می‌زنی، به جای password، token رو وارد کن
```

---

## 🌿 مرحله 6: ساخت Branch Dev

```bash
# ساخت branch dev
git checkout -b dev

# Push کردن dev
git push -u origin dev

# برگشت به main
git checkout main
```

---

## ⚙️ مرحله 7: تنظیمات GitHub

### 1️⃣ About Section
1. برو به صفحه repository
2. کلیک روی ⚙️ (Settings) کنار About
3. پر کن:
   - **Description**: `🎮 Telegram Card Game Bot with PvP - بات تلگرام بازی کارت`
   - **Topics**: `telegram-bot`, `python`, `game`, `pvp`, `card-game`, `persian`, `sqlite`, `flask`
4. Save changes

### 2️⃣ فعال کردن Features
1. برو به Settings > General
2. Features:
   - ✅ Issues
   - ✅ Discussions (برای سوالات کاربران)
   - ❌ Wiki (نیاز نیست)
   - ❌ Projects (فعلاً نیاز نیست)

### 3️⃣ تنظیم Default Branch
1. Settings > Branches
2. Default branch: تغییر بده به `dev`
3. این باعث میشه همه PR ها به dev برن نه main

### 4️⃣ Branch Protection (اختیاری ولی توصیه می‌شه)
1. Settings > Branches > Add rule
2. Branch name pattern: `main`
3. تنظیمات:
   - ✅ Require a pull request before merging
   - ✅ Require approvals (1)
4. Save changes

---

## 🏷️ مرحله 8: ساخت اولین Release

```bash
# تگ کردن نسخه اول
git tag -a v1.0.0 -m "Release v1.0.0 - Initial public release"

# Push کردن tag
git push origin v1.0.0
```

یا از GitHub:
1. برو به repository
2. کلیک روی "Releases" (سمت راست)
3. "Create a new release"
4. Choose a tag: `v1.0.0` (تایپ کن و "Create new tag" بزن)
5. Release title: `🎉 v1.0.0 - Initial Release`
6. توضیحات:
```markdown
## 🎮 اولین نسخه عمومی TelBattle

### ✨ ویژگی‌های اصلی
- 🎴 سیستم کارت‌های جمع‌آوری (Normal, Epic, Legend)
- ⚔️ مبارزه PvP در گروه‌ها
- 🏆 لیدربورد جهانی و گروهی
- 🌐 پنل مدیریت وب
- ❄️ سیستم کولدان کارت‌ها
- 🎁 کلیم روزانه
- 💖 سیستم جان (10 جان روزانه)

### 📦 نصب
مستندات کامل در [docs/SETUP.md](docs/SETUP.md)

### 🙏 تشکر
از همه کسانی که در توسعه کمک کردن!
```
7. Publish release

---

## ✅ Checklist نهایی

- [ ] Git initialize شد
- [ ] اولین commit انجام شد
- [ ] Repository در GitHub ساخته شد
- [ ] Push به GitHub انجام شد
- [ ] Branch dev ساخته شد
- [ ] About section پر شد
- [ ] Topics اضافه شدن
- [ ] Issues و Discussions فعال شدن
- [ ] Default branch به dev تغییر کرد
- [ ] اولین release ساخته شد

---

## 🎉 تبریک!

پروژه‌ت روی GitHub هست! حالا می‌تونی:

### لینک repository:
```
https://github.com/kasra-dastranj/telegram-card-game-bot
```

### کارهای بعدی:
1. **README رو بخون** و مطمئن شو همه چی درسته
2. **دوستات رو دعوت کن** که مشارکت کنن
3. **Star بزن** به repository خودت! 😄
4. **Share کن** در شبکه‌های اجتماعی

---

## 🔄 Workflow روزانه

### برای خودت (Owner):
```bash
# دریافت آخرین تغییرات
git checkout dev
git pull origin dev

# ساخت branch جدید برای فیچر
git checkout -b feature/new-feature

# کار کردن...
git add .
git commit -m "feat: add new feature"

# Push
git push origin feature/new-feature

# بعد در GitHub یه PR به dev بساز
```

### برای همکاران:
1. Fork کنن
2. Clone کنن
3. Branch جدید بسازن
4. تغییرات رو commit کنن
5. Push به fork خودشون
6. PR به repository اصلی بسازن

---

## 🆘 مشکلات رایج

### مشکل 1: git command not found
```bash
# نصب Git
# Windows: https://git-scm.com/download/win
# Mac: brew install git
# Linux: sudo apt install git
```

### مشکل 2: Permission denied (publickey)
```bash
# استفاده از HTTPS به جای SSH
git remote set-url origin https://github.com/kasra-dastranj/telegram-card-game-bot.git
```

### مشکل 3: game_config.json اشتباهی commit شد
```bash
# حذف از staging
git reset HEAD game_config.json

# اگه commit شده:
git rm --cached game_config.json
git commit -m "Remove sensitive config file"
```

---

## 📞 کمک بیشتر

- 📖 [راهنمای کامل GitHub](GITHUB_SETUP.md)
- 📧 Email: kasra.dastranj80@gmail.com
- 💬 [GitHub Discussions](https://github.com/kasra-dastranj/telegram-card-game-bot/discussions)

---

**موفق باشی! 🚀**
