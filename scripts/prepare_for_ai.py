#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آماده‌سازی فایل برای دادن به AI دیگه
"""

import json

# خواندن فایل اصلی
with open('cards_phase2_balanced.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# ساخت فایل ساده برای AI
output = {
    "game_info": {
        "name": "TelBattle - Card Collection Game",
        "battle_system": "3-Round Battle (Best of 3)",
        "stats": ["Power", "Speed", "IQ", "Popularity"],
        "stat_locking": "Each stat can only be used once per match",
        "card_stages": {
            "Normal": "Starting stage (14-22 total stats)",
            "Epic": "Upgraded via Fusion (18-26 total stats)",
            "Legend": "Maximum power (22-32 total stats, one stat can be 10)"
        }
    },
    "total_cards": len(data['cards']),
    "cards": []
}

# اضافه کردن کارت‌ها
for card in data['cards']:
    card_info = {
        "name": card['name'],
        "name_fa": card['name_fa'],
        "primary_stat": card['primary_stat'],
        "card_type": card['card_type'],
        "stats": {
            "normal": {
                "power": card['normal']['power'],
                "speed": card['normal']['speed'],
                "iq": card['normal']['iq'],
                "popularity": card['normal']['popularity'],
                "total": card['normal']['total']
            },
            "epic": {
                "power": card['epic']['power'],
                "speed": card['epic']['speed'],
                "iq": card['epic']['iq'],
                "popularity": card['epic']['popularity'],
                "total": card['epic']['total']
            },
            "legend": {
                "power": card['legend']['power'],
                "speed": card['legend']['speed'],
                "iq": card['legend']['iq'],
                "popularity": card['legend']['popularity'],
                "total": card['legend']['total']
            }
        },
        "stories": {
            "story_normal": "TODO: Write story for Normal stage",
            "story_epic": "TODO: Write story for Epic stage",
            "story_legend": "TODO: Write story for Legend stage"
        },
        "abilities": [
            "TODO: Ability 1 (related to primary stat)",
            "TODO: Ability 2 (related to character)",
            "TODO: Ability 3 (legendary ability)"
        ],
        "dialogs": [
            "TODO: Famous quote 1",
            "TODO: Famous quote 2",
            "TODO: Famous quote 3"
        ]
    }
    
    output['cards'].append(card_info)

# ذخیره فایل
with open('cards_for_ai_story_generation.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ فایل آماده شد!")
print(f"📁 فایل: cards_for_ai_story_generation.json")
print(f"🎴 تعداد کارت‌ها: {len(output['cards'])}")
print("\n📋 برای استفاده:")
print("1. فایل STORY_GENERATION_PROMPT.md را بخوان (راهنمای کامل)")
print("2. فایل cards_for_ai_story_generation.json را به AI بده")
print("3. از AI بخواه داستان‌ها، abilities و dialogs رو پر کنه")
