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


def seed_database():
    """لود کارت‌ها از cards_export.json اگه DB خالیه"""
    try:
        from game_core import DatabaseManager
        db = DatabaseManager()
        cards = db.get_all_cards()
        if len(cards) < 10:
            logger.info(f"DB has only {len(cards)} cards — running migration...")
            import json, sqlite3
            from datetime import datetime
            base_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(base_dir, "cards_export.json")
            if os.path.exists(json_path):
                with open(json_path, encoding="utf-8") as f:
                    card_data = json.load(f)
                conn = sqlite3.connect(db.db_path)
                cursor = conn.cursor()
                added = 0
                for card in card_data:
                    abilities = card.get("abilities", [])
                    if isinstance(abilities, list):
                        abilities = json.dumps(abilities, ensure_ascii=False)
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO cards
                            (card_id, name, rarity, power, speed, iq, popularity,
                             abilities, biography, card_type, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            card["card_id"], card["name"], card["rarity"],
                            card["power"], card["speed"], card["iq"], card["popularity"],
                            abilities, card.get("biography", ""),
                            card.get("card_type", "POWER_TYPE"),
                            datetime.now().isoformat()
                        ))
                        if cursor.rowcount > 0:
                            added += 1
                    except Exception:
                        pass
                conn.commit()
                conn.close()
                logger.info(f"✅ Seeded {added} cards into DB")
            else:
                logger.warning(f"cards_export.json not found at {json_path}")
        else:
            logger.info(f"DB has {len(cards)} cards — no seed needed")
    except Exception as e:
        logger.error(f"Seed error: {e}", exc_info=True)


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

    # اول DB رو seed کن
    seed_database()

    # Flask در thread جداگانه
    flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskAPI")
    flask_thread.start()

    # ربات در main thread
    run_bot()
