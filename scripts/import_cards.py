#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت اضافه کردن کارت‌ها از پوشه card_images به دیتابیس
"""

import os
import uuid
import random
from game_core import DatabaseManager, Card, CardRarity

# آمار از پیش تعریف شده برای کارت‌های شناخته‌شده
KNOWN_CARDS = {
    # Legend
    "thanos":           {"rarity": CardRarity.LEGEND, "power": 94, "speed": 80, "iq": 78, "popularity": 64},
    "darkseid":         {"rarity": CardRarity.LEGEND, "power": 96, "speed": 75, "iq": 82, "popularity": 60},
    "kratos":           {"rarity": CardRarity.LEGEND, "power": 95, "speed": 85, "iq": 70, "popularity": 75},
    "homelander":       {"rarity": CardRarity.LEGEND, "power": 92, "speed": 88, "iq": 65, "popularity": 72},
    "omni_man":         {"rarity": CardRarity.LEGEND, "power": 93, "speed": 90, "iq": 68, "popularity": 70},
    "hulk":             {"rarity": CardRarity.LEGEND, "power": 97, "speed": 72, "iq": 55, "popularity": 80},
    "thor":             {"rarity": CardRarity.LEGEND, "power": 91, "speed": 82, "iq": 72, "popularity": 78},
    "venom":            {"rarity": CardRarity.LEGEND, "power": 89, "speed": 80, "iq": 60, "popularity": 74},
    "terminator":       {"rarity": CardRarity.LEGEND, "power": 90, "speed": 78, "iq": 75, "popularity": 82},
    "god_father":       {"rarity": CardRarity.LEGEND, "power": 70, "speed": 55, "iq": 95, "popularity": 90},
    "joker":            {"rarity": CardRarity.LEGEND, "power": 72, "speed": 78, "iq": 92, "popularity": 95},
    "darth_whither":    {"rarity": CardRarity.LEGEND, "power": 88, "speed": 76, "iq": 85, "popularity": 88},
    "tony_soprano":     {"rarity": CardRarity.LEGEND, "power": 75, "speed": 60, "iq": 88, "popularity": 85},
    "walter_white":     {"rarity": CardRarity.LEGEND, "power": 65, "speed": 58, "iq": 98, "popularity": 92},
    "heisenberg":       {"rarity": CardRarity.LEGEND, "power": 65, "speed": 58, "iq": 98, "popularity": 92},
    "putin":            {"rarity": CardRarity.LEGEND, "power": 78, "speed": 65, "iq": 90, "popularity": 80},
    "trump":            {"rarity": CardRarity.LEGEND, "power": 68, "speed": 55, "iq": 62, "popularity": 88},

    # Epic
    "john_wick":        {"rarity": CardRarity.NORMAL, "power": 82, "speed": 88, "iq": 78, "popularity": 85},
    "batman":           {"rarity": CardRarity.EPIC, "power": 80, "speed": 85, "iq": 90, "popularity": 92},
    "iron_man":         {"rarity": CardRarity.EPIC, "power": 78, "speed": 80, "iq": 95, "popularity": 90},
    "spiderman":        {"rarity": CardRarity.EPIC, "power": 76, "speed": 92, "iq": 82, "popularity": 88},
    "dead_pool":        {"rarity": CardRarity.EPIC, "power": 85, "speed": 84, "iq": 72, "popularity": 90},
    "captain_america":  {"rarity": CardRarity.EPIC, "power": 82, "speed": 80, "iq": 78, "popularity": 88},
    "black_widow":      {"rarity": CardRarity.EPIC, "power": 72, "speed": 90, "iq": 85, "popularity": 86},
    "ezio":             {"rarity": CardRarity.EPIC, "power": 80, "speed": 88, "iq": 82, "popularity": 78},
    "leon_kennedy":     {"rarity": CardRarity.EPIC, "power": 78, "speed": 82, "iq": 75, "popularity": 72},
    "ada_wong":         {"rarity": CardRarity.EPIC, "power": 70, "speed": 88, "iq": 85, "popularity": 80},
    "albert_wesker":    {"rarity": CardRarity.EPIC, "power": 88, "speed": 85, "iq": 90, "popularity": 68},
    "negan":            {"rarity": CardRarity.EPIC, "power": 82, "speed": 72, "iq": 78, "popularity": 80},
    "rick_grimes":      {"rarity": CardRarity.EPIC, "power": 78, "speed": 75, "iq": 80, "popularity": 82},
    "michle_scofield":  {"rarity": CardRarity.EPIC, "power": 65, "speed": 72, "iq": 95, "popularity": 85},
    "t_bag":            {"rarity": CardRarity.EPIC, "power": 60, "speed": 68, "iq": 88, "popularity": 72},
    "saul_goodman":     {"rarity": CardRarity.EPIC, "power": 55, "speed": 65, "iq": 95, "popularity": 88},
    "mike_ehrmantraut": {"rarity": CardRarity.EPIC, "power": 80, "speed": 75, "iq": 88, "popularity": 72},
    "tyrion":           {"rarity": CardRarity.EPIC, "power": 50, "speed": 60, "iq": 96, "popularity": 88},
    "deanerys_targaryen":{"rarity": CardRarity.EPIC, "power": 72, "speed": 68, "iq": 82, "popularity": 90},
    "sherlock":         {"rarity": CardRarity.EPIC, "power": 55, "speed": 70, "iq": 98, "popularity": 82},
    "patrick_bateman":  {"rarity": CardRarity.EPIC, "power": 75, "speed": 72, "iq": 88, "popularity": 78},
    "arthur_morgan":    {"rarity": CardRarity.EPIC, "power": 85, "speed": 78, "iq": 72, "popularity": 82},
    "joel":             {"rarity": CardRarity.EPIC, "power": 82, "speed": 75, "iq": 78, "popularity": 80},
    "ellie":            {"rarity": CardRarity.EPIC, "power": 72, "speed": 82, "iq": 80, "popularity": 78},
    "ghost":            {"rarity": CardRarity.EPIC, "power": 85, "speed": 88, "iq": 82, "popularity": 80},
    "scorpion":         {"rarity": CardRarity.EPIC, "power": 88, "speed": 85, "iq": 68, "popularity": 75},
    "subzero":          {"rarity": CardRarity.EPIC, "power": 86, "speed": 82, "iq": 70, "popularity": 74},
    "mileena":          {"rarity": CardRarity.EPIC, "power": 82, "speed": 88, "iq": 65, "popularity": 72},
    "shredder":         {"rarity": CardRarity.EPIC, "power": 85, "speed": 80, "iq": 72, "popularity": 70},
    "tai_lung":         {"rarity": CardRarity.EPIC, "power": 88, "speed": 85, "iq": 70, "popularity": 68},
    "hannah_irani":     {"rarity": CardRarity.EPIC, "power": 38, "speed": 53, "iq": 68, "popularity": 92},
    "billie_butcher":   {"rarity": CardRarity.EPIC, "power": 80, "speed": 75, "iq": 78, "popularity": 76},
    "jack_sporrow":     {"rarity": CardRarity.EPIC, "power": 65, "speed": 78, "iq": 80, "popularity": 90},
    "bruce_lee":        {"rarity": CardRarity.EPIC, "power": 88, "speed": 95, "iq": 78, "popularity": 90},
    "jackie_chan":      {"rarity": CardRarity.EPIC, "power": 82, "speed": 90, "iq": 75, "popularity": 88},
    "noob_sibot":       {"rarity": CardRarity.EPIC, "power": 82, "speed": 80, "iq": 68, "popularity": 65},
    "mr_chief":         {"rarity": CardRarity.EPIC, "power": 88, "speed": 82, "iq": 78, "popularity": 75},
    "daryl_dixon":      {"rarity": CardRarity.EPIC, "power": 78, "speed": 82, "iq": 72, "popularity": 75},

    # Normal
    "spongebob":        {"rarity": CardRarity.NORMAL, "power": 27, "speed": 55, "iq": 12, "popularity": 60},
    "sponge_bob":       {"rarity": CardRarity.NORMAL, "power": 27, "speed": 55, "iq": 12, "popularity": 60},
    "mrbean":           {"rarity": CardRarity.NORMAL, "power": 14, "speed": 36, "iq": 23, "popularity": 56},
    "mr_bean":          {"rarity": CardRarity.NORMAL, "power": 14, "speed": 36, "iq": 23, "popularity": 56},
    "tataloo":          {"rarity": CardRarity.NORMAL, "power": 42, "speed": 37, "iq": 40, "popularity": 57},
    "reza":             {"rarity": CardRarity.NORMAL, "power": 5,  "speed": 22, "iq": 46, "popularity": 45},
    "kangfupanda":      {"rarity": CardRarity.NORMAL, "power": 63, "speed": 31, "iq": 39, "popularity": 65},
    "kangfu_panda":     {"rarity": CardRarity.NORMAL, "power": 63, "speed": 31, "iq": 39, "popularity": 65},
    "tr":               {"rarity": CardRarity.NORMAL, "power": 43, "speed": 8,  "iq": 53, "popularity": 34},
    "rehi":             {"rarity": CardRarity.NORMAL, "power": 35, "speed": 45, "iq": 50, "popularity": 55},
    "sonic":            {"rarity": CardRarity.NORMAL, "power": 55, "speed": 98, "iq": 45, "popularity": 72},
    "mario":            {"rarity": CardRarity.NORMAL, "power": 50, "speed": 60, "iq": 55, "popularity": 80},
    "shrek":            {"rarity": CardRarity.NORMAL, "power": 72, "speed": 45, "iq": 48, "popularity": 75},
    "toothless":        {"rarity": CardRarity.NORMAL, "power": 68, "speed": 75, "iq": 55, "popularity": 72},
    "ben10":            {"rarity": CardRarity.NORMAL, "power": 65, "speed": 70, "iq": 58, "popularity": 68},
    "tom":              {"rarity": CardRarity.NORMAL, "power": 35, "speed": 65, "iq": 42, "popularity": 70},
    "jerry":            {"rarity": CardRarity.NORMAL, "power": 20, "speed": 80, "iq": 72, "popularity": 75},
    "patrick":          {"rarity": CardRarity.NORMAL, "power": 30, "speed": 25, "iq": 5,  "popularity": 65},
    "squidward":        {"rarity": CardRarity.NORMAL, "power": 25, "speed": 35, "iq": 55, "popularity": 45},
    "mr.krabs":         {"rarity": CardRarity.NORMAL, "power": 35, "speed": 30, "iq": 65, "popularity": 55},
    "bojak":            {"rarity": CardRarity.NORMAL, "power": 30, "speed": 40, "iq": 60, "popularity": 58},
    "pink_panther":     {"rarity": CardRarity.NORMAL, "power": 35, "speed": 55, "iq": 60, "popularity": 65},
    "doge":             {"rarity": CardRarity.NORMAL, "power": 20, "speed": 45, "iq": 30, "popularity": 80},
    "gigachad":         {"rarity": CardRarity.NORMAL, "power": 70, "speed": 65, "iq": 55, "popularity": 85},
    "risitas":          {"rarity": CardRarity.NORMAL, "power": 25, "speed": 40, "iq": 35, "popularity": 78},
    "michelangelo":     {"rarity": CardRarity.NORMAL, "power": 65, "speed": 72, "iq": 55, "popularity": 68},
    "master_shifu":     {"rarity": CardRarity.NORMAL, "power": 60, "speed": 70, "iq": 80, "popularity": 65},
    "cj":               {"rarity": CardRarity.NORMAL, "power": 55, "speed": 60, "iq": 50, "popularity": 70},
    "snoop_dogg":       {"rarity": CardRarity.NORMAL, "power": 45, "speed": 50, "iq": 65, "popularity": 85},
    "rostam":           {"rarity": CardRarity.NORMAL, "power": 80, "speed": 70, "iq": 65, "popularity": 60},
    "mokhtar":          {"rarity": CardRarity.NORMAL, "power": 72, "speed": 65, "iq": 68, "popularity": 62},
    "jumong":           {"rarity": CardRarity.NORMAL, "power": 75, "speed": 68, "iq": 70, "popularity": 65},
    "semir_gerkhan":    {"rarity": CardRarity.NORMAL, "power": 65, "speed": 60, "iq": 58, "popularity": 62},
    "pezeshkian":       {"rarity": CardRarity.NORMAL, "power": 45, "speed": 40, "iq": 70, "popularity": 65},
    "bashar_al_assad":  {"rarity": CardRarity.NORMAL, "power": 55, "speed": 45, "iq": 60, "popularity": 40},
    "abbas_araqchi":    {"rarity": CardRarity.NORMAL, "power": 40, "speed": 38, "iq": 65, "popularity": 45},
    "aghaye_ghazy":     {"rarity": CardRarity.NORMAL, "power": 35, "speed": 32, "iq": 60, "popularity": 50},
    "big_masoud":       {"rarity": CardRarity.NORMAL, "power": 50, "speed": 42, "iq": 55, "popularity": 60},
    "amoo_poorang":     {"rarity": CardRarity.NORMAL, "power": 30, "speed": 35, "iq": 45, "popularity": 55},
    "daddy_golzar":     {"rarity": CardRarity.NORMAL, "power": 40, "speed": 38, "iq": 50, "popularity": 65},
    "daeso":            {"rarity": CardRarity.NORMAL, "power": 45, "speed": 42, "iq": 48, "popularity": 58},
    "davood_zzz":       {"rarity": CardRarity.NORMAL, "power": 35, "speed": 30, "iq": 45, "popularity": 50},
    "dr_stop":          {"rarity": CardRarity.NORMAL, "power": 40, "speed": 35, "iq": 55, "popularity": 52},
    "etabaki":          {"rarity": CardRarity.NORMAL, "power": 38, "speed": 32, "iq": 48, "popularity": 55},
    "heshmat_ferdous":  {"rarity": CardRarity.NORMAL, "power": 35, "speed": 30, "iq": 50, "popularity": 52},
    "jenab_khan":       {"rarity": CardRarity.NORMAL, "power": 42, "speed": 38, "iq": 55, "popularity": 58},
    "mamooti":          {"rarity": CardRarity.NORMAL, "power": 38, "speed": 35, "iq": 48, "popularity": 55},
    "naghi_mamooli":    {"rarity": CardRarity.NORMAL, "power": 35, "speed": 32, "iq": 45, "popularity": 52},
    "nima_afshar":      {"rarity": CardRarity.NORMAL, "power": 40, "speed": 38, "iq": 52, "popularity": 60},
    "pourya_vali":      {"rarity": CardRarity.NORMAL, "power": 42, "speed": 40, "iq": 50, "popularity": 62},
    "rambod_javan":     {"rarity": CardRarity.NORMAL, "power": 38, "speed": 35, "iq": 55, "popularity": 65},
    "shir_farhad":      {"rarity": CardRarity.NORMAL, "power": 40, "speed": 38, "iq": 50, "popularity": 58},
}

def filename_to_display_name(filename: str) -> str:
    """تبدیل نام فایل به نام نمایشی"""
    name = filename.replace('_', ' ').replace('-', ' ')
    return ' '.join(word.capitalize() for word in name.split())

def get_card_type(stats: dict) -> str:
    """تعیین نوع کارت بر اساس بالاترین آمار"""
    s = {
        "POWER_TYPE": stats["power"],
        "SPEED_TYPE": stats["speed"],
        "IQ_TYPE": stats["iq"],
        "POPULARITY_TYPE": stats["popularity"],
    }
    return max(s, key=s.get)

def main():
    db = DatabaseManager()
    
    # کارت‌های موجود در دیتابیس
    existing = {c.name.lower().replace(' ', '_'): c for c in db.get_all_cards()}
    existing_names = set(existing.keys())
    
    # کارت‌های موجود در پوشه
    images_dir = "card_images"
    image_files = [
        os.path.splitext(f)[0]
        for f in os.listdir(images_dir)
        if f.endswith('.png') and '(2)' not in f and f != '.png'
    ]
    
    added = 0
    skipped = 0
    
    for filename in sorted(image_files):
        key = filename.lower()
        
        # اگه قبلاً اضافه شده، رد کن
        if key in existing_names:
            skipped += 1
            continue
        
        # آمار کارت
        if key in KNOWN_CARDS:
            info = KNOWN_CARDS[key]
            rarity = info["rarity"]
            power = info["power"]
            speed = info["speed"]
            iq = info["iq"]
            popularity = info["popularity"]
        else:
            # آمار تصادفی برای کارت‌های ناشناخته
            rarity = CardRarity.NORMAL
            power = random.randint(20, 65)
            speed = random.randint(20, 65)
            iq = random.randint(20, 65)
            popularity = random.randint(20, 65)
        
        display_name = filename_to_display_name(filename)
        card_type = get_card_type({"power": power, "speed": speed, "iq": iq, "popularity": popularity})
        
        card = Card(
            card_id=str(uuid.uuid4())[:8],
            name=display_name,
            rarity=rarity,
            power=power,
            speed=speed,
            iq=iq,
            popularity=popularity,
            abilities=[],
            dialogs=[],
            biography="Biography not available.",
            image_path=f"card_images/{filename}.png",
            card_type=card_type,
        )
        
        result = db.add_card(card)
        if result:
            added += 1
            rarity_icon = {"normal": "🟢", "epic": "🟣", "legend": "🟡"}.get(rarity.value, "⚪")
            print(f"  {rarity_icon} اضافه شد: {display_name} (P:{power} S:{speed} IQ:{iq} Pop:{popularity})")
        else:
            print(f"  ⚠️ خطا در اضافه کردن: {display_name}")
    
    print(f"\n{'='*50}")
    print(f"✅ {added} کارت جدید اضافه شد")
    print(f"⏭️  {skipped} کارت قبلاً موجود بود")
    print(f"📦 مجموع کارت‌ها: {len(db.get_all_cards())}")

if __name__ == "__main__":
    main()
