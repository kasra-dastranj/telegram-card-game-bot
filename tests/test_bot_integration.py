#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Bot Integration - Simple Test
تست ساده یکپارچگی با Bot
"""

import sys

print("="*50)
print("Testing Bot Integration")
print("="*50)

try:
    # تست import ها
    print("\n1. Testing imports...")
    from telegram_bot import TelegramCardBot
    from tier_decay_system import TierDecaySystem
    from card_missions_system import CardMissionsSystem
    print("   OK - All imports successful")
    
    # تست initialization
    print("\n2. Testing bot initialization...")
    bot = TelegramCardBot(use_env=False)
    print("   OK - Bot initialized")
    
    # بررسی سیستم‌های جدید
    print("\n3. Checking new systems...")
    assert hasattr(bot, 'tier_decay'), "tier_decay not found"
    assert hasattr(bot, 'missions'), "missions not found"
    assert hasattr(bot, 'rare_cards'), "rare_cards not found"
    assert hasattr(bot, 'skins'), "skins not found"
    assert hasattr(bot, 'risk_mode'), "risk_mode not found"
    print("   OK - All systems initialized")
    
    # بررسی handlers
    print("\n4. Checking handlers...")
    assert hasattr(bot, 'claim_mission_reward_handler'), "claim_mission_reward_handler not found"
    print("   OK - New handlers exist")
    
    print("\n" + "="*50)
    print("ALL TESTS PASSED!")
    print("="*50)
    print("\nBot is ready with Phase 2 features:")
    print("  - Tier Decay System")
    print("  - Card Missions System")
    print("  - Rare Cards System (backend)")
    print("  - Skins System (backend)")
    print("  - Risk Mode System (backend)")
    print("\nNext: Setup Cron Job for Tier Decay")
    print("See: CRON_SETUP.md")
    
    sys.exit(0)
    
except Exception as e:
    print(f"\nTEST FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
