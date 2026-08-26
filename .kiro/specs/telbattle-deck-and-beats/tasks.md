# وظایف پیاده‌سازی: سیستم دک و نقشه برتری (TelBattle Deck & Beats Map)

## خلاصه

پیاده‌سازی در ۵ مرحله ترتیبی انجام می‌شود. هر مرحله بر مرحله قبل وابسته است.

---

## مرحله ۱: پایگاه داده و لایه داده

### Task 1.1 — ایجاد جدول `player_decks` در DB
**فایل:** `core/database.py`

- [ ] اضافه کردن `CREATE TABLE IF NOT EXISTS player_decks` به تابع `create_tables` یا `initialize_db`:
  ```sql
  CREATE TABLE IF NOT EXISTS player_decks (
      deck_id    TEXT PRIMARY KEY,
      player_id  INTEGER NOT NULL,
      deck_name  TEXT NOT NULL,
      card_id_1  TEXT NOT NULL,
      card_id_2  TEXT NOT NULL,
      card_id_3  TEXT NOT NULL,
      is_valid   INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (player_id) REFERENCES players (user_id)
  );
  CREATE INDEX IF NOT EXISTS idx_player_decks_player ON player_decks (player_id);
  ```
- [ ] تست: اجرای bot و بررسی ایجاد جدول در DB

**Requirements:** 7.1

---

### Task 1.2 — Migration ستون‌های جدید `battle_states`
**فایل:** `core/database.py`

- [ ] اضافه کردن تابع `migrate_battle_states_for_decks()` که با `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` ستون‌های زیر را اضافه می‌کند:
  - `challenger_deck_cards TEXT DEFAULT '[]'`
  - `opponent_deck_cards TEXT DEFAULT '[]'`
  - `challenger_remaining_cards TEXT DEFAULT '[]'`
  - `opponent_remaining_cards TEXT DEFAULT '[]'`
  - `challenger_deck_selected INTEGER DEFAULT 0`
  - `opponent_deck_selected INTEGER DEFAULT 0`
- [ ] فراخوانی این تابع در startup bot (در `telegram_bot.py` یا `game_core.py`)
- [ ] تست: بررسی ستون‌های جدید در DB موجود بدون از دست دادن داده

**Requirements:** 8.1

---

### Task 1.3 — Migration ستون‌های جدید `active_fights`
**فایل:** `core/database.py`

- [ ] اضافه کردن به تابع migration:
  - `ALTER TABLE active_fights ADD COLUMN challenger_deck_id TEXT DEFAULT NULL`
  - `ALTER TABLE active_fights ADD COLUMN opponent_deck_id TEXT DEFAULT NULL`
- [ ] تست: بررسی ستون‌های جدید بدون خطا

**Requirements:** 3.4

---

### Task 1.4 — متدهای CRUD دک در `DatabaseManager`
**فایل:** `core/database.py`

- [ ] پیاده‌سازی `create_deck(player_id, deck_name, card_id_1, card_id_2, card_id_3) -> str`
  - uuid جدید می‌سازد، INSERT می‌زند، deck_id برمی‌گرداند
- [ ] پیاده‌سازی `get_player_decks(player_id: int) -> List[Dict]`
  - همه دک‌های بازیکن را برمی‌گرداند (شامل is_valid)
- [ ] پیاده‌سازی `get_deck_by_id(deck_id: str) -> Optional[Dict]`
- [ ] پیاده‌سازی `update_deck(deck_id, deck_name=None, card_id_1=None, card_id_2=None, card_id_3=None, is_valid=None) -> bool`
  - فقط فیلدهای غیر-None را UPDATE می‌کند + updated_at
- [ ] پیاده‌سازی `delete_deck(deck_id: str) -> bool`
- [ ] پیاده‌سازی `count_player_decks(player_id: int) -> int`

**Requirements:** 7.2

---

### Task 1.5 — متدهای وضعیت فایت با دک در `DatabaseManager`
**فایل:** `core/database.py`

- [ ] پیاده‌سازی `set_fight_deck(fight_id, role, deck_id) -> bool`
  - `role` می‌تواند `'challenger'` یا `'opponent'` باشد
  - ستون `challenger_deck_id` یا `opponent_deck_id` در `active_fights` را UPDATE می‌کند
- [ ] پیاده‌سازی `update_battle_deck_state(fight_id, role, remaining_cards: List[str], selected: bool = None) -> bool`
  - `remaining_cards` را JSON می‌کند و در `battle_states` ذخیره می‌کند
  - اگر `selected=True` باشد، flag `challenger_deck_selected` یا `opponent_deck_selected` را ۱ می‌کند
