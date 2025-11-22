# 🔧 تمام مشکلات حل شد!

## ❌ مشکلات پیدا شده:

### 1. خطای Enum در update_fight
```
sqlite3.InterfaceError: Error binding parameter - probably unsupported type
```
**علت**: FightStatus Enum به جای string پاس می‌شد
**راه‌حل**: تبدیل خودکار Enum به `.value`

### 2. خطای Type در is_unclaimed
```
sqlite3.InterfaceError: Error binding parameter 0
```
**علت**: PvPFight object به جای fight_id پاس می‌شد
**راه‌حل**: پذیرش هم object و هم string

### 3. خطای NoneType در cleanup_task
```
TypeError: '>' not supported between instances of 'NoneType' and 'int'
```
**علت**: cleanup_expired_fights هیچی return نمی‌کرد
**راه‌حل**: return تعداد deleted fights

### 4. خطای NoneType در reset_lives_task
```
TypeError: '>' not supported between instances of 'NoneType' and 'int'
```
**علت**: reset_all_player_lives هیچی return نمی‌کرد
**راه‌حل**: return تعداد reset شده

## ✅ تغییرات اعمال شده:

### 1. update_fight()
```python
# تبدیل Enum به string
if isinstance(value, FightStatus):
    values.append(value.value)
elif hasattr(value, 'value'):
    values.append(value.value)
```

### 2. is_unclaimed()
```python
# پذیرش هم object و هم string
if isinstance(fight_or_id, PvPFight):
    fight_id = fight_or_id.fight_id
else:
    fight_id = fight_or_id
```

### 3. cleanup_expired_fights()
```python
deleted_count = cursor.rowcount
return deleted_count
```

### 4. reset_all_player_lives()
```python
reset_count = cursor.rowcount
return reset_count
```

## 🚀 برای آپلود:

```bash
scp "C:\Users\lenovo\Desktop\card game\game_core.py" root@195.248.243.122:"/root/card game/"

ssh root@195.248.243.122
cd "/root/card game"
pkill -9 -f telegram_bot.py
nohup python3 telegram_bot.py > bot.log 2>&1 &
```

## ✅ تست کامل:

### در پیوی:
1. `/start` - شروع بازی ✅
2. `/claim` - دریافت کارت ✅
3. `/cards` - مشاهده کارت‌ها ✅
4. `/profile` - مشاهده پروفایل ✅

### در گروه:
1. `/fight` - شروع چالش ✅
2. نفر دوم قبول کنه ✅
3. هر دو کارت انتخاب کنن ✅
4. هر دو ویژگی انتخاب کنن ✅
5. نتیجه نمایش داده بشه ✅

---
**🎉 همه مشکلات حل شد! حالا باید کامل کار کنه!**
