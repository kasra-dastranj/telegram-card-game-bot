# فاز سوم: کارت سفارشی و Quick Friendly

این راهنما مربوط به کد شاخهٔ همکاری است؛ اجرای آن روی VPS در این کار انجام نشده است. همهٔ قابلیت‌های عمومی پیش‌فرض خاموش‌اند. Easy در Mini App فعلی وجود ندارد و این فاز آن را اضافه نمی‌کند؛ Easy در بات و موتور مشترک آزموده می‌شود. Quick Friendly، کلکسیون و Practice در Mini App نیز به همان قرارداد سرور وصل‌اند.

## ممیزی زیرساخت موجود

| بخش | مسیر واقعی |
|---|---|
| منشأ و Rarity | `core/models.py`، جدول `cards.origin` مستقل از `cards.rarity` |
| فرم و نسخه‌های رسمی | `card_variants`، `player_card_stacks` و `systems/card_inventory_system.py` |
| مالکیت انتخاب رسمی | `player_cards`؛ کارت سفارشی از Grant استفاده می‌کند |
| تنظیمات و هویت مسابقه | `systems/shared_foundation.py`؛ `foundation_settings` و `match_contexts` |
| شروع، انتخاب، Random و Resume | `systems/game_mode_system.py`، `systems/mini_three_round_system.py`، `web/miniapp_api.py` و `bot/handlers/game_modes.py` |
| پاداش و کسر قلب | `systems/match_rewards_system.py`، `systems/progression_match_rewards.py` و `systems/reward_ledger.py` |
| اقتصاد و مأموریت | `systems/progression_economy.py` و `systems/progression_missions.py` |
| کارت سفارشی و تخصیص | `systems/custom_cards.py` و `web/custom_admin_api.py` |

مبنای فاز دوم commit `13ded7b0018104261b88c7bf882854a367bb65b6` است. پیش از تغییر فاز سوم، ۱۴۹ تست زیرساخت و اقتصاد موفق شدند. فاز سوم موتور Quick یا اقتصاد را کپی نمی‌کند؛ Variant و Grant به مسیر مشترک وصل شده‌اند.

## قرارداد بازی

- کارت سفارشی Rarity واقعی Normal/Epic/Legend و Badge «سفارشی» دارد. ID پایدار `cc-…` است. نام نمایشی می‌تواند مشابه کارت رسمی باشد؛ هویت و مأموریت‌ها با ID و منشأ کنترل می‌شوند.
- یک تعریف کارت می‌تواند برای ده کاربر یا بیشتر Grant داشته باشد؛ کلید یکتای `(card_id,user_id)` تکرار را می‌بندد. Grant به موجودی Duplicate رسمی وارد نمی‌شود و قابل انتقال، هدیه یا فروش توسط بازیکن نیست.
- Quick اصلی، Three-Round، Deck و Risk کارت سفارشی را در انتخاب دستی، Random و مسیر سرور رد می‌کنند.
- Quick Friendly: همهٔ نتایج `XP=Score=Coin=TP=0`؛ فقط باخت `Heart=-1`. Retry و پایان مهلت پس از شروع مسابقه از Ledger مشترک استفاده می‌کنند. اگر انتخاب کارت هنوز کامل نشده، مسیر قدیمی لغو قبل از شروع حفظ است. Friendly در History با `quick_friendly` ثبت می‌شود و آمار، مأموریت و رتبهٔ رقابتی را جلو نمی‌برد.
- Easy با اجازهٔ سازنده همچنان مسابقهٔ عادی است: کمتر از پنج شرکت‌کنندهٔ واجدشرایط پاداش صفر؛ با حداقل پنج نفر، پاداش رتبه‌های اول تا سوم برای ۳/۵/۱۰ راند همان `10/5/3`، `15/10/8` و `20/15/13` است؛ Score رتبهٔ اول `1/2/3` و کسر قلب صفر. رتبه مشترک و قطع اتصال طبق فاز دوم حفظ‌اند.
- اجازهٔ Custom فقط هنگام ایجاد Easy قفل می‌شود. گزینهٔ این فاز در بات نمایش داده می‌شود؛ API انتخاب و نتیجه از Context ذخیره‌شده استفاده می‌کند.
- Practice با Custom: XP/Score/Coin/TP و کسر قلب صفر؛ سهمیهٔ روزانهٔ ASO و شرط داشتن قلب قبلی حفظ‌اند. Custom در Practice به سیاست پاداش `progression_v2_enabled` نیاز دارد؛ بدون آن ورود جدید رد می‌شود.
- مشخصات و Trait/Passive/Hidden Stats کارت پذیرفته‌شده Snapshot می‌شوند. تغییر یا تعلیق بعد از شروع نتیجه را عوض نمی‌کند؛ لغو قبل از شروع ورود تازه را می‌بندد. تصویر مستقل از Snapshot فوراً قابل لغو است.
- Custom از Daily/Silver Claim، Upgrade/Fusion، Sell، Shop، Wheel و Rare/Trade حذف است؛ تعداد رسمی و شرط مالکیت مأموریت رسمی نیز آن را حساب نمی‌کنند. مأموریت عمومی Easy معتبر همچنان پیشرفت دارد.

