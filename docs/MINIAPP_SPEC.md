# TelBattle Mini App — مشخصات کامل فنی و طراحی
> این فایل برای همکاری Claude (بخش فنی) + Gemini (بخش طراحی) آماده شده است.
> تاریخ: خرداد ۱۴۰۵

---

## بخش اول: چشم‌انداز کلی

Mini App یه وب‌اپ داخل تلگرامه که با کلیک روی یه دکمه در پیوی ربات باز می‌شه.
هدف اصلی: **بازی Solo (تک‌نفره در مقابل AI)** بدون نیاز به گروه.

### چرا Mini App؟
- ربات فعلی فقط در گروه کار می‌کنه
- بازیکن می‌خواد در پیوی ربات، هر وقت خواست بازی کنه
- رابط گرافیکی به جای متن خشک تلگرام

---

## بخش دوم: صفحات (Screens) — برای Gemini

> **Gemini باید برای هر صفحه زیر طراحی UI بده.**

---

### 🎨 پالت رنگ پیشنهادی (برای Gemini)
```
پس‌زمینه اصلی:   #0A0A1A  (آبی-مشکی خیلی تیره)
پس‌زمینه کارت:   #12122A  (کمی روشن‌تر)
رنگ اصلی:        #7B5EEA  (بنفش)
رنگ تأکید:       #F0C040  (طلایی)
متن اصلی:        #FFFFFF
متن ثانویه:      #8888AA
Normal rarity:   #4CAF50  (سبز)
Epic rarity:     #9C27B0  (بنفش)
Legend rarity:   #FF9800  (نارنجی-طلایی)
Rare rarity:     #F44336  (قرمز)
```

### 🖋️ فونت پیشنهادی
- متن فارسی: Vazirmatn
- متن انگلیسی: Rajdhani یا Oswald (فانتزی و خوانا)

---

### Screen 1: صفحه اصلی (Home)
**URL:** `/`

**المان‌ها:**
- عکس پروفایل تلگرام کاربر (گرد، بالا چپ)
- نام کاربر
- سطح (Level) + نوار پیشرفت XP (progress bar کوچک)
- Tier فعلی با رنگ مربوطه (Bronze/Silver/Gold/Platinum/Diamond)
- تعداد قلب‌ها با آیکون ❤️ (مثلاً ۸/۱۰)
- تعداد سکه با آیکون 🪙
- امتیاز کل

**دکمه‌های اصلی (بزرگ، وسط صفحه):**
```
[ ⚔️  بازی Solo ]    ← بزرگترین دکمه، رنگ اصلی
[ 🃏  کارت‌هایم  ]
[ 🏆  جدول امتیازات ]
[ 👤  پروفایل     ]
```

**نکات طراحی:**
- دکمه Solo باید بزرگ‌تر و برجسته‌تر از بقیه باشه
- پس‌زمینه می‌تونه یه پارتیکل/گلو کمرنگ داشته باشه
- موبایل-فرست (عرض ۳۷۵-۴۳۰px)

---

### Screen 2: انتخاب سختی (Difficulty Select)
**URL:** `/solo/difficulty`

**المان‌ها:**
- عنوان "مبارزه Solo انتخاب کن"
- ۳ کارت بزرگ قابل انتخاب:

```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│    😊 آسان       │   │    😤 متوسط      │   │    💀 سخت        │
│                  │   │                  │   │                  │
│  AI از کارت‌های  │   │  AI از کارت‌های  │   │  AI از کارت‌های  │
│  Normal استفاده  │   │  Epic استفاده    │   │  Legend استفاده  │
│  می‌کنه          │   │  می‌کنه          │   │  می‌کنه          │
│                  │   │                  │   │                  │
│  🏆 +3 امتیاز   │   │  🏆 +5 امتیاز   │   │  🏆 +8 امتیاز   │
│  ⭐ +5 XP       │   │  ⭐ +8 XP       │   │  ⭐ +10 XP      │
└──────────────────┘   └──────────────────┘   └──────────────────┘
```

**نکات طراحی:**
- وقتی روی یکی hover می‌کنی (یا tap می‌کنی) بزرگ‌تر بشه
- رنگ آسان: سبز | متوسط: آبی | سخت: قرمز

