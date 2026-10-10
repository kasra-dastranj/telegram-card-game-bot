# فاز دوم: پیشرفت و اقتصاد

## بررسی قبل از تغییر کد

مبنای کار فاز اول commit `a43984b6` است؛ تست پایه Windows: 381 passed, 3 skipped.
وابستگی‌ها با Graphify بررسی شدند. این کار روی شاخهٔ شخصی و دیتابیس موقت انجام می‌شود.

| مسیر واقعی | وضعیت قبلی | تغییر لازم |
|---|---|---|
| shared_foundation / match_contexts | چهار پرچم خاموش، هویت ثابت مسابقه | نسخهٔ تنظیمات در شروع مسابقه |
| MatchRewardsSystem / LegacyFightRewardsSystem / GameModeSystem | پاداش یک‌باره با قواعد قدیمی | محاسبهٔ مشترک XP/Score/Heart؛ حفظ مسابقهٔ قدیمی |
| miniapp_api / solo | تمرین دارای پاداش و کسر قلب | تمرین جدید بدون پاداش و کسر قلب |
| player_card_stacks / player_cards | تعداد واقعی فرم‌ها و فرم فعال | استفادهٔ مجدد؛ بدون ساخت مدل مالکیت موازی |
| PlayerRewardsSystem / ClaimSystem | Normal روزانه و یک Ability | Normal یا Ticket، Silver، وزن مستقل هر دریافت |
| FusionSystem / CardUpgradeSystem | ترکیب متفاوت و ارتقای سکه‌ای | فقط نسخه‌های یک شخصیت و Upgrade Card |
| EconomySystem / shop handlers | Mining، تبدیل Score، قلب ثابت | منع مسیر قدیمی در v2 و خرید با قیمت تأییدشده |
| LevelRewardsSystem / mode_access | جوایز اختیاری سکه، ورود آزاد | جوایز یک‌باره، ظرفیت، دسترسی Level 5/7 |
| weekly_rewards_system / bot.main | هفتهٔ دوشنبه، تهران، ساعت 00:15 | دورهٔ مشترک، ماهانه، رتبه مشترک و جلوگیری از پرداخت مجدد |
| card_missions_system | مأموریت ثابت کارت | تعریف و پرداخت مأموریت عمومی قابل تنظیم |
| web_api / card editor | پنل کارت و Arena | تنظیمات اقتصاد با ابزار ادمین مستقل، بدون رمز تولید |

منحنی موجود با فرمول سند یکسان است: `25*(L-1)*L + 50*(L-1)`؛ XP و دادهٔ قبلی بازنویسی نمی‌شوند.

## تصمیم‌های محصول

- Daily Claim: احتمال اولیهٔ Ticket برابر ۲۰٪، قابل تغییر توسط ادمین؛ بقیه Normal.
- تساوی: رتبهٔ مشترک و پاداش کامل همان رتبه برای هر نفر.
- Easy: انتخاب نامعتبر/قطع اتصال فقط امتیاز همان راند را از بین می‌برد؛ شرکت معتبر در راندهای دیگر محفوظ است.
- Risk: XP قدیمی ۲۵/۵؛ انتقال سکهٔ موجود حفظ می‌شود؛ Score جدید صفر.
- ساعت‌ها و مرز هفته از رفتار فعلی تهران/دوشنبه گرفته می‌شوند.
- پرچم progression_v2_enabled پیش‌فرض خاموش؛ Custom/Friendly همچنان خاموش.

## وضعیت اجرا

انتشار، فعال‌سازی روی تولید و فاز سوم بخشی از این درخواست نیست. موجودی و دادهٔ کاربر قدیمی حفظ می‌شود و جوایز جدید لول او تا تصمیم بعدی محصول **مسدود** هستند؛ نه پرداخت گذشته، نه هدیهٔ جبرانی خودکار. حساب تازهٔ ساخته‌شده بعد از روشن‌شدن v2 از قوانین تازه استفاده می‌کند. با پرچم خاموش رفتار قدیمی حفظ می‌شود.

## فایل‌ها و قراردادها

