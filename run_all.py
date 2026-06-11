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
        port = int(os.environ.get("PORT", 5001))
        logger.info(f"🌐 Starting Mini App API on port {port}...")
        run_miniapp_server(host="0.0.0.0", port=port, debug=False)
    except ImportError as e:
        logger.error(f"Failed to import miniapp_api: {e}")
    except Exception as e:
        logger.error(f"Flask server error: {e}", exc_info=True)


def run_bot():
    """اجرای ربات تلگرام"""
    try:
        import telegram_bot
        logger.info("🤖 Starting Telegram Bot...")
        telegram_bot.main()
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[logging.StreamHandler()]
    )

    # Flask در thread جداگانه
    flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskAPI")
    flask_thread.start()

    # ربات در main thread
    run_bot()