---

### Screen 3: انتخاب کارت (Card Selection)
**URL:** `/solo/card-select`

**لایوت:**
```
┌─────────────────────────────────────┐
│  سختی: [متوسط] │ کارت هوش مصنوعی: ؟│
├─────────────────────────────────────┤
│        کارت خودت رو انتخاب کن       │
├──────┬──────┬──────┬──────┬─────────┤
│ [کارت] [کارت] [کارت] [کارت] [کارت] │  ← اسکرول افقی
│ [کارت] [کارت] [کارت] [کارت] [کارت] │
└─────────────────────────────────────┘
│           [ فیلتر: همه | Normal | Epic | Legend ] │
```

**هر کارت در گرید:**
```
┌──────────┐
│  [تصویر] │  ← استیکر WebP (80×80px)
│  John    │
│  Wick    │
│ ──────── │
│ P:82 S:88│
│ IQ:78 PP:85│
│ [Normal] │
└──────────┘
```

**وقتی کارت انتخاب می‌شه:**
- کارت بزرگ‌تر نمایش داده می‌شه (modal یا slide-up panel)
- آمار کامل + ابیلیتی‌ها نشون داده می‌شه
- دکمه "انتخاب این کارت"

**نکات طراحی:**
- کارت انتخاب‌شده باید highlighted باشه (border طلایی)
- کارت‌هایی که cooldown دارن باید grayed out باشن با آیکون ⏳

---

### Screen 4: انتخاب زمین (Arena Select)
**URL:** `/solo/arena`
*(فقط وقتی هر دو طرف یه rarity برابر دارن — وگرنه تصادفیه)*

**المان‌ها:**
- ۴ زمین به صورت گرید ۲×۲:

```
┌─────────────────┐  ┌─────────────────┐
│   ⚡ عرصه قدرت  │  │   🏃 پیست سرعت  │
│  کارت Power    │  │  کارت Speed    │
│  +1 بونوس      │  │  +1 بونوس      │
└─────────────────┘  └─────────────────┘
┌─────────────────┐  ┌─────────────────┐
│   🧠 اتاق فکر   │  │   ⭐ صحنه        │
│  کارت IQ       │  │  کارت Pop      │
│  +1 بونوس      │  │  +1 بونوس      │
└─────────────────┘  └─────────────────┘
```

- زیر هر زمین: "کارت تو اینجا X بونوس می‌گیره" یا "کارت AI اینجا بونوس می‌گیره"

---

### Screen 5: صحنه مبارزه (Battle Screen)
**URL:** `/solo/battle`

**این مهم‌ترین صفحه‌ست.**

**لایوت کلی:**
```
┌─────────────────────────────────────┐
│  زمین: ⚡ عرصه قدرت    راوند: 1/3   │
├─────────────────────────────────────┤
│                                     │
│  ┌──────────┐     VS    ┌─────────┐ │
│  │  کارت AI │           │کارت تو │ │
│  │  [تصویر] │           │[تصویر] │ │
│  │  ???     │           │JohnWick│ │
│  └──────────┘           └────────┘ │
│                                     │
├─────────────────────────────────────┤
│        راوند ۱: آماری رو انتخاب کن  │
│                                     │
│  [ 💪 Power: 82 ]  [ ⚡ Speed: 88 ] │
│  [ 🧠 IQ: 78    ]  [ ⭐ Pop: 85   ] │
│                                     │
│  (آمارهایی که قبلاً استفاده شدن خاکستری│
└─────────────────────────────────────┘
```

**بعد از انتخاب آمار (نتیجه راوند):**
```
┌─────────────────────────────────────┐
│          نتیجه راوند ۱              │
├──────────────┬──────────────────────┤
│   AI انتخاب: │  تو انتخاب:          │
│   Speed      │  Speed               │
├──────────────┼──────────────────────┤
│   ۷۲         │  ۸۸ (+1 بونوس=89)  │
├──────────────┼──────────────────────┤
│         🏆 تو بردی!                 │
└─────────────────────────────────────┘
```

**نوار پیشرفت راوندها (بالای صفحه):**
```
راوند ۱: 🟢   راوند ۲: ⬜   راوند ۳: ⬜
امتیاز:  AI: 0  |  تو: 1
```