- `systems/progression_config.py`: تنظیمات DB، نسخه، اعتبارسنجی، تقویم تهران/دوشنبه و schema افزایشی.
- `systems/reward_ledger.py`: XP/Score/Coin/Heart اتمیک، جوایز مستقل لول، ظرفیت خریداری‌شده و رسید تکرار.
- `systems/progression_match_rewards.py`: پاداش کل مسابقه با نسخهٔ زمان ساخت؛ مسابقهٔ قدیمی با `legacy_v1` تمام می‌شود. Snapshot پس از خاموش‌کردن پرچم هم باقی می‌ماند.
- `systems/progression_economy.py`: Daily/Silver، وزن مستقل دریافت هر شخصیت، Upgrade، Sell، قیمت پیشنهادی و تأیید خرید، ظرفیت و قلب.
- `systems/progression_missions.py`: تعریف مأموریت قابل ویرایش، پیشرفت از رویداد واجد شرایط، مالکیت رسمی هنگام پرداخت، رسید مستقل هر دوره.
- `systems/progression_leaderboard.py`: تاریخچهٔ موجود حفظ، رتبه مشترک `1,1,3`، هفته و ماه یک‌بار. دورهٔ هفتگی قبلاً پرداخت‌شده در `weekly_reward_batches` دوباره پرداخت نمی‌شود. روزانه و کل زمان‌ها پرداخت ندارند.
- `systems/progression_rare.py`: قرارداد صدور رسمی با Stock/Serial اتمیک؛ هیچ Wheel/Event/Auction تازه‌ای فعال نیست.
- `bot/handlers/progression.py`، `web/miniapp_api.py` و Mini App: یک backend مشترک برای بات و وب، نمایش مقدار مصرف/قیمت قبل از تأیید؛ Mining/Score Conversion/Coin Upgrade/Distinct Fusion در v2 بسته هستند.
- `migrations/migrate_progression_v2.py`: backup سازگار SQLite، کپی آزمایشی، quick_check، بدون restore خودکار یا حذف داده.

پرشدن روزانهٔ قلب در ledger ثبت می‌شود و تکرار آن در همان روز، قلب مصرف‌شدهٔ تازه را دوباره پر نمی‌کند. ظرفیت قلب قدیمی حتی اگر از سقف فروش تازه بالاتر باشد کاهش داده نمی‌شود؛ خرید تازه همچنان سقف ۲۰ دارد.

شناسهٔ درخواست کاربر به فضای نام مستقل Claim/Upgrade/Sell/Rare وصل می‌شود؛ نمی‌تواند رسید مسابقه/لول را اشغال کند. فروش آخرین نسخه، دک را نامعتبر می‌کند و دلیل در بات/API/مینی‌اپ نمایش داده می‌شود. کارت شروع در v2 فقط یک‌بار ثبت می‌شود تا فروش همهٔ کارت‌ها دریافت تازه نسازد.

## تنظیمات ادمین، بدون تغییر Source Code

پنل گرافیکی کارت و Arena قبلی حفظ شده است. **فرم گرافیکی جدید برای اقتصاد، Recipe، Mission، Wheel و Rare اضافه نشده**؛ ابزار ادمین زیر مسیر جایگزین این فاز است. فقط روی کپی تست یا توسط صاحب دسترسی مجاز به DB اجرا شود. همکار از سیستم خود به DB تولیدی دسترسی نمی‌گیرد.

```powershell
# فقط DB موقتِ خودتان؛ مسیر واقعی تولید را اینجا قرار ندهید.
python scripts/economy_admin.py --database .test-tmp-stage/game.db --export .test-tmp-stage/economy.json
# فایل JSON صادرشده را ویرایش کنید؛ سپس validation و ثبت نسخه:
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --import-config .test-tmp-stage/economy.json
python scripts/economy_admin.py --database .test-tmp-stage/game.db --audit
# A = دو Epic، B = سه Epic؛ هیچ شخصیت خودکار A/B نمی‌گیرد.
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --legend-tier OFFICIAL_CARD_ID A
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --skin-price EXISTING_SKIN_ID 175
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --rare-supply EXISTING_RARE_ID 50
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --mission .test-tmp-stage/mission.json
# فقط Stage پس از بررسی؛ مقدار پیش‌فرض خاموش است.
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --flag on
python scripts/economy_admin.py --database .test-tmp-stage/game.db --actor tester --flag off
```

