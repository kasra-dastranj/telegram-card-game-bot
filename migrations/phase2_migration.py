#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔄 TelBattle Phase 2 Migration Script
مهاجرت از فاز ۱ به فاز ۲

این اسکریپت:
1. تبدیل آمار کارت‌ها از 0-100 به 0-10
2. تخصیص Card Type به کارت‌ها
3. تبدیل همه کارت‌های بازیکنان به Normal
4. Initialize Level & Tier برای بازیکنان
5. اضافه کردن ستون‌های جدید به دیتابیس
"""

import sqlite3
import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Tuple

class Phase2Migration:
    def __init__(self, db_path: str = "game_bot_test.db"):
        self.db_path = db_path
        self.backup_path = None
        self.migration_log = []
        
    def log(self, message: str, level: str = "INFO"):
        """لاگ پیام‌ها"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.migration_log.append(log_entry)
        print(log_entry)
    
    def create_backup(self) -> bool:
        """بکاپ گرفتن از دیتابیس"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_path = f"{self.db_path}.backup_phase2_{timestamp}"
            shutil.copy2(self.db_path, self.backup_path)
            self.log(f"✅ بکاپ ایجاد شد: {self.backup_path}", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"❌ خطا در ایجاد بکاپ: {e}", "ERROR")
            return False
    
    def migrate_card_stats(self, old_stats: Dict[str, int]) -> Dict[str, int]:
        """
        تبدیل آمار از سیستم 0-100 به سیستم 0-10
        
        فرمول: new_value = round(old_value / 10)
        محدودیت: 0 <= new_value <= 10
        """
        new_stats = {}
        
        for stat_name in ['power', 'speed', 'iq', 'popularity']:
            old_value = old_stats.get(stat_name, 50)  # پیش‌فرض 50
            
            # تبدیل خطی
            new_value = round(old_value / 10)
            
            # محدود کردن به بازه 0-10
            new_value = max(0, min(10, new_value))
            
            new_stats[stat_name] = new_value
        
        return new_stats
    
    def assign_card_type(self, card_stats: Dict[str, int]) -> str:
        """
        تعیین تایپ کارت بر اساس بالاترین آمار
        
        اولویت در صورت تساوی: power > speed > iq > popularity
        """
        max_stat = max(card_stats, key=lambda k: (card_stats[k], ['power', 'speed', 'iq', 'popularity'].index(k)))
        
        type_mapping = {
            "power": "POWER_TYPE",
            "speed": "SPEED_TYPE",
            "iq": "IQ_TYPE",
            "popularity": "POPULARITY_TYPE"
        }
        
        return type_mapping.get(max_stat, "POWER_TYPE")
    
    def add_new_columns(self) -> bool:
        """اضافه کردن ستون‌های جدید به جداول موجود"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # اضافه کردن card_type به جدول cards
            try:
                cursor.execute("ALTER TABLE cards ADD COLUMN card_type TEXT DEFAULT 'POWER_TYPE'")
                self.log("✅ ستون card_type به جدول cards اضافه شد")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    self.log("⚠️  ستون card_type از قبل وجود دارد", "WARNING")
                else:
                    raise
            
            # اضافه کردن coins به جدول players
            try:
                cursor.execute("ALTER TABLE players ADD COLUMN coins INTEGER DEFAULT 0")
                self.log("✅ ستون coins به جدول players اضافه شد")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    self.log("⚠️  ستون coins از قبل وجود دارد", "WARNING")
                else:
                    raise
            
            # اضافه کردن weekly_score به جدول players
            try:
                cursor.execute("ALTER TABLE players ADD COLUMN weekly_score INTEGER DEFAULT 0")
                self.log("✅ ستون weekly_score به جدول players اضافه شد")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    self.log("⚠️  ستون weekly_score از قبل وجود دارد", "WARNING")
                else:
                    raise
            
            # اضافه کردن max_hearts به جدول players
            try:
                cursor.execute("ALTER TABLE players ADD COLUMN max_hearts INTEGER DEFAULT 10")
                self.log("✅ ستون max_hearts به جدول players اضافه شد")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    self.log("⚠️  ستون max_hearts از قبل وجود دارد", "WARNING")
                else:
                    raise
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            self.log(f"❌ خطا در اضافه کردن ستون‌ها: {e}", "ERROR")
            return False
    
    def create_new_tables(self) -> bool:
        """ایجاد جداول جدید فاز ۲"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # جدول player_progression
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS player_progression (
                    user_id INTEGER PRIMARY KEY,
                    level INTEGER DEFAULT 1,
                    total_xp INTEGER DEFAULT 0,
                    tier_points INTEGER DEFAULT 0,
                    current_tier TEXT DEFAULT 'Bronze',
                    last_played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES players (user_id)
                )
            ''')
            self.log("✅ جدول player_progression ایجاد شد")
            
            # جدول fusion_log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fusion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    fusion_type TEXT NOT NULL,
                    consumed_card_1 TEXT NOT NULL,
                    consumed_card_2 TEXT NOT NULL,
                    consumed_card_3 TEXT NOT NULL,
                    upgraded_card_id TEXT NOT NULL,
                    result_rarity TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES players (user_id)
                )
            ''')
            self.log("✅ جدول fusion_log ایجاد شد")
            
            # جدول card_missions (برای آینده)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS card_missions (
                    user_id INTEGER,
                    card_id TEXT,
                    mission_type TEXT,
                    current_progress INTEGER DEFAULT 0,
                    target INTEGER,
                    completed BOOLEAN DEFAULT 0,
                    PRIMARY KEY (user_id, card_id)
                )
            ''')
            self.log("✅ جدول card_missions ایجاد شد")
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            self.log(f"❌ خطا در ایجاد جداول: {e}", "ERROR")
            return False
    
    def migrate_cards(self) -> Tuple[int, int]:
        """
        مهاجرت کارت‌ها:
        1. تبدیل آمار از 0-100 به 0-10
        2. تخصیص Card Type
        
        Returns: (تعداد کارت‌های migrate شده, تعداد خطاها)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # دریافت تمام کارت‌ها
            cursor.execute("SELECT card_id, name, power, speed, iq, popularity FROM cards")
            cards = cursor.fetchall()
            
            migrated_count = 0
            error_count = 0
            
            for card in cards:
                card_id, name, power, speed, iq, popularity = card
                
                try:
                    # تبدیل آمار
                    old_stats = {
                        'power': power,
                        'speed': speed,
                        'iq': iq,
                        'popularity': popularity
                    }
                    
                    new_stats = self.migrate_card_stats(old_stats)
                    card_type = self.assign_card_type(new_stats)
                    
                    # به‌روزرسانی کارت
                    cursor.execute('''
                        UPDATE cards 
                        SET power = ?, speed = ?, iq = ?, popularity = ?, card_type = ?
                        WHERE card_id = ?
                    ''', (
                        new_stats['power'],
                        new_stats['speed'],
                        new_stats['iq'],
                        new_stats['popularity'],
                        card_type,
                        card_id
                    ))
                    
                    migrated_count += 1
                    self.log(f"  ✓ {name}: {old_stats} → {new_stats} ({card_type})")
                    
                except Exception as e:
                    error_count += 1
                    self.log(f"  ✗ خطا در migrate کارت {name}: {e}", "ERROR")
            
            conn.commit()
            conn.close()
            
            self.log(f"✅ {migrated_count} کارت migrate شدند ({error_count} خطا)", "SUCCESS")
            return migrated_count, error_count
            
        except Exception as e:
            self.log(f"❌ خطا در migrate کارت‌ها: {e}", "ERROR")
            return 0, 0
    
    def migrate_player_cards(self) -> Tuple[int, int]:
        """
        تبدیل همه کارت‌های بازیکنان به Normal
        
        Returns: (تعداد کارت‌های migrate شده, تعداد خطاها)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # دریافت تمام کارت‌های بازیکنان
            cursor.execute("""
                SELECT pc.id, pc.user_id, pc.card_id, c.name, c.rarity
                FROM player_cards pc
                JOIN cards c ON pc.card_id = c.card_id
            """)
            player_cards = cursor.fetchall()
            
            # تبدیل همه به Normal
            # نکته: در فاز ۱ rarity در جدول cards ذخیره می‌شود، نه player_cards
            # پس فقط باید cards را به‌روز کنیم
            
            cursor.execute("UPDATE cards SET rarity = 'normal'")
            
            migrated_count = len(player_cards)
            
            conn.commit()
            conn.close()
            
            self.log(f"✅ {migrated_count} کارت بازیکنان به Normal تبدیل شدند", "SUCCESS")
            return migrated_count, 0
            
        except Exception as e:
            self.log(f"❌ خطا در migrate کارت‌های بازیکنان: {e}", "ERROR")
            return 0, 0
    
    def initialize_player_progression(self) -> Tuple[int, int]:
        """
        Initialize Level & Tier برای بازیکنان موجود
        
        Returns: (تعداد بازیکنان initialize شده, تعداد خطاها)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # دریافت تمام بازیکنان
            cursor.execute("SELECT user_id, username FROM players")
            players = cursor.fetchall()
            
            initialized_count = 0
            error_count = 0
            
            for user_id, username in players:
                try:
                    # بررسی اینکه آیا قبلاً initialize شده
                    cursor.execute("SELECT user_id FROM player_progression WHERE user_id = ?", (user_id,))
                    if cursor.fetchone():
                        self.log(f"  ⚠️  بازیکن {username} ({user_id}) قبلاً initialize شده", "WARNING")
                        continue
                    
                    # Initialize با مقادیر پیش‌فرض
                    cursor.execute('''
                        INSERT INTO player_progression (user_id, level, total_xp, tier_points, current_tier, last_played_at)
                        VALUES (?, 1, 0, 0, 'Bronze', CURRENT_TIMESTAMP)
                    ''', (user_id,))
                    
                    # Initialize coins اگر وجود نداشت
                    cursor.execute("UPDATE players SET coins = 0 WHERE user_id = ? AND coins IS NULL", (user_id,))
                    
                    initialized_count += 1
                    self.log(f"  ✓ {username} ({user_id}): Level 1, Bronze, 0 TP")
                    
                except Exception as e:
                    error_count += 1
                    self.log(f"  ✗ خطا در initialize بازیکن {user_id}: {e}", "ERROR")
            
            conn.commit()
            conn.close()
            
            self.log(f"✅ {initialized_count} بازیکن initialize شدند ({error_count} خطا)", "SUCCESS")
            return initialized_count, error_count
            
        except Exception as e:
            self.log(f"❌ خطا در initialize بازیکنان: {e}", "ERROR")
            return 0, 0
    
    def verify_migration(self) -> bool:
        """بررسی صحت migration"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            issues = []
            
            # بررسی ۱: آمار کارت‌ها در بازه 0-10 هستند؟
            cursor.execute("""
                SELECT card_id, name, power, speed, iq, popularity 
                FROM cards 
                WHERE power < 0 OR power > 10 
                   OR speed < 0 OR speed > 10 
                   OR iq < 0 OR iq > 10 
                   OR popularity < 0 OR popularity > 10
            """)
            invalid_stats = cursor.fetchall()
            if invalid_stats:
                issues.append(f"❌ {len(invalid_stats)} کارت با آمار نامعتبر")
                for card in invalid_stats[:5]:  # نمایش ۵ مورد اول
                    issues.append(f"  - {card[1]}: power={card[2]}, speed={card[3]}, iq={card[4]}, pop={card[5]}")
            
            # بررسی ۲: همه کارت‌ها card_type دارند؟
            cursor.execute("SELECT COUNT(*) FROM cards WHERE card_type IS NULL OR card_type = ''")
            no_type_count = cursor.fetchone()[0]
            if no_type_count > 0:
                issues.append(f"❌ {no_type_count} کارت بدون card_type")
            
            # بررسی ۳: همه کارت‌ها Normal هستند؟
            cursor.execute("SELECT COUNT(*) FROM cards WHERE rarity != 'normal'")
            non_normal_count = cursor.fetchone()[0]
            if non_normal_count > 0:
                issues.append(f"❌ {non_normal_count} کارت Non-Normal")
            
            # بررسی ۴: همه بازیکنان progression دارند؟
            cursor.execute("""
                SELECT COUNT(*) 
                FROM players p 
                LEFT JOIN player_progression pp ON p.user_id = pp.user_id 
                WHERE pp.user_id IS NULL
            """)
            no_progression_count = cursor.fetchone()[0]
            if no_progression_count > 0:
                issues.append(f"❌ {no_progression_count} بازیکن بدون progression")
            
            # بررسی ۵: همه بازیکنان coins دارند؟
            cursor.execute("SELECT COUNT(*) FROM players WHERE coins IS NULL")
            no_coins_count = cursor.fetchone()[0]
            if no_coins_count > 0:
                issues.append(f"❌ {no_coins_count} بازیکن بدون coins")
            
            conn.close()
            
            if issues:
                self.log("❌ مشکلات یافت شد:", "ERROR")
                for issue in issues:
                    self.log(issue, "ERROR")
                return False
            else:
                self.log("✅ تمام بررسی‌ها موفق بودند", "SUCCESS")
                return True
                
        except Exception as e:
            self.log(f"❌ خطا در verify: {e}", "ERROR")
            return False
    
    def run(self) -> bool:
        """اجرای کامل migration"""
        self.log("=" * 60)
        self.log("🔄 شروع Migration فاز ۲")
        self.log("=" * 60)
        
        # مرحله ۱: بکاپ
        self.log("\n📦 مرحله ۱: ایجاد بکاپ...")
        if not self.create_backup():
            self.log("❌ Migration متوقف شد (بکاپ ناموفق)", "ERROR")
            return False
        
        # مرحله ۲: اضافه کردن ستون‌ها
        self.log("\n🔧 مرحله ۲: اضافه کردن ستون‌های جدید...")
        if not self.add_new_columns():
            self.log("❌ Migration متوقف شد (خطا در ستون‌ها)", "ERROR")
            return False
        
        # مرحله ۳: ایجاد جداول جدید
        self.log("\n🏗️  مرحله ۳: ایجاد جداول جدید...")
        if not self.create_new_tables():
            self.log("❌ Migration متوقف شد (خطا در جداول)", "ERROR")
            return False
        
        # مرحله ۴: migrate کارت‌ها
        self.log("\n🎴 مرحله ۴: migrate کارت‌ها (آمار و تایپ)...")
        cards_migrated, cards_errors = self.migrate_cards()
        if cards_errors > 0:
            self.log(f"⚠️  {cards_errors} خطا در migrate کارت‌ها", "WARNING")
        
        # مرحله ۵: تبدیل کارت‌های بازیکنان به Normal
        self.log("\n👥 مرحله ۵: تبدیل کارت‌های بازیکنان به Normal...")
        player_cards_migrated, player_cards_errors = self.migrate_player_cards()
        
        # مرحله ۶: initialize progression
        self.log("\n📊 مرحله ۶: initialize Level & Tier...")
        players_initialized, players_errors = self.initialize_player_progression()
        if players_errors > 0:
            self.log(f"⚠️  {players_errors} خطا در initialize بازیکنان", "WARNING")
        
        # مرحله ۷: verify
        self.log("\n🧪 مرحله ۷: بررسی صحت migration...")
        verification_passed = self.verify_migration()
        
        # خلاصه
        self.log("\n" + "=" * 60)
        if verification_passed:
            self.log("✅ Migration با موفقیت کامل شد!", "SUCCESS")
            self.log(f"📊 خلاصه:")
            self.log(f"  - کارت‌ها: {cards_migrated} migrate شدند")
            self.log(f"  - کارت‌های بازیکنان: {player_cards_migrated} به Normal تبدیل شدند")
            self.log(f"  - بازیکنان: {players_initialized} initialize شدند")
            self.log(f"  - بکاپ: {self.backup_path}")
        else:
            self.log("❌ Migration با مشکل مواجه شد", "ERROR")
            self.log(f"💾 بکاپ در: {self.backup_path}")
            self.log("⚠️  برای بازگشت: cp {self.backup_path} {self.db_path}")
        
        self.log("=" * 60)
        
        # ذخیره لاگ
        log_file = f"migration_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.migration_log))
        self.log(f"📝 لاگ ذخیره شد: {log_file}")
        
        return verification_passed


if __name__ == "__main__":
    migration = Phase2Migration()
    success = migration.run()
    
    if success:
        print("\n✅ آماده برای فاز ۲!")
        print("مراحل بعدی:")
        print("  1. تست کارت‌ها: python -c 'from game_core import *; db = DatabaseManager(); print(db.get_all_cards()[:3])'")
        print("  2. تست بازیکنان: python -c 'from game_core import *; db = DatabaseManager(); print(db.get_all_players()[:3])'")
        print("  3. شروع توسعه سیستم‌های جدید")
    else:
        print("\n❌ Migration ناموفق بود")
        print(f"برای بازگشت: cp {migration.backup_path} game_bot.db")
