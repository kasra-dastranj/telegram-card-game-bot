# گزارش تحویل سه فاز TelBattle

تاریخ: ۹ اکتبر ۲۰۲۶. مخاطب: محمدحسین و کسری. این گزارش کد و آزمون شاخهٔ همکاری را شرح می‌دهد؛ فعال‌شدن قابلیت‌ها روی سرور را تأیید نمی‌کند.

**به‌روزرسانی مالک، ۱۰ اکتبر:** PR شمارهٔ ۱ ادغام و کد هر سه فاز همراه با مهاجرت‌های بررسی‌شده روی VPS نصب شده است. اقتصاد v2 پس از اصلاح و تست، با تأیید تازهٔ مالک فعال شد؛ موجودی حساب قدیمی محفوظ و جوایز Level جدید آن متوقف است. ۱۰۱ دستور Legend B و ۴ مأموریت آزمایشی ثبت شدند؛ Custom/Friendly خاموش ماندند. بخش‌های بعدی این سند تاریخچهٔ تحویل همکار در ۹ اکتبرند؛ برای وضعیت جاری، [راهنمای انتشار](DEPLOYMENT_STATUS_2026-10-10_FA.md) و بخش ۷ [گزارش توسعه](PROGRESSION_ECONOMY_DEVELOPMENT_2026-09-28.md) را بخوانید.

## خلاصهٔ هر فاز

| فاز | نتیجه و فایل‌های اصلی | راهنما |
|---|---|---|
| ۱: زیرساخت مشترک | منشأ مستقل کارت، Context تغییرناپذیر Mode/Variant، policy مستقل Reward/Heart، guard انتخاب و اقتصاد، flag خاموش؛ `systems/shared_foundation.py` و Migration افزایشی | [فاز یک](PHASE1_SHARED_FOUNDATION_FA.md) |
| ۲: پیشرفت و اقتصاد | XP/Score، تنظیمات قابل ویرایش ادمین، Ledger اتمیک، Claim/Ticket، Upgrade/Sell/Shop، ظرفیت قلب، Mission و Leaderboard؛ `systems/progression_*`، `systems/reward_ledger.py` و `migrations/migrate_progression_v2.py` | [فاز دو](PHASE2_PROGRESSION_ECONOMY_FA.md) |
| ۳: کارت سفارشی | سفارش دستی خارج از Coin، تعریف مشترک و Grant چندنفره، تصویر خصوصی، Quick Friendly، Easy با اجازهٔ سازنده، Practice و Snapshot؛ `systems/custom_cards.py`، `web/custom_admin_api.py` و `migrations/migrate_custom_cards.py` | [فاز سه و دستورات ادمین](PHASE3_CUSTOM_CARDS_FA.md) |

مبنای فاز اول commit `a43984b6` و اجرای CI `37934178252` بود؛ مبنای فاز دوم `13ded7b0018104261b88c7bf882854a367bb65b6` و CI موفق `37946884367`. فاز دوم در Linux با Python 3.11 و 3.9.25 هر کدام ۴۵۹ موفق/۱ skipped داشت. این اعداد نتیجهٔ نسخهٔ فاز سوم نیستند.

## تصمیم‌های شما که حفظ شده‌اند

- Daily Claim: احتمال Silver Ticket پیش‌فرض ۲۰٪، قابل تغییر از تنظیمات ادمین.
- رتبهٔ برابر: رتبهٔ مشترک ۱،۱،۳؛ هر بازیکن پاداش همان رتبه را می‌گیرد.
- Easy: قطع یک راوند امتیاز همان راوند را نمی‌دهد؛ امتیاز سایر راوندها جمع می‌شود. شرکت‌کننده با حداقل یک راوند معتبر حساب می‌شود؛ حداقل پنج User ID واقعی و متمایز برای پاداش لازم است.
- کاربران قدیمی: Coin، XP، قلب، کارت و دک حفظ می‌شوند؛ جوایز Level جدید برای آن‌ها، چه گذشته و چه آینده، فعلاً متوقف‌اند تا تصمیم بعدی شما.
- خرید ظرفیت قلب جای ظرفیت دو جایزهٔ آیندهٔ Level ۸ و ۱۰ را محفوظ می‌گذارد؛ سقف نهایی ۲۰ است.
- ابیلیتی سه‌راوندی در PvP و ASO: فقط یک بار در کل مسابقه و از موجودی مشترک Quick. قفل ویژگی ابیلیتی این مود نیست؛ قفل طبیعی راوند حفظ است.
- Trait دلخواه یک واژگان مستقل دارد؛ حذف Trait از آخرین کارت باعث حذف آن از منوی پنل نمی‌شود.

## قرارداد نهایی کارت سفارشی

**Friendly: پاداش صفر، باخت یک قلب. Easy مجاز: پاداش عادی، کسر قلب صفر. Practice: پاداش و کسر قلب صفر.** منشأ Custom به‌تنهایی پاداش کل Easy را صفر نمی‌کند.

