#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اجرای محلی ربات با توکن تست + دیتابیس تست (game_bot_test.db).
پروداکشن (game_config.json / game_bot.db) اصلاً لمس نمیشه.
"""
import sys

# لاگ UTF-8 روی کنسول ویندوز (جلوگیری از UnicodeEncodeError)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import game_core

# دیتابیس پیش‌فرض رو به کپی تست تغییر بده (قبل از ساخت هر DatabaseManager)
_TEST_DB = "game_bot_test.db"
_orig_db_init = game_core.DatabaseManager.__init__
def _test_db_init(self, db_path=_TEST_DB):
    _orig_db_init(self, db_path)
game_core.DatabaseManager.__init__ = _test_db_init

import telegram_bot
from telegram_bot import TelegramCardBot, setup_image_directories
from telegram.ext import Application


async def _always_in_channel(self, user_id, context):
    """در ربات تست، چک عضویت کانال بایپس میشه"""
    return True


def main():
    bot = TelegramCardBot("game_config_test.json")
    # بایپس چک کانال اجباری برای تست راحت
    bot.is_user_in_channel = _always_in_channel.__get__(bot, TelegramCardBot)

    setup_image_directories(bot.config)
    cards = bot.db.get_all_cards()
    print(f"TEST DB: {bot.db.db_path} | cards: {len(cards)}")

    app = Application.builder().token(bot.bot_token).build()
    bot.setup_handlers(app)
    app.add_error_handler(bot.error_handler)

    async def post_init(a):
        await bot.setup_bot_commands(a)
        me = await a.bot.get_me()
        print(f"TEST bot ready: @{me.username}")

    app.post_init = post_init
    print("=" * 50)
    print("Starting TEST bot (channel check bypassed)...")
    print("=" * 50)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