**نکات طراحی:**
- انیمیشن flip کارت وقتی بازی شروع می‌شه
- انیمیشن shake کارت بازنده راوند
- رنگ سبز برای برنده و قرمز برای بازنده راوند
- آمارهای استفاده‌شده در راوندهای قبل باید disabled باشن (خاکستری + خط روی)

---

### Screen 6: نتیجه نهایی (Result Screen)
**URL:** `/solo/result`

**حالت برد:**
```
┌─────────────────────────────────────┐
│                                     │
│         🏆 بُردی!                    │
│                                     │
│    [انیمیشن confetti/ستاره]          │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  +8 امتیاز                  │    │
│  │  +10 XP                    │    │
│  │  Tier Points: +15           │    │
│  └─────────────────────────────┘    │
│                                     │
│  [▶️ بازی دوباره]  [🏠 خانه]        │
└─────────────────────────────────────┘
```

**حالت باخت:**
```
┌─────────────────────────────────────┐
│                                     │
│         💔 باختی                    │
│                                     │
│  ❤️ ❤️ ❤️ ❤️ ❤️ ❤️ ❤️ 🖤 🖤 🖤      │
│  (یک قلب کم شد)                    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  +3 XP (تجربه باخت)       │    │
│  │  قلب‌های باقی: 7/10         │    │
│  └─────────────────────────────┘    │
│                                     │
│  [🔄 تلاش دوباره]  [🏠 خانه]       │
└─────────────────────────────────────┘
```

---

### Screen 7: کارت‌های من (My Cards)
**URL:** `/cards`

**لایوت:**
```
┌─────────────────────────────────────┐
│  🃏 کارت‌های من     (۱۲ کارت)       │
├─────────────────────────────────────┤
│  [ همه ] [ Normal ] [ Epic ] [ Legend ]│
├─────────────────────────────────────┤
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐       │
│  │    │ │    │ │    │ │    │       │
│  │    │ │    │ │    │ │    │       │
│  │ N  │ │ E  │ │ L  │ │ N  │       │
│  └────┘ └────┘ └────┘ └────┘       │
│  ┌────┐ ┌────┐ ...                  │
└─────────────────────────────────────┘
```

**وقتی روی کارت کلیک می‌کنی (Detail Modal):**
```
┌─────────────────────────────────────┐
│        [✕ بستن]                     │
│                                     │
│    ┌──────────────────────┐         │
│    │   [تصویر بزرگ کارت]  │         │
│    │                      │         │
│    │   John Wick          │         │
│    │   [LEGEND] ⭐⭐⭐     │         │
│    └──────────────────────┘         │
│                                     │
│  💪 Power:     82  ████████░░       │
│  ⚡ Speed:     88  █████████░       │
│  🧠 IQ:        78  ████████░░       │
│  ⭐ Popularity: 85  ████████░░      │
│                                     │
│  ✨ ابیلیتی‌ها:                      │
│  • Shadow Step                      │
│  • Bullet Time                      │
│  • Unstoppable Force                │
│                                     │
│  📖 بیوگرافی:                       │
│  یک کشتارگر خبره که...              │
│                                     │
│  استفاده در مبارزه: ۱۲ بار           │
└─────────────────────────────────────┘
```

---

### Screen 8: جدول امتیازات (Leaderboard)
**URL:** `/leaderboard`

```
┌─────────────────────────────────────┐
│  🏆 جدول امتیازات                    │
│  [ هفتگی ] [ ماهانه ] [ کل زمان ]   │
├─────────────────────────────────────┤
│  🥇 1. @ali_gamer        2,450 pt   │
│  🥈 2. @sara_cards       2,100 pt   │
│  🥉 3. @mmd_pro          1,800 pt   │
│  ─────────────────────────────────  │
│  ...                                │
│  ─────────────────────────────────  │
│  📍 رتبه تو: #47          320 pt    │
└─────────────────────────────────────┘
```

---

### Screen 9: پروفایل (Profile)
**URL:** `/profile`

