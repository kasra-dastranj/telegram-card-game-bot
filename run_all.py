#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TelBattle — اجرای همزمان ربات تلگرام + Mini App API
"""

import threading
import logging
import sys
import os

logger = logging.getLogger(__name__)


def run_flask():
    """اجرای Flask API در یک thread جداگانه"""
    try:
        from miniapp_api import run_miniapp_server
        logger.info("🌐 Starting Mini App API on port 5001...")
        run_miniapp_server(host="0.0.0.0", port=5001, debug=False)
    except ImportError as e:
        logger.error(f"Failed to import miniapp_api: {e}")
    except Exception as e:
        logger.error(f"Flask server error: {e}", exc_info=True)


def run_bot():
    """اجرای ربات تلگرام"""
    try:
        from telegram_bot import TelegramCardBot
        logger.info("🤖 Starting Telegram Bot...")
        bot = TelegramCardBot()
        bot.run()
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('run_all.log'),
            logging.StreamHandler()
        ]
    )

    # Flask در thread جداگانه
    flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskAPI")
    flask_thread.start()

    # ربات در main thread
    run_bot()
