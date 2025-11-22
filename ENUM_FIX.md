# 🔧 حل مشکل Enum در update_fight

## ❌ خطا:
```
sqlite3.InterfaceError: Error binding parameter 1 - probably unsupported type.
```

## 🔍 علت:
وقتی `telegram_bot.py` می‌خواست status رو آپدیت کنه، یه `FightStatus` Enum پاس می‌داد:
```python
update_data["status"] = FightStatus.BOTH_CARDS_SELECTED
self.db.update_fight(fight_id, **update_data)
```

ولی SQLite نمی‌تونه مستقیماً Enum بگیره، باید string باشه!

## ✅ راه‌حل:
متد `update_fight` رو تغییر دادم تا Enum ها رو خودکار به `.value` تبدیل کنه:

```python
def update_fight(self, fight_id: str, **kwargs) -> bool:
    for key, value in kwargs.items():
        # تبدیل Enum به string
        if isinstance(value, FightStatus):
            values.append(value.value)
        elif hasattr(value, 'value'):  # هر Enum دیگری
            values.append(value.value)
        else:
            values.append(value)
```

## 🚀 برای اعمال:

```bash
# روش سریع:
fix_enum_issue.bat

# یا دستی:
scp "C:\Users\lenovo\Desktop\card game\game_core.py" root@195.248.243.122:"/root/card game/"

ssh root@195.248.243.122
cd "/root/card game"
pkill -9 -f telegram_bot.py
nohup python3 telegram_bot.py > bot.log 2>&1 &
```

## ✅ تست:

1. برو تو گروه تلگرام
2. `/fight` بزن
3. نفر دوم قبول کنه
4. **هر دو نفر کارت انتخاب کنن** ← این قسمت قبلاً خطا می‌داد
5. هر دو نفر ویژگی انتخاب کنن
6. نتیجه رو ببین

---
**🎯 حالا باید کامل کار کنه!**