## پنل ادمین و گردش سفارش

پنل جدید در `/custom-cards`، روی همان سرویس ادمین، و در مسیر عمومی فعلی به صورت `https://taraz.gwfarsi.ir/card-admin/custom-cards` باز می‌شود. Nginx باید بازنویسی فعلی مسیر پنل را حفظ کند. Basic Auth فعلی و HTTPS برقرار باشند.

APIهای جدید **حتی در localhost بدون توکن ادمین باز نمی‌شوند**. `ADMIN_API_TOKEN` یا جایگزین موجود `ARENA_ADMIN_TOKEN` از محیط سرویس ادمین خوانده می‌شود؛ سرور هدر `X-Admin-Token` را بررسی می‌کند. مقدار واقعی را در Git، URL، Actions artifact یا گزارش نگذارید. پنل آن را فقط در حافظه نگه می‌دارد. `ARENA_ADMIN_ACTOR` نام حساب مسئول برای Audit است؛ در نبود آن شناسهٔ مشتق‌شدهٔ ادمین ثبت می‌شود. تنظیم این محیط‌ها بر عهدهٔ مسئول سرور است.

هر اقدام POST به `/api/custom/<action>` بدنهٔ زیر دارد. در پنل فقط محتوای `data` را وارد کنید؛ `request_key` خودکار ساخته می‌شود و تا دریافت پاسخ موفق برای Retry ثابت می‌ماند. برای عملیات تازه کلید تازه لازم است؛ استفاده از همان کلید با دادهٔ متفاوت خطا می‌دهد.

```json
{"request_key":"unique-operation-id","data":{}}
```

مراحل با **شناسه‌های حساب ثبت‌شده و تأییدشده**:

1. `order`: مبلغ و واحد توافق‌شده را وارد کنید. نمونه ساختار؛ عدد زیر نمونهٔ تست است و قیمت محصول نیست:

   ```json
   {"buyer_id":123,"rarity":"normal","recipients":[123,456],"amount":"123.45","currency":"TEST","notes":"توضیح غیرحساس"}
   ```

   `order_id` را از پاسخ نگه دارید. شناسهٔ ناشناخته بدون Grant خطا می‌دهد؛ تا ثبت حساب کاربر و تأیید هویتش صبر کنید. نام نمایشی یا username جای User ID نیست. خریدار تنها در صورت درج صریح در recipients دریافت‌کننده است؛ هیچ هزینه‌ای خودکار محاسبه نمی‌شود.

2. تصویر را از «آپلود خصوصی» بفرستید و `media_id` را بردارید. پیش‌نمایش تصویر و مقایسهٔ مشخصات رسمی هم‌رده از «سوابق و مقایسه» در دسترس است. رضایت صاحب تصویر، متن و مشخصات را پیش از فعال‌سازی بررسی کنید؛ اطلاعات پرداخت حساس در notes وارد نشود.

