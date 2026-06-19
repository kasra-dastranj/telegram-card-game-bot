#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست profile command با سیستم‌های جدید
"""

import sys
import io
import os

# تنظیم encoding برای ویندوز
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# تنظیم ENV_FILE
os.environ['ENV_FILE'] = '.env.test'

from game_core import DatabaseManager, GameLogic
from config_loader import load_config
from phase2_systems import LevelSystem, format_xp_bar, format_tier_badge

def simulate_profile_display(user_id: int):
    """شبیه‌سازی نمایش پروفایل"""
    print("=" * 60)
    print(f"🧪 شبیه‌سازی /profile برای user {user_id}")
    print("=" * 60)
    
    # بارگیری config
    config = load_config('.env.test')
    
    # ایجاد db و game
    db = DatabaseManager('game_bot_test.db')
    game = GameLogic(db, config)
    
    # دریافت اطلاعات بازیکن
    player = db.get_or_create_player(user_id)
    card_count = len(db.get_player_cards(user_id))
    stats_windows = db.get_player_stats(user_id)
    rank = db.get_player_rank(user_id)
    card_counts = db.get_player_card_counts(user_id)
    
    rank_text = f"#{rank}" if rank else "N/A"
    total_stats = stats_windows.get('total', {
        'games_played': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'win_rate': 0
    })
    
    # دریافت اطلاعات پیشرفت
    progression = game.get_player_progression(user_id)
    
    if progression:
        current_level, xp_in_level, xp_needed = LevelSystem.get_xp_progress(progression.total_xp)
        xp_bar = format_xp_bar(xp_in_level, xp_needed, bar_length=8)
        tier_badge = format_tier_badge(progression.current_tier)
        
        progression_text = (
            f"\n📈 پیشرفت:\n"
            f"⭐ Level: {current_level}/30\n"
            f"   {xp_bar} ({xp_in_level}/{xp_needed} XP)\n"
            f"{tier_badge} Tier: {progression.current_tier} ({progression.tier_points} TP)\n"
        )
    else:
        progression_text = "\n❌ اطلاعات پیشرفت یافت نشد\n"
    
    # ساخت متن پروفایل
    text = (
        f"👤 پروفایل شما: User {user_id}\n\n"
        f"📊 آمار کلی:\n"
        f"🏆 امتیاز کل: {player.total_score}  •  رتبه: {rank_text}\n"
        f"💀 جان‌ها: {player.hearts}/{config['game_settings']['daily_hearts']}\n"
        f"🎴 کارت‌ها: {card_counts.get('total', card_count)} "
        f"(🟢{card_counts.get('normal',0)} • 🟣{card_counts.get('epic',0)} • 🟡{card_counts.get('legend',0)})\n"
        f"{progression_text}\n"
        f"⚔️ آمار فایت (کلی):\n"
        f"  - کل بازی‌ها: {total_stats['games_played']}\n"
        f"  - برد: {total_stats['wins']}\n"
        f"  - باخت: {total_stats['losses']}\n"
        f"  - مساوی: {total_stats['ties']}\n"
        f"  - نرخ برد: {int(total_stats['win_rate'])}%\n"
    )
    
    print(text)
    print("=" * 60)

def simulate_match_rewards():
    """شبیه‌سازی پاداش‌های بازی"""
    print("\n" + "=" * 60)
    print("🧪 شبیه‌سازی پاداش‌های بازی")
    print("=" * 60)
    
    config = load_config('.env.test')
    db = DatabaseManager('game_bot_test.db')
    game = GameLogic(db, config)
    
    winner_id = 5735941901
    loser_id = 1431545583
    
    print(f"\n⚔️ بازی: User {winner_id} vs User {loser_id}")
    print(f"نتیجه: User {winner_id} برنده شد\n")
    
    # دریافت progression قبل از بازی
    winner_prog_before = game.get_player_progression(winner_id)
    loser_prog_before = game.get_player_progression(loser_id)
    
    print("📊 قبل از بازی:")
    if winner_prog_before:
        print(f"  برنده: Level {winner_prog_before.level}, {winner_prog_before.current_tier} ({winner_prog_before.tier_points} TP)")
    if loser_prog_before:
        print(f"  بازنده: Level {loser_prog_before.level}, {loser_prog_before.current_tier} ({loser_prog_before.tier_points} TP)")
    
    # اعمال پاداش‌ها
    rewards = game.apply_match_rewards(winner_id, loser_id, "normal")
    
    # دریافت progression بعد از بازی
    winner_prog_after = game.get_player_progression(winner_id)
    loser_prog_after = game.get_player_progression(loser_id)
    
    print("\n📊 بعد از بازی:")
    if winner_prog_after:
        print(f"  برنده: Level {winner_prog_after.level}, {winner_prog_after.current_tier} ({winner_prog_after.tier_points} TP)")
    if loser_prog_after:
        print(f"  بازنده: Level {loser_prog_after.level}, {loser_prog_after.current_tier} ({loser_prog_after.tier_points} TP)")
    
    print("\n🎁 پاداش‌ها:")
    winner_rewards = rewards.get("winner", {})
    print(f"\n  برنده:")
    print(f"    - XP: +{winner_rewards.get('xp_gained', 0)}")
    print(f"    - TP: +{winner_rewards.get('tp_gained', 0)}")
    if winner_rewards.get("level_up"):
        print(f"    - 🎉 Level Up: {winner_rewards.get('old_level')} → {winner_rewards.get('new_level')}")
    if winner_rewards.get("tier_change"):
        print(f"    - 📈 Tier Change: {winner_rewards.get('old_tier')} → {winner_rewards.get('new_tier')}")
    
    loser_rewards = rewards.get("loser", {})
    print(f"\n  بازنده:")
    print(f"    - XP: +{loser_rewards.get('xp_gained', 0)}")
    print(f"    - TP: -{loser_rewards.get('tp_lost', 0)}")
    if loser_rewards.get("level_up"):
        print(f"    - 🎉 Level Up: {loser_rewards.get('old_level')} → {loser_rewards.get('new_level')}")
    if loser_rewards.get("tier_change"):
        print(f"    - 📉 Tier Change: {loser_rewards.get('old_tier')} → {loser_rewards.get('new_tier')}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    try:
        # تست نمایش پروفایل
        simulate_profile_display(5735941901)
        
        # تست پاداش‌های بازی
        simulate_match_rewards()
        
        # نمایش پروفایل بعد از بازی
        simulate_profile_display(5735941901)
        
        print("\n✅ همه تست‌ها با موفقیت انجام شد!")
        
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        import traceback
        traceback.print_exc()
