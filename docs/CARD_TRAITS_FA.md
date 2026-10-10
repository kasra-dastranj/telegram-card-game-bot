# Traitهای مستقل فرم‌ها و فهرست دائمی

## اصلاح اتصال تریت‌های Normal، Epic و Legend

تریت‌های هر فرم مستقل‌اند: مثلاً Subzero در Normal فقط «یخ»، در Epic «یخ، نینجا» و در Legend «یخ، نینجا، رهبر» می‌تواند داشته باشد. در تب اطلاعات پایه فرم را انتخاب کنید؛ در تب مودهای جدید عنوان Trait همان فرم را نشان می‌دهد. انتخاب و برداشتن تریت فقط به آن فرم تعلق دارد. تغییر فرم قبل از ذخیره، انتخاب‌های هر سه فرم را حفظ می‌کند؛ «ذخیره کارت» هر سه فرم را در یک تراکنش ثبت می‌کند. پس از refresh هم انتخاب‌ها جدا می‌مانند.

Quick برای شرط Passive حریف، Easy برای سؤال و گزینه‌ها، اولویت Trait زمین در نبرد دک و هم‌افزایی دک، تریت **فرم فعال بازیکن** را می‌خوانند. رسید مأموریت‌ها هم تریت همان فرم را هنگام تسویه ثبت می‌کند؛ تغییر بعدی کارت یا تکرار تسویه، پیشرفت ثبت‌شده را عوض نمی‌کند و پاداش دوباره نمی‌دهد. مقدار XP/Score/Coin یا قوانین اقتصاد تغییر نکرده‌اند. Series، متن و Hidden Stats همچنان اطلاعات شخصیت هستند. کارت‌های سفارشی metadata ثبت‌شدهٔ خودشان را استفاده می‌کنند.

در `card_variants.traits` یک ستون nullable اضافه شده است. مقدار `NULL` فقط برای سازگاری با اطلاعات قدیمی به `card_mode_metadata.traits` رجوع می‌کند؛ `[]` یعنی فرم عمداً بدون تریت است. مهاجرت هیچ کارت، آمار، موجودی، Level یا اقتصاد را تغییر نمی‌دهد. مقدارهای قبلی برای هر سه فرم محفوظ‌اند؛ انتخاب‌هایی که قبلاً بر اثر این باگ بازنویسی شده‌اند قابل حدس یا بازیابی خودکار نیستند و پس از انتشار باید یک بار فرم‌ها را مطابق نظر خود تنظیم کنید.

### آماده‌سازی همین اصلاح روی سرور

زیرساخت انتشار و مهاجرت قبلی فهرست دائمی آماده‌اند؛ bootstrap را تکرار نکنید. این اصلاح فقط ستون تازهٔ بالا را می‌خواهد. مالک ابتدا PR و CI را بازبینی و ادغام کند، clone خودش را روی **SHA دقیق بازبینی‌شدهٔ main** قرار دهد و از ریشهٔ همان clone دستور زیر را اجرا کند. همکار به سرور یا دیتابیس وارد نمی‌شود. preflight همچنان تغییر خودکار دیتابیس را رد می‌کند؛ پس از این آماده‌سازی Deploy از Actions و تأیید Environment انجام می‌شود.

```bash
sudo flock -x /opt/telbattle/deploy.lock bash -s -- "$PWD" <<'FORM_TRAITS'
set -euo pipefail
umask 077
cd "$1"
stamp="$(date -u +%Y%m%dT%H%M%S)-$$"
/opt/telbattle/venv/bin/python migrations/migrate_card_variant_traits.py \
  --database /opt/telbattle/shared/game_bot.db \
  --preview-copy "/opt/telbattle/backups/form-traits-preview-$stamp.db"
# همان migration ابتدا روی کپی آزمایش می‌شود؛ اصل داده هنوز دست‌نخورده است.
trap 'systemctl start telbattle-bot telbattle-api telbattle-admin' EXIT
systemctl stop telbattle-bot telbattle-api telbattle-admin
/opt/telbattle/venv/bin/python migrations/migrate_card_variant_traits.py \
  --database /opt/telbattle/shared/game_bot.db \
  --apply --backup "/opt/telbattle/backups/before-form-traits-$stamp.db"
systemctl start telbattle-bot telbattle-api telbattle-admin
trap - EXIT
systemctl is-active telbattle-bot telbattle-api telbattle-admin
FORM_TRAITS
```

این ابزار از SQLite backup API، quick_check و تراکنش استفاده می‌کند؛ بکاپ موجود را بازنویسی نمی‌کند و اجرای مجدد overrideهای ثبت‌شده را پاک نمی‌کند. backup/preview روی VPS باقی می‌مانند و به GitHub یا چت فرستاده نمی‌شوند. rollback کد ستون را حذف یا دیتابیس را restore نمی‌کند؛ تا بازگشت به کد جدید، با پنل قدیمی تریت فرم‌ها را ویرایش نکنید.

