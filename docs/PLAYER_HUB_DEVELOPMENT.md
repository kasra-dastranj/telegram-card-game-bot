# برنامه توسعه Player Hub مینی‌اپ TelBattle

> وضعیت: در حال اجرا
> آخرین بروزرسانی: ۱۴۰۵/۰۶/۰۳ (2026-08-25)
> مرجع اجرایی: این سند منبع اصلی دامنه، ترتیب مراحل و معیار پذیرش Player Hub است.

## 1. هدف

ساخت یک مرکز کامل مدیریت بازیکن در Mini App که بدون شلوغ‌کردن زمین بازی، امکانات زیر را در اختیار بازیکن قرار دهد:

- مشاهده جان، زمان بازیابی جان، سکه، امتیاز، Level، XP و Tier
- مشاهده، فیلتر، مرتب‌سازی و بررسی جزئیات همه کارت‌ها
- ارتقای امن کارت با سکه
- ساخت، ویرایش، اعتبارسنجی و حذف Deck
- دریافت Claim روزانه
- مشاهده و دریافت پاداش مأموریت‌های کارت
- مشاهده و فعال‌کردن Skin کارت
- Fusion سه کارت با پیش‌نمایش و تأیید دومرحله‌ای

Player Hub مکمل زمین بازی است. در زمان Match فقط HUD خلاصه نمایش داده می‌شود و عملیات تغییردهنده موجودی، Deck یا کارت قفل خواهد بود.

## 2. محدوده فنی

### در محدوده

- Frontend اصلی: `frontend/game` با Vite، TypeScript و Phaser
- Backend اصلی: `web/miniapp_api.py`
- احراز هویت: Telegram Mini App `initData` و decorator فعلی `require_auth`
- منطق دامنه موجود در `core/` و `systems/`
- تست API با Flask test client و تست UI/Build موجود

### خارج از محدوده

- رابط قدیمی `frontend/miniapp`
- پنل ادمین
- تغییر قوانین اصلی Quick، Deck و Easy
- انتشار روی VPS تا زمانی که مالک پروژه صریحاً درخواست کند
- خرید واقعی یا درگاه پرداخت

## 3. اصول معماری

1. سرور منبع حقیقت است؛ کلاینت حق تعیین سکه، مالکیت، Rarity، پاداش یا نتیجه عملیات را ندارد.
2. هر عملیات مالی یا مصرف کارت باید در یک transaction دیتابیس انجام شود.
3. endpointهای تغییردهنده باید مالکیت را دوباره در سرور بررسی کنند.
4. دکمه عملیات هنگام درخواست غیرفعال می‌شود تا درخواست دوباره ارسال نشود.
5. پاسخ mutation باید snapshot تازه منابع و موجودیت تغییریافته را برگرداند.
6. عملیات مخرب مثل Fusion و حذف Deck تأیید دومرحله‌ای دارند.
7. تغییرات مدیریتی هنگام Match فعال مجاز نیستند.
8. لیست کارت‌ها صفحه‌بندی می‌شود؛ هیچ محدودیت پنهان ۲۰ کارتی وجود نخواهد داشت.
9. APIهای Bot و Mini App باید از service مشترک استفاده کنند تا قوانین دو نسخه متفاوت نشود.
10. هیچ token، initData یا URL شامل token در log ثبت نمی‌شود.

## 4. معماری رابط

### نوار پایین خارج از Match

حداکثر پنج مقصد:

1. بازی
2. کارت‌ها
3. دک‌ها
4. پیشرفت
5. فروشگاه

### HUD ثابت

- جان و زمان بازیابی
- سکه
- Level و XP
- Tier

### رفتار هنگام Match

- Bottom Navigation مخفی می‌شود.
- HUD به نسخه کم‌ارتفاع تبدیل می‌شود.
- مدیریت کارت، ارتقا، Fusion و Deck غیرفعال است.
- Back رفتار قابل پیش‌بینی دارد و خروج از Match تأیید می‌خواهد.

### قواعد UI/UX

- طراحی Mobile-first برای عرض پایه 375px
- حداقل هدف لمسی 44×44px و فاصله حداقل 8px
- رعایت safe-area تلگرام در بالا و پایین
- متن فارسی RTL؛ شناسه‌ها و اعداد ترکیبی با wrapper جهت مناسب
- کنتراست متن حداقل 4.5:1
- transition بین 150 تا 300 میلی‌ثانیه
- پشتیبانی از `prefers-reduced-motion`
- بدون horizontal scroll در بدنه صفحه
- Bottom sheet برای جزئیات کارت و تأیید عملیات
- آیکن‌های SVG یک‌دست؛ Emoji فقط محتوای بازی است، نه کنترل رابط

## 5. قراردادهای داده

### PlayerOverview

