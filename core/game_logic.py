#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Game Logic - منطق بازی
"""

import sqlite3
import random
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from core.models import CardRarity, StatType, Card, Player, PvPFight
from core.database import DatabaseManager

logger = logging.getLogger(__name__)

class GameLogic:
    def __init__(self, db: DatabaseManager, config: Optional[dict] = None):
        self.db = db
        cfg = config or {}
        game_cfg = cfg.get('game_settings', cfg) if isinstance(cfg, dict) else {}

        # تنظیمات پیش‌فرض بازی (قابل پیکربندی)
        self.DAILY_HEARTS = int(game_cfg.get('daily_hearts', 10))  # تغییر از 5 به 10
        self.HEART_RESET_HOURS = int(game_cfg.get('heart_reset_hours', 24))
        self.CLAIM_COOLDOWN_HOURS = int(game_cfg.get('claim_cooldown_hours', 24))
        
        # تنظیمات Cooldown کارت‌ها
        cooldown_cfg = game_cfg.get('card_cooldown', {}) if isinstance(game_cfg, dict) else {}
        self.CARD_COOLDOWN_ENABLED = bool(cooldown_cfg.get('enabled', True))
        self.CARD_COOLDOWN_WIN_LIMIT = int(cooldown_cfg.get('win_limit', 10))
        self.CARD_COOLDOWN_HOURS = int(cooldown_cfg.get('cooldown_hours', 24))

        # نرخ ظهور کارت‌ها
        rates = game_cfg.get('card_drop_rates', {}) if isinstance(game_cfg, dict) else {}
        normal = int(rates.get('normal', 65))
        epic = int(rates.get('epic', 25))
        legend = int(rates.get('legend', 10))
        total = normal + epic + legend
        if total != 100 and total > 0:
            normal = round((normal / total) * 100)
            epic = round((epic / total) * 100)
            legend = 100 - (normal + epic)

        self.CARD_DROP_RATES = {
            CardRarity.NORMAL: normal,
            CardRarity.EPIC: epic,
            CardRarity.LEGEND: legend
        }

    def check_and_reset_hearts(self, player: Player) -> Player:
        """بررسی و ریست قلب‌ها در صورت نیاز"""
        now = datetime.now()
        time_diff = now - player.last_heart_reset
        
        if time_diff.total_seconds() >= self.HEART_RESET_HOURS * 3600:
            player.hearts = self.DAILY_HEARTS
            player.last_heart_reset = now
            self.db.update_player(player)
        
        return player
    
    def is_card_eligible_for_cooldown(self, card: Card) -> bool:
        """بررسی اینکه آیا کارت مشمول سیستم cooldown است یا نه"""
        if not self.CARD_COOLDOWN_ENABLED:
            return False
        return card.rarity in [CardRarity.EPIC, CardRarity.LEGEND]
    
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
    
    def claim_daily_card(self, user_id: int) -> Tuple[bool, Optional[Card], Optional[str]]:
        success, card, error, _ability = self.claim_daily_card_with_ability(user_id)
        return success, card, error

    def claim_daily_card_with_ability(self, user_id: int):
        """Atomically award the daily card and one consumable Quick Ability."""
        from systems.player_rewards_system import PlayerRewardsSystem

        self.db.get_or_create_player(user_id)
        result = PlayerRewardsSystem(self.db).claim_daily(user_id)
        if not result["ok"]:
            return False, None, result["error"], None
        card = self.db.get_card_by_id(result["card_id"])
        return True, card, None, result["ability"]
    
    def get_heart_reset_time_remaining(self, player: Player) -> Optional[timedelta]:
        """محاسبه زمان باقی‌مانده تا ریست جان‌ها"""
        if not player.last_heart_reset:
            return None
        
        next_reset = player.last_heart_reset + timedelta(hours=self.HEART_RESET_HOURS)
        now = datetime.now()
        
        if now >= next_reset:
            return None
        
        return next_reset - now
    
    def format_time_remaining(self, time_delta: timedelta) -> str:
        """فرمت کردن زمان باقی‌مانده"""
        total_seconds = int(time_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours} ساعت و {minutes} دقیقه"
        else:
            return f"{minutes} دقیقه"
    
    def resolve_pvp_fight(self, fight_id: str) -> Dict:
        """حل و فصل فایت PvP"""
        fight = self.db.get_fight_by_id(fight_id)
        
        if not fight:
            return {"success": False, "error": "فایت یافت نشد"}
        
        if not fight.challenger_card_id or not fight.opponent_card_id:
            return {"success": False, "error": "کارت‌ها انتخاب نشده‌اند"}
        
        if not fight.challenger_stat or not fight.opponent_stat:
            return {"success": False, "error": "ویژگی‌ها انتخاب نشده‌اند"}
        
        # دریافت کارت‌ها
        challenger_card = self.db.get_card_by_id_for_player(fight.challenger_card_id, fight.challenger_id)
        opponent_card = self.db.get_card_by_id_for_player(fight.opponent_card_id, fight.opponent_id)
        
        if not challenger_card or not opponent_card:
            return {"success": False, "error": "کارت‌ها یافت نشدند"}
        
        from systems.shared_foundation import validate_match_card
        try:
            validate_match_card(self.db, "fight:" + fight_id, "legacy_pvp", challenger_card.card_id, fight.challenger_id)
            validate_match_card(self.db, "fight:" + fight_id, "legacy_pvp", opponent_card.card_id, fight.opponent_id)
        except ValueError:
            return {"success": False, "error": "کارت در این مود مجاز نیست"}

        # محاسبه امتیازات - جمع دو ویژگی
        challenger_stat_value = challenger_card.get_stat_value(StatType(fight.challenger_stat))
        challenger_stat2 = challenger_card.get_stat_value(StatType(fight.opponent_stat))
        challenger_total = challenger_stat_value + challenger_stat2
        
        opponent_stat_value = opponent_card.get_stat_value(StatType(fight.opponent_stat))
        opponent_stat2 = opponent_card.get_stat_value(StatType(fight.challenger_stat))
        opponent_total = opponent_stat_value + opponent_stat2
        
        # تعیین برنده بر اساس جمع امتیازات
        if challenger_total > opponent_total:
            winner_id = fight.challenger_id
            loser_id = fight.opponent_id
            winner_card = challenger_card
            loser_card = opponent_card
            result = "win"
        elif opponent_total > challenger_total:
            winner_id = fight.opponent_id
            loser_id = fight.challenger_id
            winner_card = opponent_card
            loser_card = challenger_card
            result = "loss"
        else:
            winner_id = None
            loser_id = None
            winner_card = None
            loser_card = None
            result = "tie"
        
        # محاسبه امتیاز و جان بر اساس rarity
        def calculate_rewards(winner_rarity: CardRarity, loser_rarity: CardRarity):
            """محاسبه امتیاز برنده و جان از دست رفته بازنده"""
            # امتیاز برنده
            if winner_rarity == CardRarity.LEGEND:
                if loser_rarity == CardRarity.NORMAL:
                    score = 5  # انتظار میره ببره
                elif loser_rarity == CardRarity.EPIC:
                    score = 7
                else:  # Legend vs Legend
                    score = 10
            elif winner_rarity == CardRarity.EPIC:
                if loser_rarity == CardRarity.NORMAL:
                    score = 7
                elif loser_rarity == CardRarity.EPIC:
                    score = 10
                else:  # Epic beats Legend
                    score = 15  # upset!
            else:  # Normal wins
                if loser_rarity == CardRarity.NORMAL:
                    score = 10
                elif loser_rarity == CardRarity.EPIC:
                    score = 15  # upset!
                else:  # Normal beats Legend
                    score = 20  # huge upset!
            
            # جان از دست رفته بازنده
            if loser_rarity == CardRarity.NORMAL:
                if winner_rarity == CardRarity.LEGEND or winner_rarity == CardRarity.EPIC:
                    hearts_lost = 0  # انتظار میره ببازه
                else:  # Normal loses to Normal
                    hearts_lost = 1
            elif loser_rarity == CardRarity.EPIC:
                if winner_rarity == CardRarity.LEGEND:
                    hearts_lost = 0  # انتظار میره ببازه
                elif winner_rarity == CardRarity.EPIC:
                    hearts_lost = 1
                else:  # Epic loses to Normal
                    hearts_lost = 2  # upset!
            else:  # Legend loses
                if winner_rarity == CardRarity.LEGEND:
                    hearts_lost = 1
                elif winner_rarity == CardRarity.EPIC:
                    hearts_lost = 2  # upset!
                else:  # Legend loses to Normal
                    hearts_lost = 3  # huge upset!
            
            return score, hearts_lost
        
        # Calculate the legacy one-round rewards before touching the database.
        if result == "win":
            score_gained, hearts_lost = calculate_rewards(challenger_card.rarity, opponent_card.rarity)
            challenger_score, opponent_score = score_gained, 0
            challenger_hearts_lost, opponent_hearts_lost = 0, hearts_lost
        elif result == "loss":
            score_gained, hearts_lost = calculate_rewards(opponent_card.rarity, challenger_card.rarity)
            challenger_score, opponent_score = 0, score_gained
            challenger_hearts_lost, opponent_hearts_lost = hearts_lost, 0
        else:
            def calculate_tie_score(my_rarity: CardRarity, other_rarity: CardRarity) -> int:
                if my_rarity == other_rarity:
                    return 0
                if my_rarity == CardRarity.NORMAL:
                    return 3 if other_rarity == CardRarity.EPIC else 5
                if my_rarity == CardRarity.EPIC and other_rarity == CardRarity.LEGEND:
                    return 3
                return 0

            challenger_score = calculate_tie_score(challenger_card.rarity, opponent_card.rarity)
            opponent_score = calculate_tie_score(opponent_card.rarity, challenger_card.rarity)
            challenger_hearts_lost = int(
                challenger_card.rarity == CardRarity.LEGEND
                and opponent_card.rarity == CardRarity.NORMAL
            )
            opponent_hearts_lost = int(
                opponent_card.rarity == CardRarity.LEGEND
                and challenger_card.rarity == CardRarity.NORMAL
            )
            score_gained = hearts_lost = 0

        # تعیین result_type برای telegram_bot
        if result == "tie":
            result_type = "tie"
        elif result == "win":
            result_type = "challenger_wins"
        else:  # result == "loss"
            result_type = "opponent_wins"
        
        # ساخت winner و loser data برای telegram_bot
        # ساخت یه SimpleNamespace که مثل object رفتار می‌کنه
        from types import SimpleNamespace
        
        winner_data = None
        loser_data = None
        
        if result != "tie":
            if result == "win":
                # ساخت یه card object ساده که telegram_bot بتونه ازش استفاده کنه
                winner_card_obj = SimpleNamespace(
                    name=challenger_card.name,
                    power=challenger_card.power,
                    speed=challenger_card.speed,
                    iq=challenger_card.iq,
                    popularity=challenger_card.popularity,
                    rarity=challenger_card.rarity.value if hasattr(challenger_card.rarity, 'value') else str(challenger_card.rarity)
                )
                loser_card_obj = SimpleNamespace(
                    name=opponent_card.name,
                    power=opponent_card.power,
                    speed=opponent_card.speed,
                    iq=opponent_card.iq,
                    popularity=opponent_card.popularity,
                    rarity=opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else str(opponent_card.rarity)
                )
                
                winner_data = {
                    "user_id": fight.challenger_id,
                    "card": winner_card_obj,
                    "stat": fight.challenger_stat,
                    "stat_type": fight.challenger_stat,
                    "stat_value": challenger_stat_value,
                    "score_gained": challenger_score,
                    "hearts_lost": 0
                }
                loser_data = {
                    "user_id": fight.opponent_id,
                    "card": loser_card_obj,
                    "stat": fight.opponent_stat,
                    "stat_type": fight.opponent_stat,
                    "stat_value": opponent_stat_value,
                    "score_gained": 0,
                    "hearts_lost": opponent_hearts_lost
                }
            else:  # result == "loss"
                # ساخت یه card object ساده که telegram_bot بتونه ازش استفاده کنه
                winner_card_obj = SimpleNamespace(
                    name=opponent_card.name,
                    power=opponent_card.power,
                    speed=opponent_card.speed,
                    iq=opponent_card.iq,
                    popularity=opponent_card.popularity,
                    rarity=opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else str(opponent_card.rarity)
                )
                loser_card_obj = SimpleNamespace(
                    name=challenger_card.name,
                    power=challenger_card.power,
                    speed=challenger_card.speed,
                    iq=challenger_card.iq,
                    popularity=challenger_card.popularity,
                    rarity=challenger_card.rarity.value if hasattr(challenger_card.rarity, 'value') else str(challenger_card.rarity)
                )
                
                winner_data = {
                    "user_id": fight.opponent_id,
                    "card": winner_card_obj,
                    "stat": fight.opponent_stat,
                    "stat_type": fight.opponent_stat,
                    "stat_value": opponent_stat_value,
                    "score_gained": opponent_score,
                    "hearts_lost": 0
                }
                loser_data = {
                    "user_id": fight.challenger_id,
                    "card": loser_card_obj,
                    "stat": fight.challenger_stat,
                    "stat_type": fight.challenger_stat,
                    "stat_value": challenger_stat_value,
                    "score_gained": 0,
                    "hearts_lost": challenger_hearts_lost
                }
        
        # ساخت challenger و opponent data برای match_info_handler
        challenger_card_obj = SimpleNamespace(
            name=challenger_card.name,
            power=challenger_card.power,
            speed=challenger_card.speed,
            iq=challenger_card.iq,
            popularity=challenger_card.popularity,
            rarity=challenger_card.rarity.value if hasattr(challenger_card.rarity, 'value') else str(challenger_card.rarity)
        )
        opponent_card_obj = SimpleNamespace(
            name=opponent_card.name,
            power=opponent_card.power,
            speed=opponent_card.speed,
            iq=opponent_card.iq,
            popularity=opponent_card.popularity,
            rarity=opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else str(opponent_card.rarity)
        )
        
        challenger_data = {
            "user_id": fight.challenger_id,
            "card": challenger_card_obj,
            "stat": fight.challenger_stat,
            "stat_type": fight.challenger_stat,
            "stat_value": challenger_stat_value,
            "score_gained": challenger_score,
            "hearts_lost": challenger_hearts_lost
        }
        opponent_data = {
            "user_id": fight.opponent_id,
            "card": opponent_card_obj,
            "stat": fight.opponent_stat,
            "stat_type": fight.opponent_stat,
            "stat_value": opponent_stat_value,
            "score_gained": opponent_score,
            "hearts_lost": opponent_hearts_lost
        }
        
        # Record Score, hearts, XP, TP and history in one replay-safe transaction.
        from systems.legacy_fight_rewards_system import LegacyFightRewardsSystem
        from systems.phase2_systems import XP_SOURCES

        ch_xp = XP_SOURCES["normal_win"] if result == "win" else XP_SOURCES["normal_loss"]
        op_xp = XP_SOURCES["normal_win"] if result == "loss" else XP_SOURCES["normal_loss"]
        awards = {
            fight.challenger_id: {
                "result": result, "xp": ch_xp, "score": challenger_score,
                "hearts_lost": challenger_hearts_lost,
                "card_id": challenger_card.card_id, "opponent_card_id": opponent_card.card_id,
                "opponent_id": fight.opponent_id, "stat_used": fight.challenger_stat,
            },
            fight.opponent_id: {
                "result": "win" if result == "loss" else "loss" if result == "win" else "tie",
                "xp": op_xp, "score": opponent_score,
                "hearts_lost": opponent_hearts_lost,
                "card_id": opponent_card.card_id, "opponent_card_id": challenger_card.card_id,
                "opponent_id": fight.challenger_id, "stat_used": fight.opponent_stat,
            },
        }
        try:
            settlement = LegacyFightRewardsSystem(self.db).settle_single_round(
                fight_id, fight.challenger_id, fight.opponent_id, result_type, awards,
            )
        except (ValueError, sqlite3.Error) as exc:
            logger.error("PvP settlement failed for %s: %s", fight_id, exc)
            return {"success": False, "error": "ثبت نتیجهٔ نبرد انجام نشد"}
        if not settlement["fresh"]:
            return {"success": False, "error": "نتیجهٔ این نبرد قبلاً ثبت شده است", "already_settled": True}
        if winner_id is not None:
            self.record_card_win(winner_id, winner_card.card_id)
        ch_paid = settlement["awards"][str(fight.challenger_id)]
        op_paid = settlement["awards"][str(fight.opponent_id)]
        ch_old_level, ch_new_level = ch_paid["old_level"], ch_paid["new_level"]
        op_old_level, op_new_level = op_paid["old_level"], op_paid["new_level"]
        ch_old_tier, ch_new_tier = ch_paid["old_tier"], ch_paid["new_tier"]
        op_old_tier, op_new_tier = op_paid["old_tier"], op_paid["new_tier"]

        # اضافه کردن اطلاعات XP/Level به challenger_data و opponent_data
        challenger_data['xp_gained'] = ch_xp
        challenger_data['level_up'] = ch_new_level > ch_old_level
        challenger_data['new_level'] = ch_new_level
        challenger_data['tier_changed'] = ch_new_tier != ch_old_tier
        challenger_data['new_tier'] = ch_new_tier
        
        opponent_data['xp_gained'] = op_xp
        opponent_data['level_up'] = op_new_level > op_old_level
        opponent_data['new_level'] = op_new_level
        opponent_data['tier_changed'] = op_new_tier != op_old_tier
        opponent_data['new_tier'] = op_new_tier
        
        if winner_data:
            winner_data['xp_gained'] = ch_xp if result == "win" else op_xp
        if loser_data:
            loser_data['xp_gained'] = op_xp if result == "win" else ch_xp

        return {
            "success": True,
            "fight_id": fight_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "result": result,
            "result_type": result_type,
            "winner": winner_data,
            "loser": loser_data,
            "challenger": challenger_data,
            "opponent": opponent_data,
            "challenger_stat_value": challenger_stat_value,
            "opponent_stat_value": opponent_stat_value,
            "challenger_card": challenger_card,
            "opponent_card": opponent_card
        }

# ==================== CARD MANAGER ====================

class CardManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def create_sample_cards(self) -> int:
        """ایجاد کارت‌های نمونه"""
        sample_cards = [
            # Normal Cards
            {
                'name': 'Heisenberg',
                'rarity': CardRarity.NORMAL,
                'power': 75, 'speed': 60, 'iq': 95, 'popularity': 80,
                'abilities': ['Chemistry Master'],
                'biography': 'شیمیدان نابغه که به مسیر تاریک قدم گذاشت.'
            },
            {
                'name': 'Spongebob',
                'rarity': CardRarity.NORMAL,
                'power': 40, 'speed': 70, 'iq': 50, 'popularity': 90,
                'abilities': ['Optimism'],
                'biography': 'اسفنج پرانرژی از زیر آب که همیشه آماده است.'
            },
            # Epic Cards
            {
                'name': 'Homelander',
                'rarity': CardRarity.EPIC,
                'power': 95, 'speed': 85, 'iq': 70, 'popularity': 60,
                'abilities': ['Laser Eyes', 'Flight'],
                'biography': 'قهرمان قدرتمند با چهره‌ای پیچیده.'
            },
            # Legend Cards
            {
                'name': 'Thanos',
                'rarity': CardRarity.LEGEND,
                'power': 100, 'speed': 75, 'iq': 90, 'popularity': 85,
                'abilities': ['Infinity Stones', 'Reality Manipulation', 'Time Control'],
                'biography': 'تایتان جنون‌زده که به دنبال تعادل کیهان است.'
            }
        ]
        
        added_count = 0
        for card_data in sample_cards:
            card = Card(
                card_id=str(uuid.uuid4()),
                name=card_data['name'],
                rarity=card_data['rarity'],
                power=card_data['power'],
                speed=card_data['speed'],
                iq=card_data['iq'],
                popularity=card_data['popularity'],
                abilities=card_data['abilities'],
                biography=card_data['biography']
            )
            
            if self.db.add_card(card):
                added_count += 1
        
        return added_count