- [ ] پیاده‌سازی `get_battle_deck_state(fight_id) -> Dict`
  - ستون‌های دک را از `battle_states` برمی‌گرداند

**Requirements:** 8.1, 8.2, 6.4 (sync logic)

---

## مرحله ۲: سیستم دک (منطق کسب‌وکار)

### Task 2.1 — ایجاد فایل `systems/deck_system.py`
**فایل:** `systems/deck_system.py` (جدید)

- [ ] تعریف کلاس `DeckSystem` با ثابت‌ها:
  ```python
  MAX_DECKS = 3
  MAX_CARDS_PER_DECK = 3
  MAX_NAME_LENGTH = 20
  ```
- [ ] پیاده‌سازی `_generate_default_name(player_id) -> str`
  - دک‌های موجود را می‌شمارد، «دک ۱»، «دک ۲»، «دک ۳» برمی‌گرداند
- [ ] پیاده‌سازی `_validate(player_id, card_ids, name, is_edit=False) -> Tuple[bool, str]`
  - بررسی تعداد دک (فقط در ساخت، نه ویرایش)
  - بررسی تعداد کارت‌ها (دقیقاً ۳)
  - بررسی تکراری نبودن card_id ها
  - بررسی عضویت هر کارت در کلکسیون بازیکن
  - بررسی طول نام (اگر داده شده)

**Requirements:** 1.1 تا 1.6

---

### Task 2.2 — متدهای اصلی `DeckSystem`
**فایل:** `systems/deck_system.py`

- [ ] پیاده‌سازی `create_deck(player_id, card_ids, name=None) -> Tuple[bool, str]`
  - اعتبارسنجی → `db.create_deck()` → برگرداندن (True, deck_id) یا (False, error_msg)
- [ ] پیاده‌سازی `update_deck(player_id, deck_id, card_ids=None, name=None) -> Tuple[bool, str]`
  - بررسی مالکیت دک
  - اعتبارسنجی (is_edit=True)
  - `db.update_deck()`
- [ ] پیاده‌سازی `delete_deck(player_id, deck_id) -> Tuple[bool, str]`
  - بررسی مالکیت دک → `db.delete_deck()`
- [ ] پیاده‌سازی `get_player_decks(player_id) -> List[Dict]`
  - هر dict شامل deck_id، deck_name، cards (List[Card])، is_valid، total_points
- [ ] پیاده‌سازی `get_valid_decks(player_id) -> List[Dict]`
  - فقط دک‌هایی که `is_valid=1` هستند
- [ ] پیاده‌سازی `validate_deck_integrity(player_id, deck_id) -> bool`
  - هر ۳ کارت را در `player_cards` بررسی می‌کند
  - اگر ناقص باشد: `db.update_deck(deck_id, is_valid=0)` → False برمی‌گرداند

**Requirements:** 1.7, 1.8, 1.9, 2.2, 2.3, 2.4, 3.2

---

## مرحله ۳: منطق نبرد — Beats Map

### Task 3.1 — جایگزینی `TYPE_COUNTER` با `BEATS_MAP`
**فایل:** `systems/battle_system_3rounds.py`

- [ ] **حذف** `TYPE_COUNTER` dict و `TYPE_COUNTER_BONUS` از ابتدای فایل
- [ ] اضافه کردن `BEATS_MAP`:
  ```python
  BEATS_MAP = {
      "speed":      "power",
      "power":      "popularity",
      "popularity": "iq",
      "iq":         "speed",
  }
  ```
- [ ] اضافه کردن `DOMINANT_PRIORITY = ["power", "speed", "iq", "popularity"]`

**Requirements:** 6.1, 6.5

---

### Task 3.2 — تابع `get_dominant_attr()`
**فایل:** `systems/battle_system_3rounds.py`

- [ ] پیاده‌سازی تابع module-level:
  ```python
  def get_dominant_attr(card: Card, arena: str) -> str:
      stats = {
          "power": card.power, "speed": card.speed,
          "iq": card.iq, "popularity": card.popularity
      }
      arena_info = ARENAS.get(arena, {})
      boost_stat = arena_info.get("boost_stat")
      if boost_stat and boost_stat in stats:
          stats[boost_stat] += arena_info.get("boost_amount", 0)
      max_val = max(stats.values())
      for attr in DOMINANT_PRIORITY:
          if stats[attr] == max_val:
              return attr
  ```
- [ ] اضافه کردن تابع `beats(attr_a: str, attr_b: str) -> bool`

