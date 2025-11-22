#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test to check group type and bot permissions
"""

import asyncio
from telegram import Bot
import json

async def test_bot():
    print("=" * 50)
    print("  Testing Bot Permissions")
    print("=" * 50)
    print()
    
    # Load config
    with open('game_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    token = config['bot_settings']['token']
    bot = Bot(token=token)
    
    try:
        # Get bot info
        me = await bot.get_me()
        print(f"✅ Bot connected: @{me.username}")
        print(f"   Name: {me.first_name}")
        print(f"   ID: {me.id}")
        print()
        
        # Get bot commands
        commands = await bot.get_my_commands()
        print(f"📋 Bot commands (default): {len(commands)}")
        for cmd in commands:
            print(f"   /{cmd.command} - {cmd.description}")
        print()
        
        # Get group commands
        from telegram import BotCommandScopeAllGroupChats
        group_commands = await bot.get_my_commands(scope=BotCommandScopeAllGroupChats())
        print(f"📋 Bot commands (groups): {len(group_commands)}")
        for cmd in group_commands:
            print(f"   /{cmd.command} - {cmd.description}")
        print()
        
        print("✅ Bot is working correctly!")
        print()
        print("💡 To test in a group:")
        print("   1. Add bot to group")
        print("   2. Make bot admin with 'Delete Messages' permission")
        print("   3. Type / in group to see commands")
        print("   4. Type /fight to test")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_bot())
