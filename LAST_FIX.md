# 🎯 آخرین Fix - اضافه کردن result_type

## ❌ مشکل:
```
KeyError: 'result_type'
```

فایت کامل اجرا می‌شد ولی نتیجه نمایش داده نمی‌شد!

## 🔍 علت:
`resolve_pvp_fight` یه key به اسم `result_type` برنمی‌گردوند ولی `telegram_bot.py` انتظارش رو داشت.

## ✅ راه‌حل:
اضافه کردن `result_type` به return value:

```python
# تعیین result_type برای telegram_bot
if result == "tie":
    result_type = "tie"
elif result == "win":
    result_type = "challenger_wins"
else:  # result == "loss"
    result_type = "opponent_wins"

return {
    ...
    "result_type": result_type,
    ...
}
```

## 🚀 برای آپلود:

```bash
scp "C:\Users\lenovo\Desktop\card game\game_core.py" root@195.248.243.122:"/root/card game/"

ssh root@195.248.243.122
cd "/root/card game"
pkill -9 -f telegram_bot.py
nohup python3 telegram_bot.py > bot.log 2>&1 &
```

## ✅ تست نهایی:

1. `/fight` در گروه
2. نفر دوم قبول کنه
3. هر دو کارت انتخاب کنن
4. هر دو ویژگی انتخاب کنن
5. **نتیجه باید نمایش داده بشه!** ✅

---
**🎉 این آخرین fix بود! حالا باید کامل کار کنه!**
