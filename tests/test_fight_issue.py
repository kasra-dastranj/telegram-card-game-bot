#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to diagnose fight command issues
"""

from game_core import DatabaseManager, GameLogic
import json

def main():
    print("=" * 50)
    print("  Testing Fight Command Issues")
    print("=" * 50)
    print()
    
    # Load config
    try:
        with open('game_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("✅ Config loaded")
        print(f"   Bot Token: {config['bot_settings']['token'][:20]}...")
        print(f"   Admin IDs: {config['bot_settings']['admin_user_ids']}")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return
    
    print()
    
    # Initialize database
    try:
        db = DatabaseManager()
        game = GameLogic(db, config)
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return
    
    print()
    
    # Check players
    try:
        players = db.get_leaderboard(100)
        print(f"📊 Total players: {len(players)}")
        
        if players:
            print("\n   Top 5 players:")
            for i, p in enumerate(players[:5], 1):
                user_id = p['user_id']
                name = p.get('first_name', 'Unknown')
                
                # Get player details
                player = db.get_or_create_player(user_id)
                player = game.check_and_reset_hearts(player)
                
                # Get cards
                cards = db.get_player_cards(user_id)
                
                print(f"   {i}. {name} (ID: {user_id})")
                print(f"      Hearts: {player.hearts}/{game.DAILY_HEARTS}")
                print(f"      Cards: {len(cards)}")
                print(f"      Score: {p.get('total_score', 0)}")
                
                if len(cards) == 0:
                    print(f"      ⚠️  NO CARDS - Cannot fight!")
                if player.hearts <= 0:
                    print(f"      ⚠️  NO HEARTS - Cannot fight!")
    except Exception as e:
        print(f"❌ Error checking players: {e}")
    
    print()
    
    # Check cards
    try:
        cards = db.get_all_cards()
        print(f"🎴 Total cards in database: {len(cards)}")
        
        if len(cards) == 0:
            print("   ⚠️  WARNING: No cards in database!")
            print("   Players cannot fight without cards!")
        else:
            print(f"   Cards: {', '.join([c.name for c in cards[:5]])}...")
    except Exception as e:
        print(f"❌ Error checking cards: {e}")
    
    print()
    
    # Check active fights
    try:
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM active_fights')
        active_count = cursor.fetchone()[0]
        
        print(f"⚔️  Active fights: {active_count}")
        
        if active_count > 0:
            cursor.execute('SELECT fight_id, challenger_id, opponent_id, status FROM active_fights LIMIT 5')
            fights = cursor.fetchall()
            print("\n   Recent fights:")
            for fight in fights:
                print(f"   - Fight {fight[0]}: {fight[1]} vs {fight[2]} ({fight[3]})")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error checking fights: {e}")
    
    print()
    
    # Check bot commands
    print("🤖 Checking bot command configuration...")
    try:
        from telegram_bot import GROUP_CHAT_COMMANDS
        print(f"   Group commands: {[cmd.command for cmd in GROUP_CHAT_COMMANDS]}")
        
        if any(cmd.command == 'fight' for cmd in GROUP_CHAT_COMMANDS):
            print("   ✅ 'fight' command is registered for groups")
        else:
            print("   ❌ 'fight' command NOT found in group commands!")
    except Exception as e:
        print(f"   ⚠️  Could not check commands: {e}")
    
    print()
    print("=" * 50)
    print("  Diagnosis Complete")
    print("=" * 50)
    print()
    
    # Recommendations
    print("📋 Recommendations:")
    print()
    
    if len(players) == 0:
        print("1. ⚠️  No players found!")
        print("   → Users need to /start the bot in private chat first")
    
    if len(cards) == 0:
        print("2. ⚠️  No cards in database!")
        print("   → Run: python3 -c 'from game_core import CardManager, DatabaseManager; cm = CardManager(DatabaseManager()); cm.create_sample_cards()'")
    
    for p in players[:5]:
        player = db.get_or_create_player(p['user_id'])
        player = game.check_and_reset_hearts(player)
        cards = db.get_player_cards(p['user_id'])
        
        if len(cards) == 0:
            print(f"3. ⚠️  Player {p.get('first_name')} has no cards!")
            print(f"   → They need to /claim a card first")
        
        if player.hearts <= 0:
            print(f"4. ⚠️  Player {p.get('first_name')} has no hearts!")
            print(f"   → They need to wait for heart reset")
    
    print()
    print("💡 Common issues:")
    print("   - Bot not admin in group → Make bot admin")
    print("   - User hasn't started bot → /start in private chat")
    print("   - User has no cards → /claim in private chat")
    print("   - User has no hearts → Wait for reset")
    print()

if __name__ == '__main__':
    main()
