#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست Risk Mode UI Integration
"""

import sys
import os

def test_risk_mode_integration():
    """تست یکپارچه‌سازی Risk Mode"""
    print("🧪 Testing Risk Mode UI Integration...")
    
    # 1. بررسی import
    try:
        from risk_mode_system import RiskModeSystem, RiskTable, RiskAction
        print("✅ Risk Mode System imported successfully")
    except Exception as e:
        print(f"❌ Failed to import Risk Mode System: {e}")
        return False
    
    # 2. بررسی telegram_bot.py
    try:
        with open('telegram_bot.py', 'r', encoding='utf-8') as f:
            bot_code = f.read()
        
        # بررسی initialization
        if 'self.risk_mode = RiskModeSystem(self.db)' in bot_code:
            print("✅ Risk Mode initialized in bot")
        else:
            print("❌ Risk Mode not initialized in bot")
            return False
        
        # بررسی handlers
        handlers = [
            'risk_mode_menu_handler',
            'risk_table_select_handler',
            'risk_locked_handler'
        ]
        
        for handler in handlers:
            if f'async def {handler}' in bot_code:
                print(f"✅ Handler found: {handler}")
            else:
                print(f"❌ Handler missing: {handler}")
                return False
        
        # بررسی handler registration
        patterns = [
            'pattern="^risk_mode_menu$"',
            'pattern="^risk_table_"',
            'pattern="^risk_locked$"'
        ]
        
        for pattern in patterns:
            if pattern in bot_code:
                print(f"✅ Pattern registered: {pattern}")
            else:
                print(f"❌ Pattern not registered: {pattern}")
                return False
        
        # بررسی دکمه در منوی اصلی
        if 'Risk Mode' in bot_code and 'risk_mode_menu' in bot_code:
            print("✅ Risk Mode button added to main menu")
        else:
            print("❌ Risk Mode button not in main menu")
            return False
        
    except Exception as e:
        print(f"❌ Error reading telegram_bot.py: {e}")
        return False
    
    print("\n✅ All Risk Mode UI tests passed!")
    return True


if __name__ == '__main__':
    success = test_risk_mode_integration()
    sys.exit(0 if success else 1)
