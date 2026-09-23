#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎲 TelBattle Phase 2 - Risk Mode System
سیستم بازی شرط‌بندی با Bluff
"""

import sqlite3
import logging
import random
import uuid
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
        self, challenger_id: int, opponent_id: int, table: RiskTable, chat_id: int = None
    ) -> Dict:
        """Create the match and escrow both entry fees atomically."""
        if challenger_id == opponent_id:
            return {"success": False, "error": "نمی‌توانی با خودت بازی کنی"}
        if not isinstance(table, RiskTable):
            return {"success": False, "error": "میز نامعتبر است"}
        for uid in (challenger_id, opponent_id):
            allowed, reason = self.can_enter_risk(uid, table)
            if not allowed:
                return {"success": False, "error": reason}
        cards = [card.card_id for card in self.db.get_all_cards()]
        if len(cards) < 3:
            return {"success": False, "error": "حداقل سه کارت برای بازی لازم است"}
        challenger_cards = random.sample(cards, 3)
        opponent_cards = random.sample(cards, 3)
        # Compact IDs fit Telegram callback_data and contain no field separator.
        match_id = uuid.uuid4().hex[:16]
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for uid in (challenger_id, opponent_id):
                changed = conn.execute(
                    "UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?",
                    (table.value, uid, table.value * MIN_BALANCE_MULTIPLIER),
                )
                if changed.rowcount != 1:
                    conn.rollback()
                    return {"success": False, "error": "موجودی کافی نیست"}
            conn.execute(
                """INSERT INTO risk_matches
                   (match_id,challenger_id,opponent_id,table_value,chat_id,
                    challenger_cards,opponent_cards,current_pot,current_round,status,created_at)
                   VALUES (?,?,?,?,?,?,?,?,1,'card_selection',?)""",
                (match_id, challenger_id, opponent_id, table.value, chat_id,
                 ','.join(challenger_cards), ','.join(opponent_cards), table.value * 2,
                 datetime.now().isoformat()),
            )
            conn.commit()
            return {"success": True, "match_id": match_id, "table_value": table.value,
                    "current_pot": table.value * 2, "challenger_cards": challenger_cards,
                    "opponent_cards": opponent_cards}
        except Exception:
            conn.rollback()
            logger.exception("Risk match creation failed")
            return {"success": False, "error": "ایجاد بازی انجام نشد"}
        finally:
            conn.close()

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
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            match = conn.execute("SELECT * FROM risk_matches WHERE match_id=?", (match_id,)).fetchone()
            if not match or match["status"] == "completed":
                return {"success": False, "error": "بازی فعال پیدا نشد"}
            role = "challenger" if user_id == match["challenger_id"] else "opponent" if user_id == match["opponent_id"] else None
            if not role:
                return {"success": False, "error": "این بازی مال تو نیست"}
            if match["bluff_phase"] != "none" or match[f"{role}_selected_card"]:
                return {"success": False, "error": "انتخاب کارت قبلاً ثبت شده است"}
            if card_id not in match[f"{role}_cards"].split(","):
                return {"success": False, "error": "کارت نامعتبر است"}
            conn.execute(f"UPDATE risk_matches SET {role}_selected_card=? WHERE match_id=?", (card_id, match_id))
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    @staticmethod
    def _settle(conn, match, winner_id):
        """Settle the escrow once, together with progression and match status."""
        changed = conn.execute(
            "UPDATE risk_matches SET status='completed',winner_id=?,bluff_phase='done' WHERE match_id=? AND status!='completed'",
            (winner_id, match["match_id"]),
        )
        if changed.rowcount != 1:
            return False
        if winner_id is None:
            # A completed call leaves equal stakes; split the entire pot,
            # including raises, without creating or discarding coins.
            first = match["current_pot"] // 2
            payouts = ((match["challenger_id"], first), (match["opponent_id"], match["current_pot"] - first))
        else:
            payouts = ((winner_id, match["current_pot"]),)
        for uid, amount in payouts:
            conn.execute("UPDATE players SET coins=coins+? WHERE user_id=?", (amount, uid))
        if winner_id is not None:
            from systems.phase2_systems import LevelSystem
            for uid in (match["challenger_id"], match["opponent_id"]):
                conn.execute(
                    "INSERT OR IGNORE INTO player_progression(user_id,level,total_xp,tier_points,current_tier) VALUES (?,1,0,0,'Bronze')",
                    (uid,),
                )
                xp = conn.execute("SELECT total_xp FROM player_progression WHERE user_id=?", (uid,)).fetchone()[0]
                xp += 25 if uid == winner_id else 5
                conn.execute("UPDATE player_progression SET total_xp=?,level=?,last_played_at=? WHERE user_id=?",
                             (xp, LevelSystem.get_level_from_xp(xp), datetime.now().isoformat(), uid))
        return True

    def make_action(self, match_id: str, user_id: int, action: RiskAction, raise_amount: int = 0) -> Dict:
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            match = conn.execute("SELECT * FROM risk_matches WHERE match_id=?", (match_id,)).fetchone()
            if not match or match["status"] == "completed":
                return {"success": False, "error": "بازی فعال پیدا نشد"}
            role = "challenger" if user_id == match["challenger_id"] else "opponent" if user_id == match["opponent_id"] else None
            if not role:
                return {"success": False, "error": "این بازی مال تو نیست"}
            if action == RiskAction.FOLD:
                winner_id = match["opponent_id"] if role == "challenger" else match["challenger_id"]
                self._settle(conn, match, winner_id)
                conn.commit()
                return {"success": True, "action": "fold", "winner_id": winner_id, "pot": match["current_pot"]}
            if match["bluff_phase"] not in ("waiting", "raise_pending"):
                return {"success": False, "error": "این مرحله تمام شده است"}
            if action == RiskAction.RAISE:
                if match["bluff_phase"] != "waiting" or match[f"{role}_bluff_action"]:
                    return {"success": False, "error": "اقدام قبلاً ثبت شده است"}
                if type(raise_amount) is not int or not 0 < raise_amount <= match["table_value"] * MAX_RAISE_MULTIPLIER:
                    return {"success": False, "error": "مقدار Raise نامعتبر است"}
                charged = conn.execute("UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?",
                                       (raise_amount, user_id, raise_amount))
                if charged.rowcount != 1:
                    return {"success": False, "error": "سکه کافی نیست"}
                conn.execute(
                    f"""UPDATE risk_matches SET current_pot=current_pot+?,bluff_phase='raise_pending',
                        raise_amount=?,raise_by=?,{role}_bluff_action='raise' WHERE match_id=?""",
                    (raise_amount, raise_amount, user_id, match_id),
                )
                conn.commit()
                return {"success": True, "action": "raise", "raise_amount": raise_amount,
                        "new_pot": match["current_pot"] + raise_amount}
            if action == RiskAction.CALL:
                amount = 0
                ready = False
                if match["bluff_phase"] == "raise_pending":
                    if match["raise_by"] == user_id:
                        return {"success": False, "error": "منتظر پاسخ حریف بمان"}
                    amount = match["raise_amount"]
                    charged = conn.execute("UPDATE players SET coins=coins-? WHERE user_id=? AND coins>=?",
                                           (amount, user_id, amount))
                    if charged.rowcount != 1:
                        return {"success": False, "error": "سکه کافی نیست"}
                    ready = True
                else:
                    if match[f"{role}_bluff_action"]:
                        return {"success": False, "error": "اقدام قبلاً ثبت شده است"}
                    other = "opponent" if role == "challenger" else "challenger"
                    ready = match[f"{other}_bluff_action"] == "call"
                conn.execute(
                    f"UPDATE risk_matches SET current_pot=current_pot+?,bluff_phase=?,{role}_bluff_action='call' WHERE match_id=?",
                    (amount, "done" if ready else "waiting", match_id),
                )
                conn.commit()
                return {"success": True, "action": "call", "ready": ready}
            return {"success": False, "error": "اقدام نامعتبر است"}
        finally:
            conn.close()

    def resolve_round(self, match_id: str) -> Dict:
        conn = sqlite3.connect(self.db.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM risk_matches WHERE match_id=?", (match_id,)).fetchone()
            if not row or row["status"] == "completed":
                return {"success": False, "error": "بازی فعال پیدا نشد"}
            match = dict(row)
            c_card = self.db.get_card_by_id(match["challenger_selected_card"])
            o_card = self.db.get_card_by_id(match["opponent_selected_card"])
            if not c_card or not o_card:
                return {"success": False, "error": "هر دو کارت باید انتخاب شوند"}
            selected_stat = random.choice(["power", "speed", "iq", "popularity"])
            c_value, o_value = getattr(c_card, selected_stat), getattr(o_card, selected_stat)
            winner = "challenger" if c_value > o_value else "opponent" if o_value > c_value else "tie"
            c_won = match["challenger_rounds_won"] + (winner == "challenger")
            o_won = match["opponent_rounds_won"] + (winner == "opponent")
            next_round = match["current_round"] + 1
            conn.execute(
                """UPDATE risk_matches SET challenger_rounds_won=?,opponent_rounds_won=?,current_round=?,
                   challenger_selected_card=NULL,opponent_selected_card=NULL,bluff_phase='none',
                   challenger_bluff_action=NULL,opponent_bluff_action=NULL,raise_amount=0,raise_by=NULL
                   WHERE match_id=?""",
                (c_won, o_won, next_round, match_id),
            )
            game_over = c_won >= 2 or o_won >= 2 or next_round > 3
            final_winner_id = None
            if game_over:
                final_winner_id = match["challenger_id"] if c_won > o_won else match["opponent_id"] if o_won > c_won else None
                self._settle(conn, match, final_winner_id)
            conn.commit()
            return {"success": True, "round": match["current_round"], "selected_stat": selected_stat,
                    "challenger_value": c_value, "opponent_value": o_value, "winner": winner,
                    "game_over": game_over, "winner_id": final_winner_id}
        finally:
            conn.close()


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
