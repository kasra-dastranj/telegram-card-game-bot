# TelBattle Mini App — گزارش وضعیت و مشکلات

## وضعیت فعلی (۱۱ خرداد ۱۴۰۵)

### ✅ چیزهایی که کار می‌کنند
- ربات تلگرام روی Railway در حال اجرا است (`getUpdates 200 OK`)
- Flask API روی port 8080 کار می‌کند
- آدرس public: `https://telegram-card-game-bot-production.up.railway.app`
- دکمه Mini App در `/start` نشان داده می‌شود ✅
- Mini App باز می‌شود ✅
- صفحه اصلی (mode_select) نمایش داده می‌شود ✅
- صفحه انتخاب سختی آسو (aso_select) نمایش داده می‌شود ✅
- فایل‌های static JS لود می‌شوند (`/miniapp/api.js` → 200 OK) ✅
- endpoint `GET /api/v1/health` → `{"status": "ok"}` ✅

### ❌ مشکل فعلی
**بعد از انتخاب سختی، صفحه انتخاب کارت (card_select) خالی می‌ماند — کارت‌ها لود نمی‌شوند**

### احتمال علت
- endpoint `GET /api/v1/cards` خطا برمی‌گرداند
- player روی Railway در DB وجود ندارد (DB تازه و خالی است)
- احراز هویت با `initData` تلگرام fail می‌کند

### چیزی که باید بررسی شود
در Railway Console تب، بعد از کلیک روی «انتخاب سختی»:
1. آیا request به `/api/v1/cards` می‌رود؟
2. چه error ای برمی‌گرداند؟

همچنین در مرورگر Console این URL را تست کن:
```
https://telegram-card-game-bot-production.up.railway.app/api/v1/cards
```
باید 401 Unauthorized بدهد (چون auth header ندارد) — این طبیعی است.

---

## ساختار پروژه

```
card game/
├── telegram_bot.py       ← ربات تلگرام (دکمه Mini App اضافه شده)
├── game_core.py          ← DB + جداول solo_fights, daily_solo_count
├── ai_opponent.py        ← هوش مصنوعی آسو (easy/medium/hard)
├── miniapp_api.py        ← Flask REST API
├── run_all.py            ← اجرای همزمان ربات + Flask
├── Procfile              ← web: python run_all.py
├── .python-version       ← 3.11
└── miniapp/
    ├── index.html        ← SPA entry point
    ├── api.js            ← fetch calls
    ├── app.js            ← router + state
    └── screens/
        ├── mode_select.js   ← صفحه اصلی ✅
        ├── aso_select.js    ← انتخاب سختی ✅
        ├── card_select.js   ← انتخاب کارت ❌ (کارت‌ها نمی‌آیند)
        ├── battle.js        ← صحنه نبرد
        ├── result.js        ← نتیجه
        ├── profile.js       ← پروفایل
        └── leaderboard.js   ← جدول امتیازات
```

---

## API Endpoints

| Method | Path | توضیح |
|--------|------|-------|
| GET | `/api/v1/health` | health check ✅ |
| GET | `/api/v1/profile` | پروفایل کاربر |
| GET | `/api/v1/cards` | کارت‌های کاربر ← **مشکل دار** |
| GET | `/api/v1/solo/daily-limit` | محدودیت روزانه |
| POST | `/api/v1/solo/start` | شروع نبرد Solo |
| POST | `/api/v1/solo/round` | بازی یک راوند |
| GET | `/api/v1/solo/result/<id>` | نتیجه نبرد |
| GET | `/api/v1/leaderboard` | جدول امتیازات |

### احراز هویت
- تلگرام: `Authorization: tma <initData>` (در Mini App از `window.Telegram.WebApp.initData` گرفته می‌شود)
- Debug mode: `X-Debug-User-Id: <user_id>`

کد احراز هویت در `miniapp_api.py`:
```python
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("tma "):
            if app.debug:
                g.user_id = int(request.headers.get("X-Debug-User-Id", "1"))
                return f(*args, **kwargs)
            return jsonify({"error": "Unauthorized"}), 401
        # verify initData ...
```

---

## مشکلات حل شده