Export مقصد موجود را بازنویسی نمی‌کند؛ برای نسخهٔ بعدی نام تازه انتخاب کنید. تمام نسخه‌های Config با actor/time در `economy_config_versions`، Missionها در `economy_mission_audit` و دریافت‌ها در `reward_ledger` ثبت می‌شوند. تغییر Recipe/Skin/Supply/Flag با مقدار قبل و بعد، actor و زمان در `economy_admin_audit` نگه‌داری می‌شود. Supply نمی‌تواند از تعداد صادرشده کمتر شود و ساخت دوبارهٔ Rare موجود، شماره‌ها را ریست نمی‌کند. شناسه‌های واقعی شخصیت و Skin را از کاتالوگ همان محیط انتخاب کنید. ابزار هیچ secret نمی‌خواهد.

| کلید JSON | مقدار اولیه / رفتار |
|---|---|
| `match.quick` | XP 10/3/1، برد Score 1، باخت Heart 1 |
| `match.three_round`, `match.deck` | XP 15/5/3، برد Score 3، باخت Heart 1 |
| `match.risk` | XP 25/0/5، Score صفر؛ سکه از pot موجود، بدون خلق سکه |
| `easy` | حداقل 5 شرکت‌کنندهٔ واقعی با حداقل یک انتخاب معتبر؛ 3/5/10 راند |
| `level_thresholds`, `max_level`, `level_rewards` | تا 30؛ هر لول 50 سکه+یک Slot، هدیهٔ Silver در 3/10 و Heart در 8/10 |
| `mode_levels` | Easy/Deck در 5، Risk در 7 |
| `hearts`, `slots` | پایهٔ حساب تازه 8 قلب/3 Slot، سقف Heart 20؛ ظرفیت جوایز آینده محفوظ |
| `claim` | Ticket 20٪، Silver با 3 Ticket، بعد از دریافت سوم وزن ×0.5 فقط یک‌بار؛ دو Claim مستقل |
| `upgrade`, `sell` | Epic سه Normal+50 XP؛ Legend A/B با Upgrade Card+200 XP؛ فروش 10/60/250/350 |
| `shop` | Upgrade Card/Slot 200؛ Ticket هفتگی، refill روزانه و Heart مادام‌العمر 100×2^تعداد خرید موفق؛ Stock اختیاری |
| `leaderboard` | هفته Coin/XP:100/100،50/50،30/30،سپس10/0؛ ماه:300/300،200/200،100/100،سپس50/50 |
| `timezone`, `week_start`, `settlement_hour/minute` | تهران، دوشنبه،00:15 مطابق job قبلی؛ تغییر تقویم هنگام روشن‌بودن v2 نیازمند migration بازبینی‌شده است |
| `migration.legacy_user_policy` | `preserve_freeze_rewards`؛ جوایز لول قدیمی بسته |
| `wheel` | خاموش؛ قیمت/احتمال مصوب وجود ندارد |

فهرست خالی Daily/Silver Pool یعنی همهٔ شخصیت‌های رسمی دارای فرم آمادهٔ مربوط؛ برای محدودکردن، IDها را در `daily_pool`/`silver_pool` بنویسید. `weights` وزن پایهٔ هر ID را تغییر می‌دهد. Inventory تعداد نسخه‌ها را مستقل از تعداد دریافت Claim نگه می‌دارد. نبود Pool/فرم/Recipe هیچ نوبت یا آیتمی مصرف نمی‌کند.

نمونهٔ Mission (تعریف را خود ادمین در محیط آزمایشی ثبت می‌کند؛ هیچ Mission با پاداش خودکار Seed نشده):

```json
{"mission_id":"deadpool-three-wins","title":"سه برد با Deadpool","description":"سه برد معتبر با کارت رسمی","start":null,"end":null,"status":"active","type":"competitive_wins","target":3,"filters":{"card_id":"OFFICIAL_DEADPOOL_ID"},"eligibility":{"official_card_id":"OFFICIAL_DEADPOOL_ID"},"xp_reward":20,"coin_reward":10,"repeat_policy":"daily"}
```

