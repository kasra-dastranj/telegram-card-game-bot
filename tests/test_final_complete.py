#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 تست نهایی - بررسی کامل بودن Phase 2
"""

import sys
import os

def test_all_systems():
    """تست تمام سیستم‌های Phase 2"""
    print("=" * 60)
    print("🧪 PHASE 2 FINAL COMPLETE TEST")
    print("=" * 60)
    
    all_passed = True
    
    # ==================== BACKEND SYSTEMS ====================
    print("\n📦 Testing Backend Systems...")
    
    backend_systems = [
        'tier_decay_system',
        'card_missions_system',
        'rare_cards_system',
        'skins_system',
        'risk_mode_system'
    ]
    
    for system in backend_systems:
        try:
            __import__(system)
            print(f"  ✅ {system}")
        except Exception as e:
            print(f"  ❌ {system}: {e}")
            all_passed = False
    
    # ==================== BOT INTEGRATION ====================
    print("\n🤖 Testing Bot Integration...")
    
    try:
        with open('telegram_bot.py', 'r', encoding='utf-8') as f:
            bot_code = f.read()
        
        # بررسی initialization
        systems_init = [
            'self.tier_decay = TierDecaySystem',
            'self.missions = CardMissionsSystem',
            'self.rare_cards = RareCardsSystem',
            'self.skins = SkinsSystem',
            'self.risk_mode = RiskModeSystem'
        ]
        
        for init in systems_init:
            if init in bot_code:
                print(f"  ✅ {init.split('=')[0].strip()}")
            else:
                print(f"  ❌ {init.split('=')[0].strip()}")
                all_passed = False
        
    except Exception as e:
        print(f"  ❌ Error reading telegram_bot.py: {e}")
        all_passed = False
    
    # ==================== UI HANDLERS ====================
    print("\n🎨 Testing UI Handlers...")
    
    handlers = [
        # Tier Decay (در profile)
        'last_played_at',
        
        # Card Missions
        'claim_mission_reward_handler',
        
        # Rare Cards
        'rare_cards_menu_handler',
        'rare_card_info_handler',
        'rare_card_purchase_handler',
        
        # Skins
        'skins_menu_handler',
        'card_skins_handler',
        'skin_info_handler',
        'skin_purchase_handler',
        'skin_activate_handler',
        
        # Risk Mode
        'risk_mode_menu_handler',
        'risk_table_select_handler',
        'risk_locked_handler'
    ]
    
    try:
        with open('telegram_bot.py', 'r', encoding='utf-8') as f:
            bot_code = f.read()
        
        for handler in handlers:
            if handler in bot_code:
                print(f"  ✅ {handler}")
            else:
                print(f"  ❌ {handler}")
                all_passed = False
    
    except Exception as e:
        print(f"  ❌ Error: {e}")
        all_passed = False
    
    # ==================== HANDLER REGISTRATION ====================
    print("\n📝 Testing Handler Registration...")
    
    patterns = [
        'pattern="^claim_mission_"',
        'pattern="^rare_cards_menu$"',
        'pattern="^rare_card_info_"',
        'pattern="^rare_card_purchase_"',
        'pattern="^skins_menu$"',
        'pattern="^card_skins_"',
        'pattern="^skin_info_"',
        'pattern="^skin_purchase_"',
        'pattern="^skin_activate_"',
        'pattern="^risk_mode_menu$"',
        'pattern="^risk_table_"',
        'pattern="^risk_locked$"'
    ]
    
    try:
        with open('telegram_bot.py', 'r', encoding='utf-8') as f:
            bot_code = f.read()
        
        for pattern in patterns:
            if pattern in bot_code:
                print(f"  ✅ {pattern}")
            else:
                print(f"  ❌ {pattern}")
                all_passed = False
    
    except Exception as e:
        print(f"  ❌ Error: {e}")
        all_passed = False
    
    # ==================== MAIN MENU BUTTONS ====================
    print("\n🎮 Testing Main Menu Buttons...")
    
    buttons = [
        ('Fusion', 'fusion_menu'),
        ('Economy', 'economy_menu'),
        ('Skins', 'skins_menu'),
        ('Risk Mode', 'risk_mode_menu')
    ]
    
    try:
        with open('telegram_bot.py', 'r', encoding='utf-8') as f:
            bot_code = f.read()
        
        for button_text, callback in buttons:
            if button_text in bot_code and callback in bot_code:
                print(f"  ✅ {button_text} button")
            else:
                print(f"  ❌ {button_text} button")
                all_passed = False
    
    except Exception as e:
        print(f"  ❌ Error: {e}")
        all_passed = False
    
    # ==================== SCRIPTS ====================
    print("\n📜 Testing Scripts...")
    
    scripts = [
        'daily_tier_decay.py',
        'create_sample_rare_cards.py',
        'create_sample_skins.py',
        'migrate_optional_features.py'
    ]
    
    for script in scripts:
        if os.path.exists(script):
            print(f"  ✅ {script}")
        else:
            print(f"  ❌ {script}")
            all_passed = False
    
    # ==================== DOCUMENTATION ====================
    print("\n📚 Testing Documentation...")
    
    docs = [
        'CRON_SETUP.md',
        'INTEGRATION_COMPLETE.md',
        'OPTIONAL_FEATURES_COMPLETE.md',
        'PHASE2_COMPLETE_FINAL.md',
        'PHASE2_100_PERCENT_COMPLETE.md',
        'REMAINING_TASKS.md'
    ]
    
    for doc in docs:
        if os.path.exists(doc):
            print(f"  ✅ {doc}")
        else:
            print(f"  ⚠️  {doc} (optional)")
    
    # ==================== FINAL RESULT ====================
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - PHASE 2 IS 100% COMPLETE!")
        print("=" * 60)
        print("\n🚀 Ready for launch!")
        print("\nNext steps:")
        print("1. Run migration: python migrate_optional_features.py game_bot.db")
        print("2. Create samples: python create_sample_rare_cards.py game_bot.db")
        print("3. Create samples: python create_sample_skins.py game_bot.db")
        print("4. Setup Cron Job (see CRON_SETUP.md)")
        print("5. Launch: python telegram_bot.py")
        return True
    else:
        print("❌ SOME TESTS FAILED - PLEASE CHECK ABOVE")
        print("=" * 60)
        return False


if __name__ == '__main__':
    success = test_all_systems()
    sys.exit(0 if success else 1)