3. `create`:

   ```json
   {"order_id":"ORDER_ID","media_id":"MEDIA_ID","card":{"name":"نام کارت","rarity":"normal","power":5,"speed":6,"iq":7,"popularity":8,"abilities":[],"traits":["hero"],"series":"","hidden_stats":{"funny":20},"passive":{},"card_type":"POWER_TYPE","biography":"توضیح"}}
   ```

   Rarity باید با سفارش یکسان باشد؛ Rare مجاز نیست. اعتبارسنجی واقعی پنل `1..100` برای ویژگی‌های اصلی و Hidden Stats اعمال می‌شود؛ این محدوده تأیید بالانس Easy محسوب نمی‌شود. `image_path` و Telegram file ID از ورودی پذیرفته نمی‌شوند. کارت ابتدا draft است.

4. `payment` با `{"order_id":"ORDER_ID"}` فقط پس از بررسی دستی پرداخت خارج از بازی. سفارش pending قابل فعال‌سازی نیست.
5. `status` با `{"card_id":"CARD_ID","status":"active","review_confirmed":true}` پس از بازبینی، سپس `grant` با `{"order_id":"ORDER_ID","card_id":"CARD_ID","users":[123,456]}`. پرداخت، ساخت و Grant هیچ Coin، XP یا Level تولید نمی‌کنند.
6. گیرندهٔ تازه: سفارش جدید `order` با `card_id` تعریف قبلی، Rarity همان کارت، مبلغ توافق‌شدهٔ اضافی و recipients جدید؛ سپس payment و grant. تعریف یا تصویر تکراری نسازید.
7. `revoke` با `{"card_id":"CARD_ID","users":[123]}` فقط همان کاربر را غیرفعال می‌کند. `status=suspended` همهٔ استفاده‌های تازه را می‌بندد. History و سایر Grantها پاک نمی‌شوند.
8. `edit` شامل `order_id` اصلی، `card_id`، `card` کامل و `media_id` دلخواه است. کارت به pending_review می‌رود و فعال‌سازی مجدد بازبینی می‌خواهد. تصویر قبلی در صورت نیاز صریحاً در media_id وارد شود.
9. درخواست گزارش/حذف تصویر به ادمین تنظیم‌شده داده شود؛ `remove_image` با `{"card_id":"CARD_ID"}` نمایش تصویر را قطع و کارت را suspended می‌کند. Audit مالی و History حذف نمی‌شوند. پاک‌سازی فیزیکی فایل‌های بدون ارجاع پس از بررسی retention و بکاپ توسط مسئول سرور انجام شود؛ این فاز job حذف خودکار ندارد.

تمام mutationها همراه actor، زمان، اقدام و شناسه‌ها در `custom_audit` و رسید idempotent در `custom_operations` ثبت‌اند. آپلود نیز Audit دارد. پنل قدیمی اجازهٔ ویرایش تعریف Custom را ندارد.

## تصویر خصوصی

PNG/JPEG/WEBP تا ۸ MiB و حداکثر ۱۶ میلیون پیکسل پذیرفته، decode و به PNG با نام تولیدشدهٔ سرور تبدیل می‌شوند؛ metadata ارسالی حفظ نمی‌شود. نام فایل ورودی مسیر ذخیره نیست.

`TELBATTLE_CUSTOM_MEDIA_ROOT` روی سرور باید `/opt/telbattle/shared/private_custom_media` باشد؛ بدون تنظیم، پوشهٔ خصوصی کنار DB انتخاب می‌شود. مسیرهای عمومی assets/public/dist/web رد می‌شوند. API مینی‌اپ `/api/v1/custom/cards/<id>/image` فقط صاحب Grant فعال را می‌پذیرد؛ تصویر ادمین هم توکن می‌خواهد. پاسخ `private, no-store` است؛ مینی‌اپ با هدر احراز هویت blob موقت می‌سازد، توکن در URL نمی‌آید. کاربر حریف خودکار حق تصویر ندارد. تصویر Custom به کش استیکر inline یا تصویر نتیجهٔ گروهی فرستاده نمی‌شود. نمایش خصوصی در تلگرام همچنان تابع امکان ذخیرهٔ تصویر توسط دریافت‌کننده است؛ ارسال قبلی را نمی‌توان با Revoke پس گرفت.

