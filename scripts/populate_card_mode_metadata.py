#!/usr/bin/env python3
"""Fill safe, reproducible metadata for every existing card game mode.

The metadata is deliberately conservative: Deck gets standard traits and
series for meaningful synergies, Easy gets all six authored hidden stats, and
Quick gets one arena-bound +1 passive per card.  Existing admin edits are kept
unless ``--overwrite`` is explicitly requested.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Tuple


HIDDEN_STATS = ("funny", "scary", "charisma", "cute", "evil", "leadership")


# Traits intentionally use the vocabulary understood by the Deck arenas.
# Series names are player-facing Persian labels and create real deck synergies.
CARD_PROFILES: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "Abbas Araqchi": (("leader",), "چهره‌های ایرانی"),
    "Ada Wong": (("assassin", "hero"), "Resident Evil"),
    "Aghaye Ghazy": (("leader",), "چهره‌های ایرانی"),
    "Albert Wesker": (("villain", "mage"), "Resident Evil"),
    "Amoo Poorang": (("funny",), "چهره‌های ایرانی"),
    "Arthur Morgan": (("warrior", "hero"), "Red Dead Redemption"),
    "Bashar Al Assad": (("leader",), "چهره‌های سیاسی"),
    "Batman": (("detective", "hero"), "DC"),
    "Ben10": (("hero",), "Ben 10"),
    "Big Masoud": (("leader", "funny"), "چهره‌های ایرانی"),
    "Billie Butcher": (("warrior", "hero"), "The Boys"),
    "Black Widow": (("assassin", "hero"), "Marvel"),
    "Bojak": (("funny",), "BoJack Horseman"),
    "Bruce Lee": (("warrior", "hero"), "Legends"),
    "Captain America": (("hero", "leader"), "Marvel"),
    "Cj": (("warrior",), "GTA"),
    "Daddy Golzar": (("funny",), "چهره‌های ایرانی"),
    "Daeso": (("leader", "warrior"), "Jumong"),
    "Darkseid": (("god", "villain"), "DC"),
    "Darth Whither": (("villain", "mage"), "Star Wars"),
    "Daryl Dixon": (("warrior", "hero"), "The Walking Dead"),
    "Davood Zzz": (("funny",), "چهره‌های ایرانی"),
    "Dead Pool": (("hero", "funny"), "Marvel"),
    "Deanerys Targaryen": (("leader", "mage"), "Game of Thrones"),
    "Doge": (("funny",), "میم‌های اینترنتی"),
    "Dr Stop": (("mage",), "چهره‌های ایرانی"),
    "Ellie": (("warrior", "hero"), "The Last of Us"),
    "Etabaki": (("leader", "funny"), "چهره‌های ایرانی"),
    "Ezio": (("assassin", "hero"), "Assassin's Creed"),
    "Ghost": (("assassin",), "Call of Duty"),
    "Gigachad": (("funny",), "میم‌های اینترنتی"),
    "God Father": (("leader", "villain"), "The Godfather"),
    "Heisenberg": (("mage", "villain"), "Breaking Bad"),
    "Heshmat Ferdous": (("leader", "funny"), "چهره‌های ایرانی"),
    "Homelander": (("villain", "hero"), "The Boys"),
    "Hulk": (("monster", "hero"), "Marvel"),
    "Iron Man": (("hero", "mage"), "Marvel"),
    "Jack Sporrow": (("warrior", "funny"), "Pirates of the Caribbean"),
    "Jackie Chan": (("warrior", "funny"), "Legends"),
    "Jenab Khan": (("funny",), "چهره‌های ایرانی"),
    "Jerry": (("funny", "assassin"), "Tom and Jerry"),
    "Joel": (("warrior", "hero"), "The Last of Us"),
    "John Wick": (("assassin", "warrior"), "John Wick"),
    "Joker": (("villain", "funny"), "DC"),
    "Jumong": (("warrior", "leader"), "Jumong"),
    "Kangfu Panda": (("hero", "funny"), "Kung Fu Panda"),
    "Kratos": (("god", "warrior"), "God of War"),
    "Leon Kennedy": (("detective", "hero"), "Resident Evil"),
    "Mamooti": (("funny", "monster"), "چهره‌های ایرانی"),
    "Mario": (("hero", "funny"), "Nintendo"),
    "Master Shifu": (("mage", "leader"), "Kung Fu Panda"),
    "Michelangelo": (("hero", "funny"), "TMNT"),
    "Michle Scofield": (("detective", "hero"), "Prison Break"),
    "Mike Ehrmantraut": (("detective", "warrior"), "Breaking Bad"),
    "Mileena": (("assassin", "villain"), "Mortal Kombat"),
    "Mokhtar": (("leader", "warrior"), "چهره‌های ایرانی"),
    "Mr Bean": (("funny",), "Mr. Bean"),
    "Mr Chief": (("leader", "warrior"), "چهره‌های ایرانی"),
    "Mr.krabs": (("funny", "leader"), "SpongeBob SquarePants"),
    "Naghi Mamooli": (("leader", "funny"), "چهره‌های ایرانی"),
    "Negan": (("villain", "leader"), "The Walking Dead"),
    "Nima Afshar": (("funny",), "چهره‌های ایرانی"),
    "Noob Sibot": (("assassin", "villain"), "Mortal Kombat"),
    "Omni Man": (("monster", "villain"), "Invincible"),
    "Patrick": (("funny",), "SpongeBob SquarePants"),
    "Patrick Bateman": (("villain",), "American Psycho"),
    "Pezeshkian": (("leader",), "چهره‌های سیاسی"),
    "Pink Panther": (("funny", "assassin"), "Pink Panther"),
    "Pourya Vali": (("warrior", "leader"), "چهره‌های ایرانی"),
    "Putin": (("leader",), "چهره‌های سیاسی"),
    "Rambod Javan": (("funny",), "چهره‌های ایرانی"),
    "Rehi": (("funny",), "چهره‌های ایرانی"),
    "Rick Grimes": (("leader", "hero"), "The Walking Dead"),
    "Risitas": (("funny",), "میم‌های اینترنتی"),
    "Rostam": (("warrior", "hero"), "شاهنامه"),
    "Saul Goodman": (("detective", "funny"), "Breaking Bad"),
    "Scorpion": (("assassin", "warrior"), "Mortal Kombat"),
    "Semir Gerkhan": (("detective", "hero"), "Cobra 11"),
    "Sherlock": (("detective",), "Sherlock Holmes"),
    "Shir Farhad": (("warrior",), "افسانه‌های ایرانی"),
    "Shredder": (("villain", "warrior"), "TMNT"),
    "Shrek": (("monster", "funny"), "Shrek"),
    "Snoop Dogg": (("funny",), "Music Legends"),
    "Sonic": (("hero", "assassin"), "Sonic"),
    "Spiderman": (("hero", "assassin"), "Marvel"),
    "Sponge Bob": (("funny", "hero"), "SpongeBob SquarePants"),
    "Squidward": (("funny",), "SpongeBob SquarePants"),
    "Subzero": (("assassin", "warrior"), "Mortal Kombat"),
    "T Bag": (("villain", "funny"), "Prison Break"),
    "Tai Lung": (("villain", "warrior"), "Kung Fu Panda"),
    "Tataloo": (("funny",), "چهره‌های ایرانی"),
    "Terminator": (("monster", "warrior"), "Terminator"),
    "Thanos": (("god", "villain"), "Marvel"),
    "Thor": (("god", "hero"), "Marvel"),
    "Tom": (("funny", "warrior"), "Tom and Jerry"),
    "Tony Soprano": (("leader", "villain"), "The Sopranos"),
    "Toothless": (("monster", "hero"), "How to Train Your Dragon"),
    "Trump": (("leader",), "چهره‌های سیاسی"),
    "Tyrion": (("detective", "leader"), "Game of Thrones"),
    "Venom": (("monster", "villain"), "Marvel"),
}


def _jitter(name: str, stat: str) -> int:
    digest = hashlib.sha256(f"{name}:{stat}".encode("utf-8")).digest()
    return int(digest[0] % 13) - 6


def hidden_stats(name: str, traits: Iterable[str]) -> Dict[str, int]:
    traits = set(traits)
    bases = {stat: 45 for stat in HIDDEN_STATS}
    if "funny" in traits:
        bases["funny"] += 40
    if "villain" in traits or "monster" in traits:
        bases["scary"] += 38
        bases["evil"] += 35
    if "leader" in traits:
        bases["leadership"] += 38
        bases["charisma"] += 22
    if "hero" in traits:
        bases["leadership"] += 16
        bases["charisma"] += 12
    if "detective" in traits or "mage" in traits:
        bases["charisma"] += 10
    if "assassin" in traits:
        bases["scary"] += 16
    if name in {"Doge", "Jerry", "Patrick", "Sponge Bob", "Toothless", "Mamooti"}:
        bases["cute"] += 42
    if name in {"Joker", "Mr Bean", "Risitas", "Sponge Bob", "Dead Pool", "Jenab Khan"}:
        bases["funny"] = 96
    if name in {"Thanos", "Darkseid", "Hulk", "Venom", "Omni Man", "Kratos"}:
        bases["scary"] = 94
    return {stat: max(1, min(100, bases[stat] + _jitter(name, stat))) for stat in HIDDEN_STATS}


def passive_for(traits: Iterable[str]) -> Dict[str, object]:
    traits = set(traits)
    if "god" in traits or "monster" in traits:
        return {"name": "حضور سنگین", "condition": {"arena": "desert"}, "effect": {"stat": "power", "delta": 1}}
    if "assassin" in traits:
        return {"name": "حرکت سایه", "condition": {"arena": "ice"}, "effect": {"stat": "speed", "delta": 1}}
    if "detective" in traits or "mage" in traits:
        return {"name": "ذهن آماده", "condition": {"arena": "silent_temple"}, "effect": {"stat": "iq", "delta": 1}}
    if "leader" in traits:
        return {"name": "فرماندهی", "condition": {"arena": "city"}, "effect": {"stat": "popularity", "delta": 1}}
    if "funny" in traits:
        return {"name": "جلب توجه", "condition": {"arena": "city"}, "effect": {"stat": "popularity", "delta": 1}}
    if "villain" in traits:
        return {"name": "نقشه پنهان", "condition": {"arena": "forest"}, "effect": {"stat": "iq", "delta": 1}}
    return {"name": "ثبات میدان", "condition": {"arena": "city"}, "effect": {"stat": "power", "delta": 1}}


def build_metadata(name: str) -> Dict[str, object]:
    traits, series = CARD_PROFILES[name]
    return {"traits": list(traits), "series": series, "hidden_stats": hidden_stats(name, traits), "passive": passive_for(traits)}


def populate(db_path: Path, apply: bool, overwrite: bool = False):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS card_mode_metadata (
        card_id TEXT PRIMARY KEY, traits TEXT NOT NULL DEFAULT '[]', series TEXT,
        hidden_stats TEXT NOT NULL DEFAULT '{}', passive TEXT NOT NULL DEFAULT '{}'
    )""")
    cards = list(conn.execute("SELECT card_id, name FROM cards ORDER BY name"))
    card_names = {row["name"] for row in cards}
    missing_profiles = sorted(card_names - set(CARD_PROFILES))
    stale_profiles = sorted(set(CARD_PROFILES) - card_names)
    if missing_profiles:
        raise ValueError("Missing profiles for: " + ", ".join(missing_profiles))
    updates = []
    for card in cards:
        old = conn.execute("SELECT * FROM card_mode_metadata WHERE card_id=?", (card["card_id"],)).fetchone()
        existing = bool(old and (old["traits"] != "[]" or old["series"] or old["hidden_stats"] != "{}" or old["passive"] != "{}"))
        if existing and not overwrite:
            continue
        metadata = build_metadata(card["name"])
        updates.append((card["card_id"], metadata))
    if apply:
        conn.executemany(
            """INSERT INTO card_mode_metadata(card_id, traits, series, hidden_stats, passive)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(card_id) DO UPDATE SET traits=excluded.traits, series=excluded.series,
               hidden_stats=excluded.hidden_stats, passive=excluded.passive""",
            [(card_id, json.dumps(meta["traits"], ensure_ascii=False), meta["series"],
              json.dumps(meta["hidden_stats"], ensure_ascii=False), json.dumps(meta["passive"], ensure_ascii=False))
             for card_id, meta in updates],
        )
        conn.commit()
    conn.close()
    return updates, stale_profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("game_bot.db"))
    parser.add_argument("--apply", action="store_true", help="Write changes; otherwise print a dry run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing manual metadata.")
    args = parser.parse_args()
    updates, stale_profiles = populate(args.db, args.apply, args.overwrite)
    print(f"{'APPLIED' if args.apply else 'DRY-RUN'}: {len(updates)} card(s) would receive mode metadata")
    if stale_profiles:
        print("Profiles without a current card: " + ", ".join(stale_profiles))


if __name__ == "__main__":
    main()
