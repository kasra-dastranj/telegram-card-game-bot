#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create Sample Skins
ایجاد Skins نمونه برای تست
"""

from game_core import DatabaseManager
from skins_system import SkinsSystem


def create_sample_skins(db_path='game_bot.db'):
    """ایجاد Skins نمونه"""
    
    db = DatabaseManager(db_path)
    skins = SkinsSystem(db)
    
    print("Creating sample Skins...")
    print("="*50)
    
    # دریافت چند کارت نمونه
    sample_cards = ["john_wick", "heisenberg", "rehi"]
    
    for card_id in sample_cards:
        card = db.get_card_by_id(card_id)
        if not card:
            print(f"⚠️  Card {card_id} not found, skipping...")
            continue
        
        print(f"\nCreating skins for {card.name}:")
        
        # Skin 1: Normal
        success = skins.create_skin(
            skin_id=f"{card_id}_normal_1",
            card_id=card_id,
            name=f"{card.name} - Classic",
            skin_type="normal",
            image_path=f"skins/{card_id}_classic.png",
            description="پوسته کلاسیک"
        )
        print(f"  1. Classic: {'✅' if success else '❌'}")
        
        # Skin 2: Special
        success = skins.create_skin(
            skin_id=f"{card_id}_special_1",
            card_id=card_id,
            name=f"{card.name} - Golden",
            skin_type="special",
            image_path=f"skins/{card_id}_golden.png",
            description="پوسته طلایی با افکت درخشان"
        )
        print(f"  2. Golden: {'✅' if success else '❌'}")
        
        # Skin 3: Premium
        success = skins.create_skin(
            skin_id=f"{card_id}_premium_1",
            card_id=card_id,
            name=f"{card.name} - Legendary",
            skin_type="premium",
            image_path=f"skins/{card_id}_legendary.png",
            description="پوسته افسانه‌ای با انیمیشن"
        )
        print(f"  3. Legendary: {'✅' if success else '❌'}")
    
    print("\n" + "="*50)
    print("Sample Skins created!")
    print("\nTo view them in bot:")
    print("  1. Go to main menu")
    print("  2. Click on 'Skins'")
    print("  3. Select a card")


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'game_bot.db'
    create_sample_skins(db_path)