فایل‌ها بیرون از release، Git و artifact هستند؛ Nginx نباید این پوشه را static serve کند. بکاپ خصوصی تصاویر در کنار بکاپ SQLite و با مجوز محدود لازم است؛ SQLite تنها metadata/شناسه را نگه می‌دارد.

## Feature Flag و QA

`custom_cards_enabled`، `quick_friendly_enabled`، `easy_custom_cards_enabled`، `custom_card_orders_enabled` همگی پیش‌فرض false؛ `custom_admin_contact=null`. ساخت و بازبینی مدیریتی با flags خاموش ممکن است، ولی بازیکن دسترسی جدیدی نمی‌بیند. Friendly و Easy+Custom نیازمند سیاست فاز دوم هستند.

در دیتابیس **تست** با سیاست فاز دوم فعال، `settings` در پنل/API:

```json
{"custom_cards_enabled":true,"quick_friendly_enabled":true,"easy_custom_cards_enabled":false,"custom_card_orders_enabled":false}
```

تماس سفارش فقط بعد از تعیین حساب واقعی ادمین:

```json
{"custom_card_orders_enabled":true,"custom_admin_contact":"https://t.me/CONFIRMED_ADMIN"}
```

مقدار بالا placeholder است، نه حساب پیشنهادی. Easy برای QA روی دیتابیس مصنوعی با `{"easy_custom_cards_enabled":true,"balance_approved":true}` قابل بررسی است؛ **فعال‌سازی عمومی آن هنوز منتظر تصویب معیار بالانس است**. مقدار balance_approved جای بازبینی مالک را نمی‌گیرد. خاموش‌کردن flagها داده را پاک نمی‌کند و نتیجهٔ شروع‌شده با Snapshot تسویه می‌شود.

## آماده‌سازی فقط توسط مسئول VPS

ابتدا Bootstrap GitHub/سرور در [راهنمای انتشار](DEPLOY_FROM_GITHUB_FA.md) و Migration فازهای یک و دو در راهنماهای مربوط انجام شود. این دستورات برای مسئول سرور آماده‌اند و در این کار اجرا نشده‌اند. از کد بازبینی‌شدهٔ همان artifact استفاده شود، نه pull از شاخهٔ متحرک. `REVIEWED_RELEASE` را به مسیر بستهٔ تأییدشده و ازقبل unpackشده تنظیم کنید.

```bash
# مسئول سرور؛ پوشه خارج از static assets و Git، مجوز فقط سرویس‌ها/مسئول
sudo install -d -o telbattle -g telbattle -m 0700 /opt/telbattle/shared/private_custom_media
```

متغیر `TELBATTLE_CUSTOM_MEDIA_ROOT=/opt/telbattle/shared/private_custom_media` باید در EnvironmentFile مشترک سرویس bot/api/admin اضافه شود. توکن ادمین فقط محیط سرویس ادمین؛ کانفیگ و environment موجود بازنویسی نشوند.

Migration ابتدا روی کپی، تحت قفل مشترک انتشار:

```bash
REVIEWED_RELEASE=/opt/telbattle/releases/REVIEWED_CANDIDATE
sudo env REVIEWED_RELEASE="$REVIEWED_RELEASE" flock -x /opt/telbattle/deploy.lock bash -euc '
  stamp=$(date -u +%Y%m%dT%H%M%S)
  /opt/telbattle/venv/bin/python "$REVIEWED_RELEASE/migrations/migrate_custom_cards.py" \
    --database /opt/telbattle/shared/game_bot.db \
    --preview-copy "/opt/telbattle/backups/phase3-preview-$stamp.db"
  chmod 0600 "/opt/telbattle/backups/phase3-preview-$stamp.db"
'
```