**Requirements:** 5.1, 5.2, 5.3, 5.4

---

### Task 3.3 — آپدیت `_resolve_3round` در `bot/handlers/battle.py`
**فایل:** `bot/handlers/battle.py`

- [ ] **حذف** بلوک محاسبه `ch_counter` / `op_counter` (که از TYPE_COUNTER استفاده می‌کرد)
- [ ] جایگزینی با منطق BEATS_MAP:
  ```python
  from systems.battle_system_3rounds import get_dominant_attr, beats, BEATS_MAP

  dom_ch = get_dominant_attr(ch_card, arena_id)
  dom_op = get_dominant_attr(op_card, arena_id)
  beats_win = False
  beat_text = ""

  if beats(dom_ch, dom_op):
      round_winner = 'challenger'
      beats_win = True
      beat_text = f"⚡ برتری: {dom_ch} بر {dom_op}!"
  elif beats(dom_op, dom_ch):
      round_winner = 'opponent'
      beats_win = True
      beat_text = f"⚡ برتری: {dom_op} بر {dom_ch}!"
  else:
      # fallback به مجموع
      if ch_total > op_total:
          round_winner = 'challenger'
      elif op_total > ch_total:
          round_winner = 'opponent'
      else:
          round_winner = None
  ```
- [ ] اضافه کردن `beat_text` به متن نتیجه راوند (اگر `beats_win=True`)

**Requirements:** 6.2, 6.3, 6.4

---

## مرحله ۴: سیستم دک در فایت

### Task 4.1 — جایگزینی انتخاب کارت منفرد با انتخاب دک در `pvp.py`
**فایل:** `bot/handlers/pvp.py`

- [ ] اضافه کردن import: `from systems.deck_system import DeckSystem`
- [ ] نوشتن `_send_deck_selection(context, fight_id, user_id, fight)`:
  ```
  - valid_decks = deck_system.get_valid_decks(user_id)
  - اگر خالی بود: پیام «ساخت دک فوری» + دکمه deck_create
  - در غیر این صورت: لیست دک‌ها با callback_data: "pvp_deck_{fight_id}_{deck_id}"
  ```
- [ ] در `accept_pvp_fight_handler`: جایگزینی `send_message` با `_create_pvp_card_selection_keyboard` → `_send_deck_selection`
- [ ] در `accept_pvp_random_handler`: انتخاب تصادفی دک (اگر دک دارد) یا رد با خطا

**Requirements:** 3.1, 3.2, 3.3

---

### Task 4.2 — Handler انتخاب دک قبل از فایت
**فایل:** `bot/handlers/pvp.py`

- [ ] پیاده‌سازی `pvp_deck_select_handler(update, context)`:
  - parse: `callback_data = "pvp_deck_{fight_id}_{deck_id}"`
  - بررسی مالکیت دک توسط user_id
  - بررسی validity دک (`validate_deck_integrity`)
  - ذخیره در DB: `db.set_fight_deck(fight_id, role, deck_id)`
  - ذخیره card_ids در battle_states: `db.update_battle_deck_state(fight_id, role, [c1,c2,c3], selected=True)`
  - بررسی: اگر هر دو `deck_selected=1` شدند → `_init_3round_battle()` فراخوانی شود
  - پیام تأیید: «✅ دک انتخاب شد! منتظر حریف...»

**Requirements:** 3.4, 3.5, 6.4 (sync)

---

### Task 4.3 — جایگزینی UI انتخاب stat با UI انتخاب کارت در `battle.py`
**فایل:** `bot/handlers/battle.py`

- [ ] **حذف** تابع `_send_round_stat_selection()`
- [ ] نوشتن `_send_round_card_selection(context, fight_id, user_id, remaining_card_ids, arena_id, round_num, opponent_played_cards)`:
  ```
  متن پیام:
  - "⚔️ راوند {round_num}"
  - "🏟️ زمین: {arena_emoji} {arena_name}"
  - اگر round_num > 1: نمایش کارت‌های بازی‌شده حریف در راوندهای قبل
  - "کارت‌های باقی‌مانده تو:"
  - هر دکمه: نام کارت + rarity + dominant attr پیش‌بینی‌شده
    callback_data: "r3_card_{fight_id}_{card_id}"
  - اگر فقط ۱ کارت: خودکار انتخاب + پیام اطلاع‌رسانی
  ```
- [ ] بررسی: اگر remaining فقط ۱ کارت دارد، خودکار انتخاب شود (نیازی به دکمه نیست)