```
┌─────────────────────────────────────┐
│  [ عکس پروفایل ]                    │
│  Kasra D.    @kasra_username         │
│                                     │
│  Level 12   ████████░░  ۸۰/۱۰۰ XP  │
│  Tier: 🟡 Gold                       │
│                                     │
│  ┌─────────┬─────────┬─────────┐   │
│  │ ۱۲ کارت │ ۴۸ مبارزه│ ۶۵% برد│   │
│  └─────────┴─────────┴─────────┘   │
│                                     │
│  آمار مبارزه:                        │
│  Solo:  ۳۲ مبارزه | ۲۲ برد | ۱۰ باخت│
│  PvP:   ۱۶ مبارزه | ۹ برد  | ۷ باخت │
│                                     │
│  بهترین کارت: John Wick (Legend) ★  │
└─────────────────────────────────────┘
```

---

## بخش سوم: انیمیشن‌های مورد نیاز (برای Gemini)

| انیمیشن | کجا | توضیح |
|---------|-----|-------|
| Card Flip | شروع مبارزه | ۱۸۰ درجه flip روی محور Y |
| Card Shake | بازنده راوند | ارتعاش ۰.۳ ثانیه |
| Glow Pulse | کارت برنده | درخشش ملایم دور کارت |
| Counter + | دریافت XP | عدد با + از پایین بالا میره |
| Confetti | صفحه برد | ذرات رنگی می‌ریزن |
| Heart Break | باختن قلب | قلب به دو نیم تقسیم می‌شه |
| Slide Up | modal کارت | از پایین به بالا slide |
| Progress Fill | XP bar | انیمیشن پر شدن |

---

## بخش چهارم: API Endpoints — کار Claude

> **Claude این‌ها رو پیاده‌سازی می‌کنه روی Flask.**

### Base URL
```
https://[server-ip]/miniapp/api/v1/
```

### احراز هویت
همه request ها باید `initData` تلگرام رو در header بفرستن:
```
Authorization: tma [telegram_init_data]
```

---

### 4.1 پروفایل کاربر

**GET** `/profile`
```json
Response:
{
  "user_id": 123456,
  "first_name": "Kasra",
  "username": "kasra_d",
  "photo_url": "https://...",
  "hearts": 8,
  "max_hearts": 10,
  "coins": 450,
  "total_score": 1250,
  "level": 12,
  "current_xp": 80,
  "xp_to_next_level": 100,
  "current_tier": "Gold",
  "tier_points": 850,
  "stats": {
    "total_fights": 48,
    "wins": 31,
    "losses": 17,
    "solo_fights": 32,
    "solo_wins": 22,
    "pvp_fights": 16,
    "pvp_wins": 9
  }
}
```

---

### 4.2 کارت‌های کاربر

**GET** `/cards?rarity=all&page=1&limit=20`
```json
Response:
{
  "total": 12,
  "cards": [
    {
      "card_id": "john_wick_legend",
      "name": "John Wick",
      "rarity": "legend",
      "power": 82,
      "speed": 88,
      "iq": 78,
      "popularity": 85,
      "card_type": "SPEED_TYPE",
      "abilities": ["Shadow Step", "Bullet Time", "Unstoppable Force"],
      "biography": "...",
      "sticker_file_id": "CAACAgIA...",   ← file_id استیکر تلگرام
      "usage_count": 12,
      "is_favorite": true,
      "is_in_cooldown": false,
      "cooldown_until": null
    }
  ]
}
```

---

### 4.3 شروع Solo Fight

**POST** `/solo/start`
```json
Request:
{
  "player_card_id": "john_wick_legend",
  "difficulty": "medium"    // "easy" | "medium" | "hard"
}

Response:
{
  "fight_id": "uuid-xxxx",
  "player_card": { ...card object... },
  "ai_card": {
    "card_id": "heisenberg_epic",
    "name": "Heisenberg",
    "rarity": "epic",
    "power": 45,
    "speed": 38,
    "iq": 60,
    "popularity": 56,
    "sticker_file_id": "CAACAgIA..."
  },
  "arena": {
    "arena_id": "power_arena",
    "name_fa": "عرصه قدرت",
    "boost_stat": "power",
    "emoji": "⚡"
  },
  "arena_selected_by": "random",  // "random" | "player" | "ai"
  "current_round": 1,
  "available_stats": ["power", "speed", "iq", "popularity"]
}
```

---

### 4.4 بازی راوند

