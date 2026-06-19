#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎴 Card Balance Generator for Phase 2
تولید کارت‌های متعادل بر اساس سیستم جدید (0-10)
"""

import json
from typing import Dict, List

# لیست کارت‌ها با primary stat
CARDS_LIST = [
    ("Tyrion Lannister", "تیریون لنیستر", "iq"),
    ("Rick Grimes", "ریک گرایمز", "iq"),
    ("Negan", "نیگن", "power"),
    ("Daryl Dixon", "دریل دیکسون", "speed"),
    ("Billy Butcher", "بوچر", "power"),
    ("Homelander", "هوملندر", "power"),
    ("Michelangelo", "مایکی لاک‌پشت نینجا", "speed"),
    ("Donald Trump", "ترامپ", "power"),
    ("Mahmoud Ahmadinejad", "محمود احمدی‌نژاد", "popularity"),
    ("Bashar al-Assad", "بشار اسد", "speed"),
    ("Patrick Star", "پاتریک", "popularity"),
    ("Pahlavon Puria", "پهلوان پوریا", "power"),
    ("Spider-Man", "اسپایدرمن", "speed"),
    ("Batman", "بتمن", "power"),
    ("John Wick", "جان ویک", "speed"),
    ("Captain Jack Sparrow", "کاپتان جک اسپارو", "popularity"),
    ("Deadpool", "ددپول", "speed"),
    ("Thanos", "تانوس", "power"),
    ("Rostam", "رستم", "power"),
    ("Snoop Dogg", "اسنوپ داگ", "popularity"),
    ("Tataloo", "تتلو", "popularity"),
    ("Jackie Chan", "جکی چان", "speed"),
    ("Heisenberg", "هایزنبرگ", "iq"),
    ("Mokhtar", "مختار", "power"),
    ("Jumong", "جومونگ", "speed"),
    ("Scorpion", "اسکورپین", "speed"),
    ("Leon Kennedy", "لئون رزیدنت ایول", "speed"),
    ("Ben10", "بن تن", "power"),
    ("Mr Bean", "مستربین", "popularity"),
    ("CJ", "سی جی", "popularity"),
    ("Dr Stop", "دکتر استاپ", "popularity"),
    ("Master Shifu", "استاد شیفو", "speed"),
    ("Putin", "پوتین", "power"),
    ("Big Masoud", "بیگ مسعود", "popularity"),
    ("Mike Ehrmantraut", "مایک", "iq"),
    ("Shao Kahn", "شاوکان", "power"),
    ("Amoo Poorang", "عمو پورنگ", "popularity"),
    ("Saul Goodman", "ساول گودمن", "iq"),
    ("Sub-Zero", "سابزیرو", "speed"),
    ("Tom and Jerry", "تام و جری", "speed"),
    ("Kung Fu Panda", "پاندای کونگ‌فوکار", "power"),
    ("Shredder", "شریدر", "power"),
    ("Mario", "ماریو", "popularity"),
    ("Captain America", "کاپتان امریکا", "power"),
    ("Arthur Morgan", "آرتور مورگان", "popularity"),
    ("Darth Vader", "دارث ویدر", "iq"),
    ("Iron Man", "ایرون من", "iq"),
    ("Michael Scofield", "مایکل اسکافیلد", "iq"),
    ("T-Bag", "تی بگ", "iq"),
    ("Thor", "ثور", "power"),
    ("Billie Eilish", "بیلی ایلیش", "popularity"),
    ("Risitas", "ریسیتاس", "popularity"),
    ("Gigachad", "گیگاچد", "power"),
    ("Kratos", "کریتوس", "power"),
    ("Mileena", "ملینا", "speed"),
    ("Shir Farhad", "شیر فرهاد", "power"),
    ("Shrek", "شرک", "power"),
    ("Joker", "جوکر", "iq"),
    ("Naghi Mamooli", "نقی معمولی", "popularity"),
    ("Hulk", "هالک", "power"),
    ("Davood ZZZ", "داوود ززز", "popularity"),
    ("Abbas Araqchi", "عراقچی", "iq"),
    ("Tai Lung", "تایلانگ", "power"),
    ("Ezio", "اتزیو", "speed"),
    ("Albert Wesker", "آلبرت وسکر", "power"),
    ("Etabaki", "اتابکی", "popularity"),
    ("BoJack", "بوجک", "iq"),
    ("Terminator", "ترمیناتور", "power"),
    ("Joel", "جوئل در لست آف اس", "iq"),
    ("Sonic", "سونیک", "speed"),
    ("Sherlock", "شرلوک", "iq"),
    ("Ghost", "گوست توی کال آف دیوتی", "power"),
    ("SpongeBob", "باب اسفنجی", "popularity"),
    ("Tony Soprano", "تونی سوپرانوز", "iq"),
    ("Master Chief", "مسترچیف", "speed"),
    ("Zuko", "زوکو", "speed"),
    ("Captain Price", "کاپتان پرایس", "iq"),
    ("Hitman", "هیتمن", "power"),
    ("Ragnar", "رگنار", "popularity"),
    ("Leon The Professional", "لئون حرفه‌ای", "iq"),
    ("Oogway", "ارباب شن", "iq"),
    ("Muhammad Ali", "محمدعلی کلی", "power"),
    ("Undertaker", "اندرتیکر", "power"),
    ("Superman", "سوپرمن", "power"),
    ("Nader Shah", "نادرشاه", "iq"),
    ("Lalo Salamanca", "لالو سالامانکا", "iq"),
    ("Doctor Strange", "دکتر استرنج", "speed"),
    ("Jon Snow", "جان اسنو", "speed"),
    ("Zeus", "زئوس", "power"),
    ("Witcher", "ویچر", "speed"),
    ("Ali Daei", "علی دایی", "popularity"),
    ("Levi", "لیوای", "speed"),
    ("Koeman", "کومان", "popularity"),
    ("Optimus Prime", "اپتیموس پرایم", "power"),
    ("Napoleon", "ناپلئون", "iq"),
    ("Harry Potter", "هری پاتر", "popularity"),
    ("Mia Khalifa", "میا خلیفه", "popularity"),
]

def determine_card_type(primary_stat: str) -> str:
    """تعیین card_type بر اساس primary stat"""
    mapping = {
        "power": "POWER_TYPE",
        "speed": "SPEED_TYPE",
        "iq": "IQ_TYPE",
        "popularity": "POPULARITY_TYPE"
    }
    return mapping.get(primary_stat, "POWER_TYPE")

def generate_normal_stats(name: str, primary_stat: str) -> Dict:
    """
    تولید آمار Normal (14-22 total)
    یک نقطه قوت واضح، حداقل یک ضعف
    """
    stats = {"power": 0, "speed": 0, "iq": 0, "popularity": 0}
    
    # کاراکترهای خاص با آمار دستی
    special_cases = {
        # Genius Characters (IQ focused)
        "Tyrion Lannister": {"power": 2, "speed": 3, "iq": 9, "popularity": 5},
        "Heisenberg": {"power": 3, "speed": 2, "iq": 9, "popularity": 4},
        "Michael Scofield": {"power": 2, "speed": 4, "iq": 9, "popularity": 3},
        "Saul Goodman": {"power": 1, "speed": 3, "iq": 8, "popularity": 6},
        "Sherlock": {"power": 2, "speed": 4, "iq": 9, "popularity": 3},
        "Iron Man": {"power": 4, "speed": 5, "iq": 8, "popularity": 5},
        "Darth Vader": {"power": 7, "speed": 5, "iq": 7, "popularity": 3},
        "Rick Grimes": {"power": 6, "speed": 5, "iq": 7, "popularity": 4},
        "Mike Ehrmantraut": {"power": 5, "speed": 4, "iq": 8, "popularity": 2},
        "T-Bag": {"power": 3, "speed": 4, "iq": 8, "popularity": 3},
        "Joel": {"power": 6, "speed": 5, "iq": 7, "popularity": 3},
        "Tony Soprano": {"power": 6, "speed": 3, "iq": 8, "popularity": 5},
        "Captain Price": {"power": 6, "speed": 5, "iq": 7, "popularity": 4},
        "Leon The Professional": {"power": 6, "speed": 6, "iq": 7, "popularity": 2},
        "Oogway": {"power": 2, "speed": 3, "iq": 9, "popularity": 6},
        "Nader Shah": {"power": 7, "speed": 5, "iq": 8, "popularity": 2},
        "Lalo Salamanca": {"power": 5, "speed": 6, "iq": 8, "popularity": 3},
        "Napoleon": {"power": 5, "speed": 4, "iq": 8, "popularity": 5},
        "Abbas Araqchi": {"power": 2, "speed": 3, "iq": 8, "popularity": 5},
        "BoJack": {"power": 2, "speed": 3, "iq": 7, "popularity": 6},
        "Joker": {"power": 3, "speed": 5, "iq": 8, "popularity": 6},
        
        # Power Characters
        "Negan": {"power": 8, "speed": 4, "iq": 4, "popularity": 2},
        "Billy Butcher": {"power": 7, "speed": 5, "iq": 4, "popularity": 2},
        "Homelander": {"power": 8, "speed": 6, "iq": 2, "popularity": 4},
        "Batman": {"power": 7, "speed": 6, "iq": 6, "popularity": 3},
        "Thanos": {"power": 9, "speed": 5, "iq": 6, "popularity": 2},
        "Rostam": {"power": 9, "speed": 5, "iq": 3, "popularity": 5},
        "Pahlavon Puria": {"power": 8, "speed": 4, "iq": 2, "popularity": 6},
        "Mokhtar": {"power": 7, "speed": 5, "iq": 5, "popularity": 4},
        "Putin": {"power": 6, "speed": 4, "iq": 7, "popularity": 5},
        "Shao Kahn": {"power": 9, "speed": 4, "iq": 3, "popularity": 2},
        "Kung Fu Panda": {"power": 7, "speed": 5, "iq": 4, "popularity": 6},
        "Shredder": {"power": 7, "speed": 6, "iq": 5, "popularity": 2},
        "Captain America": {"power": 7, "speed": 6, "iq": 5, "popularity": 4},
        "Thor": {"power": 9, "speed": 5, "iq": 3, "popularity": 5},
        "Gigachad": {"power": 8, "speed": 4, "iq": 2, "popularity": 6},
        "Kratos": {"power": 9, "speed": 6, "iq": 4, "popularity": 2},
        "Shir Farhad": {"power": 8, "speed": 5, "iq": 3, "popularity": 4},
        "Shrek": {"power": 7, "speed": 3, "iq": 4, "popularity": 6},
        "Hulk": {"power": 9, "speed": 4, "iq": 1, "popularity": 4},
        "Tai Lung": {"power": 8, "speed": 6, "iq": 3, "popularity": 2},
        "Albert Wesker": {"power": 7, "speed": 6, "iq": 6, "popularity": 2},
        "Terminator": {"power": 8, "speed": 5, "iq": 3, "popularity": 3},
        "Ghost": {"power": 7, "speed": 6, "iq": 5, "popularity": 2},
        "Hitman": {"power": 7, "speed": 6, "iq": 6, "popularity": 1},
        "Muhammad Ali": {"power": 8, "speed": 7, "iq": 4, "popularity": 3},
        "Undertaker": {"power": 8, "speed": 4, "iq": 4, "popularity": 6},
        "Superman": {"power": 9, "speed": 6, "iq": 4, "popularity": 3},
        "Zeus": {"power": 9, "speed": 5, "iq": 5, "popularity": 3},
        "Optimus Prime": {"power": 9, "speed": 5, "iq": 5, "popularity": 3},
        "Donald Trump": {"power": 5, "speed": 3, "iq": 6, "popularity": 8},
        "Ben10": {"power": 7, "speed": 5, "iq": 3, "popularity": 5},
        
        # Speed Characters
        "Daryl Dixon": {"power": 5, "speed": 8, "iq": 3, "popularity": 4},
        "Michelangelo": {"power": 5, "speed": 8, "iq": 2, "popularity": 6},
        "Spider-Man": {"power": 5, "speed": 8, "iq": 5, "popularity": 4},
        "John Wick": {"power": 7, "speed": 8, "iq": 5, "popularity": 2},
        "Deadpool": {"power": 6, "speed": 8, "iq": 4, "popularity": 4},
        "Jackie Chan": {"power": 6, "speed": 8, "iq": 4, "popularity": 4},
        "Jumong": {"power": 5, "speed": 8, "iq": 5, "popularity": 4},
        "Scorpion": {"power": 6, "speed": 8, "iq": 3, "popularity": 3},
        "Leon Kennedy": {"power": 6, "speed": 8, "iq": 5, "popularity": 3},
        "Master Shifu": {"power": 3, "speed": 8, "iq": 7, "popularity": 4},
        "Sub-Zero": {"power": 6, "speed": 8, "iq": 4, "popularity": 3},
        "Tom and Jerry": {"power": 2, "speed": 8, "iq": 6, "popularity": 6},
        "Mileena": {"power": 6, "speed": 8, "iq": 3, "popularity": 4},
        "Ezio": {"power": 6, "speed": 8, "iq": 6, "popularity": 2},
        "Sonic": {"power": 3, "speed": 9, "iq": 4, "popularity": 6},
        "Master Chief": {"power": 7, "speed": 8, "iq": 5, "popularity": 2},
        "Zuko": {"power": 6, "speed": 8, "iq": 5, "popularity": 3},
        "Doctor Strange": {"power": 5, "speed": 6, "iq": 7, "popularity": 4},
        "Jon Snow": {"power": 6, "speed": 6, "iq": 5, "popularity": 5},
        "Witcher": {"power": 7, "speed": 8, "iq": 5, "popularity": 2},
        "Levi": {"power": 6, "speed": 9, "iq": 5, "popularity": 2},
        "Bashar al-Assad": {"power": 4, "speed": 7, "iq": 6, "popularity": 1},
        
        # Popularity Characters
        "Patrick Star": {"power": 2, "speed": 2, "iq": 2, "popularity": 8},
        "Captain Jack Sparrow": {"power": 4, "speed": 5, "iq": 5, "popularity": 8},
        "Snoop Dogg": {"power": 2, "speed": 3, "iq": 5, "popularity": 8},
        "Tataloo": {"power": 3, "speed": 4, "iq": 4, "popularity": 8},
        "Mr Bean": {"power": 1, "speed": 2, "iq": 3, "popularity": 8},
        "CJ": {"power": 5, "speed": 6, "iq": 3, "popularity": 7},
        "Dr Stop": {"power": 2, "speed": 3, "iq": 5, "popularity": 8},
        "Big Masoud": {"power": 4, "speed": 3, "iq": 3, "popularity": 8},
        "Amoo Poorang": {"power": 3, "speed": 4, "iq": 4, "popularity": 8},
        "Mario": {"power": 5, "speed": 6, "iq": 4, "popularity": 7},
        "Arthur Morgan": {"power": 7, "speed": 5, "iq": 5, "popularity": 5},
        "Billie Eilish": {"power": 2, "speed": 4, "iq": 5, "popularity": 8},
        "Risitas": {"power": 2, "speed": 3, "iq": 3, "popularity": 8},
        "Naghi Mamooli": {"power": 3, "speed": 3, "iq": 4, "popularity": 8},
        "Davood ZZZ": {"power": 2, "speed": 3, "iq": 3, "popularity": 8},
        "Etabaki": {"power": 3, "speed": 4, "iq": 5, "popularity": 7},
        "SpongeBob": {"power": 2, "speed": 4, "iq": 3, "popularity": 8},
        "Ragnar": {"power": 7, "speed": 5, "iq": 5, "popularity": 5},
        "Ali Daei": {"power": 5, "speed": 5, "iq": 4, "popularity": 7},
        "Koeman": {"power": 4, "speed": 5, "iq": 6, "popularity": 7},
        "Harry Potter": {"power": 4, "speed": 5, "iq": 7, "popularity": 6},
        "Mia Khalifa": {"power": 2, "speed": 4, "iq": 3, "popularity": 8},
        "Mahmoud Ahmadinejad": {"power": 3, "speed": 3, "iq": 5, "popularity": 8},
    }
    
    if name in special_cases:
        return special_cases[name]
    
    # Default fallback (shouldn't happen)
    stats[primary_stat] = 7
    remaining = ["power", "speed", "iq", "popularity"]
    remaining.remove(primary_stat)
    stats[remaining[0]] = 5
    stats[remaining[1]] = 4
    stats[remaining[2]] = 3
    
    return stats

def upgrade_to_epic(normal_stats: Dict) -> Dict:
    """
    ارتقا به Epic: +2 تا +4 به total
    بهبود ثبات و تقویت نقطه قوت اصلی
    """
    epic = normal_stats.copy()
    
    # پیدا کردن بالاترین stat
    max_stat = max(epic, key=epic.get)
    
    # +1 به بالاترین stat (اگر کمتر از 9 باشه)
    if epic[max_stat] < 9:
        epic[max_stat] += 1
    
    # +1 یا +2 به بقیه stats برای ثبات
    for stat in epic:
        if stat != max_stat and epic[stat] < 8:
            epic[stat] += 1
    
    # اطمینان از total در بازه 18-26
    total = sum(epic.values())
    if total < 18:
        # اضافه کردن به ضعیف‌ترین stat
        min_stat = min(epic, key=epic.get)
        epic[min_stat] += (18 - total)
    elif total > 26:
        # کم کردن از قوی‌ترین stat
        epic[max_stat] -= (total - 26)
    
    return epic

def upgrade_to_legend(epic_stats: Dict, primary_stat: str) -> Dict:
    """
    ارتقا به Legend: +2 تا +4 به total
    یا تقویت شدید نقطه قوت یا بالانس قوی
    فقط یک stat می‌تونه 10 باشه
    """
    legend = epic_stats.copy()
    
    # تصمیم: explosive یا balanced؟
    # اگر primary stat قبلاً بالاست، explosive می‌ریم
    if legend[primary_stat] >= 8:
        # Explosive: primary stat به 10
        legend[primary_stat] = min(10, legend[primary_stat] + 2)
        # بقیه +1
        for stat in legend:
            if stat != primary_stat and legend[stat] < 9:
                legend[stat] += 1
    else:
        # Balanced: همه +1 یا +2
        for stat in legend:
            if legend[stat] < 9:
                legend[stat] += 1
    
    # اطمینان از total در بازه 22-32
    total = sum(legend.values())
    if total < 22:
        legend[primary_stat] += (22 - total)
    elif total > 32:
        # کم کردن از غیر primary
        for stat in legend:
            if stat != primary_stat and total > 32:
                reduction = min(legend[stat] - 3, total - 32)
                legend[stat] -= reduction
                total -= reduction
    
    # اطمینان از اینکه فقط یک stat می‌تونه 10 باشه
    tens_count = sum(1 for v in legend.values() if v == 10)
    if tens_count > 1:
        for stat in legend:
            if stat != primary_stat and legend[stat] == 10:
                legend[stat] = 9
    
    return legend

def generate_all_cards():
    """تولید تمام کارت‌ها"""
    cards = []
    
    for name_en, name_fa, primary_stat in CARDS_LIST:
        # Normal stats
        normal = generate_normal_stats(name_en, primary_stat)
        
        # Epic stats
        epic = upgrade_to_epic(normal)
        
        # Legend stats
        legend = upgrade_to_legend(epic, primary_stat)
        
        # Card type
        card_type = determine_card_type(primary_stat)
        
        card = {
            "name": name_en,
            "name_fa": name_fa,
            "primary_stat": primary_stat,
            "card_type": card_type,
            "normal": {
                "power": normal["power"],
                "speed": normal["speed"],
                "iq": normal["iq"],
                "popularity": normal["popularity"],
                "total": sum(normal.values())
            },
            "epic": {
                "power": epic["power"],
                "speed": epic["speed"],
                "iq": epic["iq"],
                "popularity": epic["popularity"],
                "total": sum(epic.values())
            },
            "legend": {
                "power": legend["power"],
                "speed": legend["speed"],
                "iq": legend["iq"],
                "popularity": legend["popularity"],
                "total": sum(legend.values())
            }
        }
        
        cards.append(card)
    
    return {"cards": cards}

if __name__ == "__main__":
    print("🎴 تولید کارت‌های متعادل...")
    
    data = generate_all_cards()
    
    # ذخیره در فایل JSON
    with open("cards_phase2_balanced.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ {len(data['cards'])} کارت تولید شد!")
    print(f"📁 فایل ذخیره شد: cards_phase2_balanced.json")
    
    # نمایش آمار
    print("\n📊 آمار کلی:")
    
    # توزیع primary stats
    from collections import Counter
    primary_stats = [c["primary_stat"] for c in data["cards"]]
    stat_dist = Counter(primary_stats)
    print("\nتوزیع Primary Stats:")
    for stat, count in stat_dist.items():
        print(f"  {stat}: {count} کارت")
    
    # بررسی totals
    print("\nبررسی Total Ranges:")
    normal_totals = [c["normal"]["total"] for c in data["cards"]]
    epic_totals = [c["epic"]["total"] for c in data["cards"]]
    legend_totals = [c["legend"]["total"] for c in data["cards"]]
    
    print(f"  Normal: {min(normal_totals)}-{max(normal_totals)} (هدف: 14-22)")
    print(f"  Epic: {min(epic_totals)}-{max(epic_totals)} (هدف: 18-26)")
    print(f"  Legend: {min(legend_totals)}-{max(legend_totals)} (هدف: 22-32)")
    
    # نمایش چند نمونه
    print("\n📋 نمونه کارت‌ها:")
    for i in range(min(3, len(data["cards"]))):
        card = data["cards"][i]
        print(f"\n{i+1}. {card['name']} ({card['name_fa']})")
        print(f"   Type: {card['card_type']}")
        print(f"   Normal: P={card['normal']['power']}, S={card['normal']['speed']}, I={card['normal']['iq']}, Pop={card['normal']['popularity']} (Total: {card['normal']['total']})")
        print(f"   Epic: P={card['epic']['power']}, S={card['epic']['speed']}, I={card['epic']['iq']}, Pop={card['epic']['popularity']} (Total: {card['epic']['total']})")
        print(f"   Legend: P={card['legend']['power']}, S={card['legend']['speed']}, I={card['legend']['iq']}, Pop={card['legend']['popularity']} (Total: {card['legend']['total']})")