- `user_id`, `first_name`, `username`
- `hearts`, `max_hearts`, `heart_reset_seconds`
- `coins`, `total_score`
- `level`, `current_xp`, `xp_to_next_level`
- `current_tier`, `tier_points`
- `stats`, `best_card`
- `claim`, شامل قابلیت دریافت و زمان باقی‌مانده
- شمارش `cards`, `decks`, `missions_ready`

### ManagedCard

- همه فیلدهای فعلی Card
- `effective_rarity`
- `is_in_cooldown`, `cooldown_remaining_seconds`
- `upgrade_options`
- `mission`
- `skins`, `active_skin`
- `deck_ids`

### mutation envelope

```json
{
  "ok": true,
  "message": "عملیات انجام شد",
  "profile": {},
  "data": {}
}
```

خطاها با status مناسب و `error_code` پایدار برگردند.

## 6. نقشه API

### موجود و قابل توسعه

- `GET /api/v1/profile`
- `GET /api/v1/cards`
- `GET /api/v1/leaderboard`

### فاز 1

- `GET /api/v1/player-hub/overview`
- توسعه `GET /api/v1/cards?page=&limit=&rarity=&sort=&query=`
- `GET /api/v1/cards/<card_id>`

### فاز 2

- `POST /api/v1/cards/<card_id>/upgrade/preview`
- `POST /api/v1/cards/<card_id>/upgrade`

### فاز 3

- `GET /api/v1/decks`
- `POST /api/v1/decks`
- `PUT /api/v1/decks/<deck_id>`
- `DELETE /api/v1/decks/<deck_id>`

### فاز 4

- `GET /api/v1/claim`
- `POST /api/v1/claim`
- `GET /api/v1/missions`
- `POST /api/v1/missions/<mission_id>/claim`
- `GET /api/v1/cards/<card_id>/skins`
- `POST /api/v1/cards/<card_id>/skins/activate`
- `POST /api/v1/cards/<card_id>/skins/<skin_id>/purchase`

### فاز 5

- `POST /api/v1/fusions/preview`
- `POST /api/v1/fusions`

## 7. مراحل اجرا و معیار پذیرش

### فاز 0 — پایه و سند

- [x] تعیین frontend و backend مرجع
- [x] ثبت مرز دامنه و اصول امنیتی
- [x] ثبت Navigation و معیارهای UX
- [x] ایجاد typeها و serviceهای مشترک Player Hub
- [x] افزودن تست پایه endpointها

معیار پذیرش: سند توسط کد دنبال شود و هیچ قابلیت به رابط قدیمی اضافه نشود.

### فاز 1 — پوسته، پروفایل و کلکسیون

- [x] Bottom Navigation پنج‌بخشی
- [x] HUD کامل منابع
- [x] صفحه پروفایل و آمار
- [x] زمان باقی‌مانده بازیابی جان
- [x] کلکسیون کامل با pagination
- [x] فیلتر Rarity، جست‌وجو و مرتب‌سازی
- [x] Bottom sheet جزئیات کارت
- [x] Skeleton، empty state و error state

معیار پذیرش:

- بازیکن دارای بیش از ۲۰ کارت به همه کارت‌ها دسترسی دارد.
- داده پروفایل بعد از بازگشت از Match تازه می‌شود.
- صفحه در عرض‌های 375×667 و 390×844 بدون overflow کار می‌کند.

### فاز 2 — ارتقای کارت با سکه

- [x] استخراج منطق ارتقا از Handler تلگرام به service مشترک
- [x] transaction واحد برای کسر سکه، تغییر Rarity و XP
- [x] preview قیمت و نتیجه
- [x] تأیید کاربر
- [x] قفل double-submit
- [x] بروزرسانی فوری کارت، سکه و XP در رابط

معیار پذیرش:

- شکست هر بخش transaction هیچ تغییری در سکه یا کارت باقی نمی‌گذارد.
- کارت متعلق به کاربر دیگر قابل ارتقا نیست.
- Rarity نامعتبر یا ارتقای تکراری رد می‌شود.

### فاز 3 — مدیریت Deck

- [x] نمایش Deckها و وضعیت اعتبار
- [x] ساخت Deck سه‌کارتی
- [x] ویرایش نام و کارت‌ها
- [x] حذف با تأیید
- [x] نمایش Synergy و دلیل نامعتبر بودن
- [x] جلوگیری از استفاده کارت فاقد مالکیت

معیار پذیرش: قوانین `DeckSystem` بدون کپی‌شدن در frontend اعمال شوند.

### فاز 4 — Claim، Missions و Skins

- [x] وضعیت و timer Claim روزانه
- [x] Claim و نمایش کارت دریافت‌شده
- [x] فهرست مأموریت‌ها و progress
- [x] دریافت پاداش مأموریت با idempotency
- [x] فهرست Skinهای هر کارت
- [x] خرید و فعال‌سازی Skin متعلق به بازیکن