**Requirements:** 4.1, 4.2, 4.5, 5.6, 5.7

---

### Task 4.4 — Handler انتخاب کارت در راوند
**فایل:** `bot/handlers/battle.py`

- [ ] **حذف** `r3_stat_select_handler`
- [ ] پیاده‌سازی `r3_card_select_handler(update, context)`:
  - parse: `callback_data = "r3_card_{fight_id}_{card_id}"`
  - خواندن `battle_states` از DB
  - بررسی نقش بازیکن (challenger/opponent)
  - بررسی: آیا card_id در remaining_cards هست؟ اگر نه: خطا
  - بررسی: آیا قبلاً انتخاب کرده؟ اگر بله: پیام «قبلاً انتخاب کردی»
  - ذخیره موقت: `context.bot_data[f"r3_{fight_id}_{role}_card"] = card_id`
  - پیام تأیید: «✅ کارت انتخاب شد! منتظر حریف...»
  - بررسی: اگر هر دو role کارت داشتند → `_resolve_3round()` فراخوانی شود

**Requirements:** 4.3, 4.4, 8.4

---

### Task 4.5 — آپدیت `_resolve_3round` برای کارت‌محور بودن
**فایل:** `bot/handlers/battle.py`

- [ ] signature عوض شود: `_resolve_3round(context, fight_id, ch_card_id, op_card_id, ...)`
  - دیگر `ch_stat` / `op_stat` نمی‌گیرد
- [ ] بارگذاری کارت‌ها از DB با card_id
- [ ] محاسبه `ch_base = ch_card.power + ch_card.speed + ch_card.iq + ch_card.popularity` (مجموع کل)
- [ ] اعمال arena boost روی total (نه یک stat خاص)
- [ ] اعمال ابیلیتی‌ها (سیستم ابیلیتی فعلی دست نمی‌خورد)
- [ ] اعمال منطق BEATS_MAP (از Task 3.3)
- [ ] آپدیت `remaining_cards` هر بازیکن در DB: کارت بازی‌شده حذف شود
- [ ] ساخت متن نتیجه راوند:
  ```
  ⚔️ راوند X تموم شد!
  🎴 تو: {card_name} ({rarity}) — صفت غالب: {dom_attr}
  🎴 حریف: {card_name} ({rarity}) — صفت غالب: {dom_attr}
  [اگر beats_win: "🔥 برتری: {attr} بر {attr}!"]
  ✅/❌ نتیجه
  امتیاز: تو X — حریف Y
  ```
- [ ] ارسال نتیجه به هر دو بازیکن (private)
- [ ] فراخوانی `_send_round_card_selection` برای راوند بعد یا `_finalize_3round_battle` اگر تمام شد

**Requirements:** 4.4, 5.4, 5.5, 5.6, 6.2, 6.3, 6.4, 8.1, 8.2

---

## مرحله ۵: منوی مدیریت دک در ربات

### Task 5.1 — اضافه کردن دکمه «دک‌های من» به منوی اصلی
**فایل:** `telegram_bot.py`

- [ ] پیدا کردن کیبورد منوی اصلی و اضافه کردن:
  ```python
  InlineKeyboardButton("🗂️ دک‌های من", callback_data="deck_menu")
  ```
- [ ] ثبت handler برای `deck_menu` callback

**Requirements:** 2.3

---

### Task 5.2 — Handler نمایش لیست دک‌ها
**فایل:** `telegram_bot.py` یا `bot/handlers/deck.py` (جدید)

- [ ] پیاده‌سازی `deck_menu_handler(update, context)`:
  ```
  decks = deck_system.get_player_decks(user_id)
  متن: "🗂️ دک‌های من ({len(decks)}/3)"
  برای هر دک:
    - نام + وضعیت (✅/⚠️) + کارت‌ها
    - دکمه‌های: [ویرایش] [حذف]
  دکمه: [➕ ساخت دک جدید] (اگر < 3 دک)
  ```

**Requirements:** 2.1, 2.2, 2.3

---

### Task 5.3 — فرایند ساخت دک (گام‌به‌گام)
**فایل:** `telegram_bot.py` یا `bot/handlers/deck.py`

- [ ] پیاده‌سازی `deck_create_handler` — شروع فرایند:
  - ذخیره state در `context.user_data["deck_build"] = {"cards": [], "step": 1}`
  - ارسال keyboard انتخاب دسته کارت (legend/epic/normal)
- [ ] پیاده‌سازی `deck_build_category_handler` — انتخاب دسته:
  - callback_data: `"deck_build_cat_{rarity}_{page}"`
  - نمایش کارت‌های آن rarity با pagination
