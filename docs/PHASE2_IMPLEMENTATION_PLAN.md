# 🚀 نقشه پیاده‌سازی فاز ۲ - TelBattle

## ✅ وضعیت فعلی (انجام شده)

### Migration
- ✅ تبدیل آمار از 0-100 به 0-10
- ✅ تخصیص Card Type به کارت‌ها
- ✅ تبدیل همه کارت‌ها به Normal
- ✅ Initialize Level & Tier (3787 بازیکن)
- ✅ جدول player_progression ایجاد شد
- ✅ جدول fusion_log ایجاد شد
- ✅ جدول card_missions ایجاد شد

### Database
- ✅ ستون card_type در cards
- ✅ میانگین آمار: 4.7-5.2 (در بازه 0-10)

---

## 🎯 مراحل باقی‌مانده (به ترتیب اولویت)

### **WEEK 1: Core Systems** (هفته جاری)

#### ✅ Phase 1.1: Database Schema (DONE)
- ✅ player_progression
- ✅ fusion_log
- ✅ card_missions

#### 🔄 Phase 1.2: Level & XP System (IN PROGRESS)
**Priority: CRITICAL**

**Files to modify:**
- `game_core.py` - اضافه کردن XP logic
- `telegram_bot.py` - نمایش Level در profile

**Tasks:**
1. اضافه کردن متدهای XP به GameLogic:
   - `add_xp(user_id, amount, source)`
   - `get_player_level(user_id)`
   - `check_level_up(user_id)`
   
2. فرمول XP:
   ```python
   def xp_for_level(level):
       return 100 + (level - 1) * 50
   ```

3. منابع XP:
   - Normal Win: 10 XP
   - Normal Loss: 3 XP
   - Risk Win: 25 XP
   - Risk Loss: 5 XP
   - Card Upgrade Epic: 15 XP
   - Card Upgrade Legend: 30 XP

4. UI Changes:
   - نمایش Level و XP bar در /profile
   - پیام Level Up

**Estimated Time:** 4-6 ساعت

---

#### 🔄 Phase 1.3: Tier & TP System
**Priority: CRITICAL**

**Files to modify:**
- `game_core.py` - اضافه کردن TP logic
- `telegram_bot.py` - نمایش Tier

**Tasks:**
1. اضافه کردن متدهای TP:
   - `add_tp(user_id, amount)`
   - `get_player_tier(user_id)`
   - `calculate_tp_change(winner_tier, loser_tier, match_type)`

2. Tier Ranges:
   - Bronze: 0-499
   - Silver: 500-999
   - Gold: 1000-1499
   - Diamond: 1500-1999
   - Elite: 2000+

3. TP Change Formula:
   ```python
   base_gain = 15 (normal) / 25 (risk)
   tier_diff_multiplier = 5
   tp_change = base_gain + (tier_diff * multiplier)
   ```

**Estimated Time:** 4-6 ساعت

---

#### 🔄 Phase 1.4: Tier Decay System
**Priority: HIGH**

**Files to modify:**
- `game_core.py` - Decay logic
- `telegram_bot.py` - Cron job

**Tasks:**
1. Decay Algorithm:
   ```python
   protection_days = {
       'Elite': 7, 'Diamond': 5, 'Gold': 3,
       'Silver': 2, 'Bronze': 1
   }
   daily_decay = 30
   max_decay = current_tp * 0.50
   ```

2. Cron Job:
   - اجرای روزانه
   - بررسی last_played_at
   - محاسبه و اعمال Decay

**Estimated Time:** 3-4 ساعت

---

### **WEEK 2: Game Mechanics**

#### 🔄 Phase 2.1: Claim System (New)
**Priority: CRITICAL**

**Files to modify:**
- `game_core.py` - Pool management
- `telegram_bot.py` - /claim command

**Tasks:**
1. Pool Management:
   - `get_claimable_cards(user_id)` - کارت‌هایی که بازیکن در Epic/Legend ندارد
   - احتمال برابر (random.choice)
   - بدون وزن‌دهی

2. Rules:
   - همیشه Normal می‌دهد
   - هرگز ناموفق نمی‌شود
   - کارت‌های Epic/Legend از pool خارج می‌شوند

**Estimated Time:** 6-8 ساعت

---

#### 🔄 Phase 2.2: Fusion System (New)
**Priority: CRITICAL**

