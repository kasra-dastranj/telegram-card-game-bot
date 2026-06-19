# 🔒 راهنمای امنیتی پروژه

## تغییرات انجام شده

پروژه از سیستم `config.json` به `.env` مهاجرت کرده است برای امنیت بهتر.

## فایل‌های جدید

### 1. `.env` - تنظیمات محرمانه
حاوی توکن ربات و اطلاعات حساس. **هرگز commit نشود!**

### 2. `.env.example` - الگوی تنظیمات
نمونه‌ای برای کاربران جدید که می‌توانند کپی کنند.

### 3. `config_loader.py` - بارگذار تنظیمات
کلاس Python برای خواندن از `.env` با اعتبارسنجی.

### 4. `.gitignore` - فایل‌های نادیده گرفته شده
مطمئن می‌شود `.env` و فایل‌های حساس commit نشوند.

### 5. `migrate_to_env.py` - اسکریپت مهاجرت
برای انتقال خودکار از `config.json` به `.env`.

## نحوه استفاده برای توسعه‌دهندگان جدید

```bash
# 1. کپی کردن الگو
cp .env.example .env

# 2. ویرایش .env و اضافه کردن توکن
nano .env  # یا هر ادیتور دیگری

# 3. نصب وابستگی‌ها
pip install -r requirements.txt

# 4. اجرای ربات
python telegram_bot.py
```

## چک‌لیست امنیتی

- [x] توکن از config.json به .env منتقل شد
- [x] .gitignore به‌روز شد
- [x] فایل‌های قدیمی بکاپ شدند
- [x] سیستم بارگذاری جدید تست شد
- [ ] توکن‌های قدیمی در git history پاک شوند (اختیاری)

## پاک کردن توکن از Git History (پیشرفته)

اگر توکن قبلاً commit شده:

```bash
# استفاده از git-filter-repo (توصیه می‌شود)
pip install git-filter-repo
git filter-repo --path config.json --invert-paths
git filter-repo --path game_config.json --invert-paths

# یا استفاده از BFG Repo-Cleaner
java -jar bfg.jar --delete-files config.json
java -jar bfg.jar --delete-files game_config.json
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

⚠️ **هشدار:** این عملیات history را بازنویسی می‌کند. قبل از انجام بکاپ بگیرید!

## سوالات متداول

### چرا .env بهتر از config.json است؟
- فایل‌های .env استاندارد صنعت هستند
- به راحتی از git مخفی می‌مانند
- در deployment آسان‌تر مدیریت می‌شوند
- با ابزارهای CI/CD سازگارترند

### آیا می‌توانم از config.json استفاده کنم؟
بله، برای سازگاری با نسخه قبلی:
```python
bot = TelegramCardBot(use_env=False)
```
اما توصیه نمی‌شود.

### توکن من در git قرار گرفته، چه کنم؟
1. فوراً توکن را از @BotFather revoke کنید
2. توکن جدید بگیرید
3. git history را پاک کنید (بالا)
4. از .env استفاده کنید

## منابع بیشتر

- [12-Factor App Config](https://12factor.net/config)
- [OWASP Secrets Management](https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_password)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security/getting-started/best-practices-for-preventing-data-leaks-in-your-organization)
