# مشخصات توسعه سیستم یکپارچه زمین‌ها (Arena Registry)

> **وضعیت سند:** Draft آماده اجرا  
> **نسخه سند:** 1.0  
> **تاریخ:** 2026-08-29  
> **دامنه:** Telegram Bot، Mini App، Quick، نبرد سه‌راندی، Deck و پنل مدیریت  
> **هدف مخاطب:** توسعه‌دهنده انسانی و AI coding agent  
> **نوع سند:** مشخصات محصول، معماری، Migration، API، تست و Rollout  
> **نکته:** این سند مجوز شروع خودکار پیاده‌سازی نیست. هر فاز باید جداگانه تأیید و اجرا شود.

---

## 1. مأموریت سند

هدف این سند ساخت یک منبع حقیقت مرکزی برای تمام زمین‌های بازی است تا مدیر بازی بتواند بدون ویرایش مستقیم کد:

- زمین تازه ایجاد کند؛
- قوانین زمین را برای هر مود تعریف کند؛
- زمین را ابتدا فقط در تلگرام فعال کند؛
- رسانه Mini App را بعداً اضافه و منتشر کند؛
- زمین را به‌صورت Draft، Published یا Archived مدیریت کند؛
- زمین‌های رویدادی و زمان‌دار بسازد؛
- تغییرات را قبل از انتشار اعتبارسنجی و پیش‌نمایش کند؛
- بدون تغییر نتیجه مسابقات در حال اجرا، نسخه جدید قوانین را منتشر کند؛
- سابقه تغییرات و وابستگی کارت‌ها به زمین را مشاهده کند.

این سند باید در تمام مراحل توسعه Arena Registry مرجع اصلی باشد. اگر در کد موجود، سندهای قدیمی یا رفتارهای متناقض پیدا شد، توسعه‌دهنده نباید خودسرانه یکی را انتخاب کند؛ ابتدا باید اختلاف را ثبت کند و تصمیم محصولی بگیرد.

---

## 2. دستورالعمل الزامی برای AI توسعه‌دهنده

هر AI که بر اساس این سند کار می‌کند باید قواعد زیر را رعایت کند:

1. قبل از تغییر کد، وضعیت فعلی پروژه را با Graphify بررسی کند:

   ```text
   graphify query "arena registry battle quick admin miniapp database"
   ```

2. پیاده‌سازی را فقط در فازی انجام دهد که کاربر صریحاً درخواست کرده است.
3. بدون اجازه کاربر، فاز بعدی را شروع نکند.
4. رفتار فعلی زمین‌های Production را هنگام Migration حفظ کند؛ تغییر Balance بخشی از این پروژه نیست.
5. هیچ Rule جدیدی را بر اساس حدس به بازی اضافه نکند.
6. Rule خام، کد Python، SQL یا JavaScript قابل ورود از پنل نسازد.
7. همه Effectها را از فهرست سفید و Schema معتبر انتخاب کند.
8. Migrationها را Additive، قابل اجرای مجدد و سازگار با داده قدیمی بسازد.
9. هیچ زمین Published را Hard Delete نکند.
10. هیچ `arena_id` منتشرشده‌ای را تغییر ندهد.
11. قواعد مسابقه فعال را از آخرین تغییر پنل دوباره نخواند؛ از Snapshot همان مسابقه استفاده کند.
12. قبل از پایان هر فاز، تست‌های همان فاز و تست‌های Regression مودهای درگیر را اجرا کند.
13. بعد از هر تغییر کد، مطابق دستور پروژه اجرا کند:

    ```text
    graphify update .
    ```

14. تغییرات نامرتبط موجود در Worktree را حفظ کند.
15. اگر یک تصمیم مبهم نتیجه نبرد، Balance، امنیت یا Migration را تغییر می‌دهد، متوقف شود و از مالک محصول سؤال کند.

---

## 3. خلاصه تصمیم معماری

تصمیم اصلی این پروژه:

> زمین یک موجودیت مرکزی با هویت ثابت است، اما قوانین آن می‌توانند برای هر خانواده مود متفاوت باشند و رسانه آن برای هر پلتفرم جدا مدیریت شود.

ساختار مفهومی:

```text
Arena Identity
├── Published Version
│   ├── Shared Presentation
│   │   ├── name_fa
│   │   ├── name_en
│   │   ├── description
│   │   └── emoji
│   │
│   ├── Mode Profiles
│   │   ├── quick
│   │   ├── three_round
│   │   └── deck
│   │
│   └── Platform Media
│       ├── telegram
│       └── miniapp
│
├── Draft Version
├── Publication History
└── Audit Log
```

منبع حقیقت نهایی باید دیتابیس باشد. ثابت‌های داخل فایل‌های Python و Map ثابت تصاویر Frontend پس از Rollout کامل نباید منبع Runtime باقی بمانند.

---

## 4. وضعیت فعلی پروژه

### 4.1 تعریف قدیمی Arena

فایل `systems/arena_system.py` دارای موارد زیر است:

- `ArenaType` به‌صورت Enum ثابت؛
- چهار زمین `power_arena`، `speed_track`، `thinking_room` و `stage`؛
- Boost ثابت `+1`؛
- انتخاب تصادفی بر اساس اعضای Enum.

این ساختار برای زمین‌های پویا مناسب نیست، چون Enum در زمان اجرا با رکورد دیتابیس توسعه پیدا نمی‌کند.

### 4.2 نبرد سه‌راندی

فایل `systems/battle_system_3rounds.py` یک `ARENAS` مستقل دارد که شامل چهار زمین است و علاوه بر نمایش، قوانین واقعی نبرد را نگهداری می‌کند:

- `boost_stat`؛
- `boost_amount`؛
- `compare_stat`؛
- `trait_ranks`.

این تعریف توسط نبرد سه‌راندی، Solo و چند Handler تلگرام استفاده می‌شود.

### 4.3 Quick

فایل `systems/game_mode_system.py` یک `QUICK_ARENAS` جدا دارد که شامل شش زمین است:

- `city`؛
- `desert`؛
- `ice`؛
- `forest`؛
- `silent_temple`؛
- `null_zone`.

قوانین Quick شامل این موارد هستند:

- Effect شرطی بر اساس `card_type`؛
- تغییر یک Stat با `delta`؛
- `disabled_stats`؛
- `abilities_enabled`؛
- `passives_enabled`.

### 4.4 Mini App

فایل `frontend/game/src/BattleScene.ts` تصاویر زمین‌ها را با یک Map ثابت Preload می‌کند. اگر شناسه زمین شناخته نشود، Frontend آن را به `city` تبدیل می‌کند. این رفتار در سیستم جدید نباید باعث نمایش تصویر اشتباه شود.

### 4.5 پنل مدیریت

پنل `web/card_management.html` و API موجود در `web/web_api.py` برای مدیریت کارت ساخته شده‌اند. پنل در حال حاضر:

- لیست و فرم کارت دارد؛
- تب اطلاعات پایه، مودها و رسانه دارد؛
- Upload تصویر و Sticker دارد؛
- Arena را مدیریت نمی‌کند؛
- Passiveهای کارت با شرط Arena را مستقیماً در برابر `QUICK_ARENAS` اعتبارسنجی می‌کند.

### 4.6 ذخیره Arena در Matchها

شناسه زمین در چند محل ذخیره می‌شود، از جمله:

- `active_fights.arena_type`؛
- `battle_states.arena`؛
- `solo_fights.arena`؛
- `game_match_states.state_json` برای Quick.

در طراحی فعلی معمولاً فقط شناسه ذخیره می‌شود. اگر Registry پویا شود و Match فقط شناسه داشته باشد، ویرایش قوانین ممکن است نتیجه مسابقه در حال اجرا را عوض کند. این مسئله باید با Version و Snapshot حل شود.

---

## 5. اهداف محصولی

### 5.1 اهداف اصلی

- یکپارچه‌کردن هویت زمین‌ها در تمام مودها؛
- افزودن زمین از پنل بدون تغییر دستی Python؛
- فعال‌سازی مستقل برای Telegram و Mini App؛
- پشتیبانی از زمین بدون تصویر در Telegram؛
- جلوگیری از ورود زمین بدون رسانه آماده به Mini App؛
- تعریف قوانین متفاوت برای مودهای مختلف زیر یک هویت؛
- Draft، Validate، Preview، Publish، Archive و Rollback؛
- حفظ کامل Matchهای فعال هنگام انتشار نسخه تازه؛
- مدیریت Pool فعال و وزن انتخاب؛
- پشتیبانی از رویدادهای زمان‌دار؛
- ثبت Audit برای همه تغییرات؛
- فراهم‌کردن پایه Analytics و Balance در آینده.

### 5.2 اهداف ثانویه

- امکان Clone کردن یک زمین برای ساخت Variant رویدادی؛
- نمایش وابستگی کارت‌ها و Passiveها به زمین؛
- امکان Preview متنی تلگرام؛
- امکان Preview تصویری Mini App؛
- امکان شبیه‌سازی Rule روی کارت نمونه؛
- قابلیت بازگرداندن نسخه قدیمی با انتشار Revision جدید.