**POST** `/solo/round`
```json
Request:
{
  "fight_id": "uuid-xxxx",
  "player_stat": "speed"
}

Response:
{
  "round_number": 1,
  "player_stat": "speed",
  "player_value": 88,
  "player_boost": 0,
  "player_total": 88,
  "ai_stat": "power",
  "ai_value": 45,
  "ai_boost": 1,
  "ai_total": 46,
  "round_winner": "player",    // "player" | "ai" | "tie"
  "player_rounds_won": 1,
  "ai_rounds_won": 0,
  "game_over": false,
  "next_round": 2,
  "used_stats": {
    "player": ["speed"],
    "ai": ["power"]
  },
  "available_stats": ["power", "iq", "popularity"]   ← آمارهای باقی‌مانده برای پلیر
}
```

---

### 4.5 پایان بازی (وقتی game_over=true می‌شه)

**GET** `/solo/result/{fight_id}`
```json
Response:
{
  "fight_id": "uuid-xxxx",
  "winner": "player",     // "player" | "ai"
  "player_rounds_won": 2,
  "ai_rounds_won": 1,
  "rounds_detail": [
    {
      "round": 1,
      "player_stat": "speed", "player_total": 88,
      "ai_stat": "power", "ai_total": 46,
      "winner": "player"
    },
    ...
  ],
  "rewards": {
    "score_gained": 5,
    "xp_gained": 8,
    "tier_points_change": 15,
    "hearts_lost": 0,
    "level_up": false,
    "new_level": null,
    "tier_change": null
  },
  "player_after": {
    "hearts": 8,
    "total_score": 1255,
    "level": 12,
    "current_xp": 88,
    "current_tier": "Gold"
  }
}
```

---

### 4.6 انتخاب زمین توسط بازیکن (اختیاری)

**POST** `/solo/arena`
```json
Request:
{
  "fight_id": "uuid-xxxx",
  "arena_id": "speed_track"
}

Response:
{
  "arena": { ...arena object... },
  "message": "زمین انتخاب شد"
}
```

---

### 4.7 جدول امتیازات

**GET** `/leaderboard?period=weekly&limit=50`
```json
Response:
{
  "period": "weekly",
  "my_rank": 47,
  "my_score": 320,
  "entries": [
    {
      "rank": 1,
      "user_id": 999,
      "username": "ali_gamer",
      "first_name": "Ali",
      "score": 2450,
      "tier": "Diamond"
    }
  ]
}
```

---

### 4.8 لیمیت روزانه Solo

**GET** `/solo/daily-limit`
```json
Response:
{
  "used": 7,
  "limit": 10,
  "resets_at": "2026-06-11T00:00:00"
}
```

---

## بخش پنجم: منطق AI (بخش کلود)

### استراتژی AI بر اساس سختی

```python
class AIOpponent:

    def select_stat(self, available_stats, ai_card, player_card, difficulty, round_num):
        if difficulty == "easy":
            return random.choice(available_stats)           # کاملاً رندوم
        
        elif difficulty == "medium":
            if round_num == 1:
                return random.choice(available_stats)       # راوند اول رندوم
            else:
                # بهترین آماری که AI داره رو انتخاب می‌کنه
                return max(available_stats, key=lambda s: getattr(ai_card, s))
        
        elif difficulty == "hard":
            # AI آماری رو انتخاب می‌کنه که Player ضعیف‌تره
            return min(available_stats, key=lambda s: getattr(player_card, s))
```

### Pool کارت‌های AI
- Easy: فقط از کارت‌های Normal می‌کشه (rarity=normal)
- Medium: فقط از کارت‌های Epic می‌کشه (rarity=epic)
- Hard: فقط از کارت‌های Legend می‌کشه (rarity=legend)
- AI یه کارت رندوم از pool خودش انتخاب می‌کنه

---

## بخش ششم: محدودیت‌ها و قوانین

| قانون | مقدار | دلیل |
|-------|-------|------|
| Solo روزانه | ۱۰ مبارزه | جلوگیری از farming |
| قلب کم می‌شه اگه باختی | ۱ قلب | مثل PvP |
| Solo امتیاز کمتر از PvP | ۳/۵/۸ در مقابل ۱۰-۲۰ | جلوگیری از اینکه همه فقط Solo بزنن |
| Cooldown کارت‌ها در Solo هم اعمال می‌شه | — | همان قانون PvP |
| XP Solo کمتر از PvP نیست | ۵/۸/۱۰ | تشویق Solo برای leveling |

