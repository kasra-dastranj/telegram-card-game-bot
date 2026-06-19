"""
تست کامل فلوی PvP با سیستم ۳ راوندی
"""
import sqlite3
import json
from datetime import datetime
from game_core import GameLogic, DatabaseManager

def test_complete_pvp_flow():
    """تست کامل فلوی PvP"""
    print("=" * 60)
    print("🧪 تست کامل فلوی PvP - سیستم ۳ راوندی")
    print("=" * 60)
    
    # اتصال به دیتابیس تست
    db = DatabaseManager("game_bot_test.db")
    game = GameLogic(db)
    
    # ایجاد دو بازیکن تست
    player1_id = 111111
    player2_id = 222222
    
    player1 = db.get_or_create_player(player1_id, "test_player1", "Player 1")
    player2 = db.get_or_create_player(player2_id, "test_player2", "Player 2")
    
    print(f"\n✅ بازیکنان ایجاد شدند:")
    print(f"   Player 1: {player1_id}")
    print(f"   Player 2: {player2_id}")
    
    # دریافت کارت‌ها
    all_cards = db.get_all_cards()
    if len(all_cards) < 2:
        print("❌ کارت کافی در دیتابیس وجود ندارد")
        return False
    
    card1 = all_cards[0]
    card2 = all_cards[1]
    
    print(f"\n🎴 کارت‌های انتخاب شده:")
    print(f"   Player 1: {card1.name} (Power: {card1.power}, Speed: {card1.speed})")
    print(f"   Player 2: {card2.name} (Power: {card2.power}, Speed: {card2.speed})")
    
    # ایجاد فایت
    fight_id = "test_fight_123"
    conn = db._get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO active_fights 
        (fight_id, challenger_id, opponent_id, challenger_card_id, opponent_card_id,
         status, chat_id, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, 'both_cards_selected', 12345, ?, ?)
    ''', (
        fight_id, player1_id, player2_id, card1.card_id, card2.card_id,
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    
    print(f"\n✅ فایت ایجاد شد: {fight_id}")
    
    # راوند 1
    print("\n" + "=" * 60)
    print("⚔️ راوند 1")
    print("=" * 60)
    
    # انتخاب stat برای راوند 1
    db.update_fight(fight_id, challenger_stat='power', opponent_stat='speed')
    print(f"\n✅ Stats انتخاب شدند: Player1=power, Player2=speed")
    
    # اولین resolve - ایجاد battle_state و حل راوند 1
    result = game.resolve_pvp_fight(fight_id)
    print(f"\n📊 نتیجه راوند 1:")
    print(f"   Success: {result.get('success')}")
    print(f"   Action: {result.get('action')}")
    
    if result.get('arena'):
        print(f"   Arena: {result.get('arena')}")
    
    if result.get('round_result'):
        rr = result['round_result']
        print(f"   Winner: {rr.get('winner')}")
        print(f"   Challenger: {rr.get('challenger_stat')}={rr.get('challenger_value')} (+{rr.get('challenger_boost')})")
        print(f"   Opponent: {rr.get('opponent_stat')}={rr.get('opponent_value')} (+{rr.get('opponent_boost')})")
    
    if result.get('action') == 'battle_finished':
        print(f"\n🏆 بازی تمام شد!")
        print(f"   برنده: {result.get('winner')}")
        return True
    
    # راوند 2
    print("\n" + "=" * 60)
    print("⚔️ راوند 2")
    print("=" * 60)
    
    # انتخاب stat برای راوند 2
    db.update_fight(fight_id, challenger_stat='speed', opponent_stat='iq')
    print(f"\n✅ Stats انتخاب شدند: Player1=speed, Player2=iq")
    
    # حل راوند 2
    result = game.resolve_pvp_fight(fight_id)
    print(f"\n📊 نتیجه راوند 2:")
    print(f"   Success: {result.get('success')}")
    print(f"   Action: {result.get('action')}")
    
    if result.get('round_result'):
        rr = result['round_result']
        print(f"   Winner: {rr.get('winner')}")
        print(f"   Challenger: {rr.get('challenger_stat')}={rr.get('challenger_value')} (+{rr.get('challenger_boost')})")
        print(f"   Opponent: {rr.get('opponent_stat')}={rr.get('opponent_value')} (+{rr.get('opponent_boost')})")
    
    if result.get('action') == 'battle_finished':
        print(f"\n🏆 بازی تمام شد!")
        print(f"   برنده: {result.get('winner')}")
        print(f"   امتیاز Challenger: {result.get('challenger_rounds_won')}")
        print(f"   امتیاز Opponent: {result.get('opponent_rounds_won')}")
        return True
    
    # راوند 3 (اگر نیاز باشد)
    print("\n" + "=" * 60)
    print("⚔️ راوند 3")
    print("=" * 60)
    
    # انتخاب stat برای راوند 3
    db.update_fight(fight_id, challenger_stat='iq', opponent_stat='popularity')
    print(f"\n✅ Stats انتخاب شدند: Player1=iq, Player2=popularity")
    
    # حل راوند 3
    result = game.resolve_pvp_fight(fight_id)
    print(f"\n📊 نتیجه راوند 3:")
    print(f"   Success: {result.get('success')}")
    print(f"   Action: {result.get('action')}")
    
    if result.get('round_result'):
        rr = result['round_result']
        print(f"   Winner: {rr.get('winner')}")
        print(f"   Challenger: {rr.get('challenger_stat')}={rr.get('challenger_value')} (+{rr.get('challenger_boost')})")
        print(f"   Opponent: {rr.get('opponent_stat')}={rr.get('opponent_value')} (+{rr.get('opponent_boost')})")
    
    if result.get('action') == 'battle_finished':
        print(f"\n🏆 بازی تمام شد!")
        print(f"   برنده: {result.get('winner')}")
        print(f"   امتیاز Challenger: {result.get('challenger_rounds_won')}")
        print(f"   امتیاز Opponent: {result.get('opponent_rounds_won')}")
        return True
    
    print("\n❌ بازی به درستی تمام نشد")
    return False

if __name__ == "__main__":
    try:
        success = test_complete_pvp_flow()
        print("\n" + "=" * 60)
        if success:
            print("✅ تست با موفقیت انجام شد!")
        else:
            print("❌ تست با خطا مواجه شد")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