سفارش و تأیید پرداخت دستی‌اند. قیمت، ارز و هزینهٔ گیرندهٔ اضافه خودکار اختراع نشده‌اند. کاربر ناشناخته/بدون Grant با ID مستقیم هم کارت را انتخاب نمی‌کند؛ عملیات ادمین نیازمند توکن واقعی سرویس و Audit است. تصویر از assets عمومی و artifact جداست. Revoke یک کاربر دسترسی دیگران را حذف نمی‌کند؛ Snapshot نتیجهٔ مسابقهٔ شروع‌شده را حفظ می‌کند.

Custom در Quick اصلی/Three-Round/Deck/Risk و در اقتصاد رسمی، Claim، Duplicate، فروش و Trade مجاز نیست. تعداد و مأموریت مالکیت رسمی با ID و origin کنترل می‌شوند. Easy در Mini App موجود نیست؛ تجربهٔ بات به سرور مشترک وصل شده و تجربهٔ تازهٔ خارج از Scope ساخته نشده است.

## Change Log فاز سوم

| فایل/گروه | تغییر |
|---|---|
| `systems/custom_cards.py` | سفارش، تعریف، Grant، status، Audit/رسید، تصویر خصوصی و Snapshot؛ هفت جدول افزایشی |
| `web/custom_admin_api.py`، `web/custom_card_management.html` | پنل ادمین، auth بدون bypass محلی، mutation idempotent، upload/preview خصوصی و بستن مسیر ویرایش قدیمی Custom |
| `core/database.py` | projection دارای Grant؛ کاتالوگ/Pool رسمی؛ شمارش رسمی؛ شروع اتمیک Practice با Snapshot |
| `systems/shared_foundation.py` | Context سازندهٔ Friendly/Easy، eligibility و settlement مبتنی بر دسترسی/Snapshot |
| `systems/game_mode_system.py` | موتور مشترک Friendly، صف جدا، frozen metadata، انتخاب Easy و کسر قلب idempotent Friendly |
| `systems/progression_match_rewards.py` | استفاده از Context/Snapshot و History غیررقابتی Friendly |
| `systems/player_hub_system.py`، `systems/ai_opponent.py` | شمارش رسمی مستقل، فیلتر انتخاب متناسب با Match و Pool رسمی AI |
| `web/miniapp_api.py`، `web/web_api.py` | API انتخاب/Practice/تصویر و ادغام پنل جدید؛ مجوز از سرور |
| `bot/handlers/basic.py`، `game_modes.py`، `battle.py` | منوی Friendly/Easy، Badge، تصویر خصوصی و جلوگیری از cache استیکر عمومی |
| `frontend/game/src/api.ts`، `main.ts` | انتخاب Friendly، Badge با Rarity واقعی، fetch تصویر با auth و حذف عملیات اقتصاد رسمی برای Custom |
| `migrations/migrate_custom_cards.py` | preview-copy، بکاپ اجباری apply، quick_check و حفظ flags/data |
| `tests/test_custom_cards_phase3.py` | ۴۴ تست پذیرش امنیت، چندنفره، بازی، اقتصاد، Snapshot و migration |
| تست‌های release/foundation/handler/API | سازگاری قرارداد Grant و رد migration خودکار در deploy |
| `scripts/check_admin_javascript.py` و `scripts/smoke_custom_ui.mjs` | بررسی JS هر دو پنل و smoke مرورگر با API مصنوعی |

## شواهد آزمون این نسخه

- مجموعهٔ کامل محلی، Python 3.11.9 روی Windows: **۵۰۱ passed، ۳ skipped، صفر failure/error**؛ SQLite موقت و guard آفلاین. دو skipped به محدودیت سیستم‌عامل و یکی به Telegram زنده مربوط‌اند.
- ۴۴ آزمون پذیرش فاز سوم به‌تنهایی موفق؛ از جمله کارت Normal/Epic/Legend برای ده گیرنده، گیرندهٔ یازدهم، payment_pending، Retry، تصویر خصوصی، سه ترکیب Quick Friendly، پایان مهلت و کسر یک‌بارهٔ قلب، Easy با ۴/۵ نفر در ۳/۵/۱۰ راند، مأموریت عمومی/رسمی و Practice.
- مرورگر Edge با API مصنوعی: Friendly و ارسال Variant، متن پاداش/قلب، Badge و تصویر auth/blob، مخفی‌بودن فروش/Upgrade/Skin برای Custom، flags خاموش و Retry ادمین با کلید یکسان؛ بدون pageerror.
- Smoke فاز دوم با API مصنوعی، نصب پاک `npm ci`، build TypeScript/Vite و syntax JavaScript دو پنل نیز موفق بودند. فونت و تصاویر onboarding خارج از Git همان وابستگی محیطی قبلی‌اند.
- تلگرام زنده، production DB، SSH، systemd و DNS عمومی آزمایش نشده‌اند. نمونهٔ مرورگر جای نتیجهٔ تلگرام واقعی را نمی‌گیرد.