---

## بخش هفتم: ساختار فایل‌های پروژه (پس از پیاده‌سازی)

```
card game/
├── telegram_bot.py          ← ربات اصلی (تغییر کم: دکمه Mini App اضافه)
├── game_core.py             ← دیتابیس (تغییر کم: solo fight support)
├── battle_system_3rounds.py ← موتور مبارزه (تغییر: AI stat selection)
├── ai_opponent.py           ← NEW: کلاس AIOpponent
├── miniapp_api.py           ← NEW: Flask REST API برای Mini App
│
└── miniapp/                 ← NEW: فرانت‌اند
    ├── index.html           ← entry point
    ├── src/
    │   ├── main.js          ← Vue.js / Vanilla JS
    │   ├── screens/
    │   │   ├── Home.js
    │   │   ├── DifficultySelect.js
    │   │   ├── CardSelect.js
    │   │   ├── ArenaSelect.js
    │   │   ├── Battle.js
    │   │   ├── Result.js
    │   │   ├── MyCards.js
    │   │   ├── Leaderboard.js
    │   │   └── Profile.js
    │   ├── components/
    │   │   ├── CardComponent.js   ← کامپوننت کارت قابل استفاده مجدد
    │   │   ├── StatBar.js         ← نوار آمار
    │   │   └── HeartBar.js        ← نوار قلب
    │   ├── api.js               ← همه فراخوانی‌های API
    │   └── styles/
    │       ├── main.css
    │       ├── cards.css
    │       └── battle.css
    └── assets/
        └── icons/
```

---

## بخش هشتم: راهنمای Gemini

### درخواست از Gemini:
> "من یه بازی کارت جمع‌آوری (CCG) داخل تلگرام به اسم TelBattle دارم. می‌خوام یه Mini App (وب‌اپ داخل تلگرام) طراحی کنی.
>
> **ویژگی‌ها:**
> - Dark theme (پس‌زمینه تیره، رنگ‌های متالیک)
> - فانتزی/گیم‌پانک — مثل بازی‌های کارت موبایل (Clash Royale, Marvel Snap)
> - موبایل-فرست (عرض ۳۷۵-۴۳۰px)
> - RTL (راست به چپ) برای متون فارسی
>
> **پالت رنگ:** پس‌زمینه #0A0A1A، اصلی #7B5EEA، تأکید #F0C040
>
> **طراحی لازم:**
> 1. Screen 1: Home با ۴ دکمه اصلی
> 2. Screen 2: انتخاب سختی (۳ کارت)
> 3. Screen 3: انتخاب کارت (گرید کارت‌ها)
> 4. Screen 4: صفحه مبارزه (Battle Screen) ← مهم‌ترین
> 5. Screen 5: نتیجه (برد/باخت)
> 6. کامپوننت کارت (Card Component) در ۲ سایز: کوچک (گرید) و بزرگ (مبارزه)
>
> خروجی: Figma frame یا HTML/CSS آماده"

---

## بخش نهم: جدول تقسیم کار

| بخش | مسئول | وضعیت |
|-----|-------|-------|
| طراحی UI/UX همه صفحات | **Gemini** | ⏳ در انتظار |
| کامپوننت کارت (CSS/HTML) | **Gemini** | ⏳ در انتظار |
| انیمیشن‌های CSS | **Gemini** | ⏳ در انتظار |
| Flask API (miniapp_api.py) | **Claude** | ⏳ در انتظار طراحی |
| AI Opponent (ai_opponent.py) | **Claude** | ⏳ در انتظار |
| اتصال Telegram Mini App SDK | **Claude** | ⏳ در انتظار |
| Solo fight در DB | **Claude** | ⏳ در انتظار |
| JS logic (state management) | **Claude** | ⏳ در انتظار طراحی |
| دکمه Mini App در ربات | **Claude** | ⏳ در انتظار |

---

*آماده‌شده توسط Claude Sonnet 4.6 — خرداد ۱۴۰۵*
