# فهرست دائمی Traitهای کارت

نام تریت‌ها در `card_trait_registry` داخل همان دیتابیس برنامه نگه‌داری می‌شود و به تعداد کارت‌های دارای آن تریت وابسته نیست.

- «افزودن Trait» نام را همان لحظه ذخیره و در فرم انتخاب می‌کند؛ ذخیرهٔ کارت برای ثبت خود نام لازم نیست.
- برای دادن تریت به کارت، کارت را ذخیره کنید. برداشتن انتخاب فقط تریت آن کارت را تغییر می‌دهد.
- با برداشتن تریت از آخرین کارت، حذف کارت، refresh یا راه‌اندازی دوبارهٔ پنل، نام در منوی کشویی می‌ماند و برای کارت‌های دیگر قابل انتخاب است.
- افزودن دوبارهٔ نام با فاصلهٔ ابتدا/انتها یا تفاوت بزرگی حروف لاتین، گزینهٔ تکراری نمی‌سازد. نام تازه حداکثر ۱۰۰ کاراکتر است.
- تریت‌های قدیمیِ هنوز موجود در دیتابیس به فهرست منتقل می‌شوند. نامی که پیش از این اصلاح از همهٔ کارت‌ها حذف شده و دیگر جایی ذخیره نیست، قابل بازیابی خودکار نیست؛ یک بار دوباره اضافه‌اش کنید.

## آماده‌سازی دیتابیس؛ فقط صاحب پروژه، پیش از انتشار این اصلاح

این تغییر یک جدول افزایشی و backfill لازم دارد؛ schema یا دادهٔ کارت‌ها و بازیکنان تغییر نمی‌کند. محافظت `no-change` انتشار Actions حفظ شده است و تا آماده‌شدن این جدول روی سرور، preflight انتشار را متوقف می‌کند. bootstrap انتشار به‌تنهایی این migration را اجرا نمی‌کند.

صاحب پروژه اسکریپت و CI را بازبینی کند و از ریشهٔ clone نسخهٔ دقیق بازبینی‌شده اجرا کند. همکار به دیتابیس یا SSH سرور دسترسی نمی‌گیرد. هر دو فایل preview و backup فقط روی VPS و در backups با مجوز محدود باقی می‌مانند؛ در Git/چت/GitHub بارگذاری نشوند.

```bash
sudo flock -x /opt/telbattle/deploy.lock bash -s -- "$PWD" <<'TRAIT_MIGRATION'
set -euo pipefail
umask 077
cd "$1"
stamp="$(date -u +%Y%m%dT%H%M%S)-$$"
python3 migrations/migrate_card_trait_registry.py \
  --database /opt/telbattle/shared/game_bot.db \
  --preview-copy "/opt/telbattle/backups/traits-preview-$stamp.db"
# ابتدا روی کپی اجرا شد؛ پس از بازبینی، در همین قفل بکاپ تازه و migration اصلی انجام می‌شود.
trap 'systemctl start telbattle-bot telbattle-api telbattle-admin' EXIT
systemctl stop telbattle-bot telbattle-api telbattle-admin
python3 migrations/migrate_card_trait_registry.py \
  --database /opt/telbattle/shared/game_bot.db \
  --apply --backup "/opt/telbattle/backups/before-traits-$stamp.db"
systemctl start telbattle-bot telbattle-api telbattle-admin
trap - EXIT
systemctl is-active telbattle-bot telbattle-api telbattle-admin
TRAIT_MIGRATION
```

این مرحله جدول و نام‌ها را آماده می‌کند و کد جاری را عوض نمی‌کند. اسکریپت از SQLite backup API و quick_check استفاده می‌کند، فایل موجود را بازنویسی نمی‌کند و idempotent است. در صورت شکست، داده خودکار restore نمی‌شود؛ مالک خطا و بکاپ را بررسی کند. آزمون‌های CI ثابت می‌کنند کارت‌ها و metadata پس از migration بدون تغییر باقی می‌مانند و برنامه پس از آماده‌سازی کپی، preflight بدون تغییر دیتابیس را می‌گذراند.

پس از این آماده‌سازی و [فعال‌سازی مسیر Actions](DEPLOY_FROM_GITHUB_FA.md)، اصلاح را با همان فرایند بازبینی PR، ادغام در main و Deploy دستی منتشر کنید. آزمون پذیرش پنل را روی دیتابیس آزمایشی انجام دهید؛ حذف یا ویرایش کارت زنده برای smoke test لازم نیست.

## شواهد آزمون

اجرای محلی کامل روی Windows: **۲۷۴ تست موفق، ۳ skipped** (Telegram زنده، flock لینوکس و symlink ویندوز). نتیجهٔ نهایی Linux و Python 3.9.25 در CI و توضیح PR ثبت می‌شود. آزمون‌ها شامل ثبت بدون ذخیرهٔ کارت، حذف تریت از آخرین کارت در هر سه مسیر family/card/variant، حذف کارت و راه‌اندازی مجدد، استفاده برای کارت دوم، نام تکراری و نام نامعتبر، backfill دیتابیس قدیمی و جلوگیری از migration تأییدنشده در deploy هستند. هیچ دیتابیس یا کارت تولیدی برای این آزمون‌ها استفاده نشده است.
