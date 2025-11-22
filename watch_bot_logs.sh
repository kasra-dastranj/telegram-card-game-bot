#!/bin/bash
# Script to watch bot logs in real-time

echo "========================================"
echo "  Watching Bot Logs (Real-time)"
echo "========================================"
echo ""
echo "Instructions:"
echo "1. Keep this terminal open"
echo "2. Go to Telegram group"
echo "3. Type /fight"
echo "4. Watch for any errors here"
echo ""
echo "Press Ctrl+C to stop"
echo ""
echo "----------------------------------------"
echo ""

tail -f bot.log | grep --line-buffered -E "fight|Fight|FIGHT|error|Error|ERROR|exception|Exception"
