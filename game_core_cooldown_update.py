#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Game Core Cooldown Update
بروزرسانی game_core.py برای سیستم Cooldown جداگانه هر کارت
"""

# این کد باید به game_core.py اضافه شود:

# 1. در تابع init_database، جدول جدید اضافه کنید:

COOLDOWN_TABLE_SQL = '''
        # جدول تنظیمات Cooldown هر کارت - NEW
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_cooldown_settings (
                card_id TEXT PRIMARY KEY,
                win_limit INTEGER DEFAULT 10,
                cooldown_hours INTEGER DEFAULT 24,
                enabled BOOLEAN DEFAULT 1,
                FOREIGN KEY (card_id) REFERENCES cards (card_id)
            )
        ''')
'''

# 2. توابع جدید برای کلاس DatabaseManager:

DATABASE_METHODS = '''
    # ==================== CARD COOLDOWN SETTINGS ====================
    
    def get_card_cooldown_settings(self, card_id: str) -> Dict:
        """دریافت تنظیمات cooldown کارت خاص"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT win_limit, cooldown_hours, enabled 
                FROM card_cooldown_settings 
                WHERE card_id = ?
            ''', (card_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'win_limit': result[0],
                    'cooldown_hours': result[1],
                    'enabled': bool(result[2])
                }
            else:
                # اگر تنظیمات وجود ندارد، مقادیر پیش‌فرض برگردان
                return {
                    'win_limit': 10,
                    'cooldown_hours': 24,
                    'enabled': True
                }
        finally:
            conn.close()
    
    def set_card_cooldown_settings(self, card_id: str, win_limit: int = None, 
                                 cooldown_hours: int = None, enabled: bool = None) -> bool:
        """تنظیم cooldown کارت خاص"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # بررسی وجود رکورد
            cursor.execute('SELECT card_id FROM card_cooldown_settings WHERE card_id = ?', (card_id,))
            exists = cursor.fetchone()
            
            if exists:
                # بروزرسانی رکورد موجود
                updates = []
                values = []
                
                if win_limit is not None:
                    updates.append('win_limit = ?')
                    values.append(win_limit)
                if cooldown_hours is not None:
                    updates.append('cooldown_hours = ?')
                    values.append(cooldown_hours)
                if enabled is not None:
                    updates.append('enabled = ?')
                    values.append(enabled)
                
                if updates:
                    values.append(card_id)
                    query = f"UPDATE card_cooldown_settings SET {', '.join(updates)} WHERE card_id = ?"
                    cursor.execute(query, values)
            else:
                # ایجاد رکورد جدید
                cursor.execute('''
                    INSERT INTO card_cooldown_settings (card_id, win_limit, cooldown_hours, enabled)
                    VALUES (?, ?, ?, ?)
                ''', (
                    card_id,
                    win_limit if win_limit is not None else 10,
                    cooldown_hours if cooldown_hours is not None else 24,
                    enabled if enabled is not None else True
                ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting card cooldown settings: {e}")
            return False
        finally:
            conn.close()
    
    def get_all_card_cooldown_settings(self) -> Dict[str, Dict]:
        """دریافت تنظیمات cooldown همه کارت‌ها"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT c.card_id, c.name, c.rarity,
                       COALESCE(ccs.win_limit, 10) as win_limit,
                       COALESCE(ccs.cooldown_hours, 24) as cooldown_hours,
                       COALESCE(ccs.enabled, 1) as enabled
                FROM cards c
                LEFT JOIN card_cooldown_settings ccs ON c.card_id = ccs.card_id
                WHERE c.rarity IN ('epic', 'legend')
                ORDER BY c.rarity DESC, c.name
            ''')
            
            results = cursor.fetchall()
            settings = {}
            
            for result in results:
                card_id, name, rarity, win_limit, cooldown_hours, enabled = result
                settings[card_id] = {
                    'name': name,
                    'rarity': rarity,
                    'win_limit': win_limit,
                    'cooldown_hours': cooldown_hours,
                    'enabled': bool(enabled)
                }
            
            return settings
        finally:
            conn.close()
'''

# 3. بروزرسانی توابع موجود در GameLogic:

GAMELOGIC_UPDATES = '''
    def is_card_in_cooldown(self, user_id: int, card_id: str) -> Tuple[bool, Optional[datetime]]:
        """بررسی cooldown کارت با تنظیمات جداگانه"""
        card = self.db.get_card_by_id(card_id)
        if not card or not self.is_card_eligible_for_cooldown(card):
            return False, None
        
        # دریافت تنظیمات خاص این کارت
        card_settings = self.db.get_card_cooldown_settings(card_id)
        if not card_settings['enabled']:
            return False, None
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT is_in_cooldown, cooldown_until 
                FROM card_cooldowns 
                WHERE user_id = ? AND card_id = ?
            ''', (user_id, card_id))
            
            result = cursor.fetchone()
            if not result:
                return False, None
            
            is_in_cooldown, cooldown_until_str = result
            
            if not is_in_cooldown or not cooldown_until_str:
                return False, None
            
            cooldown_until = datetime.fromisoformat(cooldown_until_str)
            now = datetime.now()
            
            # اگر cooldown گذشته باشد، آن را ریست کن
            if now >= cooldown_until:
                cursor.execute('''
                    UPDATE card_cooldowns 
                    SET is_in_cooldown = 0, cooldown_until = NULL 
                    WHERE user_id = ? AND card_id = ?
                ''', (user_id, card_id))
                conn.commit()
                return False, None
            
            return True, cooldown_until
            
        except Exception as e:
            logger.error(f"Error checking card cooldown for user {user_id}, card {card_id}: {e}")
            return False, None
        finally:
            conn.close()
    
    def record_card_win(self, user_id: int, card_id: str) -> None:
        """ثبت برد کارت با تنظیمات جداگانه"""
        card = self.db.get_card_by_id(card_id)
        if not card or not self.is_card_eligible_for_cooldown(card):
            return
        
        # دریافت تنظیمات خاص این کارت
        card_settings = self.db.get_card_cooldown_settings(card_id)
        if not card_settings['enabled']:
            return
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            now = datetime.now()
            
            # دریافت یا ایجاد رکورد cooldown
            cursor.execute('''
                SELECT wins_count, last_win_time, is_in_cooldown 
                FROM card_cooldowns 
                WHERE user_id = ? AND card_id = ?
            ''', (user_id, card_id))
            
            result = cursor.fetchone()
            
            if result:
                wins_count, last_win_time, is_in_cooldown = result
                wins_count += 1
            else:
                wins_count = 1
                is_in_cooldown = False
            
            # بررسی اینکه آیا باید وارد cooldown شود (با تنظیمات خاص کارت)
            cooldown_until = None
            if wins_count >= card_settings['win_limit']:
                is_in_cooldown = True
                cooldown_until = now + timedelta(hours=card_settings['cooldown_hours'])
                wins_count = 0  # ریست شمارنده
            
            # بروزرسانی یا درج رکورد
            cursor.execute('''
                INSERT OR REPLACE INTO card_cooldowns 
                (user_id, card_id, wins_count, last_win_time, cooldown_until, is_in_cooldown)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id, card_id, wins_count, 
                now.isoformat(), 
                cooldown_until.isoformat() if cooldown_until else None,
                is_in_cooldown
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error recording card win for user {user_id}, card {card_id}: {e}")
        finally:
            conn.close()
'''

print("✅ فایل game_core_cooldown_update.py آماده شد!")
print("این فایل شامل:")
print("1. جدول جدید card_cooldown_settings")
print("2. توابع مدیریت تنظیمات کارت‌ها")
print("3. بروزرسانی منطق cooldown")