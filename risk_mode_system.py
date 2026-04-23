#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎲 TelBattle Phase 2 - Risk Mode System
سیستم بازی شرط‌بندی با Bluff
"""

import sqlite3
import logging
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ==================== RISK MODE CONSTANTS ====================

class RiskTable(Enum):
    """میزهای Risk"""
    TABLE_50 = 50
    TABLE_100 = 100
    TABLE_300 = 300


class RiskAction(Enum):
    """اقدامات ممکن در Risk"""
    FOLD = "fold"      # انصراف
    CALL = "call"      # ادامه
    RAISE = "raise"    # افزایش شرط


# حداقل موجودی برای ورود
MIN_BALANCE_MULTIPLIER = 6  # 6x ورودیه

# حداکثر Raise
MAX_RAISE_MULTIPLIER = 6  # 6x ورودیه اولیه


# ==================== RISK MODE SYSTEM ====================

class RiskModeSystem:
    """
    سیستم Risk Mode
    
    ویژگی‌ها:
    - شرط‌بندی با سکه
    - 3 راوند با Bluff
    - Raise/Fold/Call
    - کارت‌های رندوم
    - ویژگی رندوم در هر راوند
    """
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db
    
    def can_enter_risk(self, user_id: int, table: RiskTable) -> Tuple[bool, str]:
        """بررسی اینکه بازیکن می‌تواند وارد Risk شود"""
        # بررسی Level
        progression = self.db.get_or_create_progression(user_id)
        if not progression or progression.get('level', 1) < 7:
            level = progression.get('level', 1) if progression else 1
            return False, f"برای ورود به Risk باید Level 7 باشید (Level فعلی: {level})"
        
        # بررسی موجودی
        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)
        min_balance = table.value * MIN_BALANCE_MULTIPLIER
        
        if coins < min_balance:
            return False, f"موجودی کافی ندارید! حداقل: {min_balance} سکه (موجودی: {coins})"
        
        return True, ""
    
    def create_risk_match(
        self,
        challenger_id: int,
        opponent_id: int,
        table: RiskTable,
        chat_id: int = None
    ) -> Dict:
        """
        ایجاد یک بازی Risk
        
        Args:
            challenger_id: شناسه چالنجر
            opponent_id: شناسه حریف
            table: میز انتخابی
            chat_id: شناسه چت گروه
        
        Returns:
            اطلاعات بازی
        """
        # بررسی شرایط ورود
        can_enter_c, reason_c = self.can_enter_risk(challenger_id, table)
        can_enter_o, reason_o = self.can_enter_risk(opponent_id, table)
        
        if not can_enter_c:
            return {"success": False, "error": f"Challenger: {reason_c}"}
        if not can_enter_o:
            return {"success": False, "error": f"Opponent: {reason_o}"}
        
        # قفل کردن ورودیه
        entry_fee = table.value
        
        # کسر ورودیه از هر دو بازیکن
        ok_c, _ = self.db.spend_coins(challenger_id, entry_fee)
        ok_o, _ = self.db.spend_coins(opponent_id, entry_fee)
        
        if not ok_c or not ok_o:
            # برگشت سکه اگه یکی نتونست
            if ok_c:
                self.db.add_coins(challenger_id, entry_fee)
            if ok_o:
                self.db.add_coins(opponent_id, entry_fee)
            return {"success": False, "error": "خطا در کسر ورودیه"}
        
        # ایجاد match
        match_id = f"risk_{challenger_id}_{opponent_id}_{int(datetime.now().timestamp())}"
        
        # انتخاب 3 کارت رندوم برای هر بازیکن
        all_cards = self.db.get_all_cards()
        
        challenger_cards = random.sample([c.card_id for c in all_cards], 3)
        opponent_cards = random.sample([c.card_id for c in all_cards], 3)
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO risk_matches
            (match_id, challenger_id, opponent_id, table_value, chat_id,
             challenger_cards, opponent_cards, current_pot, current_round,
             status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'card_selection', ?)
        ''', (
            match_id, challenger_id, opponent_id, table.value, chat_id,
            ','.join(challenger_cards), ','.join(opponent_cards),
            entry_fee * 2,  # pot اولیه
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Risk match created: {match_id}, table={table.value}")
        
        return {
            "success": True,
            "match_id": match_id,
            "table_value": table.value,
            "current_pot": entry_fee * 2,
            "challenger_cards": challenger_cards,
            "opponent_cards": opponent_cards
        }
    
    def get_risk_match(self, match_id: str) -> Optional[Dict]:
        """
        دریافت اطلاعات بازی Risk
        
        Args:
            match_id: شناسه بازی
        
        Returns:
            اطلاعات بازی
        """
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT match_id, challenger_id, opponent_id, table_value, chat_id,
                   challenger_cards, opponent_cards, challenger_selected_card,
                   opponent_selected_card, current_pot, current_round,
                   challenger_rounds_won, opponent_rounds_won, status, created_at,
                   COALESCE(bluff_phase,'none'), challenger_bluff_action,
                   opponent_bluff_action, COALESCE(raise_amount,0), raise_by
            FROM risk_matches
            WHERE match_id = ?
        ''', (match_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "match_id": result[0],
                "challenger_id": result[1],
                "opponent_id": result[2],
                "table_value": result[3],
                "chat_id": result[4],
                "challenger_cards": result[5].split(',') if result[5] else [],
                "opponent_cards": result[6].split(',') if result[6] else [],
                "challenger_selected_card": result[7],
                "opponent_selected_card": result[8],
                "current_pot": result[9],
                "current_round": result[10],
                "challenger_rounds_won": result[11],
                "opponent_rounds_won": result[12],
                "status": result[13],
                "created_at": result[14],
                "bluff_phase": result[15],
                "challenger_bluff_action": result[16],
                "opponent_bluff_action": result[17],
                "raise_amount": result[18],
                "raise_by": result[19],
            }
        
        return None
    
    def select_card(self, match_id: str, user_id: int, card_id: str) -> Dict:
        """
        انتخاب کارت برای راوند
        
        Args:
            match_id: شناسه بازی
            user_id: شناسه بازیکن
            card_id: شناسه کارت
        
        Returns:
            نتیجه
        """
        match = self.get_risk_match(match_id)
        if not match:
            return {"success": False, "error": "Match not found"}
        
        # تعیین نقش
        if user_id == match["challenger_id"]:
            field = "challenger_selected_card"
            available_cards = match["challenger_cards"]
        elif user_id == match["opponent_id"]:
            field = "opponent_selected_card"
            available_cards = match["opponent_cards"]
        else:
            return {"success": False, "error": "Not your match"}
        
        # بررسی کارت
        if card_id not in available_cards:
            return {"success": False, "error": "Invalid card"}
        
        # ذخیره انتخاب
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute(f'''
            UPDATE risk_matches
            SET {field} = ?
            WHERE match_id = ?
        ''', (card_id, match_id))
        
        conn.commit()
        conn.close()
        
        return {"success": True}
    
    def make_action(
        self,
        match_id: str,
        user_id: int,
        action: RiskAction,
        raise_amount: int = 0
    ) -> Dict:
        """
        انجام اقدام (Fold/Call/Raise)
        
        Args:
            match_id: شناسه بازی
            user_id: شناسه بازیکن
            action: نوع اقدام
            raise_amount: مقدار Raise
        
        Returns:
            نتیجه
        """
        match = self.get_risk_match(match_id)
        if not match:
            return {"success": False, "error": "Match not found"}
        
        # FOLD - انصراف
        if action == RiskAction.FOLD:
            winner_id = match["opponent_id"] if user_id == match["challenger_id"] else match["challenger_id"]
            
            # پات به برنده
            self.db.add_coins(winner_id, match["current_pot"])
            
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE risk_matches SET status = ?, winner_id = ? WHERE match_id = ?',
                           ('completed', winner_id, match_id))
            conn.commit()
            conn.close()
            
            return {"success": True, "action": "fold", "winner_id": winner_id, "pot": match["current_pot"]}
        
        # CALL - ادامه
        elif action == RiskAction.CALL:
            return {"success": True, "action": "call"}
        
        # RAISE - افزایش شرط
        elif action == RiskAction.RAISE:
            max_raise = match["table_value"] * MAX_RAISE_MULTIPLIER
            
            if raise_amount > max_raise:
                return {"success": False, "error": f"حداکثر Raise: {max_raise}"}
            
            ok, err = self.db.spend_coins(user_id, raise_amount)
            if not ok:
                return {"success": False, "error": err}
            
            new_pot = match["current_pot"] + raise_amount
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE risk_matches SET current_pot = ? WHERE match_id = ?', (new_pot, match_id))
            conn.commit()
            conn.close()
            
            return {"success": True, "action": "raise", "raise_amount": raise_amount, "new_pot": new_pot}
        
        return {"success": False, "error": "Invalid action"}
    
    def resolve_round(self, match_id: str) -> Dict:
        """
        حل راوند (بعد از انتخاب کارت‌ها)
        
        Args:
            match_id: شناسه بازی
        
        Returns:
            نتیجه راوند
        """
        match = self.get_risk_match(match_id)
        if not match:
            return {"success": False, "error": "Match not found"}
        
        # دریافت کارت‌ها
        c_card = self.db.get_card_by_id(match["challenger_selected_card"])
        o_card = self.db.get_card_by_id(match["opponent_selected_card"])
        
        if not c_card or not o_card:
            return {"success": False, "error": "Cards not found"}
        
        # انتخاب ویژگی رندوم
        stats = ["power", "speed", "iq", "popularity"]
        selected_stat = random.choice(stats)
        
        c_value = getattr(c_card, selected_stat)
        o_value = getattr(o_card, selected_stat)
        
        # تعیین برنده
        if c_value > o_value:
            winner = "challenger"
        elif o_value > c_value:
            winner = "opponent"
        else:
            winner = "tie"
        
        # بروزرسانی امتیاز
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        if winner == "challenger":
            cursor.execute('''
                UPDATE risk_matches
                SET challenger_rounds_won = challenger_rounds_won + 1,
                    current_round = current_round + 1
                WHERE match_id = ?
            ''', (match_id,))
        elif winner == "opponent":
            cursor.execute('''
                UPDATE risk_matches
                SET opponent_rounds_won = opponent_rounds_won + 1,
                    current_round = current_round + 1
                WHERE match_id = ?
            ''', (match_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "round": match["current_round"],
            "selected_stat": selected_stat,
            "challenger_value": c_value,
            "opponent_value": o_value,
            "winner": winner
        }


# ==================== DATABASE OPERATIONS ====================

def create_risk_tables(db_path: str):
    """
    ایجاد جداول مورد نیاز برای Risk Mode
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_matches (
            match_id TEXT PRIMARY KEY,
            challenger_id INTEGER NOT NULL,
            opponent_id INTEGER NOT NULL,
            table_value INTEGER NOT NULL,
            chat_id INTEGER,
            challenger_cards TEXT NOT NULL,
            opponent_cards TEXT NOT NULL,
            challenger_selected_card TEXT,
            opponent_selected_card TEXT,
            current_pot INTEGER NOT NULL,
            current_round INTEGER DEFAULT 1,
            challenger_rounds_won INTEGER DEFAULT 0,
            opponent_rounds_won INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            winner_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (challenger_id) REFERENCES players (user_id),
            FOREIGN KEY (opponent_id) REFERENCES players (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Risk tables created")