### 5.3 خارج از دامنه نسخه اول

- Rule scripting با Python یا JavaScript؛
- Ruleهای ساخته‌شده توسط بازیکنان؛
- فروش یا مالکیت زمین؛
- تولید Procedural تصویر زمین؛
- سیستم آب‌وهوا یا چرخه شب و روز؛
- ویرایش سه‌بعدی صحنه Phaser از پنل؛
- CDN خارجی بدون سیاست امنیتی و Cache مشخص؛
- تغییر Balance زمین‌های فعلی هم‌زمان با Migration؛
- حذف فوری تمام Compatibility Adapterها در اولین Release؛
- تبدیل Arena به آیتم اقتصادی یا NFT.

---

## 6. واژگان رسمی دامنه

| اصطلاح | تعریف |
|---|---|
| Arena | هویت ثابت یک زمین در کل بازی |
| Arena ID | Slug کوتاه، انگلیسی، یکتا و غیرقابل تغییر پس از انتشار |
| Arena Version | Snapshot نسخه‌بندی‌شده محتوا، Ruleها و رسانه زمین |
| Draft | نسخه قابل ویرایش و هنوز منتشرنشده |
| Published | نسخه غیرقابل ویرایش که برای Runtime معتبر است |
| Archived | زمین خارج‌شده از Pool جدید؛ همچنان برای تاریخچه قابل خواندن است |
| Mode Profile | قوانین زمین برای یک خانواده مود مشخص |
| Platform Availability | فعال‌بودن زمین برای `telegram` یا `miniapp` |
| Media Readiness | وضعیت آماده‌بودن دارایی مورد نیاز یک پلتفرم |
| Active Pool | مجموعه زمین‌های واجد شرایط برای یک مود و پلتفرم در یک زمان |
| Selection Weight | وزن نسبی انتخاب تصادفی زمین در Active Pool |
| Arena Snapshot | داده غیرقابل تغییر زمین که در زمان شروع Match ذخیره می‌شود |
| Rule Schema Version | نسخه Schema داخلی Ruleها برای Migration آینده |
| Publish | تبدیل Draft معتبر به نسخه Published جدید |
| Rollback | ساخت و انتشار نسخه‌ای جدید بر اساس یک نسخه Published قدیمی |

---

## 7. تصمیم‌های قطعی و Invariantها

موارد این بخش نباید بدون تصمیم صریح مالک محصول تغییر کنند.

### 7.1 هویت

1. `arena_id` باید کوتاه، ASCII، lowercase و snake_case باشد.
2. الگوی پیشنهادی:

   ```text
   ^[a-z][a-z0-9_]{2,23}$
   ```

3. `arena_id` پس از اولین Publish غیرقابل تغییر است.
4. نام فارسی و انگلیسی قابل تغییر هستند.
5. دو زمین نمی‌توانند `arena_id` یکسان داشته باشند.

### 7.2 حذف و آرشیو

1. Draft منتشرنشده در صورت نداشتن Dependency می‌تواند حذف شود.
2. Arena منتشرشده هرگز Hard Delete نمی‌شود.
3. Archive فقط آن را از Matchهای جدید خارج می‌کند.
4. Matchهای تاریخی و فعال باید همچنان Snapshot یا Version مربوط را بخوانند.

### 7.3 نسخه‌بندی

1. Draft قابل ویرایش است.
2. Version منتشرشده Immutable است.
3. هر Publish شماره Version را افزایش می‌دهد.
4. Rollback نسخه قبلی را ویرایش نمی‌کند؛ Version تازه‌ای از روی آن می‌سازد.
5. Runtime فقط Published Version را مصرف می‌کند.

### 7.4 Match

1. هر Match هنگام شروع باید `arena_id`، `arena_version` و `arena_snapshot` داشته باشد.
2. تمام راندهای همان Match از همان Snapshot استفاده می‌کنند.
3. Publish جدید نباید Match فعال را تغییر دهد.
4. تغییر زمین با Ability باید به یک Version معتبر اشاره کند و Snapshot تازه‌ی همان تغییر را در State ثبت کند.

### 7.5 پلتفرم

1. Telegram بدون تصویر هم می‌تواند Arena را اجرا کند.
2. Mini App فقط وقتی Arena را انتخاب می‌کند که Background آن `ready` باشد.
3. `telegram_enabled` و `miniapp_enabled` مستقل هستند.
4. فعال‌بودن پلتفرم به‌تنهایی کافی نیست؛ Mode Profile نیز باید فعال باشد.

### 7.6 Ruleها

1. Rule خام یا قابل اجرا از پنل پذیرفته نمی‌شود.
2. فقط Rule Typeهای ثبت‌شده در Backend مجاز هستند.
3. هر Rule قبل از ذخیره Draft و دوباره قبل از Publish Validate می‌شود.
4. حداقل یک Stat باید در هر مود قابل انتخاب باقی بماند.
5. Ruleهای فعلی هنگام Seed بدون تغییر عددی منتقل می‌شوند.

### 7.7 زمان‌بندی

1. زمان‌ها در دیتابیس با UTC ذخیره می‌شوند.
2. پنل زمان را با timezone تهران نمایش می‌دهد.
3. `active_from` و `active_until` اختیاری هستند.
4. زمین خارج از بازه زمانی وارد Active Pool نمی‌شود.

---

## 8. خانواده مودهای نسخه اول

برای جلوگیری از تکثیر بی‌دلیل Profile، نسخه اول سه خانواده Rule دارد:

| کلید | مصرف‌کننده | توضیح |
|---|---|---|
| `quick` | Quick تلگرام و Quick Mini App | نبرد یک‌راندی با Effectهای شرطی |
| `three_round` | PvP سه‌راندی و Solo سه‌راندی | Boost، Compare Stat و منطق Trait |
| `deck` | Deck Mode | اولویت Trait و Compare Stat |

اگر بعداً قواعد Solo و PvP سه‌راندی از هم جدا شدند، Profile جدید فقط با Migration Schema و تصمیم محصول اضافه می‌شود. نسخه اول نباید بی‌دلیل `solo_3round` و `pvp_3round` را کپی کند.

---

## 9. مدل داده پیشنهادی

نام دقیق جدول‌ها در زمان اجرا می‌تواند با Convention پروژه هماهنگ شود، اما قابلیت‌ها و Constraintهای این بخش الزامی‌اند.

### 9.1 جدول `arenas`

هویت پایدار زمین را نگه می‌دارد.

| ستون | نوع پیشنهادی | قاعده |
|---|---|---|
| `arena_id` | TEXT PK | Slug ثابت |
| `lifecycle_status` | TEXT | `draft_only`, `published`, `archived` |
| `current_published_version` | INTEGER NULL | آخرین Version معتبر |
| `created_at` | TEXT | UTC ISO-8601 |
| `created_by` | TEXT/INTEGER | شناسه ادمین |
| `updated_at` | TEXT | UTC ISO-8601 |
| `updated_by` | TEXT/INTEGER | شناسه ادمین |

Constraintها:

- `arena_id` یکتا و مطابق Regex؛
- `current_published_version` فقط به Version Published همان Arena اشاره کند؛
- Arena Published قابل حذف نباشد.

### 9.2 جدول `arena_versions`

نسخه محتوایی زمین را نگه می‌دارد.

| ستون | نوع پیشنهادی | قاعده |
|---|---|---|
| `arena_id` | TEXT | FK به `arenas` |
| `version` | INTEGER | از 1 شروع می‌شود |
| `version_status` | TEXT | `draft`, `published`, `superseded` |
| `name_fa` | TEXT | الزامی |
| `name_en` | TEXT | اختیاری ولی توصیه‌شده |
| `description_fa` | TEXT | الزامی برای Published |
| `emoji` | TEXT | الزامی برای Telegram |
| `tags_json` | TEXT | لیست Tagهای معتبر |
| `rule_schema_version` | INTEGER | نسخه Schema Rule |
| `content_hash` | TEXT | برای Cache و Integrity |
| `created_at` | TEXT | UTC |
| `created_by` | TEXT/INTEGER | Actor |
| `published_at` | TEXT NULL | فقط Published |
| `published_by` | TEXT/INTEGER NULL | فقط Published |

کلید اصلی مرکب:

```text
(arena_id, version)
```

قواعد:

- حداکثر یک Draft باز برای هر Arena؛
- Version Published قابل Update نیست؛
- Publish با Transaction اتمیک انجام می‌شود؛
- `content_hash` از Presentation، Profileها و Media Manifest محاسبه می‌شود.

### 9.3 جدول `arena_mode_profiles`

قوانین هر Version برای هر خانواده مود را نگه می‌دارد.

