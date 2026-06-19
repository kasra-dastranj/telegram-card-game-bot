#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Card Game Bot (Compatibility Wrapper)

کد اصلی در پوشه bot/ قرار داره:
  - bot/main.py              → کلاس اصلی TelegramCardBot + main()
  - bot/handlers/basic.py    → هندلرهای پایه (start, help, profile, cards)
  - bot/handlers/battle.py   → سیستم نبرد ۳ راوندی
  - bot/handlers/shop.py     → فروشگاه، اسکین، ماموریت
  - bot/handlers/fusion.py   → ادغام کارت
  - bot/handlers/risk.py     → حالت ریسک
  - bot/handlers/pvp.py      → نبرد PvP
"""

# Re-export for backward compatibility
from bot.main import TelegramCardBot, main, setup_image_directories

if __name__ == "__main__":
    main()
