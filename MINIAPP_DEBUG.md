# TelBattle Mini App — گزارش وضعیت و مشکلات

## وضعیت فعلی (۱۱ خرداد ۱۴۰۵)

### ✅ چیزهایی که کار می‌کنند
- ربات تلگرام روی Railway در حال اجرا است (`getUpdates 200 OK`)
- Flask API روی port 8080 کار می‌کند
- آدرس public: `https://telegram-card-game-bot-production.up.railway.app`
- دکمه Mini App در `/start` نشان داده می‌شود
- endpoint `GET /api/v1/health` → `{"status": "ok"}` ✅

### ❌ مشکل فعلی
**Mini App باز می‌شود ولی روی صفحه loading می‌ماند**

### علت اصلی (شناسایی شده)
در Console مرورگر:
1. **`Failed to load resource: 404`** برای `api.js`, `app.js`, `screens/*.js`
   - علت: script‌ها با مسیر `./api.js` لود می‌شدند ولی Flask آن‌ها را از `/miniapp/api.js` سرو می‌کند
   - راه‌حل اعمال شده: تغییر به مسیر absolute `/miniapp/api.js`

2. **`Content Security Policy blocks eval`**
   - علت: Tailwind CDN از `eval()` استفاده می‌کند و Telegram WebApp CSP سختی دارد
   - راه‌حل اعمال شده: اضافه کردن `<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;">`

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
        ├── mode_select.js
        ├── aso_select.js
        ├── card_select.js
        ├── battle.js
        ├── result.js
        ├── profile.js
        └── leaderboard.js
```

---

## API Endpoints

| Method | Path | توضیح |
|--------|------|-------|
| GET | `/api/v1/health` | health check |
| GET | `/api/v1/profile` | پروفایل کاربر |
| GET | `/api/v1/cards` | کارت‌های کاربر |
| GET | `/api/v1/solo/daily-limit` | محدودیت روزانه |
| POST | `/api/v1/solo/start` | شروع نبرد Solo |
| POST | `/api/v1/solo/round` | بازی یک راوند |
| GET | `/api/v1/solo/result/<id>` | نتیجه نبرد |
| GET | `/api/v1/leaderboard` | جدول امتیازات |

### احراز هویت
- تلگرام: `Authorization: tma <initData>`
- Debug mode: `X-Debug-User-Id: <user_id>`

---

## Railway Environment Variables

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | توکن ربات تلگرام |
| `MINIAPP_URL` | `https://telegram-card-game-bot-production.up.railway.app` |
| `DATABASE_PATH` | `game_bot.db` |
| `ADMIN_IDS` | شناسه ادمین‌ها |
| `WEB_API_HOST` | `0.0.0.0` |
| `WEB_API_PORT` | `5001` |

---

## مشکل باقیمانده برای حل

### مشکل: صفحه loading می‌ماند

**آخرین تغییرات اعمال شده (`miniapp/index.html`):**
```html
<!-- CSP برای اجازه دادن به eval -->
<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;">

<!-- مسیرهای absolute برای JS -->
<script src="/miniapp/api.js"></script>
<script src="/miniapp/screens/mode_select.js"></script>
...
<script src="/miniapp/app.js"></script>
```

**آخرین تغییرات اعمال شده (`miniapp/app.js`):**
```javascript
// اجرای فوری بدون DOMContentLoaded
async function initApp() {
  const tg = window.Telegram?.WebApp;
  if (tg) { tg.ready(); tg.expand(); }
  try { state.profile = await API.getProfile(); } catch(e) {}
  navigate("mode_select"); // این loading را جایگزین می‌کند
}
initApp();
```

### چیزهایی که باید بررسی شود
1. آیا بعد از deploy جدید، در Console مرورگر هنوز 404 می‌آید؟
2. آیا این URL مستقیم کار می‌کند: `https://telegram-card-game-bot-production.up.railway.app/miniapp/api.js`
3. آیا Flask مسیر `/miniapp/` را درست serve می‌کند؟

### بررسی Flask routing
در `miniapp_api.py`:
```python
app = Flask(__name__, static_folder="miniapp", static_url_path="/miniapp")

@app.route("/")
@app.route("/miniapp")
def serve_miniapp():
    return send_from_directory("miniapp", "index.html")
```

**احتمال مشکل:** وقتی Flask روی Railway اجرا می‌شود، مسیر `miniapp/` نسبی هست. اگه working directory متفاوت باشد، فایل‌ها پیدا نمی‌شوند.

**راه‌حل پیشنهادی:**
```python
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, 
    static_folder=os.path.join(BASE_DIR, "miniapp"), 
    static_url_path="/miniapp")
```

---

## تاریخچه commits مهم

```
e8701bf  fix: add CSP meta, absolute JS paths, restore Tailwind config
b905847  fix: use defer scripts and readyState check
7b92e51  fix: remove loading screen before API call
a9de49e  fix: read BOT_TOKEN/MINIAPP_URL from env vars; add WebAppInfo import
b491264  fix: call main() instead of bot.run() in run_all.py
cdeaa26  fix: pin Python 3.11 for Railway deploy
55e831a  fix: add Procfile and PORT env var
0905cbc  feat: add Mini App (Solo vs Aso) - Phase 3
```

---

## نکات مهم برای ادامه

1. **DB روی Railway موقتی است** — هر deploy دیتابیس reset می‌شود. برای production باید PostgreSQL اضافه شود.
2. **BOT_TOKEN در env var است** — در `game_config.json` نیست.
3. **فایل `game_config.json` در `.gitignore`** است — نباید به repo اضافه شود.
4. **Railway free tier** — بعد از ۵ دلار credit ماهانه، سرویس متوقف می‌شود.