انواع: `quick_games`, `deck_games`, `competitive_wins`, `character_games`, `trait_games`, `daily_claims`, `silver_claims`, `official_upgrades`, `official_sales`, `easy_games`, `period_score`. فیلترها: `card_id`/`trait`/`modes`؛ صلاحیت: `official_card_id`/`min_level`. زمان غیرخالی ISO همراه timezone؛ repeat فقط once/daily/weekly/monthly. Friendly/Practice پاداش و پیشرفت رقابتی نمی‌سازند. کل جوایز و تعداد هدف قابل تغییرند؛ دریافت انجام‌شده با ویرایش Mission تکرار نمی‌شود.

## Migration و rollback

```powershell
python migrations/migrate_progression_v2.py --database .test-tmp-stage/legacy.db --preview-copy .test-tmp-stage/preview.db
python migrations/migrate_progression_v2.py --database .test-tmp-stage/legacy.db --apply --backup .test-tmp-stage/before-v2.db
```

Migration پرچم را روشن نمی‌کند، total_score/XP/مالکیت/مقدار wallet/قلب را تغییر نمی‌دهد و مسابقات موجود را تبدیل نمی‌کند. ظرفیت موجود کاربر قدیمی حداقل برابر ظرفیت قبلی و تعداد دک او باقی می‌ماند. Rollback عملیاتی: پرچم را خاموش کنید؛ snapshot مسابقهٔ فعال و ledgerها حفظ می‌شوند. بازگشت کد فقط به نسخهٔ سازگار با schema افزوده انجام شود. **بعد از شروع بازی، backup را خودکار restore نکنید**؛ نوشتهٔ تازهٔ بازیکن از دست می‌رود.

## کار باقی‌ماندهٔ صاحب پروژه برای انتشار آینده

پس از ادغام و تصویب Stage، schema جدید باید **پیش از** Deploy Actions با دسترسی خود صاحب سرور آماده شود. هر آماده‌سازی واقعی زیر `/opt/telbattle/deploy.lock`، با توقف سه سرویس و backup مستقل انجام شود؛ همکار این دستورها را اجرا نکرده است.

1. کد commit بازبینی‌شده را در checkout مورد اعتماد مالک آماده کنید؛ `REVIEWED_CHECKOUT` در فرمان زیر همان مسیر است، نه `/opt/telbattle/current` در حال اجرا.
2. روی کپی خصوصی SQLite preview بگیرید و گزارش شمارش و quick_check را محلی بررسی کنید؛ DB/JSON تولید را در Git/چت/artifact نگذارید.
3. سپس برنامهٔ بازبینی‌شدهٔ آماده‌سازی را اجرا کنید:

```bash
flock -x /opt/telbattle/deploy.lock -- bash -c '
set -eu
systemctl stop telbattle-bot telbattle-api telbattle-admin
trap "systemctl start telbattle-bot telbattle-api telbattle-admin" EXIT
/opt/telbattle/venv/bin/python REVIEWED_CHECKOUT/migrations/migrate_progression_v2.py \
  --database /opt/telbattle/shared/game_bot.db --apply \
  --backup /opt/telbattle/backups/UNIQUE_BEFORE_PHASE2.db
'
```

نام backup باید تازه باشد؛ در صورت شکست، نسخهٔ قبلی برنامه دوباره شروع می‌شود و داده خودکار restore نمی‌شود. قابلیت v2 در تولید همچنان خاموش بماند تا محصول انتقال کاربران قدیمی و تست Stage را تأیید کند. bootstrap/Environment محافظت‌شده و انتشار دستی اصلی طبق `DEPLOY_FROM_GITHUB_FA.md` است؛ محافظت main یا قرارداد SSH تغییر نکرده است. بستهٔ Actions همچنان سیاست `no-change` دارد و startup دارای migration را قبل از فعال‌سازی رد می‌کند.

## موارد باز یا عمداً غیرفعال