معیار پذیرش: Claim و پاداش تکراری ممکن نباشد و Skin بدون مالکیت فعال نشود.

### فاز 5 — Fusion

- [x] انتخاب دقیق سه کارت واجد شرایط
- [x] تعیین کارت باقی‌مانده
- [x] preview کارت‌های مصرفی و نتیجه
- [x] تأیید دومرحله‌ای
- [x] transaction و ثبت `fusion_log`
- [x] نتیجه تصویری و refresh کلکسیون

معیار پذیرش: قطع درخواست یا خطا هیچ Fusion ناقصی ایجاد نکند.

### فاز 6 — QA و تحویل

- [x] تست واحد serviceها
- [x] تست مالکیت و موجودی ناکافی
- [x] تست API همه endpointها
- [x] Build TypeScript
- [x] QA Drag/Drop و Match بعد از افزودن shell
- [x] QA موبایل، تبلت، افقی و Reduced Motion
- [x] بررسی امنیت logها
- [x] بروزرسانی Graphify
- [x] آماده‌سازی Release بدون انتشار

## 8. ترتیب فایل‌های هدف

- `web/miniapp_api.py`: endpoint و serialization
- `systems/player_hub_system.py`: facade خواندن overview و جزئیات
- `systems/card_upgrade_system.py`: ارتقای تراکنشی مشترک
- `frontend/game/src/api.ts`: قراردادها و client
- `frontend/game/src/main.ts`: state و navigation
- `frontend/game/src/styles.css`: shell، صفحات مدیریت و responsive
- `tests/test_player_hub_api.py`: پوشش API و امنیت
- `tests/test_card_upgrade_system.py`: transaction و مالکیت
- تست‌های جداگانه Deck، Claim/Mission/Skin و Fusion در فازهای مربوط

## 9. ریسک‌ها و کنترل‌ها

- ناسازگاری rarity پایه و `rarity_override`: همیشه effective rarity از DB خوانده شود.
- کسر سکه جدا از ارتقا: با service تراکنشی جایگزین شود.
- تغییر کارت وسط Match: mutationهای مدیریتی هنگام Match فعال رد شوند.
- دوباره‌زدن دکمه: loading lock در کلاینت و idempotency در endpointهای پاداش.
- لیست بزرگ کارت: pagination سمت سرور، lazy image و حفظ فضای تصویر.
- تداخل Phaser و DOM: Canvas زیر shell، z-index محدود و تعریف‌شده، و نابودی listenerهای صفحه قبلی.
- RTL/LTR: متن فارسی و نام انگلیسی در elementهای جدا با `dir` مشخص.

## 10. تصمیم‌های ثبت‌شده

- Player Hub سایدبار دائمی نیست؛ shell موبایلی با Bottom Navigation است.
- عملیات مدیریتی در Match انجام نمی‌شود.
- قابلیت‌ها مرحله‌ای فعال می‌شوند ولی همه از ابتدا در همین سند تعریف شده‌اند.
- پیاده‌سازی محلی است؛ Deploy فقط با دستور صریح مالک پروژه انجام می‌شود.

## 11. گزارش پیشرفت

| فاز | وضعیت | تست | توضیح |
|---|---|---:|---|
| 0 | تکمیل | 4 API test | سند و facade مشترک ساخته شد |
| 1 | تکمیل | Mobile QA | پروفایل، HUD و کلکسیون کامل |
| 2 | تکمیل | 4 service + browser QA | تراکنش امن مشترک Bot/Mini App |
| 3 | تکمیل | API + browser QA | CRUD سه‌کارتی و Synergy سمت سرور |
| 4 | تکمیل | API + browser QA | Claim/Mission/Skin تراکنشی و مالکیت‌محور |
| 5 | تکمیل | API + browser QA | Fusion اتمیک با تأیید دومرحله‌ای |
| 6 | تکمیل | 78 pytest + Build + Browser QA | آماده تستر؛ عمداً Deploy نشده است |

### یادداشت QA نهایی

- مجموعه تست‌های مدرن و مرتبط پروژه: `78 passed`
- تست‌های متمرکز Player Hub پس از آخرین اصلاح: `19 passed`
- QA واقعی مرورگر: موبایل 390×844 و 375×667، تبلت 768×1024، افقی 844×390 و Reduced Motion
- QA Quick: Drag نامعتبر، Drag موفق، Ability، Stat، Result و pagination دست کارت پاس شد.
- اجرای خام `pytest -q` هنوز به‌خاطر چند harness دستی قدیمی که importهای پیش از ساختار `systems/` و دستکاری مستقیم `sys.stdout` دارند، در مرحله Collection متوقف می‌شود. این فایل‌های legacy در تست 78تایی دخیل نیستند و تغییری در منطق محصول ایجاد نمی‌کنند.