- [ ] پیاده‌سازی `deck_build_card_handler` — انتخاب یک کارت:
  - callback_data: `"deck_build_pick_{card_id}"`
  - بررسی تکراری نبودن
  - اضافه کردن به `context.user_data["deck_build"]["cards"]`
  - اگر ۳ کارت کامل شد → درخواست نام دک
- [ ] پیاده‌سازی `deck_name_message_handler` — دریافت نام از کاربر:
  - message handler (نه callback) برای text
  - فقط اگر `context.user_data.get("deck_build")` فعال باشد
  - `deck_system.create_deck()` فراخوانی شود
  - پیام موفقیت یا خطا
- [ ] دکمه «بدون نام» برای skip نام‌گذاری

**Requirements:** 2.4, 1.5, 1.6, 1.7, 1.8

---

### Task 5.4 — Handler حذف دک
**فایل:** `telegram_bot.py` یا `bot/handlers/deck.py`

- [ ] پیاده‌سازی `deck_delete_handler`:
  - callback_data: `"deck_delete_{deck_id}"`
  - نمایش پیام تأیید: «آیا مطمئنی؟»
  - callback_data تأیید: `"deck_delete_confirm_{deck_id}"`
- [ ] پیاده‌سازی `deck_delete_confirm_handler`:
  - `deck_system.delete_deck()` فراخوانی شود
  - بازگشت به منوی دک‌ها

**Requirements:** 1.9 (حذف)، 2.3

---

### Task 5.5 — ثبت تمام handler های جدید در dispatcher
**فایل:** `telegram_bot.py`

- [ ] ثبت `CallbackQueryHandler` برای:
  - `^deck_menu$`
  - `^deck_create$`
  - `^deck_build_cat_`
  - `^deck_build_pick_`
  - `^deck_delete_`
  - `^deck_delete_confirm_`
  - `^pvp_deck_`
  - `^r3_card_`
- [ ] ثبت `MessageHandler` برای نام دک (فقط وقتی `deck_build` state فعال است)
- [ ] حذف یا غیرفعال کردن handler های قدیمی `r3_stat_` و `pvp_card_` (که دیگر استفاده نمی‌شوند)

**Requirements:** تمام requirements مربوط به UI

---

## مرحله ۶: تست

### Task 6.1 — تست‌های واحد `DeckSystem`
**فایل:** `tests/test_deck_system.py` (جدید)

- [ ] تست `create_deck` با ترکیب‌های مجاز
- [ ] تست رد شدن دک چهارم
- [ ] تست رد کارت تکراری
- [ ] تست `validate_deck_integrity` وقتی کارت از کلکسیون حذف شود
- [ ] تست `get_valid_decks` فیلتر دک‌های ناقص

**Requirements:** 1.1–1.9, Properties 1–7

---

### Task 6.2 — تست‌های واحد `Beats Map`
**فایل:** `tests/test_beats_system.py` (جدید)

- [ ] تست `get_dominant_attr` برای حالت‌های مختلف stats
- [ ] تست `get_dominant_attr` با arena boost (تغییر dominant)
- [ ] تست `beats()` برای تمام ۴ جفت چرخه برتری
- [ ] تست اینکه کارت ضعیف‌تر با برتری می‌برد (beats_win)
- [ ] تست fallback به مجموع وقتی برتری نیست

**Requirements:** 5.1–5.4, 6.1–6.5, Properties 10–12

---

### Task 6.3 — تست یکپارچگی فایت با دک
**فایل:** `tests/test_battle_integration.py` (جدید)

- [ ] تست جریان: پذیرش فایت → انتخاب دک → راوند ۱ → راوند ۲ → راوند ۳ → نتیجه
- [ ] تست sync: بازیکن اول دک انتخاب کند، فایت شروع نشود؛ بعد بازیکن دوم هم انتخاب کند
- [ ] تست auto-select کارت آخر راوند
- [ ] تست migration DB روی فایل موجود

**Requirements:** 3.5, 4.4, 4.5, 8.3

---

## ترتیب پیاده‌سازی توصیه‌شده

```
مرحله ۱ (DB)  →  مرحله ۲ (DeckSystem)  →  مرحله ۳ (Beats Map)
     ↓
مرحله ۴ (فایت با دک)  →  مرحله ۵ (منوی ربات)  →  مرحله ۶ (تست)
```

**نکته مهم:** مرحله ۳ (Beats Map) مستقل از مراحل ۱ و ۲ است و می‌تواند موازی پیاده‌سازی شود.