پس از آزمون کپی، بررسی schemas/flags و تأیید مسئول، apply در maintenance با بکاپ تازه:

```bash
sudo env REVIEWED_RELEASE="$REVIEWED_RELEASE" flock -x /opt/telbattle/deploy.lock bash -euc '
  stamp=$(date -u +%Y%m%dT%H%M%S)
  systemctl stop telbattle-bot telbattle-api telbattle-admin
  trap "systemctl start telbattle-bot telbattle-api telbattle-admin" EXIT
  /opt/telbattle/venv/bin/python "$REVIEWED_RELEASE/migrations/migrate_custom_cards.py" \
    --database /opt/telbattle/shared/game_bot.db --apply \
    --backup "/opt/telbattle/backups/pre-phase3-$stamp.db"
  chown telbattle:telbattle /opt/telbattle/shared/game_bot.db
  chmod 0600 /opt/telbattle/shared/game_bot.db
  chmod 0600 "/opt/telbattle/backups/pre-phase3-$stamp.db"
'
```

Migration شرط وجود reward_ledger فاز دوم را کنترل می‌کند، quick_check قبل/بعد دارد، افزایشی است و flag را روشن نمی‌کند. Release preflight همچنان هر تغییر startup به DB را رد می‌کند؛ Migration خودکار به Deploy اضافه نشده است.

بازگشت: ابتدا flagهای جدید را خاموش کنید؛ سپس rollback کد طبق راهنمای انتشار با قفل مشترک. جدول‌های افزایشی را نگه دارید. DB بعد از شروع بازی خودکار restore نشود؛ حذف دادهٔ تازهٔ بازیکنان ممکن است. restore بکاپ فقط maintenance جدا و تصمیم مسئول با ارزیابی دادهٔ تازه است.

## آزمون و تصمیم‌های باقی‌مانده

`tests/test_custom_cards_phase3.py` شامل ۴۴ آزمون سفارش، auth، تخصیص چندنفره، retry، تصویر، Snapshot، Friendly کامل با سه ترکیب کارت، کسر قلب، صف جدا، Easy با ۴/۵ نفر و ۳/۵/۱۰ راند، مأموریت/اقتصاد رسمی و Practice است. مجموعهٔ کامل، Python سرور و artifact در CI آخر PR بررسی می‌شوند؛ نتایج نهایی در [گزارش سه فاز](PHASES_FINAL_REPORT_FA.md) و PR ثبت می‌شوند.

تست مرورگر قابل تکرار با Vite محلی و API مصنوعی:

```powershell
# ترمینال اول: frontend/game
npm ci
npm run dev -- --host 127.0.0.1
# ترمینال دوم: ریشهٔ مخزن
$env:TELBATTLE_BROWSER_PATH='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
node scripts/smoke_custom_ui.mjs
node scripts/smoke_progression_ui.mjs
```

**PRODUCT DECISION / فعال‌سازی عمومی:** قیمت/واحد پول و هزینهٔ گیرندهٔ اضافه؛ حساب واقعی تماس ادمین؛ معیار بالانس Easy؛ سیاست رضایت و نمایش عمومی تصویر؛ تأیید رفتار ابیلیتی Friendly و ورود با صفر Heart. فعلاً ابیلیتی همان موجودی و مصرف Quick را دارد؛ مکانیک رایگان یا Unlimited ساخته نشده است. Quick موجود شرط تازهٔ Heart برای ورود ندارد و این فاز شرط آن را عوض نکرده؛ Practice شرط قلب قبلی را حفظ کرده است. قابلیت‌ها خاموش می‌مانند تا تصمیم rollout تأیید شود.

Telegram زنده، دیتای واقعی، VPS/systemd، Basic Auth عمومی و DNS در این فاز آزمایش نشده‌اند؛ دسترسی تولیدی و مجوز Deploy وجود نداشت. آزمون‌های محلی و CI فقط دادهٔ مصنوعی دارند.