### نتیجهٔ واقعی CI کد فاز سوم

[اجرای موفق 37961853592](https://github.com/kasra-dastranj/telegram-card-game-bot/actions/runs/37961853592) برای commit کد `7a7bce2868f712f8b5e9f38dbd399e44a104b607`: هر دو Python **3.11 و 3.9.25**، هرکدام **۵۰۳ passed / ۱ skipped / صفر failure/error**. Frontend/admin JavaScript، Verified release package و CI gate همگی success هستند.

[بستهٔ واقعی بررسی‌شده](https://github.com/kasra-dastranj/telegram-card-game-bot/actions/runs/37961853592/artifacts/11632660351): `release-5e76e63b1bd592dcf886a0b948afc0248111b96c-1`؛ ۹۶ فایل runtime + `RELEASE.json`، `database_policy=no-change`. SHA-256:

```text
5fbce03e1194bbff149a7983cc0c4466035d37a0b7c7d338e077835b1be7cd9c
```

Artifact و XML هر دو نسخه دانلود شدند؛ verifier هویت SHA/run و همهٔ hashها را تأیید کرد و فایل‌های کلیدی فاز سوم با blobهای commit کد نیز تطبیق داده شدند. فایل تصویر خصوصی، DB و secret در بسته نیستند. SHA بسته، merge آزمایشی GitHub برای PR است، نه SHA شاخهٔ شخصی؛ این تفاوت طبیعی است. بستهٔ PR مجوز انتشار production ندارد؛ پس از ادغام، CI و Deploy روی همان SHA ثابت main اجرا می‌شوند. Retention artifact چهارده روز است.

این بخش نتیجهٔ commit کد را ثبت می‌کند؛ commit تکمیلی گزارش تغییری به کد runtime ندارد. نتیجه و artifact آخرین commit گزارش نیز در PR ثبت می‌شود.

## هماهنگی در GitHub و انتشار

شاخه فقط `collab/mohammadhosein-mirzanezhad` است. هر سه فاز و کارهای قبلی همکاری در [PR شمارهٔ ۱](https://github.com/kasra-dastranj/telegram-card-game-bot/pull/1) برای بازبینی کسری تحویل می‌شوند؛ commit/CI/artifact آخر همان PR معیار نسخهٔ نهایی است. ادغام به main و production در این کار انجام نشده است.

پس از ادغام، CI روی main باید برای commit ادغام موفق باشد. با Bootstrap تأییدشده می‌توان Deploy TelBattle را دستی از main اجرا کرد؛ همان artifact اجرای CI منتشر می‌شود. Push روی شاخهٔ همکاری انتشار خودکار نیست. دستورهای دسترسی محدود، Environment production فقط main، قفل مشترک، health و rollback در [راهنمای انتشار](DEPLOY_FROM_GITHUB_FA.md) هستند.

## کارهای باقی‌ماندهٔ مسئول سرور و مالک محصول

1. بازبینی و پذیرش PR؛ Bootstrap اولیهٔ سرور و GitHub طبق راهنمای انتشار، اگر هنوز انجام نشده است.
2. آماده‌سازی Migrationهای Trait و فازهای ۱،۲،۳ روی کپی تأییدشده، سپس بکاپ تازه و apply در maintenance زیر `/opt/telbattle/deploy.lock`. Gate انتشار migration خودکار نمی‌کند.
3. پوشهٔ `/opt/telbattle/shared/private_custom_media` با مالک telbattle و mode 0700، محیط سرویس‌ها و توکن ادمین، بدون public static؛ دستور دقیق در راهنمای فاز سه است.
4. QA با حساب/DB تست؛ رضایت محتوا و قیمت توافق‌شده/حساب تماس واقعی. **Easy+Custom تا تصویب بالانس Stats/Traits/Hidden Stats خاموش بماند.**
5. تأیید رفتار ابیلیتی Friendly و ورود با صفر Heart پیش از rollout عمومی. مصرف موجود Quick حفظ شده؛ رایگان/نامحدود نشده است.
6. فعال‌سازی تدریجی فقط با تصمیم محصول و Deploy بازبینی‌شده. برای توقف، flags خاموش و در صورت نیاز rollback کد؛ DB بعد از شروع بازی خودکار restore نشود.

کار قابل‌انجام توسعه در این تحویل از راه‌اندازی تولیدی تفکیک شده است؛ هیچ قیمت یا تغییر پاداش خارج از تصمیم‌های شما، کلید سرور، اطلاعات بازیکن واقعی یا انتشار مستقیم به مخزن/سرور اصلی وارد این کار نشده است.