قرارداد API: `variants.normal.traits`، `variants.epic.traits` و `variants.legend.traits` آرایه‌های مستقل هستند. `traits` بالای پاسخ card برای فرم پایه است. کلاینت قدیمی family هنوز می‌تواند traits را در سطح مشترک بفرستد؛ آن درخواست صریحاً همان مقدار را برای هر سه فرم قرار می‌دهد، مگر اینکه فرم override خودش را بفرستد. حذف فیلد traits از درخواست family مقدار قبلی همان فرم را حفظ می‌کند. مسیر ویرایش variant و مسیر قدیمی ویرایش card فقط تریت فرم هدف را تغییر می‌دهند.

آزمون مرورگر محلی با Flask واقعی و SQLite تازه (هیچ API ذخیرهٔ کارت mock نشده است):

```powershell
# Playwright ابزار محلی است؛ dependency تولیدی یا تغییر lockfile نیست.
cd frontend/game
npm install --no-save --package-lock=false playwright
cd ../..
$env:TELBATTLE_BROWSER_PATH='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
node scripts/smoke_card_traits_ui.mjs
```

برای Linux مسیر مرورگر و `TELBATTLE_TEST_PYTHON` را صریح تنظیم کنید. آزمون فقط دیتابیس تازه در `.test-tmp-form-traits/` می‌سازد و سرور محلی را پس از پایان می‌بندد. سناریو: ۱/۲/۳ تریت، تعویض فرم، ذخیره، بارگذاری کل صفحه، حذف همهٔ تریت‌های Legend و حفظ دو فرم دیگر و فهرست دائمی. نتیجهٔ CI و بستهٔ دقیق در PR ثبت می‌شود؛ ساخت فایل‌ها به‌معنی انتشار روی سرور نیست.

نتیجهٔ محلی همین اصلاح، ۱۰ اکتبر ۲۰۲۶: **۵۵۴ موفق، ۳ skipped** در تست کامل Windows/Python 3.11.9؛ بررسی syntax جاوااسکریپت هر دو پنل موفق؛ آزمون Edge برای **ساخت و ویرایش کارت** با API و SQLite واقعی موفق. تست‌ها حفظ دادهٔ مهاجرت، مقدار خالی مستقل، backfill نام فقط موجود در Legend، هر سه مسیر family/card/variant، Passive حریف، سؤال/گزینهٔ Easy، فرم فعال و اولویت تریت در دک، ثبت تغییرناپذیر تریت در مأموریت بدون پاداش تکراری و توقف preflight پیش از مهاجرت را هم پوشش می‌دهند. نتیجهٔ GitHub در هر دو Python 3.11 و 3.9.25 جدا در PR گزارش می‌شود.

## فهرست دائمی (اصلاح قبلی، حفظ‌شده)

نام تریت‌ها در `card_trait_registry` داخل همان دیتابیس برنامه نگه‌داری می‌شود و به تعداد کارت‌های دارای آن تریت وابسته نیست.

- «افزودن Trait» نام را همان لحظه ذخیره و در فرم انتخاب می‌کند؛ ذخیرهٔ کارت برای ثبت خود نام لازم نیست.
- برای دادن تریت به کارت، کارت را ذخیره کنید. برداشتن انتخاب فقط تریت آن کارت را تغییر می‌دهد.
- با برداشتن تریت از آخرین کارت، حذف کارت، refresh یا راه‌اندازی دوبارهٔ پنل، نام در منوی کشویی می‌ماند و برای کارت‌های دیگر قابل انتخاب است.
- افزودن دوبارهٔ نام با فاصلهٔ ابتدا/انتها یا تفاوت بزرگی حروف لاتین، گزینهٔ تکراری نمی‌سازد. نام تازه حداکثر ۱۰۰ کاراکتر است.
- تریت‌های قدیمیِ هنوز موجود در دیتابیس به فهرست منتقل می‌شوند. نامی که پیش از این اصلاح از همهٔ کارت‌ها حذف شده و دیگر جایی ذخیره نیست، قابل بازیابی خودکار نیست؛ یک بار دوباره اضافه‌اش کنید.

## مهاجرت قبلی فهرست دائمی؛ برای نصب قدیمیِ فاقد registry

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

در [اجرای GitHub نسخهٔ c2e684a](https://github.com/kasra-dastranj/telegram-card-game-bot/actions/runs/37642218615)، **در هر دو Python 3.11 و 3.9.25 روی Linux، ۲۷۶ تست موفق و فقط تست تلگرام زنده skipped** بود؛ build و بررسی JS هم موفق شدند. آن اجرای اول پیش از شروع job بسته‌سازی پایان ناموفق گرفت و درخواست rerun چند بار HTTP 500 دریافت کرد. نتیجهٔ کل CI فقط وقتی موفق است که بسته‌سازی و CI gate هم سبز باشند؛ آخرین اجرای PR ملاک پذیرش است. بستهٔ محلی همین commit با ۸۰ فایل runtime و policy بدون تغییر خودکار دیتابیس، ساخته و تأیید شد.