| ستون | نوع پیشنهادی | قاعده |
|---|---|---|
| `arena_id` | TEXT | بخشی از FK Version |
| `version` | INTEGER | بخشی از FK Version |
| `mode_key` | TEXT | `quick`, `three_round`, `deck` |
| `enabled` | INTEGER | 0/1 |
| `selection_weight` | INTEGER | 1 تا 1000 در صورت Enabled |
| `active_from` | TEXT NULL | UTC |
| `active_until` | TEXT NULL | UTC |
| `rules_json` | TEXT | خروجی داخلی Rule Builder |
| `rules_hash` | TEXT | Integrity/Cache |

کلید اصلی:

```text
(arena_id, version, mode_key)
```

نکته: `rules_json` یک قرارداد داخلی Validate‌شده است. پنل نباید ویرایشگر JSON آزاد نمایش دهد.

### 9.4 جدول `arena_platform_settings`

فعال‌بودن هر Version برای هر پلتفرم را نگه می‌دارد.

| ستون | نوع پیشنهادی | قاعده |
|---|---|---|
| `arena_id` | TEXT | FK Version |
| `version` | INTEGER | FK Version |
| `platform` | TEXT | `telegram`, `miniapp` |
| `enabled` | INTEGER | 0/1 |
| `presentation_json` | TEXT | تنظیمات غیرقابل اجرای نمایش |

### 9.5 جدول `arena_media`

| ستون | نوع پیشنهادی | توضیح |
|---|---|---|
| `media_id` | TEXT PK | UUID یا شناسه امن |
| `arena_id` | TEXT | FK Version |
| `version` | INTEGER | FK Version |
| `platform` | TEXT | `telegram`, `miniapp` |
| `media_kind` | TEXT | `background`, `photo`, `sticker`, `thumbnail` |
| `storage_path` | TEXT | مسیر داخلی تولیدشده توسط سرور |
| `telegram_file_id` | TEXT NULL | برای Telegram |
| `mime_type` | TEXT | از File Signature تعیین شود |
| `width` | INTEGER NULL | برای تصویر |
| `height` | INTEGER NULL | برای تصویر |
| `byte_size` | INTEGER | محدودیت Upload |
| `sha256` | TEXT | Cache و Deduplication |
| `readiness_status` | TEXT | `pending`, `ready`, `failed`, `retired` |
| `created_at` | TEXT | UTC |
| `created_by` | TEXT/INTEGER | Actor |

### 9.6 جدول `arena_audit_log`

| ستون | توضیح |
|---|---|
| `id` | کلید افزایشی |
| `arena_id` | زمین هدف |
| `version` | Version هدف |
| `action` | create، update_draft، upload_media، validate، publish، archive، rollback |
| `actor_id` | ادمین |
| `request_id` | Correlation ID |
| `before_json` | Snapshot قبل، در صورت نیاز |
| `after_json` | Snapshot بعد، در صورت نیاز |
| `created_at` | UTC |

Audit باید برای عملیات تغییردهنده اجباری باشد.

### 9.7 Version/Snapshot در Matchها

برای جدول‌های Match موجود، Migration باید به‌صورت Additive این مفهوم را اضافه کند:

| محل | تغییر مفهومی |
|---|---|
| `active_fights` | `arena_version`, `arena_snapshot` در کنار `arena_type` |
| `battle_states` | `arena_version`, `arena_snapshot` در کنار `arena` |
| `solo_fights` | `arena_version`, `arena_snapshot` در کنار `arena` |
| Quick `state_json` | کلیدهای `arena_id`, `arena_version`, `arena_snapshot` |

ستون‌های شناسه قدیمی در اولین Release حذف نمی‌شوند.

---

## 10. قرارداد Runtime Arena

Backend باید یک مدل Runtime نرمال‌شده تحویل موتور نبرد دهد. نمونه مفهومی:

```json
{
  "arena_id": "desert",
  "version": 3,
  "name_fa": "بیابان سوزان",
  "description_fa": "قدرت در گرما رشد می‌کند و سرعت افت می‌کند.",
  "emoji": "🏜️",
  "mode": "quick",
  "selection_weight": 100,
  "rules": {
    "effects": [
      {
        "type": "stat_modifier",
        "condition": {"card_type": "power"},
        "target_stat": "power",
        "delta": 2
      },
      {
        "type": "stat_modifier",
        "condition": {"card_type": "speed"},
        "target_stat": "speed",
        "delta": -1
      }
    ],
    "disabled_stats": [],
    "abilities_enabled": true,
    "passives_enabled": true
  },
  "platform": {
    "telegram": {"enabled": true},
    "miniapp": {
      "enabled": true,
      "background_url": "/miniapp-assets/arena-backgrounds/desert.v3.webp"
    }
  }
}
```

این نمونه قرارداد است، نه الزام به ذخیره همین JSON در یک ستون.

---

## 11. Rule Schema نسخه اول

### 11.1 قواعد عمومی

- Stat معتبر فقط یکی از `power`, `speed`, `iq`, `popularity` است.
- Card Type در Quick فقط یکی از `power`, `speed`, `iq`, `popularity` است.
- Card Typeهای قدیمی هنگام Boundary نرمال می‌شوند.
- عددها Integer هستند.
- ترتیب اجرای Effectها باید مشخص و پایدار باشد.
- موتور نبرد نباید بر ترتیب تصادفی رکوردهای دیتابیس تکیه کند.
- هر Effect باید `priority` یا ترتیب ذخیره‌شده داشته باشد.

### 11.2 Profile مربوط به Quick

فیلدهای مجاز:

| فیلد | نوع | اعتبارسنجی |
|---|---|---|
| `effects` | List | حداکثر تعداد مورد توافق؛ هر مورد Validate شود |
| `disabled_stats` | List | از CORE_STATS؛ حداقل یک Stat آزاد بماند |
| `abilities_enabled` | bool | پیش‌فرض true |
| `passives_enabled` | bool | پیش‌فرض true |

Effect مجاز نسخه اول:

#### `stat_modifier`

```json
{
  "type": "stat_modifier",
  "condition": {"card_type": "power"},
  "target_stat": "power",
  "delta": 2,
  "priority": 100
}
```

قواعد:

- `condition.card_type` الزامی در نسخه اول؛
- `target_stat` از CORE_STATS؛
- بازه اولیه پیشنهادی `delta`: از `-10` تا `+10`؛
- مقدار خارج از بازه Hard Error؛
- Duplicate Effect دقیق با Warning یا Error رد شود.

### 11.3 Profile مربوط به `three_round`

| فیلد | نوع | قاعده |
|---|---|---|
| `boost_stat` | Stat | الزامی |
| `boost_amount` | Integer | در Seed برابر رفتار فعلی |
| `requires_card_type_match` | bool | در نسخه اول true برای رفتار فعلی |
| `compare_stat` | Stat | برای Deck/Resolution مرتبط |
| `trait_ranks` | List[List[String]] | Traitهای نرمال‌شده و بدون تکرار |

محدوده پیشنهادی Validation:

- `boost_amount`: صفر تا 30؛
- `trait_ranks`: حداکثر پنج Tier؛
- هر Trait با `strip + casefold` نرمال شود؛
- Trait تکراری در دو Tier مختلف Hard Error است.

### 11.4 Profile مربوط به `deck`

در نسخه اول می‌تواند از Profile سه‌راندی مشتق شود، اما Runtime باید قرارداد مستقل بگیرد:

| فیلد | توضیح |
|---|---|
| `compare_stat` | Stat عددی Fallback |
| `trait_ranks` | اولویت Tierهای Trait |
| `stat_tiebreak_enabled` | آیا مقایسه عددی پس از Trait انجام شود |

اگر `deck` Profile تعریف نشده ولی `three_round` موجود است، Compatibility Adapter می‌تواند موقتاً از همان `compare_stat` و `trait_ranks` استفاده کند. این Fallback باید Log شود و پس از Migration کامل حذف شود.

---

## 12. ترتیب اجرای Ruleها

برای جلوگیری از اختلاف بین مودها، ترتیب کلی باید مستند باشد.

### 12.1 Quick

ترتیب پیشنهادی سازگار با ساختار فعلی:

1. خواندن Snapshot زمین؛
2. خواندن Statهای پایه کارت؛
3. اعمال Effectهای زمین بر اساس `priority`؛
4. اعمال Passive مجاز، اگر `passives_enabled=true`؛
5. اعمال Ability حریف، اگر `abilities_enabled=true`؛
6. اعمال محدودیت `disabled_stats` و قفل‌های Ability؛
7. ثبت Breakdown برای UI و Report؛
8. Resolve نتیجه.

هرگونه تغییر این ترتیب یک تغییر Balance است و خارج از Migration صرف محسوب می‌شود.

### 12.2 سه‌راندی

ترتیب اولیه باید رفتار فعلی را حفظ کند:

1. Stat پایه؛
2. بررسی `selected_stat == boost_stat`؛
3. بررسی تطبیق Card Type در صورت نیاز؛
4. اعمال `boost_amount`؛
5. اعمال Effect/Abilityهای موجود طبق موتور فعلی؛
6. Resolve؛
7. ثبت Breakdown.

### 12.3 Deck

1. دریافت Traitهای نرمال‌شده؛
2. محاسبه بهترین Trait Tier؛
3. برنده‌شدن Tier بالاتر؛
4. در نبود برنده Trait، مقایسه `compare_stat`؛
5. ثبت Reason دقیق `trait` یا `stat`.

---

## 13. Arena Registry Service

یک سرویس مرکزی باید تنها نقطه دسترسی Runtime به Arena باشد. نام پیشنهادی:

```text
systems/arena_registry.py
```

مسئولیت‌های سرویس:

- خواندن Version Published؛
- دریافت Arena بر اساس ID/Version؛
- ساخت Active Pool برای Mode و Platform؛
- انتخاب وزن‌دار؛
- ساخت Snapshot Match؛
- Validate کردن Draft؛
- Normalize کردن Ruleها؛
- ارائه Manifest رسانه Mini App؛
- مدیریت Cache نسخه‌محور؛
- پشتیبانی موقت از Compatibility Adapter.

Interface مفهومی:

```text
get_published(arena_id)
get_version(arena_id, version)
list_active(mode, platform, at_utc)
select_for_match(mode, platform, exclude_ids=None, rng=None)
snapshot_for_match(arena_id, mode, platform)
validate_draft(arena_id)
publish(arena_id, actor_id, expected_draft_revision)
archive(arena_id, actor_id)
list_dependencies(arena_id)
get_miniapp_manifest(version_token=None)
```

### 13.1 انتخاب وزن‌دار

قواعد انتخاب:

1. فقط Arenaهای Published؛
2. فقط Lifecycle غیر Archived؛
3. فقط Profile فعال مود؛
4. فقط Platform فعال؛
5. فقط داخل بازه زمانی؛
6. برای Mini App فقط با Background آماده؛
7. وزن بیشتر، احتمال نسبی بیشتر؛
8. `exclude_ids` برای Reroll رعایت شود؛
9. اگر بعد از Exclude هیچ گزینه‌ای نماند، Pool اصلی استفاده شود؛
10. اگر Pool اصلی خالی است، سیستم نباید تصویر یا Rule جعلی بسازد.

رفتار Empty Pool باید با Feature Flag و Fallback Seed کنترل شود. در Rollout اولیه یک Arena Seed امن مثل `power_arena` باید همواره Published بماند.

### 13.2 RNG

- RNG باید قابل تزریق در تست باشد؛
- نتیجه انتخاب و Candidate Pool در سطح مناسب Log شود؛
- برای Gameplay عادی RNG رمزنگاری‌شده الزام نیست، اما رفتار باید قابل تست و بدون Bias پیاده‌سازی شود؛
- Weightها پیش از انتخاب Validate و Normalize شوند.

### 13.3 Cache

بات، Mini App API و Admin API Processهای مستقل دارند. Cache باید:

- با `content_hash` یا Global Registry Version کلید بخورد؛
- TTL کوتاه و قابل تنظیم داشته باشد؛
- پس از Publish در Process پنل Invalidate شود؛
- در Processهای دیگر حداکثر بعد از TTL تازه شود؛
- در صورت نیاز از فایل Signal یا جدول `arena_registry_meta` برای Version Poll استفاده کند؛
- هرگز Snapshot Match را با Cache جدید جایگزین نکند.

نسخه اول می‌تواند بدون Cache شروع شود اگر Load کم است؛ صحت بر Performance مقدم است.

---

## 14. Snapshot مسابقه

Snapshot مهم‌ترین الزام صحت سیستم است.

نمونه مفهومی:

```json
{
  "arena_id": "power_arena",
  "arena_version": 2,
  "mode": "three_round",
  "name_fa": "عرصه قدرت",
  "emoji": "⚡",
  "rules": {
    "boost_stat": "power",
    "boost_amount": 8,
    "requires_card_type_match": true,
    "compare_stat": "power",
    "trait_ranks": [
      ["god", "monster"],
      ["hero", "warrior"],
      ["villain"]
    ]
  }
}
```

قواعد:

- Snapshot فقط داده لازم برای همان Mode را داشته باشد؛
- مسیر فایل محلی حساس یا داده Admin وارد Snapshot نشود؛
- Snapshot در Match ایجاد و سپس Immutable تلقی شود؛
- Ability تغییر زمین Snapshot جدید را جایگزین و Arena History را ثبت کند؛
- نتیجه Match باید Versionهای استفاده‌شده را گزارش کند؛
- Replay/Report آینده باید از Snapshot استفاده کند، نه Registry امروز.

---

## 15. رسانه و Mini App

### 15.1 سیاست رسانه Mini App

Background Mini App در نسخه اول:

- `webp` ترجیحی؛
- `jpg` و `png` فقط در صورت Pipeline تبدیل امن؛
- نسبت هدف 9:16؛
- رزولوشن پیشنهادی 1080×1920 یا بالاتر با همان نسبت؛
- حداکثر حجم اولیه پیشنهادی 3MB پس از پردازش؛
- Safe Zone مرکز برای کارت‌ها و پنل‌های UI؛
- نام فایل توسط سرور تولید شود؛
- نام فایل اصلی کاربر مستقیماً به مسیر تبدیل نشود؛
- مسیر نسخه‌دار و Immutable باشد.

نمونه مسیر:

```text
frontend/game/public/arena-backgrounds/desert/v3-<hash>.webp
```

در Deploymentهای فعلی ممکن است مسیر نهایی متفاوت باشد. اصل الزامی، Immutable و Versioned بودن URL است.

### 15.2 Readiness

Mini App Availability فقط وقتی معتبر است که:

- Upload موفق باشد؛
- MIME واقعی تصویر معتبر باشد؛
- ابعاد خوانده شده باشند؛
- فایل قابل Decode باشد؛
- Hash ثبت شده باشد؛
- Preview موفق باشد؛
- وضعیت Media برابر `ready` باشد.

اگر `miniapp_enabled=true` ولی Background آماده نیست، Publish باید Hard Error بدهد.

### 15.3 Preload پویا

در فاز Mini App پویا:

1. API Match باید `background_url` و Version را برگرداند؛
2. Phaser باید Texture را بر اساس Arena ID + Version Load کند؛
3. Loading باید قبل از نمایش Battle کامل شود یا Fallback بصری خنثی نمایش دهد؛
4. Fallback نباید تصویر یک زمین دیگر مثل `city` باشد؛
5. شکست Load باید Telemetry و UI قابل فهم داشته باشد؛
6. Textureهای نسخه قدیمی Match فعال نباید با Version تازه جایگزین شوند.

### 15.4 Telegram

برای Telegram حداقل موارد زیر کافی‌اند:

- `name_fa`؛
- `description_fa`؛
- `emoji`؛
- متن Rule تولیدشده توسط Formatter.

موارد اختیاری:

- `photo_file_id`؛
- `sticker_file_id`؛
- Thumbnail پنل.

نبود تصویر Telegram نباید Arena را غیرفعال کند.

---

## 16. طراحی پنل مدیریت

### 16.1 معماری Navigation

پنل باید Navigation سطح‌بالا داشته باشد:

```text
[ کارت‌ها ] [ زمین‌ها ]
```

تب زمین نباید داخل فرم یک کارت قرار بگیرد؛ Arena موجودیتی مستقل است.

### 16.2 فهرست زمین‌ها

فهرست باید نمایش دهد:

- نام و Emoji؛
- Arena ID؛
- Version Published؛
- وضعیت Draft/Published/Archived؛
- مودهای فعال؛
- Telegram Enabled؛
- Mini App Enabled؛
- وضعیت Media؛
- زمان آخرین انتشار؛
- Warningهای Validation.

فیلترها:

- جستجوی نام/ID؛
- Lifecycle؛
- Mode؛
- Platform؛
- Missing Media؛
- Active Now؛
- Has Draft.

### 16.3 Editor زمین

تب‌های داخل Editor:

1. **اطلاعات پایه**
   - نام فارسی؛
   - نام انگلیسی؛
   - Arena ID؛
   - توضیح؛
   - Emoji؛
   - Tagها.

2. **قوانین مودها**
   - Quick Profile؛
   - Three-round Profile؛
   - Deck Profile؛
   - Enabled و Selection Weight؛
   - Active Window.

3. **رسانه و پلتفرم‌ها**
   - Telegram Enabled؛
   - Mini App Enabled؛
   - Upload Background؛
   - Preview؛
   - وضعیت Readiness.

4. **بررسی و انتشار**
   - Errorها؛
   - Warningها؛
   - Dependencyها؛
   - Diff با Published Version؛
   - Preview تلگرام؛
   - Simulation؛
   - Publish.

5. **تاریخچه**
   - Versionها؛
   - Actor؛
   - زمان؛
   - Diff؛
   - Rollback as New Draft.

### 16.4 Rule Builder

Rule Builder باید کنترل‌های ساختاریافته داشته باشد. مثال Quick:

```text
اگر نوع کارت [Power]
ویژگی [Power]
به اندازه [+2]
تغییر کند
```

ادمین نباید JSON تایپ کند.

### 16.5 Preview و Simulation

پنل باید بتواند:

- متن Telegram را دقیقاً مثل Bot نمایش دهد؛
- Background Mini App را با Safe Zone نمایش دهد؛
- روی یک کارت انتخابی، مقدار قبل/بعد هر Stat را نشان دهد؛
- Breakdown Effectها را نمایش دهد؛
- نشان دهد کدام Ability یا Passive غیرفعال است؛
- برای Deck، Trait Rank و Compare Stat را نمایش دهد.

Preview جای تست Backend را نمی‌گیرد.

### 16.6 Concurrency پنل

اگر دو ادمین هم‌زمان Draft را ویرایش کنند، Last Write Wins خام پذیرفته نیست.

راه‌حل پیشنهادی:

- ارسال `draft_revision` یا `updated_at` با Update؛
- رد درخواست قدیمی با HTTP 409؛
- نمایش پیام «این Draft توسط فرد دیگری تغییر کرده است»؛
- Reload و Diff قبل از Overwrite.

---

## 17. API پیشنهادی پنل

Prefix باید با ساختار نهایی Deployment هماهنگ شود. قرارداد مفهومی:

### 17.1 Query

```text
GET /api/arenas
GET /api/arenas/{arena_id}
GET /api/arenas/{arena_id}/versions
GET /api/arenas/{arena_id}/dependencies
GET /api/arenas/{arena_id}/preview?mode=quick&platform=telegram
```

### 17.2 Mutation

```text
POST /api/arenas
PUT  /api/arenas/{arena_id}/draft
POST /api/arenas/{arena_id}/validate
POST /api/arenas/{arena_id}/publish
POST /api/arenas/{arena_id}/archive
POST /api/arenas/{arena_id}/restore
POST /api/arenas/{arena_id}/versions/{version}/clone-as-draft
POST /api/arenas/{arena_id}/media
DELETE /api/arenas/{arena_id}/draft
```

### 17.3 پاسخ خطا

خطاهای Validation باید ساختاریافته باشند:

```json
{
  "success": false,
  "error": "arena_validation_failed",
  "issues": [
    {
      "severity": "error",
      "path": "profiles.quick.disabled_stats",
      "code": "all_stats_disabled",
      "message_fa": "حداقل یک ویژگی باید قابل انتخاب بماند."
    }
  ]
}
```

کدهای مهم:

- `arena_not_found`؛
- `arena_id_invalid`؛
- `arena_id_locked`؛
- `draft_conflict`؛
- `draft_not_found`؛
- `arena_validation_failed`؛
- `miniapp_media_not_ready`؛
- `arena_has_dependencies`؛
- `arena_already_archived`؛
- `unauthorized_admin`؛
- `invalid_mode_profile`؛
- `published_version_immutable`.

### 17.4 Auth و Audit

تمام Mutationها باید:

- احراز هویت ادمین داشته باشند؛
- Actor ID معتبر استخراج کنند؛
- Audit Log بنویسند؛
- Request ID داشته باشند؛
- در صورت استفاده از Cookie، CSRF Protection داشته باشند؛
- محدودیت Upload و Rate Limit مناسب داشته باشند.

اگر Auth در Reverse Proxy انجام می‌شود، Backend باید Header مورد اعتماد را فقط از Proxy امن بپذیرد و دسترسی مستقیم به سرویس محدود باشد.

---

## 18. API و قرارداد Mini App

Mini App نباید فهرست ثابت تصاویر را منبع حقیقت بداند.

در فاز پویا یکی از این دو الگو قابل قبول است:

### الگوی پیشنهادی: Arena داخل Match Snapshot

هر پاسخ Match اطلاعات لازم را برگرداند:

```json
{
  "arena": {
    "arena_id": "forest",
    "version": 4,
    "name_fa": "جنگل باستانی",
    "emoji": "🌲",
    "background_url": "/miniapp-assets/arena-backgrounds/forest/v4-abc.webp",
    "rules_summary": "هوش +1، محبوبیت -1"
  }
}
```

مزیت: Match همیشه Asset Version درست را دریافت می‌کند.

### Manifest اختیاری

برای Preload یا Cache:

```text
GET /api/v1/arenas/manifest?mode=quick
```

پاسخ باید ETag یا Version Token داشته باشد. Manifest جای Snapshot Match را نمی‌گیرد.

---

## 19. Dependency Management

زمین ممکن است توسط این موارد Refer شود:

- Passive کارت با شرط Arena؛
- Match فعال؛
- تاریخچه Match؛
- Event یا Rotation؛
- Ability تغییر زمین؛
- تنظیمات Mini App؛
- تست یا Seed داخلی.

پیش از Archive یا تغییر مهم، پنل باید Dependency Summary نمایش دهد.

### 19.1 Passive کارت

اعتبارسنجی Passive نباید دیگر `QUICK_ARENAS` ثابت را بخواند. باید از Registry، Arenaهای معتبر Profile مربوط به Quick را دریافت کند.

قواعد:

- Passive می‌تواند به Arena Published یا Draft موجود اشاره کند؛
- انتشار کارت با Passive وابسته به Arena ناموجود ممنوع است؛
- Archive زمین باید Warning جدی برای Passiveهای وابسته ایجاد کند؛
- Archive می‌تواند مجاز باشد، اما Dependencyها باید در پنل قابل مشاهده باشند؛
- حذف Draft وابسته باید رد شود یا ابتدا Reference اصلاح شود.

### 19.2 تغییر نام

- تغییر `name_fa` Dependencyها را نمی‌شکند؛
- تغییر `arena_id` پس از Publish ممنوع است؛
- Clone یک ID جدید می‌سازد و Referenceها خودکار منتقل نمی‌شوند.

---

## 20. Migration زمین‌های موجود

Migration باید رفتار کنونی را دقیقاً Seed کند.

### 20.1 Seed خانواده سه‌راندی

از `systems/battle_system_3rounds.py`:

- `power_arena`؛
- `speed_track`؛
- `thinking_room`؛
- `stage`.

فیلدهای زیر عیناً منتقل شوند:

- نام فارسی و انگلیسی؛
- Emoji؛
- `boost_stat`؛
- `boost_amount`؛
- `compare_stat`؛
- `trait_ranks`.

هیچ عددی در Migration تغییر نکند.

### 20.2 Seed خانواده Quick

از `systems/game_mode_system.py`:

- `city`؛
- `desert`؛
- `ice`؛
- `forest`؛
- `silent_temple`؛
- `null_zone`.

این موارد عیناً منتقل شوند:

- Name؛
- Emoji؛
- Effectها؛
- `disabled_stats`؛
- `abilities_enabled`؛
- `passives_enabled`.

### 20.3 تعریف قدیمی `arena_system.py`

این فایل با چهار زمین هم‌نام سه‌راندی ولی Boost متفاوت `+1` تعارض تاریخی دارد.

قبل از حذف یا تبدیل آن باید Usage واقعی دوباره بررسی شود. تصمیم پیش‌فرض:

- آن را منبع Runtime جدید ندانیم؛
- تست‌های Legacy را به Adapter منتقل کنیم؛
- رفتار Production سه‌راندی را از `battle_system_3rounds.py` Seed کنیم؛
- تا تأیید نبود Consumer ناشناخته، فایل را حذف نکنیم.

### 20.4 تصاویر موجود

ده تصویر فعلی Mini App باید به Version نخست Arena متناظر متصل شوند. در اولین Rollout می‌توان URL قدیمی را حفظ کرد، اما Media Record باید Hash و Readiness داشته باشد.

### 20.5 Idempotency

Seed Migration باید:

- اجرای دوباره را تحمل کند؛
- Version تکراری نسازد؛
- Published Version موجود را بی‌اجازه Overwrite نکند؛
- اختلاف Seed و DB را Report کند؛
- در حالت Dry Run قابل اجرا باشد؛
- تعداد رکوردهای ایجاد/رد/متفاوت را چاپ کند.

---

## 21. Compatibility Strategy

تغییر نباید Big Bang باشد.

### 21.1 Adapter

در دوره انتقال، Adapter می‌تواند شکل Registry را به شکل مورد انتظار کد قدیمی تبدیل کند:

- برای سه‌راندی: Dict مشابه `ARENAS`؛
- برای Quick: List/Dict مشابه `QUICK_ARENAS`؛
- برای Frontend: Manifest مشابه `ARENA_ASSETS`.

### 21.2 Shadow Read

پیش از تغییر Runtime:

1. انتخاب زمین با سیستم قدیمی انجام شود؛
2. Registry همان Arena را بخواند؛
3. Snapshotها مقایسه شوند؛
4. اختلاف Log شود؛
5. نتیجه Match همچنان از سیستم قدیمی باشد.

بعد از صفرشدن اختلاف‌های Seed، Feature Flag تغییر کند.

### 21.3 Feature Flagهای پیشنهادی

```text
ARENA_REGISTRY_READS
ARENA_REGISTRY_SHADOW_COMPARE
ARENA_ADMIN_WRITES
ARENA_DYNAMIC_MINIAPP_MEDIA
```

نام نهایی باید با Convention تنظیمات پروژه هماهنگ شود.

### 21.4 حذف کد قدیمی

ثابت‌های قدیمی فقط وقتی حذف شوند که:

- تمام Consumerها به Registry منتقل شده باشند؛
- حداقل دو Release پایدار گذشته باشد؛
- تست Regression کامل باشد؛
- Rollback دیگر به ثابت‌ها وابسته نباشد؛
- Graphify هیچ Usage Runtime باقی‌مانده نشان ندهد.

---

## 22. Validation

Validation دو سطح دارد.

### 22.1 Hard Error

مواردی که Publish را متوقف می‌کنند:

- Arena ID نامعتبر یا تکراری؛
- نام فارسی خالی؛
- Profile فعال بدون Rule معتبر؛
- Selection Weight خارج از محدوده؛
- `active_until <= active_from`؛
- Stat نامعتبر؛
- Delta خارج از محدوده؛
- غیرفعال‌شدن تمام Statها؛
- Trait تکراری در چند Rank؛
- Mini App فعال بدون Background Ready؛
- Media نامعتبر یا مسیر ناامن؛
- Reference به Arena/Rule ناشناخته؛
- Version Conflict؛
- تلاش برای ویرایش Published Version؛
- نبود حداقل یک Platform فعال در صورت Published فعال.

### 22.2 Warning

مواردی که نیازمند تأیید آگاهانه‌اند:

- Weight بسیار بیشتر از میانگین Pool؛
- Effectهای عمدتاً منفی؛
- Arena بدون توضیح انگلیسی؛
- Arena بدون Telegram Image؛
- Archive زمینی که Passive وابسته دارد؛
- Profile Deck بدون Trait Rank؛
- Arena زمان‌دار با بازه بسیار کوتاه؛
- تغییر شدید Boost نسبت به Version Published؛
- فعال‌شدن بیش از تعداد توصیه‌شده Arena در یک Pool؛
- زمین جدید بدون Test Fixture.

### 22.3 Balance Diff

قبل از Publish، پنل باید اختلاف Rule با Published Version را خلاصه کند:

```text
boost_amount: 8 -> 12
abilities_enabled: true -> false
selection_weight: 100 -> 250
effect[power/power]: +1 -> +3
```

تغییرات عددی بزرگ Warning می‌گیرند؛ Threshold نهایی باید Configurable باشد.

---

## 23. امنیت

از آنجا که Arena روی نتیجه Match اثر می‌گذارد، API زمین بخشی از سطح امنیت Gameplay است.

الزامات:

- Admin Authentication برای تمام Routeها؛
- Authorization مستقل برای Publish/Archive؛
- Audit اجباری؛
- عدم اعتماد به Filename کاربر؛
- بررسی File Signature، نه فقط Extension؛
- محدودیت Size و Dimension؛
- جلوگیری از Path Traversal؛
- جلوگیری از SVG/HTML قابل اجرا در Upload اولیه؛
- عدم پذیرش URL خارجی دلخواه در نسخه اول؛
- CSRF Protection در Auth مبتنی بر Cookie؛
- CORS محدود برای پنل Production؛
- عدم نمایش Stack Trace در پاسخ؛
- Rate Limit برای Upload و Publish؛
- Backup قبل از Migration Production؛
- Queryهای Parameterized؛
- Transaction برای Publish؛
- Actor و Request ID در Log.

Publish باید یک عملیات اتمیک باشد: یا Version، Profileها، Platformها، Media Reference، Current Version و Audit همگی ثبت شوند یا هیچ‌کدام.

---

## 24. Observability و Analytics

حداقل Eventهای پیشنهادی:

| Event | داده‌های کلیدی |
|---|---|
| `arena_selected` | arena_id، version، mode، platform، weight، selection_source |
| `arena_rerolled` | from، to، ability، match_id |
| `arena_match_finished` | arena_id، version، winner، card types، duration |
| `arena_media_failed` | arena_id، version، URL، error |
| `arena_published` | arena_id، version، actor، diff summary |
| `arena_archived` | arena_id، actor، dependencies_count |
| `arena_registry_empty_pool` | mode، platform، timestamp |
| `arena_snapshot_mismatch` | match_id، expected hash، actual hash |

Metricهای آینده:

- Pick Rate؛
- Win Rate بر اساس Card Type؛
- Win Rate هر سمت/نقش؛
- Reroll Rate؛
- Ability Usage در هر زمین؛
- Average Match Duration؛
- Error Rate Media؛
- تعداد Arena فعال هر Pool؛
- اختلاف Win Rate از 50 درصد.

Analytics نباید منطق Match را کند یا Failure آن Match را Fail کند.

---

## 25. تست‌ها

### 25.1 Unit Test Registry

- دریافت Published Version؛
- Draft از Runtime پنهان است؛
- Archived از Active Pool حذف می‌شود؛
- Time Window درست است؛
- Platform Flag درست است؛
- Mini App بدون Media Ready رد می‌شود؛
- Telegram بدون تصویر پذیرفته می‌شود؛
- Weight Selection با RNG تزریقی قابل پیش‌بینی است؛
- Exclude در Reroll رعایت می‌شود؛
- Empty Pool رفتار تعریف‌شده دارد؛
- Cache با Version تازه Invalidate می‌شود؛
- Published Version Immutable است.

### 25.2 Unit Test Rule Validation

- Stat نامعتبر؛
- Delta خارج محدوده؛
- همه Statها Disabled؛
- Duplicate Trait Rank؛
- Mode ناشناخته؛
- Weight صفر/منفی برای Profile فعال؛
- زمان نامعتبر؛
- Effect Type ناشناخته؛
- JSON داخلی خراب؛
- Mini App بدون Background؛
- Arena ID نامعتبر.

### 25.3 Regression سه‌راندی

برای چهار زمین فعلی:

- `boost_stat` برابر قبل؛
- `boost_amount` برابر قبل؛
- Card Type Match برابر قبل؛
- Dominant Attribute برابر قبل؛
- `compare_stat` برابر قبل؛
- Trait Rank برابر قبل؛
- متن انتخاب زمین دارای نام و Emoji درست؛
- Ability تغییر زمین Snapshot تازه می‌گیرد.

### 25.4 Regression Quick

برای شش زمین فعلی:

- Effect هر Card Type برابر قبل؛
- Delta برابر قبل؛
- Disabled Stat برابر قبل؛
- Ability Flag برابر قبل؛
- Passive Flag برابر قبل؛
- Reroll زمین فعلی را Exclude می‌کند؛
- Snapshot API اطلاعات حریف را Leak نمی‌کند؛
- Rule Breakdown برابر رفتار قبلی است.

### 25.5 API Test پنل

- List/Get؛
- Create Draft؛
- Update Draft؛
- Optimistic Conflict؛
- Validate؛
- Publish موفق؛
- Publish نامعتبر؛
- Published Update ممنوع؛
- Archive؛
- Restore با Version جدید؛
- Clone Version؛
- Media Upload معتبر/نامعتبر؛
- Auth/Authorization؛
- Audit Log؛
- Dependency Response؛
- Idempotent Publish Request در صورت طراحی Idempotency Key.

### 25.6 Mini App

- Load تصویر نسخه‌دار؛
- Arena ناشناخته تصویر زمین دیگری نشان نمی‌دهد؛
- Failure تصویر Fallback خنثی دارد؛
- Match قدیمی پس از Publish جدید همان تصویر Version قبلی را می‌بیند؛
- Quick و Solo Arena درست را نمایش می‌دهند؛
- Cache URL بر اساس Version عوض می‌شود؛
- حالت Reduced Motion و صفحه کوچک نمی‌شکند.

### 25.7 Migration Test

- DB خالی؛
- DB Production-like؛
- اجرای Migration دو بار؛
- اختلاف Seed با رکورد موجود؛
- Match قدیمی بدون Version؛
- Match جدید با Snapshot؛
- Rollback Feature Flag؛
- حفظ تمام ده زمین فعلی؛
- عدم تغییر نتیجه Fixtureهای فعلی.

### 25.8 End-to-End Acceptance

سناریوی اصلی:

1. ادمین زمین `storm_city` را Draft می‌کند؛
2. فقط Profile Quick را فعال می‌کند؛
3. Telegram را فعال و Mini App را غیرفعال می‌کند؛
4. Validate و Publish می‌کند؛
5. زمین بدون Restart طولانی وارد Pool Telegram می‌شود؛
6. یک Match با Snapshot Version 1 شروع می‌شود؛
7. ادمین Boost را در Draft Version 2 تغییر و Publish می‌کند؛
8. Match قبلی همچنان Version 1 را استفاده می‌کند؛
9. Match تازه Version 2 را می‌گیرد؛
10. تصویر Mini App آپلود و Version 3 منتشر می‌شود؛
11. از Version 3 به بعد Mini App نیز زمین را انتخاب می‌کند؛
12. Archive، Matchهای تازه را متوقف می‌کند ولی History و Matchهای فعال سالم می‌مانند.

---

## 26. برنامه فازبندی توسعه

هر فاز باید مستقل Review و Deploy شود.

### فاز 0 — Baseline و تصمیم‌های نهایی

خروجی:

- ثبت Snapshot دقیق ده زمین فعلی؛
- تعیین Consumerهای واقعی `arena_system.py`؛
- ثبت تست‌های Characterization؛
- تعیین Auth واقعی پنل Production؛
- تأیید Mode Familyها؛
- تأیید محدودیت Ruleها و Media؛
- Backup و Runbook Migration.

معیار خروج:

- تست‌ها رفتار فعلی را قفل کرده‌اند؛
- ابهام Balance باقی نمانده است؛
- هیچ کدی هنوز از Registry جدید استفاده نمی‌کند.

### فاز 1 — Schema و Registry Read Model

خروجی:

- Migration جدول‌های Arena؛
- Seed ده Arena موجود؛
- مدل‌ها و Validatorها؛
- Registry Read API داخلی؛
- Snapshot Builder؛
- Unit Testها؛
- بدون تغییر Runtime Production.

معیار خروج:

- Seed با ثابت‌های فعلی برابر است؛
- Migration Idempotent است؛
- Registry می‌تواند Profileها را بخواند؛
- هیچ Matchی هنوز به Registry وابسته نیست.

### فاز 2 — Shadow Read و Match Snapshot

خروجی:

- Shadow Compare؛
- افزودن Version/Snapshot به Matchها؛
- Feature Flagها؛
- Log اختلاف؛
- Backfill سازگار برای Matchهای قدیمی.

معیار خروج:

- اختلاف Rule صفر یا توضیح‌داده‌شده است؛
- Match فعال با Publish مصنوعی تغییر نمی‌کند؛
- Rollback Flag آزمایش شده است.

### فاز 3 — انتقال Runtime تلگرام و موتورهای بازی

ترتیب پیشنهادی:

1. Quick؛
2. سه‌راندی/Solo؛
3. Deck؛
4. Arena Shift/Reroll؛
5. Passive Validation.

معیار خروج:

- تست Regression هر مود سبز؛
- Static Definition دیگر منبع اصلی آن مود نیست؛
- Callbackهای Telegram با IDهای پویا امن هستند؛
- Empty Pool Monitor شده است.

### فاز 4 — پنل مدیریت زمین

خروجی:

- Navigation کارت‌ها/زمین‌ها؛
- CRUD Draft؛
- Rule Builder؛
- Validate/Preview؛
- Publish/Archive؛
- Version History؛
- Auth/Audit؛
- Dependency View.

معیار خروج:

- ادمین می‌تواند زمین Telegram-only بسازد؛
- Published Version مستقیم قابل ویرایش نیست؛
- Conflict هم‌زمان مدیریت می‌شود؛
- Routeهای Mutation محافظت شده‌اند.

### فاز 5 — Media پویا در Mini App

خروجی:

- Upload و Readiness؛
- URL نسخه‌دار؛
- Dynamic Phaser Load؛
- Manifest/Match Contract؛
- Fallback خنثی؛
- Cache/ETag؛
- Visual QA.

معیار خروج:

- Arena تازه بدون Deploy کد Frontend، پس از Upload و Publish قابل نمایش است؛
- Arena بدون Media وارد Pool Mini App نمی‌شود؛
- تصویر اشتباه `city` به‌جای Arena ناشناخته نمایش داده نمی‌شود.

### فاز 6 — Cleanup و Analytics

خروجی:

- حذف Consumerهای ثابت قدیمی؛
- حفظ Adapter فقط در صورت نیاز Migration؛
- Dashboard اولیه Arena؛
- Runbook کامل Rollback؛
- به‌روزرسانی README و اسناد Deployment؛
- Graphify Update نهایی.

معیار خروج:

- Graphify Usage Runtime ثابت‌های قدیمی نشان نمی‌دهد؛
- دو Release پایدار سپری شده است؛
- Metric و Error Alert موجود است.

---

## 27. Rollout Production

ترتیب پیشنهادی Deploy:

1. Backup تأییدشده دیتابیس؛
2. اجرای Migration با Registry Reads خاموش؛
3. اجرای Seed و گزارش Diff؛
4. Deploy Backend با Feature Flag خاموش؛
5. اجرای Smoke Test پنل و Match؛
6. فعال‌کردن Shadow Compare؛
7. بررسی Logها؛
8. فعال‌کردن Registry برای درصد یا مود محدود؛
9. فعال‌کردن کامل Telegram؛
10. فعال‌کردن Admin Writes؛
11. فعال‌کردن Dynamic Mini App پس از Deploy Frontend؛
12. نگهداری کد Compatibility تا عبور از دوره پایدار.

### 27.1 Rollback

Rollback نباید به حذف جدول یا Downgrade داده نیاز داشته باشد.

در صورت مشکل:

1. Feature Flag Runtime به منبع قبلی برگردد؛
2. Admin Writes خاموش شود؛
3. Version مشکل‌دار Archive یا نسخه قبلی Clone و Publish شود؛
4. Matchهای دارای Snapshot ادامه پیدا کنند؛
5. Media Version مشکل‌دار Retire شود؛
6. Audit و Incident Report ثبت شود.

Migrationهای Additive در Rollback باقی می‌مانند.

---

## 28. Risk Register

| ریسک | شدت | کنترل |
|---|---|---|
| تغییر نتیجه Match فعال پس از Publish | بحرانی | Snapshot Immutable |
| زمین بدون تصویر در Mini App | زیاد | Media Readiness Gate |
| Rule نامعتبر از پنل | بحرانی | Whitelist + Validator + Publish Gate |
| دسترسی غیرمجاز به Publish | بحرانی | Auth + Authorization + Audit |
| شکستن Passive کارت با حذف Arena | زیاد | Archive + Dependency View |
| اختلاف Quick و سه‌راندی | زیاد | Mode Profile مستقل زیر Identity مشترک |
| تغییر Balance ناخواسته در Migration | زیاد | Seed Exact + Characterization Tests |
| Cache قدیمی بین Processها | متوسط | Version Token + TTL + Invalidation |
| شلوغ‌شدن انتخاب زمین در Telegram | متوسط | Active Pool/Rotation + Weight |
| طول زیاد Callback Data | متوسط | Arena ID کوتاه و ثابت |
| افزایش شدید ترکیب‌های QA | زیاد | Profile محدود + Test Matrix + Pool محدود |
| Last Write Wins بین دو ادمین | متوسط | Optimistic Concurrency |
| Path Traversal در Upload | بحرانی | Server-generated Path + Signature Check |
| Empty Active Pool | زیاد | Validation + Seed Fallback + Alert |
| تصویر نسخه قدیمی حذف شود | زیاد | Immutable Media Retention |
| حذف زودهنگام ثابت‌های قدیمی | متوسط | Two-release Cleanup Gate |

---

## 29. معیار پذیرش نهایی

سیستم زمانی کامل محسوب می‌شود که همه موارد زیر برقرار باشند:

- [ ] یک Arena Identity مرکزی در دیتابیس وجود دارد.
- [ ] هر Published Arena Version Immutable است.
- [ ] Matchها Arena Snapshot دارند.
- [ ] Quick از Profile مرکزی استفاده می‌کند.
- [ ] سه‌راندی و Solo از Profile مرکزی استفاده می‌کنند.
- [ ] Deck از Profile مرکزی یا قرارداد مستند Adapter استفاده می‌کند.
- [ ] Reroll/Arena Shift Version و Snapshot درست ثبت می‌کند.
- [ ] Passive کارت Arenaهای معتبر را از Registry می‌گیرد.
- [ ] پنل بخش سطح‌بالای زمین‌ها دارد.
- [ ] ساخت Draft، Validate، Publish، Archive و Rollback قابل انجام است.
- [ ] Published Arena قابل Hard Delete نیست.
- [ ] Telegram بدون تصویر می‌تواند زمین را اجرا کند.
- [ ] Mini App بدون Background Ready زمین را انتخاب نمی‌کند.
- [ ] Mini App تصویر Version درست را Load می‌کند.
- [ ] Arena ناشناخته به تصویر Arena دیگری تبدیل نمی‌شود.
- [ ] Upload امن و Versioned است.
- [ ] Mutationهای پنل Auth و Audit دارند.
- [ ] Migration ده Arena فعلی را بدون تغییر Balance منتقل کرده است.
- [ ] Migration دوباره قابل اجراست.
- [ ] تست‌های Regression فعلی پاس می‌شوند.
- [ ] تست Snapshot ثابت می‌کند Publish جدید Match فعال را تغییر نمی‌دهد.
- [ ] Empty Pool Alert دارد.
- [ ] Rollback با Feature Flag آزمایش شده است.
- [ ] مستندات Deployment و README به‌روزرسانی شده‌اند.
- [ ] `graphify update .` پس از تغییرات اجرا شده است.

---

## 30. فایل‌های محتمل درگیر

این فهرست راهنماست و قبل از هر فاز باید دوباره با Graphify و Source بررسی شود.

| فایل/بخش | نقش احتمالی |
|---|---|
| `systems/arena_system.py` | Legacy Arena و Adapter/Retirement |
| `systems/battle_system_3rounds.py` | انتقال ARENAS و Snapshot-based Resolve |
| `systems/game_mode_system.py` | انتقال QUICK_ARENAS و انتخاب/Reroll |
| `core/database.py` | Schema/Migration/Repository |
| `bot/handlers/battle.py` | انتخاب زمین، Callback، Arena Shift، نمایش |
| `bot/handlers/game_modes.py` | متن و نمایش Quick Arena |
| `web/miniapp_api.py` | Arena Snapshot و Media URL برای Mini App |
| `web/web_api.py` | Admin Arena API، Validation و Upload |
| `web/card_management.html` | Navigation و UI پنل زمین |
| `frontend/game/src/BattleScene.ts` | Dynamic Arena Texture Loading |
| `frontend/game/src/api.ts` | Typeهای Arena Contract |
| `frontend/game/public/arena-backgrounds/` | Media فعلی و Migration Assets |
| `tests/test_arena_ui.py` | Legacy Characterization |
| `tests/test_battle_depth.py` | Regression سه‌راندی |
| `tests/test_game_mode_system.py` | Regression Quick |
| `tests/test_miniapp_quick_api.py` | Arena Snapshot/API Quick |
| `tests/test_card_effects.py` | Arena Shift و Effectها |
| `tests/test_card_admin_api.py` | الگوی تست API پنل |

فایل‌های جدید احتمالی:

```text
systems/arena_registry.py
systems/arena_validation.py
migrations/migrate_arena_registry.py
tests/test_arena_registry.py
tests/test_arena_admin_api.py
tests/test_arena_migration.py
tests/test_arena_match_snapshot.py
```

AI نباید صرفاً چون این نام‌ها پیشنهاد شده‌اند، بدون بررسی Convention پروژه همه را بسازد.

---

## 31. تصمیم‌هایی که قبل از شروع فاز 0 باید تأیید شوند

مقادیر زیر Default پیشنهادی دارند، اما مالک محصول می‌تواند آن‌ها را تغییر دهد:

| تصمیم | Default پیشنهادی |
|---|---|
| خانواده مودها | `quick`, `three_round`, `deck` |
| حداکثر طول Arena ID | 24 کاراکتر |
| Pool فعال پیشنهادی | 4 تا 8 Arena برای هر مود/فصل |
| محدوده Weight | 1 تا 1000 |
| Delta Quick | -10 تا +10 |
| Boost سه‌راندی | 0 تا 30 |
| Mini App بدون تصویر | غیرقابل انتشار/فعال‌سازی |
| Telegram بدون تصویر | مجاز |
| ذخیره زمان | UTC؛ نمایش تهران |
| Published Delete | ممنوع، فقط Archive |
| Published Edit | ممنوع، فقط Draft Version جدید |
| Dynamic Mini App | فاز جدا پس از Telegram |
| External Media URL | در نسخه اول ممنوع |
| Rule JSON آزاد | ممنوع |

مواردی که باید پیش از Coding مشخص شوند:

- Auth واقعی پنل روی VPS چیست؟
- آیا Admin ID از Telegram، Reverse Proxy یا Login مستقل می‌آید؟
- آیا `deck` در نسخه اول Profile مستقل می‌گیرد یا Adapter سه‌راندی کافی است؟
- آیا Event Scheduler بخشی از نسخه اول است یا فقط ستون‌های زمان‌بندی ایجاد می‌شوند؟
- آیا Rollback از UI در نسخه اول لازم است یا Clone Version از API کافی است؟
- آیا پردازش تصویر روی سرور انجام می‌شود یا فقط WebP استاندارد پذیرفته می‌شود؟

---

## 32. Template اجرای هر فاز توسط AI

AI در ابتدای هر فاز باید این قالب را تکمیل کند:

```text
فاز درخواستی:
هدف:
فایل‌های درگیر طبق Graphify:
رفتار فعلی که باید حفظ شود:
Migration مورد نیاز:
Feature Flag:
تست‌های قبل از تغییر:
تست‌های جدید:
ریسک‌های فاز:
Rollback:
موارد خارج از دامنه:
```

در پایان هر فاز گزارش باید شامل این موارد باشد:

```text
نتیجه:
فایل‌های تغییرکرده:
Migration اجراشده/نشده:
تست‌های اجراشده و نتیجه:
رفتارهای عمداً تغییرکرده:
رفتارهای حفظ‌شده:
Feature Flag و وضعیت آن:
Rollback آزمایش‌شده:
Graphify update status:
کارهای باقی‌مانده در همین فاز:
```

تا وقتی «کارهای باقی‌مانده در همین فاز» خالی نشده، فاز Complete محسوب نمی‌شود.

---

## 33. سناریوهای ممنوع برای AI

AI نباید:

- تمام تعریف‌های فعلی را یک‌باره حذف کند؛
- مقدار Boostهای فعلی را به بهانه یکپارچه‌سازی تغییر دهد؛
- Arena IDهای فعلی را Rename کند؛
- Match فعال را مجبور به خواندن آخرین Version کند؛
- نبود تصویر را با تصویر یک Arena دیگر پنهان کند؛
- Published Row را Update in place کند؛
- JSON خام را مستقیماً از پنل به موتور نبرد بفرستد؛
- Media Path ورودی کاربر را مستقیم ذخیره کند؛
- Auth پنل را به‌دلیل «داخلی بودن» حذف کند؛
- Archive را معادل Delete پیاده کند؛
- Cache را بدون Version Key بسازد؛
- تست‌های Legacy را به‌جای سازگارکردن حذف کند؛
- هم‌زمان با این پروژه اقتصاد، کارت‌ها یا Abilityها را بازطراحی کند؛
- بدون Backup و Feature Flag روی Production مهاجرت Big Bang انجام دهد.

---

## 34. Definition of Ready برای شروع پیاده‌سازی

شروع فاز 1 فقط وقتی مجاز است که:

- [ ] این سند توسط مالک محصول مرور شده باشد.
- [ ] تصمیم‌های بخش 31 مشخص شده باشند.
- [ ] Baseline ده Arena فعلی ثبت شده باشد.
- [ ] Auth پنل Production مشخص شده باشد.
- [ ] Backup و مسیر Restore دیتابیس آزمایش شده باشد.
- [ ] تست‌های Characterization زمین‌ها موجود و سبز باشند.
- [ ] Feature Flag Strategy تأیید شده باشد.
- [ ] دامنه دقیق فاز اول در یک درخواست جدا مشخص شده باشد.

---

## 35. نتیجه نهایی طراحی

Arena Registry باید تفاوت میان سه مفهوم را حفظ کند:

1. **هویت مشترک زمین**؛
2. **قوانین متفاوت هر مود**؛
3. **رسانه و Availability متفاوت هر پلتفرم**.

این جداسازی اجازه می‌دهد یک زمین ابتدا بدون تصویر در Telegram منتشر شود و بعد، پس از آماده‌شدن Background و Preview، در Mini App نیز فعال شود. Version و Snapshot تضمین می‌کنند تغییرات پنل نتیجه Matchهای در حال اجرا را عوض نکنند. Draft/Publish/Archive، Validator محدود، Auth، Audit و Rollback نیز تبدیل پنل زمین از یک فرم ساده به ابزار امن LiveOps را ممکن می‌کنند.

این پروژه باید مرحله‌ای انجام شود: ابتدا ثبت رفتار موجود و Registry خواندنی، سپس Snapshot و Shadow Read، بعد انتقال Runtime تلگرام، سپس پنل و در نهایت Media پویا در Mini App. هر مسیر دیگری که از همان ابتدا همه Consumerها و تصاویر را یک‌باره پویا کند، ریسک Regression و Rollback را بی‌دلیل بالا می‌برد.

---

## 36. منابع کد فعلی برای بازبینی هنگام اجرا

- `systems/arena_system.py`
- `systems/battle_system_3rounds.py`
- `systems/game_mode_system.py`
- `bot/handlers/battle.py`
- `bot/handlers/game_modes.py`
- `core/database.py`
- `web/web_api.py`
- `web/card_management.html`
- `web/miniapp_api.py`
- `frontend/game/src/BattleScene.ts`
- `frontend/game/src/api.ts`
- `tests/test_arena_ui.py`
- `tests/test_battle_depth.py`
- `tests/test_game_mode_system.py`
- `tests/test_miniapp_quick_api.py`
- `tests/test_card_effects.py`

> این مسیرها بر اساس وضعیت پروژه در تاریخ این سند هستند. قبل از اجرا باید با Graphify دوباره بررسی شوند.