**Files to create:**
- `fusion_system.py` - کل لاجیک Fusion

**Files to modify:**
- `telegram_bot.py` - UI و handlers

**Tasks:**
1. Normal → Epic Fusion:
   - انتخاب 3 کارت Normal
   - بازیکن انتخاب می‌کند کدام Epic شود
   - حذف 3 کارت، اضافه 1 Epic
   - 2 کارت دیگر به pool بازمی‌گردند

2. Epic → Legend Fusion:
   - انتخاب 3 کارت Epic
   - بازیکن انتخاب می‌کند کدام Legend شود
   - حذف 3 کارت، اضافه 1 Legend
   - همیشه موفق (100%)

3. UI Flow:
   - لیست کارت‌ها با pagination
   - انتخاب 3 کارت
   - انتخاب کارت ارتقایافته
   - تأیید نهایی
   - نمایش نتیجه

4. Logging:
   - ثبت در fusion_log

**Estimated Time:** 10-12 ساعت

---

#### 🔄 Phase 2.3: 3-Round Battle System
**Priority: HIGH**

**Files to modify:**
- `game_core.py` - Round logic
- `telegram_bot.py` - UI راوندها

**Tasks:**
1. Stat Locking:
   - ذخیره used_stats برای هر بازیکن
   - فیلتر کردن ویژگی‌های قابل انتخاب

2. Round Info Display:
   - نمایش اطلاعات بعد از هر راوند
   - نمایش rarity حریف (نه نام)
   - نمایش ویژگی و عدد انتخابی
   - نمایش برنده و کاهش

3. Arena System:
   - انتخاب زمین بر اساس rarity
   - اعمال boost (+1)

**Estimated Time:** 8-10 ساعت

---

### **WEEK 3: Economy & Advanced**

#### 🔄 Phase 3.1: Coin Economy
**Priority: HIGH**

**Tasks:**
1. Coin Sources:
   - تبدیل امتیاز (100 = 1 coin)
   - ماینینگ روزانه (5 کارت = 1 coin)
   - Risk wins
   - Leaderboard

2. Coin Sinks:
   - Normal → Epic: 100 coins
   - Epic → Legend: 500 coins
   - Heart increase: 200 coins
   - Skins: 50-150 coins

**Estimated Time:** 6-8 ساعت

---

#### 🔄 Phase 3.2: Shop System
**Priority: MEDIUM**

**Tasks:**
1. Shop Categories:
   - Card Upgrades
   - Heart Increase
   - Skins (future)

2. UI:
   - منوی shop
   - تأیید خرید
   - نمایش موجودی

**Estimated Time:** 4-6 ساعت

---

#### 🔄 Phase 3.3: Risk Mode (Simple)
**Priority: MEDIUM**

**Tasks:**
1. Basic Risk:
   - Level 7+ requirement
   - Table sizes: 50/100/300
   - 3 random cards
   - Simple pot management

2. Bluff System (ساده):
   - Raise/Call/Fold
   - Pot limit: 6x

**Estimated Time:** 8-10 ساعت

---

### **WEEK 4: Testing & Launch**

#### 🔄 Phase 4.1: Testing
**Priority: CRITICAL**

**Tasks:**
1. Unit Tests:
   - XP calculation
   - TP calculation
   - Decay algorithm
   - Fusion logic
   - Claim pool

2. Integration Tests:
   - کل جریان بازی
   - Migration با داده واقعی

**Estimated Time:** 6-8 ساعت

---

#### 🔄 Phase 4.2: Launch
**Priority: CRITICAL**

**Tasks:**
1. پیام همگانی
2. مانیتور اقتصاد
3. Balance tuning

**Estimated Time:** 2-4 ساعت

---

## 📊 تخمین زمان کل

- Week 1: 15-20 ساعت
- Week 2: 24-30 ساعت
- Week 3: 18-24 ساعت
- Week 4: 8-12 ساعت

**Total: 65-86 ساعت** (حدود 8-11 روز کاری)

---

## 🎯 شروع: Level & XP System

**الان شروع می‌کنیم با:**
1. اضافه کردن XP methods به game_core.py
2. تست XP calculation
3. اضافه کردن UI به telegram_bot.py
4. تست با ربات تست

**آماده‌ای؟** 🚀