- انتقال نهایی لول/کارت کاربران قدیمی: تصمیم کاربر هنوز باز است؛ موجودی حفظ و جوایز تازهٔ لول برای این حساب‌ها مسدود است.
- Legend A/B: باید برای هر شخصیت تنظیم شود؛ unset خطای امن است.
- Easy یک‌راندی و تعداد دیگر: پاداش تعریف نشده، صفر با snapshot قابل ردگیری؛ UI موجود می‌تواند بازی را اجرا کند.
- ضد حساب ساختگی: پنج ID مستقل با انتخاب معتبر ملاک موجود است؛ تشخیص انسانی خارج از اطلاعات معتبر Telegram یا سیستم تازهٔ ضدتقلب در این فاز افزوده نشده.
- کمتر از سه Normal برای Starter: روش قبلیِ دریافت اتمیک سه کارت حفظ است؛ Pool ناکافی دریافت نمی‌سازد؛ کاتالوگ Stage باید حداقل سه شخصیت رسمی داشته باشد.
- Practice پاداش/قلب صفر، محدودیت روزانه و شرط ورود قلبِ قبلی حفظ‌اند؛ قانون تازهٔ ورود با صفر قلب تصویب نشده.
- Wheel، فروش Ability با قیمت پیشنهادی، Clan/Group Reward، Achievement، Auction و Phase 3 Custom/Friendly فعال نشده‌اند. قرارداد Serial/Stock آماده است؛ برای محتوای Event تصمیم جدا لازم است.
- Admin گرافیکی اقتصاد ساخته نشده؛ CLI فوق مسیر کامل ویرایش دستی این فاز است.
- تست تلگرام زنده، production SSH/systemd، DNS و دیتابیس واقعی اجرا نشده‌اند.

## شواهد آزمون

اعداد نهایی تست/CI و شناسهٔ artifact در PR ثبت می‌شوند؛ شمارش نسخهٔ قبلی نتیجهٔ این نسخه نیست. تست‌ها DB موقت دارند. تست مرورگر Edge با API مصنوعی، و تست API Flask با SQLite واقعی موقت جدا گزارش می‌شوند. بررسی مرورگر جای اثبات Telegram زنده را نمی‌گیرد.

نتیجهٔ نهایی محلی این تغییر: **457 passed / 3 skipped، صفر failure/error** با Python 3.11.9 روی Windows و guard آفلاین SQLite؛ 76 تست فاز دوم اضافه شده‌اند. TypeScript/Vite build و JavaScript پنل موفق‌اند. Smoke مرورگر Edge موفق است و pageerror ندارد. تست‌های API/بات mock، concurrency، retry/restart، کپی migration/quick_check، نسخهٔ تنظیمات، legacy fallback و جلوگیری از migration خودکار در release gate در مجموعه اجرا شدند. سازگاری Python 3.9.25 و بستهٔ واقعی را نتیجهٔ CI همین commit در PR مشخص می‌کند.

آزمون مرورگر قابل تکرار، از ریشهٔ مخزن در Windows با Edge نصب‌شده:

```powershell
# ترمینال اول؛ Vite محلی، بدون توکن یا اطلاعات تولیدی
cd frontend/game
npm ci
npm run dev -- --host 127.0.0.1
# ترمینال دوم؛ ریشهٔ مخزن
$env:TELBATTLE_BROWSER_PATH='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
node scripts/smoke_progression_ui.mjs
```

در سیستم دیگر `TELBATTLE_BROWSER_PATH` مسیر مرورگر Chromium محلی است؛ یا Playwright Chromium از قبل نصب‌شده استفاده می‌شود. اسکریپت API را با دادهٔ ساختگی جایگزین می‌کند و خرید، تأیید Recipe دو Epic، Upgrade، Sell، Ticket+Ability و مخفی‌بودن Tier را بررسی می‌کند. Screenshot/نتیجه در `.test-tmp-phase2/` هستند و وارد Git نمی‌شوند. وابستگی‌های توسعهٔ nanoid و source-map-js به نسخهٔ patch به‌روز شده‌اند؛ `npm ci` با lockfile جدید صفر vulnerability گزارش کرد.
