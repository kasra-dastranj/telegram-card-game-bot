#!/bin/bash
# Script to check server logs

echo "========================================"
echo "  Checking Server Status"
echo "========================================"
echo ""

echo "[1] Checking running processes..."
ps aux | grep -E "telegram_bot|web_api" | grep -v grep
echo ""

echo "[2] Last 30 lines of bot.log..."
tail -30 bot.log
echo ""

echo "[3] Last 20 lines of web_api.log..."
tail -20 web_api.log
echo ""

echo "[4] Testing API endpoints..."
curl -s http://localhost:5000/api/stats | python3 -m json.tool
echo ""

echo "[5] Checking database..."
python3 -c "
from game_core import DatabaseManager
db = DatabaseManager()
cards = db.get_all_cards()
players = db.get_leaderboard(10)
print(f'Cards: {len(cards)}')
print(f'Players: {len(players)}')
"
echo ""

echo "========================================"
echo "  Check Complete"
echo "========================================"
