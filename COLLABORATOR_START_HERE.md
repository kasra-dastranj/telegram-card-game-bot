# شروع همکاری روی TelBattle — این فایل را اول به Codex بده

- مخزن اصلی: `https://github.com/kasra-dastranj/telegram-card-game-bot`
- شاخهٔ اصلی و نسخهٔ منتشرشده: `main`
- شاخهٔ شخصی همکار: `collab/<GitHub-username>`

## پیامی که به Codex بده

> این فایل را کامل بخوان و مراحلش را **روی سیستم من** اجرا کن. مخزن را با حساب GitHub خودم clone کن، محیط Python و Mini App را راه بینداز، Graphify را برای Codex نصب و گراف محلی پروژه را بساز، تست‌ها را اجرا کن و شاخهٔ شخصی من را روی GitHub ایجاد کن. بعد از هر کار کامل، تغییرات را فقط روی همان شاخه commit و push کن و آدرس commit را گزارش بده. اگر ورود تعاملی GitHub یا توکن ربات تست لازم شد، همان‌جا از من بخواه؛ از حساب، دیتابیس، کلید SSH یا توکن صاحب پروژه استفاده نکن. به `main`، VPS و دیتابیس زنده دست نزن و چیزی را بدون بازبینی صاحب پروژه merge یا deploy نکن. اگر مرحله‌ای شکست خورد علت را رفع و دوباره بررسی کن؛ کار را در حالت نیمه‌آماده رها نکن.

این راهنما برای کسی است که قبلاً به **همین مخزن** به‌عنوان Collaborator اضافه شده است. نیازی به Fork نیست. دعوت GitHub باید با حساب خود همکار پذیرفته شده باشد. راهنمای عمومی `CONTRIBUTING.md` برای مشارکت‌کنندهٔ بیرونی و Fork نوشته شده؛ در این همکاری، همین فایل مبنای شاخه‌هاست.

## ۱. دریافت مخزن و ایزوله‌کردن کار

در ترمینال VS Code/Visual Studio، Codex باید وجود Git و GitHub CLI را بررسی کند و با حساب خود همکار وارد GitHub شود. اگر `gh` نصب نیست، آن را نصب کند؛ اگر دعوت هنوز پذیرفته نشده، همکار باید آن را در GitHub بپذیرد. سپس:

```powershell
gh auth status
gh api user --jq .login
git clone https://github.com/kasra-dastranj/telegram-card-game-bot.git
cd telegram-card-game-bot
git remote -v
```

نام و ایمیل Git باید متعلق به خود همکار باشد. اگر تنظیم نیست، Codex با اطلاعات همان حساب تنظیم کند. در clone تمیز، اسکریپت یک‌باره را اجرا کند:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_collaborator.ps1
```

اسکریپت نام کاربری را از `gh` می‌گیرد. اگر GitHub CLI در دسترس نیست ولی Git احراز هویت شده، می‌توان نام کاربری را صریح داد:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_collaborator.ps1 -GitHubUser YOUR_GITHUB_USERNAME
```

اسکریپت از تازه‌ترین `origin/main` شاخهٔ `collab/<username>` را می‌سازد یا شاخهٔ موجود را باز می‌کند، آن را روی GitHub push می‌کند و hookهای **محلی همین clone** را فعال می‌کند. Hookها commit روی شاخهٔ دیگر و push به شاخهٔ دیگر یا force-push را رد می‌کنند. هر commit عادی روی شاخهٔ شخصی، پس از به‌روزرسانی Graphify، خودکار به GitHub push می‌شود. اگر شبکه قطع بود commit محلی حفظ می‌شود؛ Codex باید push را دوباره انجام دهد و نتیجه را تأیید کند. این تنظیم، clone صاحب پروژه را تغییر نمی‌دهد.

## ۲. محیط اجرای پروژه

