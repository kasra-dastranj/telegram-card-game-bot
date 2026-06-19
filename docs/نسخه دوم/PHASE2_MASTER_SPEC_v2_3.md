# 🎮 TelBattle Phase 2 - Master Specification Document
## نسخه جامع و کامل برای پیاده‌سازی

**تاریخ**: فوریه 2026  
**نسخه**: 2.3.0  
**وضعیت**: Production Ready — Added Migration + Stat Locking + Round Info Display

---

# 📑 فهرست مطالب

1. [چشم‌انداز کلی](#چشم‌انداز-کلی)
2. [سیستم کارت‌ها](#سیستم-کارتها)
3. [سیستم‌های مبارزه](#سیستمهای-مبارزه)
4. [سیستم اقتصاد و سکه](#سیستم-اقتصاد-و-سکه)
5. [سیستم پیشرفت (Level & Tier)](#سیستم-پیشرفت)
6. [جریان کامل بازی](#جریان-کامل-بازی)
7. [فرمول‌های ریاضی](#فرمولهای-ریاضی)
8. [Balancing و توازن](#balancing-و-توازن)

---

# 🎯 چشم‌انداز کلی

## تغییر ماهیت بازی

**فاز 1**: بازی PvP ساده با کارت‌های ثابت  
**فاز 2**: اکوسیستم کارت کلکسیونی با اقتصاد پویا

## اهداف اصلی فاز 2

1. ✅ ایجاد حس **ارزش واقعی** برای کارت‌ها
2. ✅ سیستم **پیشرفت بلندمدت** (Level & Tier)
3. ✅ اقتصاد **سالم و متوازن** (Coin Economy)
4. ✅ تنوع در **حالت‌های بازی** (Normal + Risk)
5. ✅ **عمق استراتژیک** بیشتر (۳ راوند، زمین بازی، تایپ کارت‌ها)

## اصول طراحی (Design Principles)

این اصول باید در تمام سیستم‌ها رعایت شوند:

1. **بدون تصادف ناعادلانه در پیشرفت** — Fusion کاملاً قطعی و تحت کنترل بازیکن است.
2. **بدون Claim Burn** — کلیم هرگز نباید ناموفق باشد یا هیچ چیز ندهد.
3. **Fusion قطعی و انتخابی** — بازیکن تصمیم می‌گیرد کدام کارت ارتقا یابد.
4. **لیگ فعالیت‌محور** — سیستم Tier باید فعالیت را پاداش دهد، نه موقعیت را.
5. **منصفانه و مهارت‌محور** — تمام مسیرهای پیشرفت باید احساس عادلانه بودن داشته باشند.

---

---

# 🔄 Migration از فاز ۱ به فاز ۲

> ⚠️ **مهم**: بازی در حال حاضر در حال اجرا است و کاربران فعلی کارت‌هایی دارند. قبل از راه‌اندازی فاز ۲، باید Migration اجرا شود.

## قوانین Migration

### ۱. تبدیل همه کارت‌ها به Normal

```
هدف: همه کاربران از یک نقطه شروع برابر آغاز کنند

قانون:
  - همه کارت‌های موجود کاربران → تبدیل به NORMAL
  - بدون توجه به rarity قبلی
  - آمار کارت‌ها از سیستم قدیمی (0-100) به سیستم جدید (0-10) تبدیل می‌شود
```

### ۲. فرمول تبدیل آمار

```python
def migrate_card_stats(old_stats: dict) -> dict:
    """
    تبدیل آمار از سیستم 0-100 به سیستم 0-10
    """
    new_stats = {}
    
    for stat_name, old_value in old_stats.items():
        # تبدیل خطی: 0-100 → 0-10
        new_value = round(old_value / 10)
        
        # محدود کردن به بازه 0-10
        new_value = max(0, min(10, new_value))
        
        new_stats[stat_name] = new_value
    
    return new_stats

# مثال:
# {power: 85, speed: 70, iq: 60, popularity: 90}
# → {power: 9, speed: 7, iq: 6, popularity: 9}
```

### ۳. تخصیص تایپ به کارت‌ها

```python
def assign_card_type(card_stats: dict) -> str:
    """
    تعیین تایپ کارت بر اساس بالاترین آمار
    """
    max_stat = max(card_stats, key=card_stats.get)
    
    type_mapping = {
        "power": "POWER_TYPE",
        "speed": "SPEED_TYPE",
        "iq": "IQ_TYPE",
        "popularity": "POPULARITY_TYPE"
    }
    
    return type_mapping.get(max_stat, "POWER_TYPE")

# مثال:
# {power: 9, speed: 7, iq: 6, popularity: 9}
# → max = power or popularity (تساوی)
# → POWER_TYPE (اولویت اول)
```

### ۴. Migration Script کامل

```python
def migrate_all_players():
    """
    Migration همه بازیکنان از فاز ۱ به فاز ۲
    """
    players = db.get_all_players()
    
    for player in players:
        # ۱. دریافت کارت‌های بازیکن
        player_cards = db.get_player_cards(player.user_id)
        
        # ۲. تبدیل هر کارت
        for card in player_cards:
            # تبدیل آمار
            new_stats = migrate_card_stats({
                "power": card.power,
                "speed": card.speed,
                "iq": card.iq,
                "popularity": card.popularity
            })
            
            # تعیین تایپ
            card_type = assign_card_type(new_stats)
            
            # بروزرسانی کارت
            db.update_card(
                card_id=card.card_id,
                rarity="NORMAL",  # همه Normal می‌شوند
                **new_stats,
                card_type=card_type
            )
        
        # ۳. Initialize Level & Tier
        db.create_player_progression(
            user_id=player.user_id,
            level=1,
            total_xp=0,
            tier_points=0,
            current_tier="Bronze"
        )
        
        # ۴. Initialize موجودی سکه (اگر وجود نداشت)
        if not hasattr(player, 'coins'):
            db.update_player(player.user_id, coins=0)
    
    print(f"✅ Migration کامل شد. {len(players)} بازیکن migrate شدند.")
```

### ۵. بررسی Integrity بعد از Migration

```python
def verify_migration():
    """
    اطمینان از صحت Migration
    """
    issues = []
    
    players = db.get_all_players()
    
    for player in players:
        cards = db.get_player_cards(player.user_id)
        
        # بررسی ۱: همه کارت‌ها Normal هستند؟
        non_normal = [c for c in cards if c.rarity != "NORMAL"]
        if non_normal:
            issues.append(f"Player {player.user_id}: {len(non_normal)} کارت Non-Normal")
        
        # بررسی ۲: آمار در بازه 0-10 هستند؟
        for card in cards:
            for stat in ["power", "speed", "iq", "popularity"]:
                value = getattr(card, stat)
                if not (0 <= value <= 10):
                    issues.append(f"Card {card.card_id}: {stat}={value} خارج از بازه")
        
        # بررسی ۳: تایپ تعیین شده؟
        for card in cards:
            if not hasattr(card, 'card_type') or not card.card_type:
                issues.append(f"Card {card.card_id}: تایپ تعیین نشده")
        
        # بررسی ۴: Level & Tier ایجاد شده؟
        progression = db.get_player_progression(player.user_id)
        if not progression:
            issues.append(f"Player {player.user_id}: Progression ایجاد نشده")
    
    if issues:
        print("❌ مشکلات یافت شد:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ Migration بدون مشکل انجام شد")
    
    return len(issues) == 0
```

### ۶. پیام اطلاع‌رسانی به کاربران

**قبل از Migration:**
```
📢 TelBattle فاز ۲ در راه است!

🔄 تغییرات مهم:
- همه کارت‌ها به Normal تبدیل می‌شوند
- سیستم جدید ارتقا (Fusion)
- سیستم Level & Tier
- اقتصاد سکه

⏰ زمان: [تاریخ دقیق]

📚 اطلاعات بیشتر: @TelBattle
```

**بعد از Migration:**
```
✨ به TelBattle فاز ۲ خوش آمدید!

🎉 تغییرات:
✅ کارت‌های شما به سیستم جدید migrate شدند
✅ همه در نقطه شروع برابر هستند
✅ از امروز می‌توانید با Fusion کارت‌ها را ارتقا دهید

🎁 هدیه راه‌اندازی:
- ۱۰۰ سکه رایگان
- ۳ کارت Normal اضافی

🚀 شروع کنید: /claim
```

---

# 🃏 سیستم کارت‌ها

## انواع کارت‌ها (Rarity)

### 1. Normal Cards
- **دریافت**: فقط از کلیم روزانه
- **آمار**: مجموع ۱۵-۳۰
- **قابلیت ارتقا**: بله (به Epic از طریق Fusion)
- **کمیابی**: معمولی

### 2. Epic Cards  
- **دریافت**: ارتقای Normal از طریق Fusion، خرید با سکه
- **آمار**: مجموع ۲۰-۳۰
- **قابلیت ارتقا**: بله (به Legend از طریق Fusion)
- **کمیابی**: متوسط

### 3. Legend Cards
- **دریافت**: ارتقای Epic از طریق Fusion، ماموریت خاص، خرید با سکه
- **آمار**: مجموع ۲۵-۳۵
- **قابلیت ارتقا**: خیر
- **کمیابی**: کمیاب

### 4. Rare Cards
- **دریافت**: فقط رتبه اول لیگ هفتگی، خرید محدود با سکه
- **آمار**: متغیر (طراحی خاص)
- **قابلیت ارتقا**: خیر (تکی هستند)
- **کمیابی**: بسیار کمیاب
- **ویژگی خاص**: تعداد محدود در کل بازی
- **ماینینگ**: ❌ سهمی در ماینینگ روزانه ندارد

## سیستم آمارگذاری کارت‌ها

### ویژگی‌های هر کارت (Stats)
```
{
  "power": 0-10,      // قدرت فیزیکی
  "speed": 0-10,      // سرعت
  "iq": 0-10,         // هوش
  "popularity": 0-10  // محبوبیت
}
```

### محدودیت‌های مجموع آمار
- **Normal**: sum(stats) = 15-30
- **Epic**: sum(stats) = 20-30  
- **Legend**: sum(stats) = 25-35
- **Rare**: طراحی دستی (خارج از محدودیت)

### تایپ کارت‌ها (Card Types)
هر کارت یک تایپ اصلی دارد:
- `POWER_TYPE`: متخصص قدرت (+۱ power در زمین قدرتی)
- `SPEED_TYPE`: متخصص سرعت (+۱ speed در زمین سرعتی)
- `IQ_TYPE`: متخصص هوش (+۱ iq در زمین فکری)
- `POPULARITY_TYPE`: متخصص محبوبیت (+۱ popularity در زمین محبوبیتی)

**نکته**: این تایپ در دیتابیس کارت ذخیره می‌شود و روی دیزاین کارت نمایش داده می‌شود. بوست فقط زمانی اعمال می‌شود که تایپ کارت با نوع زمین یکسان باشد **و** بازیکن همان stat متناظر را در آن راوند انتخاب کند.

---

## ✅ سیستم کلیم جدید (CORRECTED — v2.1)

> ⚠️ **تغییر کامل از نسخه قبلی**: سیستم وزن‌دهی ۹۰/۱۰ و مکانیزم ارتقای اتوماتیک از کلیم حذف شده‌اند. کلیم اکنون سیستم ساده، منصفانه، و بدون دستکاری احتمال است.

### قوانین کلیم روزانه

```
✅ هر روز فقط ۱ کارت کلیم می‌شود
✅ کلیم همیشه کارت NORMAL می‌دهد
✅ کلیم هرگز ناموفق نمی‌شود
✅ کلیم هرگز هیچ چیز نمی‌دهد — همیشه یک کارت قابل استفاده دریافت می‌شود
✅ همه کارت‌های Normal موجود در pool شانس برابر دارند
✅ هیچ وزن‌دهی پنهانی وجود ندارد
```

### قوانین Pool کلیم

```
📌 قوانین pool کلیم:

1. اگر بازیکن یک کارت را در حالت Normal دارد:
   → کارت همچنان در pool باقی می‌ماند (می‌تواند دوباره دریافت شود)
   → اگر دریافت شد، دوباره Normal اضافه می‌شود

2. اگر بازیکن یک کارت را در حالت Epic دارد:
   → آن کارت از pool کلیم حذف می‌شود
   → نسخه Normal آن کارت دیگر از کلیم دریافت نمی‌شود
   → این کارت "فعلاً خارج از pool" است

3. اگر بازیکن یک کارت را در حالت Legend دارد:
   → آن کارت از pool کلیم حذف می‌شود
   → هیچ نسخه‌ای از این کارت از طریق کلیم در دسترس نیست

4. اگر ۳ کارت Normal از طریق Fusion به یک Epic تبدیل شوند:
   → ۳ کارت Normal از موجودی بازیکن حذف می‌شوند
   → آن ۳ کارت به global claim pool بازمی‌گردند
   → بازیکن می‌تواند در آینده دوباره آن‌ها را کلیم کند

5. کلیم هرگز نباید pool خالی داشته باشد:
   → اگر همه کارت‌ها در Epic یا Legend هستند، سیستم باید یک کارت Normal جایگزین ارائه دهد
   → در این حالت، کارت‌هایی که در حال حاضر Normal در موجودی دارند نیز مجاز هستند وارد pool شوند
```

### الگوریتم کلیم (Equal Probability)

```python
def get_claimable_cards(user_id: int) -> list:
    """
    برمی‌گرداند لیست کارت‌هایی که بازیکن می‌تواند کلیم کند.
    
    کارتی در pool است اگر:
    - بازیکن آن را در حالت EPIC یا LEGEND ندارد
    
    کارتی از pool خارج است اگر:
    - بازیکن همان کارت را در حالت EPIC دارد
    - بازیکن همان کارت را در حالت LEGEND دارد
    """
    all_cards = get_all_normal_card_definitions()
    player_owned_epic_or_legend = get_player_cards_with_rarity(user_id, ["EPIC", "LEGEND"])
    
    excluded_card_ids = {card.card_id for card in player_owned_epic_or_legend}
    
    claimable = [card for card in all_cards if card.card_id not in excluded_card_ids]
    
    if not claimable:
        # fallback: اگر همه کارت‌ها در سطح بالا هستند
        # کارت‌هایی که بازیکن در حالت Normal دارد اضافه می‌کنیم
        claimable = get_player_cards_with_rarity(user_id, ["NORMAL"])
    
    return claimable

def perform_claim(user_id: int) -> Card:
    """
    انتخاب یک کارت با احتمال برابر از pool.
    هیچ وزن‌دهی پنهانی وجود ندارد.
    """
    pool = get_claimable_cards(user_id)
    
    # احتمال برابر — بدون دستکاری
    selected_card = random.choice(pool)
    
    # اضافه کردن کارت به موجودی بازیکن (Normal)
    add_card_to_player(user_id, selected_card.card_id, rarity="NORMAL")
    
    return selected_card
```

### مثال جریان کلیم

```
Day 1:  کلیم → John Wick (Normal) → موجود در کارکرد عادی
Day 3:  کلیم → Walter White (Normal) → کارت جدید اضافه شد
Day 7:  کلیم → John Wick (Normal) → John Wick دوم اضافه شد (pool شامل اوست)
Day 10: Fusion: John Wick + Walter White + Rehi → John Wick انتخاب شد → Epic
         هر سه کارت از موجودی حذف شدند
         هر سه به global pool بازگشتند
Day 11: کلیم → John Wick اکنون از pool خارج است (بازیکن Epic دارد)
         از سایر کارت‌های موجود در pool انتخاب می‌شود
```

---

## ✅ سیستم Fusion (CORRECTED — v2.1)

> ⚠️ **تغییر کامل از نسخه قبلی**: Fusion رندوم حذف شده است. بازیکن کاملاً کنترل دارد که کدام کارت ارتقا یابد. هیچ شانس شکست وجود ندارد. Legend همیشه تضمین می‌شود.

### اصول کلی Fusion

```
✅ بازیکن دقیقاً ۳ کارت انتخاب می‌کند
✅ بازیکن تصمیم می‌گیرد کدام یک از ۳ کارت ارتقا یابد
✅ هر ۳ کارت مصرف می‌شوند (از موجودی حذف می‌شوند)
✅ کارت انتخاب‌شده ارتقا می‌یابد
✅ موفقیت ۱۰۰٪ تضمین است — هیچ شانس شکستی وجود ندارد
✅ هیچ رندومی در این فرآیند وجود ندارد
```

---

### 🔹 Normal → Epic Fusion

#### قوانین
```
ورودی:    دقیقاً ۳ کارت NORMAL
کنترل:    بازیکن انتخاب می‌کند کدام یک Epic شود
خروجی:    ۱ کارت EPIC (همانی که بازیکن انتخاب کرد)
مصرف:     هر ۳ کارت Normal از موجودی حذف می‌شوند
نرخ موفقیت: ۱۰۰٪ — همیشه موفق
تصادف:   صفر — کاملاً قطعی
```

#### جریان کامل Normal → Epic Fusion

```
مرحله ۱: بازیکن گزینه Fusion را باز می‌کند
  ↓
مرحله ۲: سیستم لیست کارت‌های Normal بازیکن را نشان می‌دهد
  ↓
مرحله ۳: بازیکن دقیقاً ۳ کارت Normal انتخاب می‌کند
          (هر ۳ کارت می‌توانند مختلف یا یکسان باشند)
  ↓
مرحله ۴: سیستم می‌پرسد: "کدام کارت را می‌خواهی Epic شود؟"
          → نمایش ۳ کارت انتخاب‌شده به عنوان گزینه
  ↓
مرحله ۵: بازیکن یک کارت از آن ۳ را به عنوان کارت ارتقایافته انتخاب می‌کند
  ↓
مرحله ۶: سیستم تأیید نهایی می‌خواهد:
          "⚠️ هر ۳ کارت مصرف می‌شوند. [کارت انتخاب‌شده] Epic می‌شود. ادامه دهی؟"
  ↓
مرحله ۷: بازیکن تأیید می‌کند
  ↓
مرحله ۸: سیستم عملیات را انجام می‌دهد:
          - هر ۳ کارت Normal از موجودی بازیکن حذف می‌شوند
          - کارت انتخاب‌شده در حالت Epic به موجودی اضافه می‌شود
          - ۲ کارت دیگر به global claim pool بازمی‌گردند
  ↓
مرحله ۹: نتیجه نمایش داده می‌شود:
          "✨ Fusion موفق!
          کارت‌های مصرف‌شده: [کارت A], [کارت B], [کارت C]
          کارت Epic شما: [کارت انتخاب‌شده] 🎉"
```

#### مثال کامل

```
بازیکن دارد:
  - John Wick (Normal)
  - Walter White (Normal)
  - Rehi (Normal)

بازیکن انتخاب می‌کند: هر ۳ کارت برای Fusion

سیستم می‌پرسد: "کدام یک Epic شود؟"
  → [John Wick] [Walter White] [Rehi]

بازیکن انتخاب می‌کند: John Wick

نتیجه:
  - John Wick (Normal) ❌ مصرف شد
  - Walter White (Normal) ❌ مصرف شد → به pool بازمی‌گردد
  - Rehi (Normal) ❌ مصرف شد → به pool بازمی‌گردد
  - John Wick (Epic) ✅ اضافه شد
```

---

### 🔹 Epic → Legend Fusion

#### قوانین
```
ورودی:    دقیقاً ۳ کارت EPIC
کنترل:    بازیکن انتخاب می‌کند کدام یک Legend شود
خروجی:    ۱ کارت LEGEND (همانی که بازیکن انتخاب کرد)
مصرف:     هر ۳ کارت Epic از موجودی حذف می‌شوند
نرخ موفقیت: ۱۰۰٪ — همیشه موفق
تصادف:   صفر — کاملاً قطعی
شکست:    وجود ندارد — Legend همیشه اعطا می‌شود
```

#### جریان کامل Epic → Legend Fusion

```
مرحله ۱: بازیکن گزینه Fusion را باز می‌کند
  ↓
مرحله ۲: سیستم لیست کارت‌های Epic بازیکن را نشان می‌دهد
  ↓
مرحله ۳: بازیکن دقیقاً ۳ کارت Epic انتخاب می‌کند
          (هر ۳ کارت می‌توانند مختلف یا یکسان باشند)
  ↓
مرحله ۴: سیستم می‌پرسد: "کدام کارت را می‌خواهی Legend شود؟"
          → نمایش ۳ کارت انتخاب‌شده به عنوان گزینه
  ↓
مرحله ۵: بازیکن یک کارت از آن ۳ را به عنوان کارت ارتقایافته انتخاب می‌کند
  ↓
مرحله ۶: سیستم تأیید نهایی می‌خواهد:
          "⚠️ هر ۳ کارت Epic مصرف می‌شوند. [کارت انتخاب‌شده] Legend می‌شود. ادامه دهی؟"
  ↓
مرحله ۷: بازیکن تأیید می‌کند
  ↓
مرحله ۸: سیستم عملیات را انجام می‌دهد:
          - هر ۳ کارت Epic از موجودی بازیکن حذف می‌شوند
          - کارت انتخاب‌شده در حالت Legend به موجودی اضافه می‌شود
  ↓
مرحله ۹: نتیجه نمایش داده می‌شود:
          "🌟 Fusion Legend موفق!
          کارت‌های Epic مصرف‌شده: [کارت A], [کارت B], [کارت C]
          کارت Legend شما: [کارت انتخاب‌شده] 👑"
```

#### مثال کامل

```
بازیکن دارد:
  - John Wick (Epic)
  - Heisenberg (Epic)
  - Joker (Epic)

بازیکن انتخاب می‌کند: هر ۳ کارت برای Fusion

سیستم می‌پرسد: "کدام یک Legend شود؟"
  → [John Wick] [Heisenberg] [Joker]

بازیکن انتخاب می‌کند: Heisenberg

نتیجه:
  - John Wick (Epic) ❌ مصرف شد
  - Heisenberg (Epic) ❌ مصرف شد
  - Joker (Epic) ❌ مصرف شد
  - Heisenberg (Legend) ✅ اضافه شد
  Legend همیشه تضمین است — هیچ شانس شکستی وجود ندارد.
```

---

### قوانین بازگشت به Pool پس از Fusion

```
Normal → Epic Fusion:
  - کارت انتخاب‌شده → Epic (در موجودی بازیکن)
  - ۲ کارت دیگر → به global claim pool بازمی‌گردند
  - این ۲ کارت دیگر از موجودی بازیکن حذف شده‌اند
  - بازیکن می‌تواند آن‌ها را در آینده دوباره کلیم کند

Epic → Legend Fusion:
  - کارت انتخاب‌شده → Legend (در موجودی بازیکن)
  - ۲ کارت Epic دیگر کاملاً حذف می‌شوند (به pool بازنمی‌گردند، چون Epic بودند)
  - Pool فقط برای Normal cards اعمال می‌شود
```

### ساختار دیتابیس Fusion

```sql
-- لاگ Fusion برای شفافیت کامل
CREATE TABLE fusion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    fusion_type TEXT NOT NULL,          -- 'NORMAL_TO_EPIC' یا 'EPIC_TO_LEGEND'
    consumed_card_1 TEXT NOT NULL,      -- card_id کارت مصرف‌شده اول
    consumed_card_2 TEXT NOT NULL,      -- card_id کارت مصرف‌شده دوم
    consumed_card_3 TEXT NOT NULL,      -- card_id کارت مصرف‌شده سوم
    upgraded_card_id TEXT NOT NULL,     -- card_id کارتی که بازیکن انتخاب کرد
    result_rarity TEXT NOT NULL,        -- 'EPIC' یا 'LEGEND'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## سیستم ارتقای کارت‌ها (سایر روش‌ها)

### ۱. Normal → Epic (از طریق خرید)
- ✅ خرید مستقیم با سکه (۱۰۰ سکه)

### ۲. Epic → Legend (از طریق خرید یا ماموریت)
- ✅ پرداخت سکه (۵۰۰ سکه)
- ✅ انجام ماموریت اختصاصی کارت

### ماموریت‌های اختصاصی کارت‌ها

هر کارت یک ماموریت خاص برای Legend شدن دارد:

**مثال‌ها**:
```json
{
  "john_wick": {
    "mission": "با این کارت ۲۰ برد سرعتی بگیر",
    "progress_type": "speed_wins",
    "target": 20
  },
  "heisenberg": {
    "mission": "با این کارت Walter White را ۳ بار شکست بده",
    "progress_type": "defeat_specific",
    "target": "walter_white",
    "count": 3
  },
  "rehi": {
    "mission": "۱۵ بار مود Risk را با این کارت ببر",
    "progress_type": "risk_wins",
    "target": 15
  }
}
```

**ساختار Mission Progress در دیتابیس**:
```sql
CREATE TABLE card_missions (
    user_id INTEGER,
    card_id TEXT,
    mission_type TEXT,
    current_progress INTEGER DEFAULT 0,
    target INTEGER,
    completed BOOLEAN DEFAULT 0,
    PRIMARY KEY (user_id, card_id)
);
```

---

## سیستم اسکین

### تعریف اسکین
- **اسکین فقط ظاهر کارت را عوض می‌کند**
- هیچ تاثیری بر آمار (stats) ندارد
- هر کارت می‌تواند چندین اسکین داشته باشد

### انواع اسکین‌ها
```
- فصلی (نوروز، هالووین، کریسمس)
- ویژه (خرید با سکه)
- رایگان (ایونت‌های خاص)
```

### ساختار اسکین در دیتابیس
```sql
CREATE TABLE player_skins (
    user_id INTEGER,
    card_id TEXT,
    skin_id TEXT,
    unlocked BOOLEAN DEFAULT 1,
    PRIMARY KEY (user_id, card_id, skin_id)
);

CREATE TABLE active_skins (
    user_id INTEGER,
    card_id TEXT,
    skin_id TEXT,
    PRIMARY KEY (user_id, card_id)
);
```

---

# ⚔️ سیستم‌های مبارزه

## ۱. Normal Battle (بازی نرمال ۳ راوندی)

### ساختار کلی
```
بازی = Best of 3 Rounds
هر راوند = مقایسه یک ویژگی
برنده نهایی = کسی که ۲ راوند ببرد

⭐ ویژگی جدید فاز ۲: قفل ویژگی‌های استفاده شده
```

### 🔒 سیستم قفل ویژگی (Stat Locking)

```
قانون کلی:
  - وقتی بازیکنی یک ویژگی انتخاب می‌کند، آن ویژگی برای خودش قفل می‌شود
  - ویژگی قفل شده در راوندهای بعدی توسط همان بازیکن قابل انتخاب نیست
  - حریف می‌تواند ویژگی قفل شده شما را انتخاب کند
  - اگر حریف ویژگی قفل شده شما را انتخاب کند، آن ویژگی وارد بازی می‌شود

مثال:
  راوند ۱: من "power" انتخاب می‌کنم → power برای من قفل شد
  راوند ۲: من دیگر نمی‌توانم power انتخاب کنم
           ولی حریف می‌تواند power انتخاب کند
           اگر حریف power انتخاب کند، power من هم وارد محاسبه می‌شود
```

**جدول قفل ویژگی**:
```
راوند ۱: هیچ چیز قفل نیست
  → هر دو بازیکن می‌توانند هر ۴ ویژگی را انتخاب کنند

راوند ۲: ویژگی راوند ۱ قفل است
  → من: power, speed, iq, popularity
     اگر در راوند ۱ "power" انتخاب کردم:
     حالا فقط می‌توانم: speed, iq, popularity انتخاب کنم
  
  → حریف: power, speed, iq, popularity
     حریف همچنان می‌تواند "power" انتخاب کند

راوند ۳: ویژگی‌های راوند ۱ و ۲ قفل هستند
  → من: اگر در راوند ۱ "power" و در راوند ۲ "speed" انتخاب کردم
     فقط می‌توانم: iq, popularity انتخاب کنم
```

**مکانیزم در بازی**:
```python
# ذخیره انتخاب‌های قبلی
fight_state = {
    "challenger_used_stats": [],  # ["power", "speed"]
    "opponent_used_stats": []     # ["iq"]
}

def get_available_stats(user_id, fight_id) -> list:
    """
    ویژگی‌های قابل انتخاب برای بازیکن
    """
    all_stats = ["power", "speed", "iq", "popularity"]
    used_stats = fight_state.get(f"{user_id}_used_stats", [])
    
    available = [s for s in all_stats if s not in used_stats]
    return available

# مثال:
# راوند ۱: من power انتخاب کردم
# راوند ۲: available = ["speed", "iq", "popularity"]
```

**نمایش UI**:
```
راوند ۲: انتخاب ویژگی

ویژگی‌های شما:
  [⚡ قدرت: 8] ❌ قفل شده
  [🏃 سرعت: 7] ✅
  [🧠 هوش: 6] ✅
  [⭐ محبوبیت: 9] ✅
  
انتخاب کنید: [🏃 سرعت] [🧠 هوش] [⭐ محبوبیت]
```

---

### 📊 نمایش اطلاعات بعد از هر راوند

**هدف**: استراتژیک شدن بازی با دادن اطلاعات کافی بدون افشای کارت حریف

```
بعد از هر راوند، در PV هر بازیکن نمایش داده می‌شود:

┏━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  📊 نتیجه راوند ۱      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━┛

🎴 کارت شما: John Wick (Epic)
🎴 کارت حریف: ??? (Epic)

⚔️ ویژگی انتخابی:
  شما: ⚡ قدرت
  حریف: ⚡ قدرت

📈 آمار:
  شما: 8 + 1 (زمین) = 9
  حریف: 7 + 0 = 7

🏆 برنده: شما!
💥 کاهش: قدرت شما 9 → 7

🔒 قفل شده برای راوند بعد:
  - قدرت (شما)
  - [ویژگی حریف نمایش داده نمی‌شود]

امتیاز کلی: شما ۱ - حریف ۰
```

**اطلاعاتی که نمایش داده می‌شود**:
```
✅ رریتی کارت حریف (Epic/Legend/Normal)
✅ ویژگی انتخابی حریف
✅ عدد ویژگی حریف (مقدار دقیق)
✅ تاثیر زمین (+ boost)
✅ برنده راوند
✅ کاهش آمار برنده
✅ امتیاز کلی

❌ نام کارت حریف (تا پایان بازی مخفی است)
❌ سایر آمار کارت حریف
❌ ویژگی‌های قفل شده حریف
```

**مثال کامل ۳ راوند**:
```
━━━━━━━━━━━━━━━━━━━━━━
     📊 راوند ۱
━━━━━━━━━━━━━━━━━━━━━━
شما: John Wick (Epic)
حریف: ??? (Legend)

انتخاب:
  شما: ⚡ قدرت
  حریف: ⚡ قدرت

آمار:
  شما: 8 + 1 (زمین) = 9
  حریف: 9 + 0 = 9

🤝 مساوی! هر دو 1 واحد کم می‌شود
💥 قدرت شما: 9 → 8
💥 قدرت حریف: 9 → 8

امتیاز: ۰-۰

━━━━━━━━━━━━━━━━━━━━━━
     📊 راوند ۲
━━━━━━━━━━━━━━━━━━━━━━
انتخاب:
  شما: 🏃 سرعت
  حریف: 🧠 هوش

آمار:
  شما (سرعت): 7 + 0 = 7
  حریف (هوش): 8 + 0 = 8

🏆 حریف برنده!
💥 هوش حریف: 8 → 6

امتیاز: ۰-۱

━━━━━━━━━━━━━━━━━━━━━━
     📊 راوند ۳
━━━━━━━━━━━━━━━━━━━━━━
انتخاب:
  شما: 🧠 هوش
  حریف: ⚡ قدرت (قفل شده شما!)

آمار:
  شما (هوش): 6 + 0 = 6
  حریف (قدرت): 8 + 0 = 8

🏆 حریف برنده!

━━━━━━━━━━━━━━━━━━━━━━
     🏁 نتیجه نهایی
━━━━━━━━━━━━━━━━━━━━━━
💀 شما باختید: ۰-۲

کارت حریف: Heisenberg (Legend)
```

---

### جریان کامل یک بازی Normal

#### مرحله ۱: شروع چالش
```
Challenger در گروه: /fight
  → سیستم: ایجاد fight_id
  → ارسال دکمه "قبول چالش" در گروه
```

#### مرحله ۲: قبول چالش
```
Opponent: کلیک "قبول چالش"
  → سیستم: claim_opponent_if_waiting(fight_id, opponent_id)
  → ارسال پیام در PV هر دو نفر: "انتخاب کارت"
```

#### مرحله ۳: انتخاب کارت
```
هر بازیکن در PV خود:
  → لیست کارت‌های خود (با pagination)
  → انتخاب کارت
  → سیستم: ذخیره card_id

وقتی هر دو انتخاب کردند:
  → تشخیص رریتی کارت‌ها
  → تعیین چه کسی زمین انتخاب می‌کند
```

#### مرحله ۴: انتخاب زمین

**قانون**:
```
IF challenger_rarity < opponent_rarity:
    challenger انتخاب می‌کند
ELIF opponent_rarity < challenger_rarity:
    opponent انتخاب می‌کند  
ELSE:
    زمین به صورت RANDOM انتخاب می‌شود
```

**رریتی برای مقایسه**:
```
NORMAL = 1
EPIC = 2
LEGEND = 3
RARE = 4
```

**زمین‌های موجود**:
```json
{
  "power_arena":    {"boosts": {"power": 1}},
  "speed_track":    {"boosts": {"speed": 1}},
  "thinking_room":  {"boosts": {"iq": 1}},
  "stage":          {"boosts": {"popularity": 1}}
}
```

#### مرحله ۵: راوند ۱

```
هر بازیکن در PV:
  → نمایش آمار کارت خود
  → نمایش ویژگی‌های قابل انتخاب (همه ۴ ویژگی در راوند ۱)
  → انتخاب ویژگی (power / speed / iq / popularity)
  → سیستم: ذخیره selected_stat + اضافه به used_stats
  
وقتی هر دو انتخاب کردند:
  → محاسبه stats با boost زمین
  → مقایسه
  → تعیین برنده راوند
  → کاهش stat:
      - اگر تساوی: هر دو 1 واحد کم می‌شود
      - اگر برد: برنده 1-2 واحد (بسته به اختلاف) کم می‌شود
  → ارسال اطلاعات کامل راوند در PV هر دو نفر
```

**فرمول کاهش**:
```python
def reduce_stat(stat_value, win_margin, is_tie=False):
    if is_tie:
        reduction = 1  # تساوی: هر دو 1 واحد
    elif win_margin >= 5:
        reduction = 2  # اختلاف زیاد
    else:
        reduction = 1  # اختلاف کم
    
    return max(0, stat_value - reduction)
```

**اطلاعات ارسالی بعد از راوند**:
```
📊 نتیجه راوند ۱

🎴 کارت شما: {your_card} ({your_rarity})
🎴 کارت حریف: ??? ({opponent_rarity})

⚔️ ویژگی انتخابی:
  شما: {your_stat_name}
  حریف: {opponent_stat_name}

📈 آمار:
  شما: {base} + {boost} (زمین) = {total}
  حریف: {base} + {boost} = {total}

🏆 {result}  // "شما برنده!" / "حریف برنده!" / "مساوی!"
💥 کاهش: {reduction_info}

🔒 قفل شده: {locked_stat}

امتیاز: {challenger_score} - {opponent_score}
```
    
    return max(0, stat_value - reduction)
```

#### مرحله ۶: راوند ۲ و ۳

```
همان فرآیند راوند ۱ تکرار می‌شود
با این تفاوت‌ها:
  
  ✅ Stats کاهش یافته از راوند قبل استفاده می‌شود
  ✅ ویژگی‌های قفل شده قابل انتخاب نیستند
  ✅ UI فقط ویژگی‌های available را نمایش می‌دهد
  
  مثال راوند ۲:
    من در راوند ۱ "power" انتخاب کردم
    → دکمه‌های موجود: [🏃 سرعت] [🧠 هوش] [⭐ محبوبیت]
    → دکمه power غیرفعال یا مخفی است
    
  مثال راوند ۳:
    من در راوند ۱ "power" و راوند ۲ "speed" انتخاب کردم
    → دکمه‌های موجود: [🧠 هوش] [⭐ محبوبیت]
  
  ⚠️ نکته استراتژیک: 
    اگر حریف ویژگی قفل شده من را انتخاب کند،
    آن ویژگی همچنان وارد محاسبه می‌شود!
    
    مثال: من "power" را در راوند ۱ استفاده کردم (قدرت=8)
           در راوند ۲ حریف "power" انتخاب می‌کند
           → power من (8) با power حریف مقایسه می‌شود
```

**بررسی پایان زودهنگام**:
```python
if challenger_rounds_won == 2 or opponent_rounds_won == 2:
    # برنده نهایی مشخص شد
    skip_to_final_result()
else:
    # ادامه به راوند بعد
    continue_to_next_round()
```

#### مرحله ۷: تعیین برنده نهایی

```
IF challenger_rounds_won >= 2:
    winner = challenger
ELIF opponent_rounds_won >= 2:
    winner = opponent
```

#### مرحله ۸: پاداش‌دهی

**برنده**:
```
+ امتیاز بر اساس تفاوت رریتی (۵-۲۰)
+ XP (۱۰ XP)
+ سکه بر اساس امتیاز (هر ۱۰۰ امتیاز = ۱ سکه)
+ افزایش Tier Points
```

**بازنده**:
```
- ۱ قلب (Heart)
+ XP (۳ XP برای تلاش)
- کاهش Tier Points
```

#### مرحله ۹: اعلام نتایج

```
در گروه:
  → تصویر کارت برنده
  → نام برنده و بازنده
  → امتیاز کسب شده
  → آمار بازی (۳ راوند چطور پیش رفت)
```

---

## ۲. Risk Battle (بازی شرط‌بندی)

### پیش‌نیاز ورود به Risk
```
✅ Level >= 7
✅ حداقل سکه بر اساس میز:
   - میز ۵۰ سکه‌ای: ۳۰۰ سکه
   - میز ۱۰۰ سکه‌ای: ۶۰۰ سکه
   - میز ۳۰۰ سکه‌ای: ۱۵۰۰ سکه
```

### ساختار Risk Battle

```
ورودیه میز: ۵۰ / ۱۰۰ / ۳۰۰ سکه
سقف Raise: ۶x ورودیه اولیه
مثال: میز ۵۰ → حداکثر ۳۰۰ سکه در پات
```

### جریان کامل Risk Battle

#### مرحله ۱: شروع
```
Challenger: انتخاب میز (۵۰/۱۰۰/۳۰۰)
  → سیستم: قفل کردن ورودیه از کیف هر دو نفر
  → Current Pot = ۲ × ورودیه
```

#### مرحله ۲: دریافت کارت‌ها
```
سیستم به هر بازیکن ۳ کارت RANDOM می‌دهد
بازیکن‌ها کارت‌های خود را می‌بینند ولی حریف نمی‌بیند
```

#### مرحله ۳: راوند ۱

```
هر بازیکن یک کارت انتخاب می‌کند
سیستم یک ویژگی RANDOM انتخاب می‌کند
مقایسه و تعیین برنده راوند
```

**فرصت Raise بعد از دیدن کارت‌ها**:
```
هر بازیکن می‌تواند:
  ۱. FOLD (انصراف) → باخت فوری، پات به حریف
  ۲. CALL (ادامه بدون raise)
  ۳. RAISE (افزایش شرط تا ۳x ورودیه اولیه)
```

#### مرحله ۴: Bluff System

**قوانین Bluff**:
```
- اگر بازیکن RAISE بدهد و حریف CALL کند:
    → هر دو وارد حالت "Committed" می‌شوند
    → اگر یکی دوباره RAISE بدهد، دیگری باید CALL یا FOLD کند
    → FOLD = باخت فوری

- اگر بازیکن RAISE بدهد و حریف FOLD کند:
    → بازیکن raise‌دهنده برنده می‌شود (بدون ادامه بازی)
    → کل پات را می‌برد

- اگر هیچکس RAISE نداد:
    → بازی به صورت نرمال ادامه می‌یابد
```

#### مرحله ۵: راوند ۲ و ۳
```
همان فرآیند راوند ۱
با فرصت Raise بعد از هر راوند
```

#### مرحله ۶: پاداش‌دهی

**برنده**:
```
+ کل سکه‌های پات
+ XP (۲۵ XP)
+ امتیاز ویژه Risk (۳۰ امتیاز)
+ Tier Points بیشتر
```

**بازنده**:
```
- کل سکه‌های شرط زده شده
- ۱ قلب
+ XP (۵ XP)
```

---

# 💰 سیستم اقتصاد و سکه

## منابع سکه (Coin Sources)

### ۱. از بازی‌ها
```
برد Normal: ۰ سکه مستقیم (فقط امتیاز)
برد Risk: مقدار پات (۵۰-۳۰۰+)
تبدیل امتیاز: هر ۱۰۰ امتیاز = ۱ سکه
```

### ۲. ماینینگ روزانه کارت‌ها

```
✅ هر ۵ کارت (Normal، Epic، یا Legend) = ۱ سکه در روز
✅ کارت‌های Rare هیچ سهمی در ماینینگ ندارند
✅ محاسبه بر اساس تعداد کل کارت‌های موجودی (نه منحصربفرد)
✅ هیچ سقف روزانه‌ای وجود ندارد
✅ دلیل عدم سقف: تعداد کل کارت‌های قابل نگهداری در بازی محدود است
   (inventory cap)، بنابراین ماینینگ نمی‌تواند بی‌نهایت رشد کند

فرمول: floor(تعداد_کل_کارت_بدون_Rare / 5) سکه در روز

مثال‌ها:
  - ۴۹ کارت (Normal/Epic/Legend) → 49 // 5 = 9 سکه/روز
  - ۱۰۰ کارت (Normal/Epic/Legend) → 100 // 5 = 20 سکه/روز
  - ۱۰ کارت + ۵ کارت Rare → 10 // 5 = 2 سکه/روز (Rare حساب نمی‌شود)

⚠️ نکته درباره Rare:
  - کارت‌های Rare در حال حاضر هیچ سهمی در ماینینگ ندارند.
  - امکان درآمد جداگانه برای Rare در آینده (فاز ۳) بررسی می‌شود، اما در سیستم فعلی اعمال نمی‌شود.
```

### ۳. لیدربرد هفتگی
```
رتبه ۱: ۱۰۰ سکه + ۱ Rare Card
رتبه ۲: ۵۰ سکه
رتبه ۳: ۳۰ سکه
رتبه ۴-۱۰: ۱۰ سکه
```

### ۴. ایونت‌ها و چالش‌ها
```
طراحی دستی توسط ادمین
مثال: "این هفته ۱۰ برد بگیر → ۵۰ سکه"
```

### ۵. خرید مستقیم
```
از طریق ادمین (فعلاً دستی)
نرخ‌های پیشنهادی:
  ۵۰۰ سکه = ۱۰,۰۰۰ تومان
  ۱۰۰۰ سکه = ۱۸,۰۰۰ تومان
  ۳۰۰۰ سکه = ۵۰,۰۰۰ تومان
```

## مصارف سکه (Coin Sinks)

### ۱. ارتقای کارت‌ها
```
Normal → Epic: ۱۰۰ سکه
Epic → Legend: ۵۰۰ سکه
```

### ۲. خرید کارت‌های Rare
```
قیمت متغیر بر اساس کمیابی
مثال: ۸۰۰-۲۰۰۰ سکه
```

### ۳. افزایش سقف قلب
```
+۱ قلب دائمی: ۲۰۰ سکه
حداکثر: ۱۵ قلب (۵ خرید)
```

### ۴. خرید اسکین
```
اسکین عادی: ۵۰ سکه
اسکین ویژه: ۱۵۰ سکه
اسکین فصلی: ۱۰۰ سکه
```

### ۵. ورود به Risk
```
هزینه‌ای ندارد، فقط level و موجودی کافی
```

### ۶. کارت سفارشی گروه
```
طراحی + اضافه کردن: ۵۰۰ سکه
(فقط در گروه خودشان قابل استفاده)
```

---

# 📊 سیستم پیشرفت (Level & Tier)

## سیستم Level

### تعریف
```
Level = شاخص دائمی پیشرفت
- هیچوقت پایین نمی‌آید
- فقط با XP بالا می‌رود
- از ۱ تا ۳۰
```

### منابع XP

```python
XP_SOURCES = {
    "normal_win": 10,
    "normal_loss": 3,
    "risk_win": 25,
    "risk_loss": 5,
    "card_upgrade_to_epic": 15,
    "card_upgrade_to_legend": 30,
    "daily_quest": 20,
    "weekly_top1": 100,
    "weekly_top2": 50,
    "weekly_top3": 30
}
```

### فرمول XP مورد نیاز برای هر لول

```python
def xp_for_level(level):
    if level == 1:
        return 100
    return 100 + (level - 1) * 50
```

### جدول کامل Level (۱ تا ۳۰)

```
Level 1:  0 XP     | برنز
Level 2:  100 XP   | برنز
Level 3:  250 XP   | برنز
Level 4:  450 XP   | برنز  
Level 5:  700 XP   | برنز
Level 6:  1000 XP  | سیلور
Level 7:  1350 XP  | سیلور ← Risk باز می‌شود
Level 8:  1750 XP  | سیلور
Level 9:  2200 XP  | سیلور
Level 10: 2700 XP  | سیلور
Level 11: 3250 XP  | گلد
Level 12: 3850 XP  | گلد
Level 13: 4500 XP  | گلد
Level 14: 5200 XP  | گلد
Level 15: 5950 XP  | گلد
Level 16: 6750 XP  | دایموند
Level 17: 7600 XP  | دایموند
Level 18: 8500 XP  | دایموند
Level 19: 9450 XP  | دایموند
Level 20: 10450 XP | دایموند
Level 21: 11500 XP | الایت
Level 22: 12600 XP | الایت
Level 23: 13750 XP | الایت
Level 24: 14950 XP | الایت
Level 25: 16200 XP | الایت
Level 26: 17500 XP | الایت
Level 27: 18850 XP | الایت
Level 28: 20250 XP | الایت
Level 29: 21700 XP | الایت
Level 30: 23200 XP | الایت (حداکثر)
```

---

## ✅ سیستم Tier و Decay (CORRECTED — v2.1)

> ⚠️ **تغییر کامل از نسخه قبلی**: Diamond و Elite دیگر از Decay معاف نیستند. تمام Tier ها Decay دارند اما با مدت حفاظت متفاوت. این سیستم فعالیت را پاداش می‌دهد، نه موقعیت را.

### تعریف
```
Tier = رتبه فعلی بازیکن بر اساس عملکرد اخیر
- با برد بالا می‌رود
- با باخت پایین می‌آید
- با بی‌فعالیت برای همه Tier ها Decay می‌شود
```

### سطوح Tier

```
Bronze:   0-499 TP
Silver:   500-999 TP
Gold:     1000-1499 TP
Diamond:  1500-1999 TP
Elite:    2000+ TP
```

**TP = Tier Points**

### فرمول محاسبه Tier Points

```python
def calculate_tp_change(winner_tier, loser_tier, is_risk=False):
    """
    محاسبه تغییر TP بر اساس تفاوت tier
    """
    base_gain = 15 if not is_risk else 25
    base_loss = 10 if not is_risk else 15
    
    tier_diff = abs(winner_tier - loser_tier)
    
    if winner_tier < loser_tier:  # شکست دادن بازیکن قوی‌تر
        gain = base_gain + tier_diff * 5
        loss = max(5, base_loss - tier_diff * 2)
    elif winner_tier > loser_tier:  # شکست دادن بازیکن ضعیف‌تر
        gain = max(5, base_gain - tier_diff * 2)
        loss = base_loss + tier_diff * 3
    else:  # tier یکسان
        gain = base_gain
        loss = base_loss
    
    return gain, loss
```

---

### ✅ سیستم Decay کامل (CORRECTED — v2.1)

#### اصول Decay

```
📌 قوانین Decay:

1. همه Tier ها بدون استثنا Decay دارند — Elite و Diamond نیز شامل می‌شوند.

2. هر Tier یک دوره حفاظت (Protection) دارد:
   → در طول حفاظت: هیچ TP از دست نمی‌رود (فقط از بی‌فعالیت)
   → بعد از پایان حفاظت: Decay روزانه شروع می‌شود

3. حفاظت با هر بازی (برد یا باخت) تجدید می‌شود.

4. Decay جدا از باخت TP در بازی است:
   → باختن بازی: TP را مستقیم کم می‌کند (طبیعی)
   → Decay: فقط برای بی‌فعالیت اعمال می‌شود

5. Decay سقف دارد: حداکثر ۵۰٪ از TP فعلی.
   → بازیکن می‌تواند از Tier خود سقوط کند اگر TP از آستانه عبور کند.
```

#### جدول Protection Days

```
Tier      | Protection (روز بی‌فعالیت بدون Decay)
--------- | -----------------------------------------
Elite     | ۷ روز
Diamond   | ۵ روز
Gold      | ۳ روز
Silver    | ۲ روز
Bronze    | ۱ روز
```

#### نرخ Decay بعد از پایان Protection

```
نرخ Decay: ۳۰ TP در روز (برای هر روز بی‌فعالیت بعد از پایان حفاظت)
سقف Decay: ۵۰٪ از کل TP فعلی (هرگز از این بیشتر نمی‌شود)
```

#### الگوریتم Decay کامل

```python
def apply_tier_decay(user_id: int, last_played_date: datetime, current_tp: int, current_tier: str) -> int:
    """
    محاسبه و اعمال Decay بر اساس روزهای بی‌فعالیت.
    
    Protection Days برای هر Tier:
    Elite: 7 روز
    Diamond: 5 روز
    Gold: 3 روز
    Silver: 2 روز
    Bronze: 1 روز
    """
    
    PROTECTION_DAYS = {
        "Elite": 7,
        "Diamond": 5,
        "Gold": 3,
        "Silver": 2,
        "Bronze": 1
    }
    
    DAILY_DECAY_AMOUNT = 30
    MAX_DECAY_PERCENT = 0.50
    
    days_inactive = (datetime.now() - last_played_date).days
    protection = PROTECTION_DAYS.get(current_tier, 1)
    
    # اگر هنوز در دوره حفاظت است
    if days_inactive <= protection:
        return current_tp  # بدون Decay
    
    # روزهایی که Decay فعال است
    decay_days = days_inactive - protection
    
    # محاسبه Decay
    raw_decay = decay_days * DAILY_DECAY_AMOUNT
    max_allowed_decay = int(current_tp * MAX_DECAY_PERCENT)
    actual_decay = min(raw_decay, max_allowed_decay)
    
    new_tp = max(0, current_tp - actual_decay)
    
    return new_tp

def get_current_tier(tp: int) -> str:
    if tp < 500:
        return "Bronze"
    elif tp < 1000:
        return "Silver"
    elif tp < 1500:
        return "Gold"
    elif tp < 2000:
        return "Diamond"
    else:
        return "Elite"
```

#### مثال‌های Decay

```
مثال ۱ — بازیکن Elite بعد از ۱۰ روز بی‌فعالیت:
  TP فعلی: 2500
  Tier: Elite → حفاظت ۷ روز
  روزهای بی‌فعال: 10
  روزهای Decay فعال: 10 - 7 = 3 روز
  Decay خام: 3 × 30 = 90 TP
  سقف Decay: 2500 × 50٪ = 1250
  Decay واقعی: min(90, 1250) = 90 TP
  TP جدید: 2500 - 90 = 2410 (هنوز Elite)

مثال ۲ — بازیکن Diamond بعد از ۸ روز بی‌فعالیت:
  TP فعلی: 1550
  Tier: Diamond → حفاظت ۵ روز
  روزهای بی‌فعال: 8
  روزهای Decay فعال: 8 - 5 = 3 روز
  Decay خام: 3 × 30 = 90 TP
  سقف Decay: 1550 × 50٪ = 775
  Decay واقعی: 90 TP
  TP جدید: 1550 - 90 = 1460 (سقوط به Gold!)

مثال ۳ — بازیکن Silver بعد از ۱ روز بی‌فعالیت:
  TP فعلی: 750
  Tier: Silver → حفاظت ۲ روز
  روزهای بی‌فعال: 1
  وضعیت: هنوز در حفاظت است
  Decay: 0 TP
  TP جدید: 750 (بدون تغییر)

مثال ۴ — بازیکن Gold بعد از ۳۰ روز بی‌فعالیت:
  TP فعلی: 1200
  Tier: Gold → حفاظت ۳ روز
  روزهای بی‌فعال: 30
  روزهای Decay فعال: 30 - 3 = 27 روز
  Decay خام: 27 × 30 = 810 TP
  سقف Decay: 1200 × 50٪ = 600
  Decay واقعی: min(810, 600) = 600 TP
  TP جدید: 1200 - 600 = 600 (سقوط به Silver!)
```

#### نکات مهم Decay

```
✅ Decay کاملاً مستقل از باختن بازی است
✅ باختن بازی TP را کم می‌کند (مکانیزم جداگانه)
✅ Decay فقط در صورت بی‌فعالیت اتفاق می‌افتد
✅ بازی کردن (حتی باخت) دوره حفاظت را تجدید می‌کند
✅ هیچ Tier ای از Decay معاف نیست — Elite هم Decay دارد
✅ سقف ۵۰٪ از سقوط شدید جلوگیری می‌کند، اما سقوط Tier هنوز ممکن است
✅ Decay هر روز (cron job) بررسی و اعمال می‌شود
```

#### ساختار دیتابیس Decay

```sql
-- اضافه کردن به player_progression
ALTER TABLE player_progression 
ADD COLUMN last_played_at DATETIME;

-- نمونه query برای بررسی decay روزانه
SELECT 
    user_id,
    tier_points,
    last_played_at,
    JULIANDAY('now') - JULIANDAY(last_played_at) AS days_inactive
FROM player_progression
WHERE JULIANDAY('now') - JULIANDAY(last_played_at) > 1;
```

---

# 🎮 جریان کامل بازی

## ۱. ورود و شروع

```
کاربر: /start
  ↓
سیستم: بررسی عضویت کانال
  ↓
  YES → ایجاد/بازیابی Player
     ↓
     اعطای کارت‌های شروعی (۳ کارت Normal)
     ↓
     نمایش منوی اصلی
  ↓
  NO → "لطفاً ابتدا در کانال عضو شوید"
```

---

## ۲. کلیم روزانه (Updated Flow)

```
کاربر: /claim یا کلیک "🎁 دریافت کارت"
  ↓
سیستم: بررسی آخرین کلیم
  ↓
  گذشته < ۲۴ ساعت → "تا کلیم بعدی X ساعت مانده"
  ↓
  گذشته >= ۲۴ ساعت:
    ↓
    محاسبه pool:
      → تمام کارت‌های Normal تعریف‌شده در بازی
      → حذف کارت‌هایی که بازیکن در Epic یا Legend دارد
    ↓
    انتخاب رندوم با احتمال برابر از pool
    ↓
    اضافه کردن کارت Normal به موجودی بازیکن
    ↓
    نمایش نتیجه:
      "🎁 کلیم موفق!
      کارت دریافتی: [نام کارت] (Normal)
      موجودی: [تعداد کل کارت‌ها]"
```

---

## ۳. Fusion (Updated Flow)

### Normal → Epic

```
کاربر: منوی Fusion → "ارتقای Normal به Epic"
  ↓
سیستم: نمایش لیست کارت‌های Normal بازیکن
  ↓
کاربر: انتخاب ۳ کارت Normal (checkbox یا multi-select)
  ↓
سیستم: تأیید انتخاب → "کدام کارت را می‌خواهی Epic شود؟"
        نمایش ۳ کارت انتخاب‌شده
  ↓
کاربر: انتخاب یک کارت از ۳ تا
  ↓
سیستم: تأیید نهایی:
        "⚠️ [کارت A]، [کارت B]، [کارت C] مصرف می‌شوند.
        [کارت انتخاب‌شده] Epic می‌شود.
        ادامه دهی؟"
  ↓
کاربر: تأیید
  ↓
سیستم:
  - حذف هر ۳ کارت Normal از موجودی بازیکن
  - اضافه کردن کارت Epic انتخاب‌شده
  - بازگرداندن ۲ کارت دیگر به global pool
  - لاگ در fusion_log
  ↓
نتیجه:
  "✨ Fusion موفق!
  Epic دریافتی: [کارت انتخاب‌شده] 🎉"
```

### Epic → Legend

```
کاربر: منوی Fusion → "ارتقای Epic به Legend"
  ↓
سیستم: نمایش لیست کارت‌های Epic بازیکن
  ↓
کاربر: انتخاب ۳ کارت Epic
  ↓
سیستم: تأیید انتخاب → "کدام کارت را می‌خواهی Legend شود؟"
        نمایش ۳ کارت انتخاب‌شده
  ↓
کاربر: انتخاب یک کارت از ۳ تا
  ↓
سیستم: تأیید نهایی:
        "⚠️ [کارت A Epic]، [کارت B Epic]، [کارت C Epic] مصرف می‌شوند.
        [کارت انتخاب‌شده] Legend می‌شود.
        این عمل برگشت‌ناپذیر است. ادامه دهی؟"
  ↓
کاربر: تأیید
  ↓
سیستم:
  - حذف هر ۳ کارت Epic از موجودی بازیکن
  - اضافه کردن کارت Legend انتخاب‌شده
  - لاگ در fusion_log
  ↓
نتیجه:
  "🌟 Fusion Legend موفق!
  Legend دریافتی: [کارت انتخاب‌شده] 👑"
```

---

## ۴. مشاهده پروفایل

```
کاربر: /profile
  ↓
سیستم: نمایش اطلاعات
  ↓
- Username & User ID
- Level & XP Progress Bar
- Tier Badge & TP
- Total Score
- Hearts (❤️) با نمایش X/Y
- Coins (💰)
- تعداد کارت‌های منحصربفرد
- Win/Loss Ratio
  ↓
دکمه‌ها:
  [📊 آمار تفصیلی] [🎴 کارت‌ها] [🎨 شخصی‌سازی]
```

---

## ۵. مشاهده کارت‌ها

```
کاربر: /cards یا کلیک "🎴 کارت‌ها"
  ↓
منوی دسته‌بندی:
  ↓
  [⭐ Favorite] [🏆 Legend] [💎 Epic] [🃏 Normal] [🌟 Rare]
  ↓
کاربر: انتخاب دسته
  ↓
سیستم: نمایش کارت‌ها (pagination اگر > 8)
  ↓
  [کارت 1] [کارت 2] [کارت 3] [کارت 4]
  [کارت 5] [کارت 6] [کارت 7] [کارت 8]
  [◀️ قبلی] [🏠 منو] [بعدی ▶️]
  ↓
کاربر: کلیک روی کارت
  ↓
سیستم: نمایش جزئیات کارت
  ↓
- تصویر کارت (با اسکین فعال)
- نام و رریتی
- آمار (Power, Speed, IQ, Popularity)
- تایپ کارت (Power/Speed/IQ/Popularity Type)
- بیوگرافی
- پیشرفت ماموریت (اگر Epic باشد)
  ↓
دکمه‌ها:
  [⭐ علاقه‌مندی] [⬆️ ارتقا] [🎨 اسکین] [🔙 بازگشت]
```

---

# 📐 فرمول‌های ریاضی

## ۱. فرمول XP به Level

```python
def get_level_from_xp(total_xp):
    level = 1
    xp_needed = 0
    
    while level < 30:
        next_level_xp = 100 + (level - 1) * 50
        if total_xp >= xp_needed + next_level_xp:
            xp_needed += next_level_xp
            level += 1
        else:
            break
    
    return level
```

---

## ۲. فرمول امتیاز بازی

```python
def calculate_match_score(winner_card, loser_card):
    rarity_values = {
        "NORMAL": 1,
        "EPIC": 2,
        "LEGEND": 3,
        "RARE": 4
    }
    
    winner_rarity = rarity_values[winner_card.rarity]
    loser_rarity = rarity_values[loser_card.rarity]
    
    if winner_rarity > loser_rarity:
        return 5  # برد آسان
    elif winner_rarity == loser_rarity:
        return 10  # برد متعادل
    else:
        return 20  # برد دشوار
```

---

## ۳. فرمول تبدیل امتیاز به سکه

```python
def calculate_coins_earned(old_score, new_score):
    old_coins = old_score // 100
    new_coins = new_score // 100
    return new_coins - old_coins
```

---

## ۴. فرمول ماینینگ روزانه

```python
def calculate_daily_mining(player_cards: list) -> int:
    """
    محاسبه سکه ماینینگ روزانه.

    قوانین:
    - کارت‌های RARE کاملاً از محاسبه خارج می‌شوند.
    - Normal، Epic، و Legend همه شمارش می‌شوند.
    - محاسبه بر اساس تعداد کل است، نه منحصربفرد.
    - هر 5 کارت = 1 سکه. بدون سقف روزانه.
    - دلیل نبود سقف: inventory کل بازیکن محدود است.
    """
    non_rare_count = sum(1 for card in player_cards if card.rarity != "RARE")
    return non_rare_count // 5

# مثال‌ها:
# 49 کارت Normal/Epic/Legend → 49 // 5 = 9 سکه/روز
# 100 کارت Normal/Epic/Legend → 100 // 5 = 20 سکه/روز
# 10 کارت Non-Rare + 5 کارت Rare → 10 // 5 = 2 سکه/روز
```

---

## ۵. فرمول Tier Points

```python
def calculate_tier_change(winner, loser, match_type="normal"):
    base_gain = 15 if match_type == "normal" else 25
    base_loss = 10 if match_type == "normal" else 15
    
    winner_tier_level = get_tier_level(winner.tier_points)
    loser_tier_level = get_tier_level(loser.tier_points)
    
    tier_diff = loser_tier_level - winner_tier_level
    
    if tier_diff > 0:
        gain = base_gain + tier_diff * 5
        loss = max(5, base_loss - tier_diff * 2)
    elif tier_diff < 0:
        gain = max(5, base_gain + tier_diff * 2)
        loss = base_loss - tier_diff * 3
    else:
        gain = base_gain
        loss = base_loss
    
    return gain, loss

def get_tier_level(tp):
    if tp < 500: return 1      # Bronze
    elif tp < 1000: return 2   # Silver
    elif tp < 1500: return 3   # Gold
    elif tp < 2000: return 4   # Diamond
    else: return 5             # Elite
```

---

## ۶. فرمول کاهش Stat در راوند

```python
def reduce_stat_after_win(stat_value, win_margin):
    if win_margin >= 5:
        reduction = 2
    else:
        reduction = 1
    return max(0, stat_value - reduction)
```

---

## ۷. فرمول Boost زمین

```python
def apply_arena_boost(card, arena_type: str, selected_stat: str) -> int:
    """
    اعمال boost زمین روی stat انتخاب‌شده.

    بوست +1 فقط زمانی اعمال می‌شود که:
    1. نوع زمین با تایپ کارت یکسان باشد
    2. stat انتخاب‌شده با stat متناظر آن زمین یکسان باشد

    مثال:
    - کارت POWER_TYPE در power_arena و انتخاب "power" → +1
    - کارت POWER_TYPE در power_arena و انتخاب "speed" → بدون بوست
    - کارت SPEED_TYPE در power_arena → بدون بوست
    """
    base_value = getattr(card, selected_stat)

    if (arena_type == "power_arena"   and card.type == "POWER_TYPE"      and selected_stat == "power")      or \
       (arena_type == "speed_track"   and card.type == "SPEED_TYPE"      and selected_stat == "speed")      or \
       (arena_type == "thinking_room" and card.type == "IQ_TYPE"         and selected_stat == "iq")         or \
       (arena_type == "stage"         and card.type == "POPULARITY_TYPE" and selected_stat == "popularity"):
        return base_value + 1

    return base_value
```

---

## ۸. فرمول Tier Decay (Updated)

```python
def apply_tier_decay(last_played_date: datetime, current_tp: int, current_tier: str) -> int:
    """
    همه Tier ها Decay دارند.
    Protection Days: Elite=7, Diamond=5, Gold=3, Silver=2, Bronze=1
    Decay: 30 TP در روز بعد از اتمام حفاظت
    سقف: 50٪ از TP فعلی
    """
    PROTECTION_DAYS = {
        "Elite": 7,
        "Diamond": 5,
        "Gold": 3,
        "Silver": 2,
        "Bronze": 1
    }
    
    DAILY_DECAY = 30
    MAX_DECAY_RATIO = 0.50
    
    days_inactive = (datetime.now() - last_played_date).days
    protection = PROTECTION_DAYS.get(current_tier, 1)
    
    if days_inactive <= protection:
        return current_tp
    
    decay_days = days_inactive - protection
    raw_decay = decay_days * DAILY_DECAY
    max_decay = int(current_tp * MAX_DECAY_RATIO)
    actual_decay = min(raw_decay, max_decay)
    
    return max(0, current_tp - actual_decay)
```

---

# ⚖️ Balancing و توازن

## اقتصاد کلی

### ورودی سکه (روزانه، بازیکن فعال)
```
۵ بازی Normal (۳ برد، ۲ باخت):
  - امتیاز: ~۳۰
  - سکه از امتیاز: ۰

ماینینگ (فرض: ۴۵ کارت Non-Rare):
  - 45 // 5 = 9 سکه/روز

Risk (۱ برد از ۲ بازی، میز ۵۰):
  - +۵۰ سکه (برد)
  - -۵۰ سکه (باخت)
  - خالص: ۰

لیدربرد (فرض: رتبه ۱۵):
  - ۰ سکه

جمع (بدون Risk): ~۹ سکه/روز
```

### خروجی سکه (هفتگی، بازیکن متوسط)
```
۱ ارتقا Epic→Legend: ۵۰۰ سکه
۱ اسکین: ۵۰ سکه
۱ افزایش قلب: ۲۰۰ سکه

جمع: ~۷۵۰ سکه/هفته = ~۱۰۷ سکه/روز
```

**نتیجه**: با ماینینگ جدید، بازیکن فعال با کارت‌های زیاد درآمد بهتری دارد. برای دستیابی به Legend یا خرید اسکین، همچنان Risk یا خرید مستقیم توصیه می‌شود.

---

## توازن Fusion (Updated)

### تعداد کلیم و زمان برای ساخت Legend

```
برای Normal → Epic از طریق Fusion:
  - نیاز: ۳ کارت Normal
  - زمان: حداقل ۳ روز کلیم (اگر کارت‌ها در pool باشند)
  - بازیکن انتخاب می‌کند کدام کارت Epic شود

برای Epic → Legend از طریق Fusion:
  - نیاز: ۳ کارت Epic
  - هر Epic = ۳ کارت Normal = حداقل ۳ روز
  - ۳ Epic = حداقل ۹ روز کلیم
  - بازیکن انتخاب می‌کند کدام کارت Legend شود

مسیر کامل از Normal به Legend:
  - ۹ روز حداقل (۳ کلیم برای هر Epic، ۳ Epic برای Legend)
  - یا پرداخت ۵۰۰ سکه مستقیم
```

### ارزش‌گذاری Fusion
```
۳ Normal (از Fusion) = ارزش ۱۰۰ سکه (قیمت خرید مستقیم Epic)
۳ Epic (از Fusion) = ارزش ۵۰۰ سکه (قیمت خرید مستقیم Legend)

توازن: هزینه زمانی Fusion < هزینه مستقیم → تشویق به Fusion فعال
```

---

## توازن Tier Progression

### زمان رسیدن به Elite

```
فرض: ۵۰٪ Win Rate، ۵ بازی/روز

Bronze→Silver (۵۰۰ TP):
  - خالص روزانه: ~۱۲ TP
  - زمان: ~۴۲ روز

Silver→Gold (۵۰۰ TP):
  - خالص روزانه: ~۱۰ TP
  - زمان: ~۵۰ روز

Gold→Diamond (۵۰۰ TP):
  - خالص روزانه: ~۸ TP
  - زمان: ~۶۳ روز

Diamond→Elite (۵۰۰ TP):
  - خالص روزانه: ~۵ TP
  - زمان: ~۱۰۰ روز

جمع: ~۲۵۵ روز (۸.۵ ماه)
```

### تأثیر Decay بر Balancing

```
بازیکن Elite که ۷ روز بازی نکند:
  - بعد از ۷ روز حفاظت، Decay شروع می‌شود
  - ۳۰ TP/روز از دست می‌دهد
  - با ۲۰۰۰ TP، بعد از ۱۶ روز بی‌فعالیت: 2000 - (9 × 30) = 1730 TP → سقوط به Diamond!

این سیستم:
  → بازیکنان Elite را تشویق می‌کند فعال بمانند
  → جایگاه Elite را ارزشمند نگه می‌دارد
  → سیستم Tier را پویا نگه می‌دارد
  → بازیکنان جدید فرصت رسیدن به Tier بالا را دارند
```

---

## توازن Risk Reward

### میز ۵۰ سکه
```
ورودیه: ۵۰
حداکثر pot: ۳۰۰
ریسک: ۵۰
پاداش: ۵۰-۳۰۰

Risk/Reward Ratio: 1:1 تا 1:6
```

**توصیه**: بازیکن باید ۶۰٪+ Win Rate داشته باشد تا سودآور باشد.

---

# 📝 خلاصه تغییرات v2.3

## ✅ اضافات جدید در v2.3

### 1. Migration System (سیستم مهاجرت)
- ✅ اضافه: تبدیل همه کارت‌های موجود به Normal
- ✅ اضافه: فرمول تبدیل آمار از 0-100 به 0-10
- ✅ اضافه: تخصیص اتوماتیک تایپ به کارت‌ها
- ✅ اضافه: Initialize Level & Tier برای بازیکنان موجود
- ✅ اضافه: Verification Script برای اطمینان از صحت migration
- ✅ اضافه: پیام‌های اطلاع‌رسانی قبل و بعد از migration

### 2. Stat Locking System (قفل ویژگی در راوندها)
- ✅ اضافه: قفل خودکار ویژگی‌های استفاده شده
- ✅ اضافه: نمایش فقط ویژگی‌های available در UI
- ✅ اضافه: مکانیزم "حریف می‌تواند ویژگی قفل شده شما را انتخاب کند"
- ✅ اضافه: ذخیره used_stats برای هر بازیکن در active_fights
- ✅ اضافه: عمق استراتژیک بیشتر در انتخاب ویژگی‌ها

### 3. Round-by-Round Information Display
- ✅ اضافه: نمایش جزئیات کامل بعد از هر راوند
- ✅ اضافه: نمایش رریتی کارت حریف (بدون نام)
- ✅ اضافه: نمایش ویژگی و مقدار دقیق انتخابی حریف
- ✅ اضافه: نمایش تاثیر boost زمین
- ✅ اضافه: نمایش کاهش آمار
- ✅ اضافه: نمایش ویژگی قفل شده خود بازیکن
- ✅ اضافه: امتیاز لحظه‌ای بعد از هر راوند
- ❌ حذف: مخفی نگه داشتن نام کارت حریف تا پایان بازی

### 4. Database Schema Updates
- ✅ اضافه: `challenger_used_stats` در active_fights
- ✅ اضافه: `opponent_used_stats` در active_fights  
- ✅ اضافه: `round_1_details`, `round_2_details`, `round_3_details` برای ذخیره اطلاعات کامل
- ✅ اضافه: Support برای تساوی در راوندها

### 5. Tie Handling (مدیریت تساوی)
- ✅ اضافه: اگر راوندی مساوی شود، هر دو بازیکن 1 واحد کاهش می‌یابند
- ✅ اضافه: امتیاز راوند به هیچکس تعلق نمی‌گیرد

---

# 📝 خلاصه تغییرات v2.2

## ✅ اصلاحات اعمال‌شده در v2.2

### 4. سیستم ماینینگ روزانه (تغییر اساسی)
- ❌ حذف: "هر ۱۰ کارت منحصربفرد = ۱ سکه"
- ❌ حذف: سقف ۵ سکه در روز
- ❌ حذف: دخالت Rare در ماینینگ
- ✅ اضافه: هر ۵ کارت (Normal/Epic/Legend) = ۱ سکه در روز
- ✅ اضافه: بر اساس تعداد کل، نه منحصربفرد
- ✅ اضافه: کارت‌های Rare کاملاً از محاسبه حذف شدند
- ✅ اضافه: بدون سقف روزانه (inventory cap جایگزین است)

### 5. بوست زمین (تغییر مقدار)
- ❌ حذف: بوست +۲ هنگام تطابق تایپ کارت با زمین
- ✅ اضافه: بوست +۱ هنگام تطابق تایپ کارت با زمین و انتخاب stat متناظر

---

# 📝 خلاصه تغییرات v2.1

## ✅ اصلاحات اعمال‌شده در v2.1

### 1. سیستم Fusion (تغییر اساسی)
- ❌ حذف: ۵ کارت → ۱ رندوم
- ❌ حذف: شانس شکست در Epic→Legend
- ❌ حذف: انتخاب رندوم کارت ارتقایافته
- ✅ اضافه: ۳ کارت انتخابی → بازیکن کنترل کامل دارد
- ✅ اضافه: موفقیت ۱۰۰٪ تضمین‌شده
- ✅ اضافه: Legend همیشه اعطا می‌شود

### 2. سیستم Claim (تغییر اساسی)
- ❌ حذف: وزن‌دهی ۹۰/۱۰ به نفع کارت‌های جدید
- ❌ حذف: ارتقای اتوماتیک از کلیم تکراری
- ❌ حذف: رد کلیم در صورت داشتن Epic
- ✅ اضافه: احتمال برابر برای همه کارت‌های pool
- ✅ اضافه: کارت‌هایی که در Epic/Legend دارید از pool خارج می‌شوند
- ✅ اضافه: بازگشت Normal به pool بعد از Fusion
- ✅ اضافه: کلیم هرگز ناموفق نمی‌شود

### 3. سیستم Tier Decay (تغییر اساسی)
- ❌ حذف: حفاظت دائمی Elite (۳۰ روز)
- ❌ حذف: حفاظت دائمی Diamond (۲۱ روز)
- ❌ حذف: Decay هفتگی (۵۰ TP هر ۷ روز)
- ✅ اضافه: Decay روزانه (۳۰ TP/روز بعد از اتمام حفاظت)
- ✅ اضافه: Protection Days متفاوت برای هر Tier
- ✅ اضافه: همه Tier ها بدون استثنا Decay دارند
- ✅ اضافه: سقف Decay ۵۰٪ از TP فعلی

---

# 🎯 اولویت پیاده‌سازی (برای ۱ ماه)

## هفته ۱: پایه و سیستم‌های اصلی
- [ ] Schema جدید دیتابیس (Level, XP, TP, Tier)
- [ ] سیستم کلیم جدید (احتمال برابر + pool management)
- [ ] سیستم Level & XP
- [ ] سیستم Tier & TP (بدون decay فعلاً)
- [ ] بازی نرمال ۳ راوندی

## هفته ۲: زمین، Fusion، اقتصاد
- [ ] زمین‌های بازی (۴ زمین)
- [ ] تایپ کارت‌ها
- [ ] سیستم Fusion (انتخابی، قطعی، ۳ کارت)
- [ ] اقتصاد سکه کامل
- [ ] ماینینگ روزانه
- [ ] شاپ (ارتقا، قلب، اسکین)

## هفته ۳: Risk، Polish، آماده‌سازی
- [ ] مود Risk (بدون bluff پیشرفته)
- [ ] سیستم اسکین ساده
- [ ] Tier Decay روزانه (با Protection Days)
- [ ] Cleanup بهینه‌سازی
- [ ] تست و باگ‌فیکس

## هفته ۴: لانچ و مانیتور
- [ ] پیام همگانی
- [ ] کانال TelBattle
- [ ] مانیتورینگ اقتصاد
- [ ] تنظیم دقیق balance

---

# 🚀 فاز ۳ (آینده)

- [ ] Bluff System پیشرفته در Risk
- [ ] ماموریت‌های کارت برای Legend
- [ ] کارت‌های گروه سفارشی
- [ ] کارت‌های پویا (Dynamic)
- [ ] Tournament Mode
- [ ] Trading System
- [ ] Special Abilities
- [ ] Daily Missions
- [ ] Multi-Language

---

# 📞 تماس و پشتیبانی

برای هرگونه سوال یا ابهام در پیاده‌سازی، این سند را مرجع قرار دهید.

**نسخه سند**: 2.2.0  
**آخرین بروزرسانی**: فوریه ۲۰۲۶  
**وضعیت**: Production Ready ✅  
**تغییرات**: Fusion قطعی + Claim منصفانه + Decay همگانی + Mining جدید + Arena Boost اصلاح شد

---

**پایان سند**