### ۱. No start command detected (Railway)
**علت:** `Procfile` وجود نداشت  
**راه‌حل:** ساخت `Procfile` با محتوای `web: python run_all.py`

### ۲. Python 3.13 precompiled not found
**علت:** Railway نمی‌توانست Python 3.13 نصب کند  
**راه‌حل:** ساخت `.python-version` با محتوای `3.11`

### ۳. bot.run() AttributeError
**علت:** `TelegramCardBot` متد `run()` ندارد  
**راه‌حل:** تغییر به `telegram_bot.main()` در `run_all.py`

### ۴. Invalid Token
**علت:** `telegram_bot.py` توکن را از `game_config.json` می‌خواند که روی Railway وجود ندارد  
**راه‌حل:** اضافه کردن `os.environ.get("BOT_TOKEN")` با اولویت بالاتر

### ۵. Mini App loading stuck
**علت:** Tailwind CDN از `eval()` استفاده می‌کرد که CSP تلگرام بلاک می‌کرد  
**راه‌حل:** اضافه کردن `<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;">`

### ۶. JS files 404
**علت:** Flask `static_folder` مسیر relative داشت و working directory روی Railway متفاوت بود  
**راه‌حل در `miniapp_api.py`:**
```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
    static_folder=os.path.join(BASE_DIR, "miniapp"),
    static_url_path="/miniapp")
```
**راه‌حل در `index.html`:** تغییر از `./api.js` به `/miniapp/api.js`

---

## Railway Environment Variables

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | `8764374097:AAELXfFzdYEZEMlCnyYuLwxHtiLGWl9yONE` |
| `MINIAPP_URL` | `https://telegram-card-game-bot-production.up.railway.app` |
| `DATABASE_PATH` | `game_bot.db` |
| `ADMIN_IDS` | `5735941901,1431545583` |
| `WEB_API_HOST` | `0.0.0.0` |
| `WEB_API_PORT` | `5001` |

---

## نکات مهم برای ادامه

### ۱. مشکل DB خالی روی Railway
روی Railway دیتابیس `game_bot.db` خالی است — کارتی ندارد. باید:
- یا کارت‌های sample به DB اضافه شوند (از طریق Railway Console یا migration script)
- یا از PostgreSQL به جای SQLite استفاده شود

**دستور اضافه کردن کارت‌ها از Railway Console:**
```bash
python -c "from game_core import DatabaseManager, CardManager; db = DatabaseManager(); cm = CardManager(db); print(cm.create_sample_cards(), 'cards added')"
```

### ۲. DB موقتی است
هر بار که Railway سرویس را restart کند، فایل `game_bot.db` از بین می‌رود. برای production باید Railway PostgreSQL اضافه شود.

### ۳. مشکل card_select
در `miniapp/screens/card_select.js` تابع `renderCardSelect(state)` کارت‌ها را از `state.cards` می‌خواند. این array زمانی پر می‌شود که `loadCards()` در `app.js` صدا زده شود.

`loadCards()` در `app.js` وقتی `select_difficulty` action اتفاق می‌افتد صدا زده می‌شود:
```javascript
case "select_difficulty":
  navigate("card_select", { selectedDifficulty: value });
  await loadCards();  // ← این باید API.getCards() را صدا بزند
  break;
```

`API.getCards()` به `/api/v1/cards` می‌رود که نیاز به auth دارد. اگه `initData` تلگرام درست پاس نشود → 401 → cards خالی می‌ماند.

---

## تاریخچه commits مهم

```
b71978e  fix: use absolute path for Flask static_folder; add debug doc
e8701bf  fix: add CSP meta, absolute JS paths, restore Tailwind config
b905847  fix: use defer scripts and readyState check
7b92e51  fix: remove loading screen before API call
a9de49e  fix: read BOT_TOKEN/MINIAPP_URL from env vars; add WebAppInfo import
b491264  fix: call main() instead of bot.run() in run_all.py
cdeaa26  fix: pin Python 3.11 for Railway deploy
55e831a  fix: add Procfile and PORT env var
0905cbc  feat: add Mini App (Solo vs Aso) - Phase 3
a7be8dc  v2.0 - Phase 2 complete: 107 cards, PvP, economy, fusion, tier system
```