نسخهٔ Python در `.python-version` برابر 3.11 است. Codex باید آن را نصب/پیدا کند و یک `.venv` محلی بسازد؛ `pytest` جدا از وابستگی‌های runtime نصب می‌شود:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
.\.venv\Scripts\python.exe -m pytest -q
```

برای Mini App، Node.js و npm سازگار با `frontend/game/package-lock.json` لازم است:

```powershell
cd frontend/game
npm ci
npm run build
cd ../..
```

Codex باید خطاهای نصب یا build را حل کند و نتیجهٔ واقعی تست و build را گزارش بدهد. در زمان نوشتن این راهنما، مجموعهٔ محلی ۲۴۷ تست موفق و یک تستِ نیازمند تلگرام زنده Skip داشت؛ با تغییر کد، این عدد ممکن است عوض شود. اجرای تست‌ها و build به توکن ربات یا دیتابیس تولیدی نیاز ندارد.

## ۳. نصب قطعی Graphify برای Codex

فایل‌های `.codex/skills/graphify` و `graphify-out/` محلی و در Git نادیده گرفته شده‌اند؛ بنابراین clone تازه خودبه‌خود ابزار یا گراف آماده ندارد. Codex باید `uv` را در صورت نیاز نصب کند و سپس در ریشهٔ پروژه این دستورها را اجرا کند:

```powershell
uv tool install graphifyy
graphify install --platform codex
graphify extract . --code-only
graphify query "Where is the card battle logic and how is it tested?" --budget 800
```

`graphify install --platform codex` مهارت را برای Codex همان سیستم نصب می‌کند و فایل tracked پروژه را تغییر نمی‌دهد. `--code-only` گراف اولیه را از AST کد می‌سازد و به Gemini/API key نیاز ندارد. اگر `graphify` پس از نصب هنوز در PATH ترمینال فعلی نیست، Codex باید مسیر ابزار را اصلاح یا ترمینال را دوباره باز کند. بعد از نصب skill، ممکن است لازم باشد جلسهٔ Codex دوباره باز شود تا skill جدید دیده شود. موفقیت نصب یعنی `graphify-out/graph.json` ساخته شده و `graphify query` پاسخ می‌دهد. برای هر سؤال دربارهٔ کد، اول `graphify query` و در صورت نیاز `path` یا `explain`؛ پس از تغییر کد `graphify update .` اجرا شود. دستور `graphify hook install` لازم نیست، چون hookهای همکاری همین کار را پس از commit انجام می‌دهند و نصب hook جدا ممکن است با آن‌ها تداخل پیدا کند.

## ۴. روال هر کار بعدی

قبل از شروع کار، Codex شاخه را با `git branch --show-current` بررسی کند؛ باید `collab/<username>` باشد. تغییرهای تازهٔ صاحب پروژه را **بدون بازنویسی تاریخچه** به شاخهٔ شخصی بیاورد:

```powershell
git fetch origin main
git merge origin/main
```

اگر merge تعارض داشت، Codex تعارض را حل و تست کند؛ `reset --hard` یا `push --force` نکند. پس از هر تغییر کامل، تست‌های مرتبط و در صورت تغییر Mini App، build را اجرا کند؛ سپس commit بسازد. Hook به‌طور معمول push می‌کند، اما Codex باید خروجی را بررسی کند و در صورت شکست، پس از رفع مشکل صریحاً `git push origin HEAD` بزند. پایان هر کار باید با `git status -sb` و مقایسهٔ commit محلی با `origin/collab/<username>` تأیید و SHA/لینک commit به صاحب پروژه اعلام شود.

برای تحویل به پروژهٔ اصلی، از شاخهٔ شخصی به `main` یک Pull Request با توضیح تغییر و تست‌ها بسازید. ادغام و انتشار روی VPS با بازبینی و هماهنگی صاحب پروژه انجام می‌شود. هیچ‌کس برای این همکاری مستقیماً روی `main` کار نکند.

## ۵. داده و دسترسی‌های جدا از Git

فایل‌های `.env`، `config.json`، دیتابیس `*.db`، تصاویر `assets/` و `card_images/` در Git نیستند. این عمدی است: clone برای کدنویسی، تست و build کافی است، اما برای اجرای یک ربات واقعی، حساب/توکن **ربات تست جداگانه** و برای دیدن تمام کارت‌ها یک بستهٔ محتوای مجاز یا دیتابیس آزمایشی بدون دادهٔ بازیکنان لازم است. Codex نباید اطلاعات تولیدی را از VPS بردارد یا در Git ثبت کند. اگر کار مشخص به این داده‌ها نیاز داشت، دقیقاً بگوید چه دادهٔ آزمایشی کم است تا صاحب پروژه آن را جداگانه فراهم کند. تصاویر باقی‌مانده هم طبق تصمیم صاحب پروژه بعداً اضافه می‌شوند.

در پایان راه‌اندازی، Codex باید این‌ها را گزارش کند: حساب GitHub فعال، نام شاخه و لینک آن، وضعیت hook و push آزمایشی شاخه، نسخه‌های Python/Node/Graphify، ساخته‌شدن گراف و پاسخ query، تعداد تست‌های پاس/Skip، نتیجهٔ build، و هر پیش‌نیاز محتوایی که هنوز برای اجرای زنده لازم است.
