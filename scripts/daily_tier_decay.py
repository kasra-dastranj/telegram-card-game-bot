#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⏰ Daily Tier Decay Cron Job
اجرای روزانه برای اعمال Tier Decay به همه بازیکنان
"""

import sys
import logging
from datetime import datetime
from tier_decay_system import TierDecaySystem
from game_core import DatabaseManager

# تنظیم logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('tier_decay.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main():
    """اجرای Tier Decay روزانه"""
    try:
        # دریافت مسیر دیتابیس از آرگومان یا استفاده از پیش‌فرض
        db_path = sys.argv[1] if len(sys.argv) > 1 else 'game_bot.db'
        
        logger.info(f"Starting daily Tier Decay job for database: {db_path}")
        logger.info(f"Timestamp: {datetime.now()}")
        
        # راه‌اندازی سیستم
        db = DatabaseManager(db_path=db_path)
        tier_decay = TierDecaySystem(db)
        
        # اعمال Decay به همه بازیکنان
        stats = tier_decay.apply_decay_to_all_players()
        
        # نمایش آمار
        logger.info("=" * 50)
        logger.info("Tier Decay Job Completed Successfully!")
        logger.info("=" * 50)
        logger.info(f"Total players processed: {stats['total_players']}")
        logger.info(f"Players with decay: {stats['decayed_players']}")
        logger.info(f"Total TP lost: {stats['total_tp_lost']}")
        logger.info(f"Tier changes: {stats['tier_changes']}")
        logger.info("=" * 50)
        
        # نمایش جزئیات تغییرات Tier
        if stats['tier_changes'] > 0:
            logger.info("\nTier Changes Details:")
            for change in stats.get('tier_change_details', []):
                logger.info(f"  User {change['user_id']}: {change['old_tier']} → {change['new_tier']} (Lost {change['tp_lost']} TP)")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in daily Tier Decay job: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
