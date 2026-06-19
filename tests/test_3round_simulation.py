#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 شبیه‌سازی بازی ۳ راوندی
"""

import sys
import sqlite3
import json
from game_core import DatabaseManager, GameLogic, Card, CardRarity

def test_3round_simulation():
    """شبیه‌سازی یک بازی ۳ راوندی کامل"""
    
    print("🧪 شبیه‌سازی بازی ۳ راوندی\n")
    
    # استفاده از دیتابیس تست
    db = DatabaseManager("game_bot_test.db")
    game = GameLogic(db)
    
    # ایجاد دو بازیکن تست
    player1_id = 111111
    player2_id = 222222
    
    player1 = db.get_or_create_player(player1_id, "TestPlayer1")
    player2 = db.get_or_create_player(player2_id, "TestPlayer2")
    
    print(f"✅ بازیکنان ایجاد شدند:")
    print(f"   Player 1: {player1_id}")
    print(f"   Player 2: {player2_id}\n")
    
    # دریافت دو کارت برای تست
    all_cards = db.get_all_cards()
    if len(all_cards) < 2:
        print("❌ کارت کافی در دیتابیس وجود ندارد!")
        return False
    
    card1 = all_cards[0]
    card2 = all_cards[1]
    
    print(f"✅ کارت‌ها انتخاب شدند:")
    print(f"   Card 1: {card1.name} (Power:{card1.power}, Speed:{card1.speed}, IQ:{card1.iq}, Pop:{card1.popularity})")
    print(f"   Card 2: {card2.name} (Power:{card2.power}, Speed:{card2.speed}, IQ:{card2.iq}, Pop:{card2.popularity})\n")
    
    # ایجاد fight
    fight_id = "test_fight_123"
    
    conn = sqlite3.connect("game_bot_test.db")
    cursor = conn.cursor()
    
    # حذف fight قبلی اگر وجود داشت
    cursor.execute("DELETE FROM active_fights WHERE fight_id = ?", (fight_id,))
    cursor.execute("DELETE FROM battle_states WHERE fight_id = ?", (fight_id,))
    cursor.execute("DELETE FROM round_history WHERE fight_id = ?", (fight_id,))
    
    # ایجاد fight جدید
    from datetime import datetime, timedelta
    now = datetime.now()
    expires = now + timedelta(minutes=5)
    
    cursor.execute('''
        INSERT INTO active_fights
        (fight_id, challenger_id, opponent_id, challenger_card_id, opponent_card_id,
         status, chat_id, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, 'card_selection', 123456, ?, ?)
    ''', (fight_id, player1_id, player2_id, card1.card_id, card2.card_id,
          now.isoformat(), expires.isoformat()))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Fight ایجاد شد: {fight_id}\n")
    
    # شبیه‌سازی راوندها
    rounds = [
        {"challenger": "power", "opponent": "speed"},
        {"challenger": "speed", "opponent": "iq"},
        {"challenger": "iq", "opponent": "popularity"}
    ]
    
    for round_num, stats in enumerate(rounds, 1):
        print(f"━━━━━━━━━━━━━━━━━━━━━━")
        print(f"     🎮 راوند {round_num}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━\n")
        
        # بروزرسانی stats انتخاب شده
        db.update_fight(fight_id, 
                       challenger_stat=stats["challenger"],
                       opponent_stat=stats["opponent"])
        
        print(f"Player 1 انتخاب کرد: {stats['challenger']}")
        print(f"Player 2 انتخاب کرد: {stats['opponent']}\n")
        
        # حل راوند
        result = game.resolve_pvp_fight(fight_id)
        
        if not result.get("success"):
            print(f"❌ خطا: {result.get('error')}")
            return False
        
        action = result.get("action")
        
        if action == "waiting_for_stats":
            print("⏳ منتظر انتخاب stats...")
            continue
        
        elif action == "next_round":
            round_result = result.get("round_result", {})
            round_winner = round_result.get("winner")
            
            print(f"📊 نتیجه:")
            print(f"   Player 1: {round_result.get('challenger_total', 0)}")
            print(f"   Player 2: {round_result.get('opponent_total', 0)}")
            
            if round_winner == "challenger":
                print(f"   🏆 برنده: Player 1")
            elif round_winner == "opponent":
                print(f"   🏆 برنده: Player 2")
            else:
                print(f"   🤝 مساوی!")
            
            print(f"\n📈 امتیاز کلی: {result.get('challenger_rounds_won', 0)} - {result.get('opponent_rounds_won', 0)}")
            
            print(f"\n🔒 Stats قفل شده:")
            challenger_available = result.get("challenger_available_stats", [])
            opponent_available = result.get("opponent_available_stats", [])
            print(f"   Player 1 available: {challenger_available}")
            print(f"   Player 2 available: {opponent_available}\n")
            
        elif action == "battle_finished":
            round_result = result.get("round_result", {})
            print(f"📊 نتیجه راوند آخر:")
            print(f"   Player 1: {round_result.get('challenger_total', 0)}")
            print(f"   Player 2: {round_result.get('opponent_total', 0)}")
            
            print(f"\n━━━━━━━━━━━━━━━━━━━━━━")
            print(f"     🏁 نتیجه نهایی")
            print(f"━━━━━━━━━━━━━━━━━━━━━━\n")
            
            winner = result.get("winner")
            if winner == "challenger":
                print(f"🏆 برنده: Player 1")
            elif winner == "opponent":
                print(f"🏆 برنده: Player 2")
            else:
                print(f"🤝 مساوی!")
            
            print(f"\n📈 امتیاز نهایی: {result.get('challenger_rounds_won', 0)} - {result.get('opponent_rounds_won', 0)}")
            
            # نمایش تاریخچه راوندها
            print(f"\n📜 تاریخچه راوندها:")
            conn = sqlite3.connect("game_bot_test.db")
            cursor = conn.cursor()
            cursor.execute('''
                SELECT round_number, challenger_stat, opponent_stat,
                       challenger_total, opponent_total, winner
                FROM round_history
                WHERE fight_id = ?
                ORDER BY round_number
            ''', (fight_id,))
            
            for row in cursor.fetchall():
                round_num, c_stat, o_stat, c_total, o_total, winner = row
                winner_text = "Player 1" if winner == "challenger" else ("Player 2" if winner == "opponent" else "مساوی")
                print(f"   راوند {round_num}: {c_stat} vs {o_stat} → {c_total} vs {o_total} (برنده: {winner_text})")
            
            conn.close()
            
            print("\n✅ بازی با موفقیت تمام شد!")
            return True
    
    print("\n❌ بازی به پایان نرسید!")
    return False


if __name__ == "__main__":
    try:
        success = test_3round_simulation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 خطا: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
