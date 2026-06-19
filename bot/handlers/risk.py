#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Risk Mode Handlers
"""

import json
import os
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import telegram
import telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, WebAppInfo
from telegram.ext import Application, ContextTypes

from game_core import DatabaseManager, GameLogic, CardManager, StatType, Card, CardRarity, Player, PvPFight, FightStatus
from systems.fusion_system import FusionSystem
from systems.phase2_systems import LevelSystem, TierSystem, format_xp_bar, format_tier_badge
from systems.economy_system import EconomySystem
from systems.tier_decay_system import TierDecaySystem
from systems.risk_mode_system import RiskModeSystem, RiskTable, RiskAction
from systems.battle_system_3rounds import BattleSystem3Rounds, BattleState, ARENAS
from systems.claim_system import ClaimSystem
from systems.card_missions_system import CardMissionsSystem, MISSION_TYPES
from systems.skins_system import SkinsSystem, SKIN_TYPES

logger = logging.getLogger(__name__)

from bot.utils import (check_user_started_bot, handle_user_not_started, ensure_text_content,
    get_card_image_path, get_victory_dialog, send_card_image_safely, ensure_not_expired,
    REQUIRED_CHANNEL, PANEL_TIMEOUT)




class RiskHandlersMixin:
    """Risk Mode Handlers"""

    async def risk_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی Risk Mode"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        prog = self.db.get_or_create_progression(user_id)
        player = self.db.get_or_create_player(user_id)
        level = prog.get('level', 1)
        coins = getattr(player, 'coins', 0)

        if level < 7:
            text = (
                f"🎲 **Risk Mode**\n\n"
                f"🔒 برای ورود به Risk باید Level 7 باشی.\n"
                f"Level فعلی: {level}\n\n"
                f"با بازی بیشتر XP بگیر و Level بالا ببر!"
            )
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        text = (
            f"🎲 **Risk Mode**\n\n"
            f"💰 موجودی: {coins:,} سکه\n\n"
            f"شرط‌بندی با سکه — برنده کل پات رو می‌بره!\n\n"
            f"میز انتخاب کن:"
        )

        keyboard = []
        for table in [RiskTable.TABLE_50, RiskTable.TABLE_100, RiskTable.TABLE_300]:
            min_bal = table.value * 6
            can = coins >= min_bal
            label = f"{'✅' if can else '❌'} میز {table.value} سکه (حداقل: {min_bal})"
            cb = f"risk_challenge_{table.value}" if can else "risk_noop"
            keyboard.append([InlineKeyboardButton(label, callback_data=cb)])

        keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def risk_noop_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer("❌ موجودی کافی نداری!", show_alert=True)

    async def risk_challenge_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع چالش Risk در گروه"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        # فقط در گروه
        if query.message.chat.type == 'private':
            await query.edit_message_text(
                "🎲 Risk Mode فقط در گروه‌ها قابل استفاده است!\n"
                "به گروه برو و دوباره امتحان کن.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="risk_menu")]])
            )
            return

        table_value = int(query.data.split("_")[2])
        table = RiskTable(table_value)

        context.user_data['risk_table'] = table_value

        text = (
            f"🎲 **چالش Risk — میز {table_value} سکه**\n\n"
            f"@{query.from_user.username or query.from_user.first_name} یه چالش Risk شروع کرد!\n\n"
            f"💰 ورودیه: {table_value} سکه هر نفر\n"
            f"🏆 پات اولیه: {table_value * 2} سکه\n\n"
            f"کی قبول می‌کنه؟"
        )
        keyboard = [[InlineKeyboardButton(
            f"⚔️ قبول چالش Risk",
            callback_data=f"risk_accept_{user_id}_{table_value}"
        )]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def risk_accept_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قبول چالش Risk"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        parts = query.data.split("_")
        challenger_id = int(parts[2])
        table_value = int(parts[3])

        if user_id == challenger_id:
            await query.answer("❌ نمی‌تونی با خودت بازی کنی!", show_alert=True)
            return

        table = RiskTable(table_value)

        # بررسی شرایط هر دو
        can_c, err_c = self.risk.can_enter_risk(challenger_id, table)
        can_o, err_o = self.risk.can_enter_risk(user_id, table)

        if not can_c:
            await query.answer(f"❌ چالنجر: {err_c}", show_alert=True)
            return
        if not can_o:
            await query.answer(f"❌ {err_o}", show_alert=True)
            return

        result = self.risk.create_risk_match(challenger_id, user_id, table, query.message.chat_id)

        if not result['success']:
            await query.answer(f"❌ {result['error']}", show_alert=True)
            return

        match_id = result['match_id']

        # ارسال کارت‌ها به هر بازیکن در PV
        for pid, card_ids in [(challenger_id, result['challenger_cards']), (user_id, result['opponent_cards'])]:
            cards = [self.db.get_card_by_id(cid) for cid in card_ids]
            cards = [c for c in cards if c]
            card_text = "\n".join(
                f"  {i+1}. {c.name} (P:{c.power} S:{c.speed} IQ:{c.iq})"
                for i, c in enumerate(cards)
            )
            keyboard = [[InlineKeyboardButton(
                f"🃏 {c.name}",
                callback_data=f"risk_card_{match_id}_{c.card_id}"
            )] for c in cards]

            try:
                await context.bot.send_message(
                    chat_id=pid,
                    text=f"🎲 **Risk Match شروع شد!**\n\nکارت‌های تو:\n{card_text}\n\nکدام را انتخاب می‌کنی؟",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception:
                pass

        await query.edit_message_text(
            f"✅ **Risk Match شروع شد!**\n\nهر دو بازیکن کارت خود را در PV انتخاب کنند.",
            parse_mode='Markdown'
        )

    async def risk_card_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب کارت در Risk"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        parts = query.data.split("_", 3)
        match_id = parts[2]
        card_id = parts[3]

        result = self.risk.select_card(match_id, user_id, card_id)
        if not result['success']:
            await query.answer(f"❌ {result['error']}", show_alert=True)
            return

        match = self.risk.get_risk_match(match_id)
        if not match:
            return

        # اگه هر دو انتخاب کردن → شروع Bluff phase
        if match['challenger_selected_card'] and match['opponent_selected_card']:
            await self._start_bluff_phase(context, match_id, match)
        else:
            await query.edit_message_text("✅ کارت انتخاب شد!\n⏳ منتظر حریف...", parse_mode='Markdown')

    async def _start_bluff_phase(self, context, match_id: str, match: dict):
        """شروع Bluff phase — Fold/Call/Raise"""
        import sqlite3 as _sq
        conn = _sq.connect(self.db.db_path)
        conn.execute("UPDATE risk_matches SET bluff_phase='waiting', challenger_bluff_action=NULL, opponent_bluff_action=NULL WHERE match_id=?", (match_id,))
        conn.commit()
        conn.close()

        pot = match['current_pot']
        table = match['table_value']
        max_raise = table * 3  # حداکثر 3x ورودیه

        text = (
            f"🎲 **Bluff Phase — راوند {match['current_round']}**\n\n"
            f"💰 پات فعلی: {pot} سکه\n"
            f"📈 حداکثر Raise: {max_raise} سکه\n\n"
            f"اقدام خود را انتخاب کن:"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Call (ادامه)", callback_data=f"risk_bluff_{match_id}_call")],
            [InlineKeyboardButton(f"📈 Raise +{table} سکه", callback_data=f"risk_bluff_{match_id}_raise_{table}")],
            [InlineKeyboardButton(f"📈 Raise +{table*2} سکه", callback_data=f"risk_bluff_{match_id}_raise_{table*2}")],
            [InlineKeyboardButton("🏳️ Fold (انصراف)", callback_data=f"risk_bluff_{match_id}_fold")],
        ]

        for pid in [match['challenger_id'], match['opponent_id']]:
            try:
                await context.bot.send_message(
                    chat_id=pid,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to send bluff UI to {pid}: {e}")

    async def risk_bluff_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت Fold/Call/Raise در Risk"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # risk_bluff_{match_id}_{action} یا risk_bluff_{match_id}_raise_{amount}
        parts = query.data.split("_")
        match_id = parts[2]
        action = parts[3]
        raise_amount = int(parts[4]) if action == "raise" and len(parts) > 4 else 0

        match = self.risk.get_risk_match(match_id)
        if not match:
            await query.answer("❌ بازی یافت نشد!", show_alert=True)
            return

        if match['bluff_phase'] not in ('waiting', 'raise_pending'):
            await query.answer("❌ این مرحله تموم شده!", show_alert=True)
            return

        is_challenger = user_id == match['challenger_id']
        is_opponent = user_id == match['opponent_id']
        if not is_challenger and not is_opponent:
            await query.answer("❌ این بازی مال تو نیست!", show_alert=True)
            return

        role = 'challenger' if is_challenger else 'opponent'
        other_id = match['opponent_id'] if is_challenger else match['challenger_id']
        other_role = 'opponent' if is_challenger else 'challenger'

        import sqlite3 as _sq

        # ── FOLD ──
        if action == "fold":
            winner_id = other_id
            self.db.add_coins(winner_id, match['current_pot'])
            self.db.add_xp(winner_id, 25)
            self.db.add_xp(user_id, 5)

            conn = _sq.connect(self.db.db_path)
            conn.execute("UPDATE risk_matches SET status='completed', winner_id=?, bluff_phase='done' WHERE match_id=?",
                         (winner_id, match_id))
            conn.commit()
            conn.close()

            fold_text = (
                f"🏳️ **Fold!**\n\n"
                f"بازیکن انصراف داد.\n"
                f"💰 برنده: {match['current_pot']} سکه!"
            )
            if match.get('chat_id'):
                try:
                    await context.bot.send_message(chat_id=match['chat_id'], text=fold_text, parse_mode='Markdown')
                except Exception:
                    pass
            await query.edit_message_text(fold_text, parse_mode='Markdown')
            return

        # ── RAISE ──
        if action == "raise":
            # بررسی موجودی
            ok, err = self.db.spend_coins(user_id, raise_amount)
            if not ok:
                await query.answer(f"❌ {err}", show_alert=True)
                return

            new_pot = match['current_pot'] + raise_amount
            conn = _sq.connect(self.db.db_path)
            conn.execute(
                "UPDATE risk_matches SET current_pot=?, bluff_phase='raise_pending', raise_amount=?, raise_by=?, "
                f"{role}_bluff_action='raise' WHERE match_id=?",
                (new_pot, raise_amount, user_id, match_id)
            )
            conn.commit()
            conn.close()

            await query.edit_message_text(
                f"📈 Raise {raise_amount} سکه زدی!\n⏳ منتظر جواب حریف...",
                parse_mode='Markdown'
            )

            # ارسال UI به حریف
            raise_text = (
                f"📈 **حریف Raise زد!**\n\n"
                f"مقدار: +{raise_amount} سکه\n"
                f"💰 پات جدید: {new_pot} سکه\n\n"
                f"جواب بده:"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Call", callback_data=f"risk_bluff_{match_id}_call")],
                [InlineKeyboardButton("🏳️ Fold", callback_data=f"risk_bluff_{match_id}_fold")],
            ]
            try:
                await context.bot.send_message(
                    chat_id=other_id,
                    text=raise_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to send raise UI: {e}")
            return

        # ── CALL ──
        if action == "call":
            # اگه raise_pending بود، باید مقدار raise رو هم بپردازه
            if match['bluff_phase'] == 'raise_pending' and match['raise_by'] != user_id:
                call_amount = match['raise_amount']
                ok, err = self.db.spend_coins(user_id, call_amount)
                if not ok:
                    await query.answer(f"❌ {err}", show_alert=True)
                    return
                new_pot = match['current_pot'] + call_amount
                conn = _sq.connect(self.db.db_path)
                conn.execute(
                    f"UPDATE risk_matches SET current_pot=?, bluff_phase='done', {role}_bluff_action='call' WHERE match_id=?",
                    (new_pot, match_id)
                )
                conn.commit()
                conn.close()
            else:
                conn = _sq.connect(self.db.db_path)
                conn.execute(
                    f"UPDATE risk_matches SET {role}_bluff_action='call' WHERE match_id=?",
                    (match_id,)
                )
                conn.commit()
                conn.close()

            await query.edit_message_text("✅ Call کردی!\n⏳ در حال resolve راوند...", parse_mode='Markdown')

            # بررسی اینکه هر دو Call کردن یا bluff_phase=done شده
            match = self.risk.get_risk_match(match_id)
            if match['bluff_phase'] == 'done' or \
               (match['challenger_bluff_action'] == 'call' and match['opponent_bluff_action'] == 'call'):
                await self._resolve_risk_round(context, match_id)
            # اگه فقط یکی Call کرده، منتظر دیگری

    async def _resolve_risk_round(self, context, match_id: str):
        """حل راوند Risk و اعلام نتیجه"""
        result = self.risk.resolve_round(match_id)
        match = self.risk.get_risk_match(match_id)
        if not match or not result['success']:
            return

        stat_names = {'power': '💪 قدرت', 'speed': '⚡ سرعت', 'iq': '🧠 هوش', 'popularity': '❤️ محبوبیت'}
        stat_label = stat_names.get(result['selected_stat'], result['selected_stat'])
        winner_text = "🏆 Challenger برنده!" if result['winner'] == 'challenger' else \
                      "🏆 Opponent برنده!" if result['winner'] == 'opponent' else "🤝 مساوی!"

        text = (
            f"⚔️ **راوند {result['round']}**\n\n"
            f"ویژگی: {stat_label}\n"
            f"Challenger: {result['challenger_value']}\n"
            f"Opponent: {result['opponent_value']}\n\n"
            f"{winner_text}\n\n"
            f"امتیاز: Challenger {match['challenger_rounds_won']} — Opponent {match['opponent_rounds_won']}\n"
            f"💰 پات: {match['current_pot']} سکه"
        )

        c_won = match['challenger_rounds_won']
        o_won = match['opponent_rounds_won']
        round_num = match['current_round']

        if c_won >= 2 or o_won >= 2 or round_num > 3:
            # تعیین برنده نهایی
            if c_won > o_won:
                final_winner_id = match['challenger_id']
            elif o_won > c_won:
                final_winner_id = match['opponent_id']
            else:
                self.db.add_coins(match['challenger_id'], match['table_value'])
                self.db.add_coins(match['opponent_id'], match['table_value'])
                final_winner_id = None

            if final_winner_id:
                self.db.add_coins(final_winner_id, match['current_pot'])
                self.db.add_xp(final_winner_id, 25)
                loser_id = match['opponent_id'] if final_winner_id == match['challenger_id'] else match['challenger_id']
                self.db.add_xp(loser_id, 5)
                text += f"\n\n🎉 **بازی تموم شد!**\n💰 برنده: {match['current_pot']} سکه!"

            import sqlite3 as _sq
            conn = _sq.connect(self.db.db_path)
            conn.execute('UPDATE risk_matches SET status=?, winner_id=? WHERE match_id=?',
                         ('completed', final_winner_id, match_id))
            conn.commit()
            conn.close()

            if match.get('chat_id'):
                try:
                    await context.bot.send_message(chat_id=match['chat_id'], text=text, parse_mode='Markdown')
                except Exception:
                    pass
        else:
            # reset کارت‌های انتخاب‌شده برای راوند بعدی
            import sqlite3 as _sq
            conn = _sq.connect(self.db.db_path)
            conn.execute(
                "UPDATE risk_matches SET challenger_selected_card=NULL, opponent_selected_card=NULL, "
                "bluff_phase='none', challenger_bluff_action=NULL, opponent_bluff_action=NULL WHERE match_id=?",
                (match_id,)
            )
            conn.commit()
            conn.close()

            if match.get('chat_id'):
                try:
                    await context.bot.send_message(chat_id=match['chat_id'], text=text, parse_mode='Markdown')
                except Exception:
                    pass

            # ارسال کارت‌ها برای راوند بعدی
            for pid, card_ids in [(match['challenger_id'], match['challenger_cards']),
                                   (match['opponent_id'], match['opponent_cards'])]:
                cards = [self.db.get_card_by_id(cid) for cid in card_ids]
                cards = [c for c in cards if c]
                keyboard = [[InlineKeyboardButton(
                    f"🃏 {c.name}", callback_data=f"risk_card_{match_id}_{c.card_id}"
                )] for c in cards]
                try:
                    await context.bot.send_message(
                        chat_id=pid,
                        text=f"🎲 **راوند {round_num + 1}** — کارت انتخاب کن:",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass


