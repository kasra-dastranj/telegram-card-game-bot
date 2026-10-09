# فاز اول: زیرساخت مشترک کارت و مسابقه

## ممیزی پیش از تغییر

این کار فقط زیرساخت است؛ اقتصاد جدید و ساخت/خرید/توزیع کارت سفارشی اجرا نمی‌شوند.

| مسیر واقعی | انتخاب و اعتبارسنجی | حل و ثبت نتیجه |
|---|---|---|
| Quick بات و Mini App | `GameModeSystem`؛ normal/random روش انتخاب هستند | `resolve_quick` → `MatchRewardsSystem` |
| سه‌راوندی Mini App | `MiniThreeRoundSystem.choose_card` | همان سیستم → `MatchRewardsSystem` |
| PvP قدیمی/سه‌راوندی بات | `bot/handlers/pvp.py`، `battle.py`، `DatabaseManager` | `core/game_logic.py` و `LegacyFightRewardsSystem` |
| Deck بات | `DeckSystem` و `game_modes.py` | مسیر battle و ledger قدیمی PvP |
| Easy | `GameModeSystem`؛ گزینه‌های trait/series و انتخاب از گزینه‌ها | `resolve_easy_round` → `MatchRewardsSystem` |
| تمرین ASO در Mini App | `web/miniapp_api.py` و `ai_opponent.py`؛ مسیر مستقل solo در handlerهای بات پیدا نشد | solo settlement؛ رفتار فعلی واقعاً پاداش و کسر قلب دارد |
| Risk | `RiskModeSystem`؛ انتخاب تصادفی از تعریف کارت‌ها | escrow و `_settle` → ledger مشترک |

نقشهٔ وابستگی: `cards` → `card_variants` + `player_cards`/`player_card_stacks` → انتخاب دستی/تصادفی → اعتبارسنجی مود → settlement → `players`/`player_progression` → `fight_history`/`card_missions` → آمار و leaderboard.

تعریف کارت واحد و مالکیت چند کاربر از قبل وجود دارد؛ برای هر دریافت‌کننده تعریف یا تصویر جدید لازم نیست. Rare و rarity_override بُعد فرم هستند و نباید origin را عوض کنند.

مسیرهای اقتصادی: Claim در `claim_system.py` و `player_rewards_system.py`، کارت شروع در `starter_cards_system.py`، اعطای موجودی در `card_inventory_system.py`، upgrade در `card_upgrade_system.py`، fusion در `fusion_system.py`، فروش Rare در `rare_cards_system.py`، قیمت/Mining/تبدیل امتیاز در `economy_system.py`، مأموریت کارت در `card_missions_system.py`. مسیر اجرایی مستقلی برای Wheel یا Auction/Trade در ممیزی پیدا نشد؛ قبل از افزودنشان باید قرارداد official-only وصل شود.

نقاط خطر: نام PvP هم برای مسیر تک‌راوندی و هم Deck/سه‌راوندی استفاده شده؛ variant فعلی Quick به معنای Friendly نیست؛ چند handler قدیمی تکراری است؛ Random Risk از کل تعریف‌ها انتخاب می‌کند؛ projectionهای SQL ممکن است origin را گم کنند؛ history و mission اکنون فرض رقابتی دارند. Ledgerهای `match_reward_events` و `fight_reward_settlements` موجودند؛ جایگزینی آنها در این فاز لازم نیست.

## اختلاف‌های فعلی با طراحی آینده

Easy فعلی با حداقل دو بازیکن شروع می‌شود و سیاست پرداختش با قرارداد پنج بازیکن/رتبه‌های ۱–۳ یکسان نیست. تمرین فعلی پاداش دارد و ممکن است قلب کم کند. این رفتارها در فاز اول حفظ می‌شوند. قرارداد آینده جدا آزموده می‌شود؛ فعال‌سازی آن به دستور فاز دوم نیاز دارد.

## حدود آزمون داده

migration فقط روی دیتابیس‌های موقت با رکوردهای نماینده آزموده می‌شود. دریافت دادهٔ تولیدی مجاز نیست. آزمون کپی واقعی، بررسی bootstrap و انتشار بر عهدهٔ مسیر بازبینی مالک است؛ نتیجهٔ آزمایش محلی به معنی تأیید انتشار نیست.

## قرارداد آماده‌شده

`systems/shared_foundation.py` مرجع مشترک است:

- `MatchContext` ثابت و JSON قابل ذخیره، با version=1، mode، variant، selection_variant، allow_custom_cards، policy_version و snapshot تنظیمات عددی.
- `bind_context` هویت را در transaction ساخت ذخیره می‌کند و تغییر دوبارهٔ آن را رد می‌کند. `context_in` برای match قدیمی فاقد context از رکورد سرور fallback می‌سازد؛ source گروه/PV/invite هرگز Friendly را تعیین نمی‌کند.
- `is_card_eligible` و `require_card_in` منشأ کارت را بررسی می‌کنند؛ دومی از SQLite تازه می‌خواند تا cache یا rarity_override باعث عبور اشتباه نشود. `eligible_cards` همان سیاست را به pool تصادفی وصل می‌کند.
- `economic_card_eligible`/`economic_card_in` تنها official را در مسیرهای Claim، اعطا/مصرف اقتصادی موجودی، upgrade، fusion، Rare shop و مأموریت کارت قبول می‌کنند. custom حتی با rarity رسمی وارد این مسیرها نمی‌شود.
- `future_settlement_policy` و `project_future_award` فقط قرارداد/preview آینده‌اند؛ به writer زنده وصل نشده‌اند. eligibility پاداش، پیشرفت رقابتی و کسر قلب مستقل هستند. Risk قلب نامشخص (`None`) و سیاست مستقل دارد، و در preview امتیاز رقابتی نمی‌گیرد.
- `MatchRewardsSystem.award` هویت ذخیره‌شده و سازگاری مود را کنترل می‌کند. mode قدیمی `pvp` می‌تواند ledger یک Deck/Three-Round معتبر باشد؛ mode دلخواه دیگر رد می‌شود. writer فعلی context Friendly/future_v2 را رد می‌کند تا بدون یکپارچه‌سازی فاز دوم، history رقابتی یا پاداش ناخواسته نسازد.

کلیدهای context با ledger موجود هماهنگ‌اند: request_id برای Quick/Mini/Easy، `fight:<id>` برای active_fights، `solo:<id>` برای تمرین و `risk:<id>` برای Risk. ledgerهای فعلی حفظ شده‌اند؛ جدول پرداخت موازی ساخته نشده است. Retry همان پرداخت قبلی را برمی‌گرداند. تغییر قیمت یا جدول XP انجام نشده است.

مسیر قدیمی PvP بات چند رفتار و callback تک‌راوندی/سه‌راوندی/انتخاب Deck را در یک ورودی دارد؛ context جدید آن صریحاً `legacy_pvp/competitive` است. ورودی مستقل Deck context=deck دارد. برای بازی قدیمی بدون context، وجود battle_states یا deck_id کمک می‌کند مود واقعی شناسایی شود. حذف/بازنام‌گذاری مسیر Legacy و جداسازی کامل ورودی‌هایش کار فاز دوم است؛ حالت رقابتی و ممنوعیت Custom آن همین حالا مشخص‌اند.

### Schema افزایشی

| محل | تغییر |
|---|---|
| cards | `origin TEXT NOT NULL DEFAULT 'official' CHECK(origin IN ('official','custom'))` |
| foundation_settings | `key PRIMARY KEY`, `value_json`؛ تنظیمات مشترک با نوع معتبر |
| match_contexts | `match_key PRIMARY KEY`, `context_json`, `created_at` |

هیچ backfill مالکیت/فرم/rarity/stats/موجودی/موجودی سکه/قلب/نتیجهٔ بازی وجود ندارد. بازی‌های جاری یکجا تبدیل نمی‌شوند. یک card_id در تعریف کارت و چند player_cards برای دریافت‌کنندگان، پایهٔ مدل آینده است؛ مجوز ادمین/تخصیص/پرداخت واقعی هنوز پیاده نشده است. `add_card` و grant اقتصادی فعلی مسیر ساخت/اعطای Custom نیستند.

### Flag و تنظیمات

چهار flag در `foundation_settings` با JSON boolean **false** درج می‌شوند؛ اجرای دوباره مقدار موجود را بازنویسی نمی‌کند:

```text
custom_cards_enabled=false
quick_friendly_enabled=false
easy_custom_cards_enabled=false
progression_v2_enabled=false
```

اعداد قرارداد آینده در همان جدول: `friendly_loss_hearts=1`، `competitive_loss_hearts=1`، `easy_min_qualified_players=5`. این اعداد در context مسابقه snapshot می‌شوند؛ تغییرشان وسط match هویت/سیاست آن را عوض نمی‌کند. flag و policy_version از payload کاربر خوانده نمی‌شوند. در این فاز هیچ endpoint یا گزینهٔ UI برای فعال‌سازی وجود ندارد؛ روشن‌کردن flag به‌تنهایی اجرای اقتصاد جدید نیست و مجاز نشده است.

### ماتریس آینده؛ تست قرارداد، نه قابلیت فعال

| مود/variant | Custom با flagهای آینده | پاداش/پیشرفت رقابتی | قلب بازنده |
|---|---|---|---|
| Quick competitive | ممنوع | سیاست رقابتی | ۱ |
| Quick friendly | مجاز | صفر XP/Score/Coin/TP و پیشرفت | ۱؛ win/tie صفر |
| Three-Round / Deck | ممنوع | سیاست رقابتی | ۱ |
| Easy competitive | فقط با allow_custom_cards سازنده | همان سیاست Easy؛ حداقل ۵ ID واقعی و واجدشرایط متمایز | صفر |
| Practice | مجاز | صفر | صفر |
| Risk | ممنوع | مستقل؛ Score صفر | نامشخص؛ تغییر نمی‌کند |

خود caller باید واقعی‌بودن/واجدشرایط‌بودن بازیکنان Easy را سمت سرور بررسی کند؛ client حق ارسال تعداد واجدشرایط را ندارد. تشخیص رتبه‌های ۱–۳ و قواعد disconnect/tie در preview پیاده نشده و به فاز دوم مربوط است.

## اجرای migration؛ فقط مسیر بازبینی مالک

برای محیط آزمایشی، از ریشهٔ نسخهٔ دقیق بازبینی‌شده:

```powershell
.\.venv\Scripts\python.exe migrations/migrate_shared_foundation.py --database PATH_TO_TEST_DB --preview-copy PATH_TO_NEW_PREVIEW_DB
.\.venv\Scripts\python.exe migrations/migrate_shared_foundation.py --database PATH_TO_TEST_DB --apply --backup PATH_TO_NEW_BACKUP_DB
```

کپی و backup با SQLite backup API و quick_check گرفته می‌شوند؛ destination موجود بازنویسی نمی‌شود. `--apply` بدون backup جدید پذیرفته نیست. schema در transaction افزایشی و idempotent ساخته می‌شود. preview دیتابیس مبدأ را تغییر نمی‌دهد. restore خودکار وجود ندارد.

دستور زیر **اینجا اجرا نشده است**؛ مالک پس از بازبینی کد/CI، فقط روی VPS و از ریشهٔ clone همان commit اجرا کند. کپی واقعی روی خود سرور می‌ماند، به GitHub یا دستگاه همکار منتقل نمی‌شود. قفل مشترک انتشار حفظ می‌شود:

```bash
sudo flock -x /opt/telbattle/deploy.lock bash -s -- "$PWD" <<'FOUNDATION_MIGRATION'
set -euo pipefail
umask 077
cd "$1"
stamp="$(date -u +%Y%m%dT%H%M%S)-$$"
/opt/telbattle/venv/bin/python migrations/migrate_shared_foundation.py \
  --database /opt/telbattle/shared/game_bot.db \
  --preview-copy "/opt/telbattle/backups/foundation-preview-$stamp.db"
# مالک پیش از apply، نتیجهٔ preview و سازگاری نسخهٔ قبلی با schema افزایشی را بررسی کند.
trap 'systemctl start telbattle-bot telbattle-api telbattle-admin' EXIT
systemctl stop telbattle-bot telbattle-api telbattle-admin
/opt/telbattle/venv/bin/python migrations/migrate_shared_foundation.py \
  --database /opt/telbattle/shared/game_bot.db \
  --apply --backup "/opt/telbattle/backups/before-foundation-$stamp.db"
systemctl start telbattle-bot telbattle-api telbattle-admin
trap - EXIT
systemctl is-active telbattle-bot telbattle-api telbattle-admin
FOUNDATION_MIGRATION
```

Actions همچنان قرارداد no-change دارد؛ تا آماده‌سازی schema، startup روی کپی تغییر می‌کند و preflight انتشار را رد می‌کند. helper انتشار تغییر نکرده است. bootstrap Actions و migration Trait نیز پیش‌نیازهای مستقل قبلی‌اند. پس از migration و تأیید مالک، از فرایند عادی PR → CI → main → Deploy دستی استفاده شود.

Rollback کد: نسخهٔ قبلی می‌تواند column/tableهای افزایشی را نادیده بگیرد؛ آنها را حذف نکنید. حذف origin یا restore DB پس از بازشدن بازی‌ها ممکن است اطلاعات جدید را از بین ببرد و جزو rollback خودکار نیست. بکاپ صرفاً برای بررسی مالک نگه داشته می‌شود.

## راه اتصال فاز دوم و سوم

1. ابتدا سند اقتصاد قبلی را با اصلاح‌های قطعی زیر یکپارچه کنید؛ هنوز آن سند در این درخواست ارائه نشده است.
2. شماره policy جدید را فقط در ساخت match جدید ثبت کنید؛ بازی‌های legacy_v1 با writer فعلی تمام شوند. برای ورودی‌های Legacy/PvP تفکیک دقیق mode را قبل از فعال‌سازی اقتصاد مشخص کنید.
3. `future_settlement_policy` eligibility را می‌دهد، نه مقدار XP/Coin و رتبه. مقدارها از Config/Admin نسخهٔ جدید بیایند. تعداد بازیکنان واقعی Easy و validity سمت سرور ساخته شوند.
4. writer جدید باید `ranked_progress` را به همهٔ history، leaderboard، mission و achievement writers وصل کند؛ Friendly صرفاً XP صفر در fight_history قدیمی نیست. تاریخچهٔ debug جدا طراحی شود. تست فعلی فقط قرارداد و جلوگیری از writer اشتباه را ثابت می‌کند، E2E یک Friendly فعال نیست.
5. همان کلید ledger و transaction اتمیک نگه داشته شود؛ Retry/Restart نباید دوباره پرداخت یا کسر قلب کند. سیاست Risk تا تصمیم مستقل تغییر نکند.
6. فاز سوم مجوز دریافت‌کنندگان، کنترل Stats، پرداخت بیرونی و UI را جدا پیاده کند؛ برای ساخت/اعطای Custom از grant اقتصادی استفاده نکند. گزینه‌های Easy و pool سؤال‌های trait/series نیز باید context سازنده را همراه داشته باشند. فعلاً همهٔ UIهای جدید غایب‌اند.
7. Wheel، Sell-to-System و Trade/Auction آینده و collection achievements باید از قرارداد official-only استفاده کنند. Mining/Score Conversion فعلی حذف یا بازنویسی نشده‌اند.

اصلاح‌های قطعی برای فاز دوم که **الان اجرا نشده‌اند**: Silver Ticket هفتگی ۱۰۰/۲۰۰/۴۰۰/۸۰۰… و ریست هفتگی؛ Permanent Heart خرید اول ۱۰۰ و هر بار ×۲ با سقف ۲۰؛ refill کامل روزانه ۱۰۰ و هر بار ×۲ با ریست روزانه؛ قیمت Coin مستقل و قابل تنظیم برای هر Skin. Easy با Custom پاداش عادی دارد؛ Friendly پاداش ندارد ولی بازنده قلب کم می‌کند.

OPEN QUESTION: قیمت پول واقعی کارت/دریافت‌کنندگان؛ سقف Stats و بالانس به‌خصوص Easy؛ ورود Friendly با قلب صفر و بازیابی آن؛ tie/disconnect در Easy؛ جایزه‌های سطح ۱۱–۳۰، achievement/clan؛ سیاست قلب و دیگر قواعد Risk. این تصمیم‌ها برای فعال‌کردن مراحل بعد لازم‌اند و در این فاز حدس زده نشده‌اند.

## فهرست تغییرات قابل بازبینی

- `core/models.py`, `core/database.py`: metadata منشأ، projectionهای همهٔ خواندن کارت، schema و context ساخت، کنترل انتخاب PvP/Solo؛ rarity و موجودی حفظ می‌شوند.
- `systems/shared_foundation.py`, `migrations/migrate_shared_foundation.py`: قراردادها، flagها، migration قابل preview و backup.
- `systems/game_mode_system.py`, `mini_three_round_system.py`, `risk_mode_system.py`, `deck_system.py`, `ai_opponent.py`: انتخاب دستی و pool تصادفی، Easy و اعتبارسنجی مستقیم.
- `bot/handlers/pvp.py`, `game_modes.py`, `battle.py`, `core/game_logic.py`, `web/miniapp_api.py`: مسیر بات، Random Legacy/Deck و درخواست API؛ UI جدیدی اضافه نمی‌شود.
- `systems/match_rewards_system.py`: context در مرز settlement، اعتبارسنجی کارت، حفظ ledger و پرداخت قبلی.
- `systems/card_inventory_system.py`, `card_upgrade_system.py`, `fusion_system.py`, `claim_system.py`, `player_rewards_system.py`, `starter_cards_system.py`, `rare_cards_system.py`, `card_missions_system.py`: تفکیک official/custom در مسیرهای اقتصادی و مأموریت موجود.
- `tests/test_shared_foundation.py`, `test_mini_three_round_api.py`, `test_actions_release.py`: قرارداد، درخواست دستکاری‌شده، Restart/Retry، migration و gate انتشار.
- همین راهنما و `DEPLOY_FROM_GITHUB_FA.md`: ممیزی، محدودیت‌ها و راه آماده‌سازی مالک.

نتیجهٔ نهایی اجرای تست‌ها و CI در بخش آزمون و PR ثبت می‌شود. این فاز به‌تنهایی اجازهٔ اجرای فاز دوم/سوم یا Deploy تولیدی نیست.

## شواهد آزمون محلی

- پیش از تغییر: اجرای کامل آفلاین Windows/Python 3.11.9، **۳۰۶ passed / ۳ skipped**. یک اجرای ابتدایی به علت نبود پوشهٔ موقت هنگام import tempfile رد شد؛ پس از ساخت پوشه و تنظیم TMP/TEMP/TMPDIR، baseline کامل موفق شد.
- پس از تغییر و رفع موارد یافت‌شده: اجرای کامل آفلاین، **۳۸۱ passed / ۳ skipped، بدون failure/error**. ۷۳ تست قرارداد/یکپارچه‌سازی جدید و دو آزمون API به مجموعه افزوده شدند. skipها Telegram زنده، flock لینوکس و symlink ویندوز هستند.
- build TypeScript/Vite و syntax JavaScript پنل موفق. هشدارهای قبلی فایل‌های فونت/تصویر خارج از Git باقی‌اند؛ asset جدید ساخته یا منتشر نشده است.
- آزمون‌ها شامل تمام rarityها و مودها، Heart مستقل Friendly، Easy چهار/پنج بازیکن، منع درخواست دستکاری‌شدهٔ API/Callback، pool تصادفی، context پس از Restart، Retry ledger، حفظ رکوردهای قدیمی و rollback transaction شکست migration هستند. preflight قبل و بعد آماده‌سازی schema روی کپی آزمایشی بررسی شده است.
- Graphify پس از تغییر کد به‌روزرسانی شد. نتیجهٔ واقعی Python 3.9.25، Linux، CI gate و artifact همین head در توضیح PR ثبت می‌شود؛ اعداد نسخهٔ قبلی جای آن استفاده نمی‌شوند.

هیچ آزمون روی دادهٔ تولیدی/کپی واقعی، نبرد زنده، Claim زنده، SSH یا Deploy انجام نشده است. حفظ رفتار فعلی با تست‌های رگرسیون پشتیبانی می‌شود؛ نتیجهٔ محیط تولیدی بدون آزمون مالک ادعا نمی‌شود. Friendly فعال، پرداخت/اعطای Custom، رتبه‌های Easy جدید و قطع کامل اقتصاد تمرین E2E نیستند، چون اجرای آنها به فاز بعد تعلق دارد.
