# ورود کنترل‌شدهٔ کارت و تصویر

`scripts/import_cards.py` اکنون به واردکنندهٔ Manifest وصل است. دیگر از روی نام فایل کارت نمی‌سازد و هیچ عدد یا شناسه‌ای را تصادفی انتخاب نمی‌کند. فایل JSON باید برای هر شخصیت `card_id` پایدار، نام، توضیح، فرم پایه و سه فرم `normal`، `epic` و `legend` داشته باشد. هر فرم چهار عدد صحیح ۰ تا ۱۰۰، `card_type`، فهرست `abilities` و مسیر تصویر واقعی در پروژه می‌خواهد. مقدار `approved: true` یعنی محتوا و تصویر بازبینی شده‌اند.

ساختار هر مدخل:

```json
{
  "cards": [{
    "approved": true,
    "card_id": "stable_character_id",
    "name": "Character Name",
    "rarity": "normal",
    "biography": "متن تأییدشده",
    "dialogs": [],
    "variants": {
      "normal": {"power": 40, "speed": 50, "iq": 60, "popularity": 70, "card_type": "IQ_TYPE", "abilities": [], "card_effects": [], "passive": {}, "image_path": "assets/card_images/character_normal.png"},
      "epic": {"power": 48, "speed": 58, "iq": 68, "popularity": 78, "card_type": "IQ_TYPE", "abilities": [], "card_effects": [], "passive": {}, "image_path": "assets/card_images/character_epic.png"},
      "legend": {"power": 56, "speed": 66, "iq": 76, "popularity": 86, "card_type": "IQ_TYPE", "abilities": [], "card_effects": [], "passive": {}, "image_path": "assets/card_images/character_legend.png"}
    }
  }]
}
```

مسیرهای نمونه باید با تصاویر واقعی و تأییدشده جایگزین شوند. اجرای `python scripts/import_cards.py path/to/cards.json --db path/to/game_bot.db` فقط اختلاف را نمایش می‌دهد. پس از بازبینی، همان دستور با `--apply` همهٔ تغییرها را در یک تراکنش اعمال می‌کند. اجرای دوبارهٔ همان فایل بدون تغییر، خروجی `changes: []` دارد. پیش از اجرای روی دیتابیس اصلی از آن پشتیبان بگیرید؛ واردکننده تعریف کارت/فرم را تغییر می‌دهد، نه موجودی بازیکنان را.

برای فهرست تصاویر مفقود یا مشترک فرم‌ها، `python scripts/audit_card_images.py --db path/to/game_bot.db` را اجرا کنید. تصویر مشترک الزاماً خطا نیست، اما باید برای هر فرم بازبینی شود. منشأ تصاویر Gemini از فایل‌های فعلی قابل تشخیص نیست؛ نام و فرم کارت‌های باقی‌مانده باید در Manifest تأیید شوند.
