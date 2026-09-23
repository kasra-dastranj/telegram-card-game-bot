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

        try:
            payload = query.data.removeprefix("risk_card_")
            if payload.startswith("risk_"):
                # Already-sent buttons use risk_<challenger>_<opponent>_<time>.
                parts = payload.split("_", 4)
                match_id, card_id = "_".join(parts[:4]), parts[4]
            else:
                match_id, card_id = payload.split("_", 1)
        except (ValueError, IndexError, AttributeError):
            await query.answer("❌ دکمه نامعتبر است", show_alert=True)
            return

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
        changed = conn.execute(
            """UPDATE risk_matches SET bluff_phase='waiting',challenger_bluff_action=NULL,opponent_bluff_action=NULL
               WHERE match_id=? AND status!='completed' AND bluff_phase='none'
               AND challenger_selected_card IS NOT NULL AND opponent_selected_card IS NOT NULL""",
            (match_id,),
        ).rowcount
        conn.commit()
        conn.close()
        if changed != 1:
            return

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
        """Persist an action before sending messages or advancing the round."""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        try:
            payload = query.data.removeprefix("risk_bluff_")
            match_id, action = payload.rsplit("_", 1)
            raise_amount = 0
            if action.isdigit() or action.startswith("-"):
                match_id, action, amount = payload.rsplit("_", 2)
                raise_amount = int(amount)
            risk_action = RiskAction(action)
        except (ValueError, AttributeError):
            await query.answer("❌ دکمه نامعتبر است", show_alert=True)
            return

        match = self.risk.get_risk_match(match_id)
        if not match or match["status"] == "completed" or match["bluff_phase"] not in ("waiting", "raise_pending"):
            await query.answer("❌ این مرحله تمام شده است", show_alert=True)
            return
        result = self.risk.make_action(match_id, user_id, risk_action, raise_amount)
        if not result["success"]:
            await query.answer(f"❌ {result['error']}", show_alert=True)
            return

        if risk_action == RiskAction.FOLD:
            text = f"🏳️ **Fold!**\n\nبازیکن انصراف داد.\n💰 برنده: {result['pot']} سکه!"
            if match.get("chat_id"):
                try:
                    await context.bot.send_message(chat_id=match["chat_id"], text=text, parse_mode="Markdown")
                except Exception:
                    pass
            await query.edit_message_text(text, parse_mode="Markdown")
        elif risk_action == RiskAction.RAISE:
            other_id = match["opponent_id"] if user_id == match["challenger_id"] else match["challenger_id"]
            await query.edit_message_text(f"📈 Raise {raise_amount} سکه زدی!\n⏳ منتظر جواب حریف...")
            keyboard = [
                [InlineKeyboardButton("✅ Call", callback_data=f"risk_bluff_{match_id}_call")],
                [InlineKeyboardButton("🏳️ Fold", callback_data=f"risk_bluff_{match_id}_fold")],
            ]
            try:
                await context.bot.send_message(
                    chat_id=other_id,
                    text=f"📈 حریف Raise زد!\nمقدار: +{raise_amount} سکه\n💰 پات: {result['new_pot']} سکه",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            except Exception as exc:
                logger.warning("Failed to send raise UI: %s", exc)
        else:
            await query.edit_message_text("✅ Call کردی!\n⏳ منتظر نتیجه...")
            if result.get("ready"):
                await self._resolve_risk_round(context, match_id)

    async def _resolve_risk_round(self, context, match_id: str):
        """The engine settles coins and progression; this handler only presents it."""
        result = self.risk.resolve_round(match_id)
        match = self.risk.get_risk_match(match_id)
        if not match or not result["success"]:
            return
        stat_names = {'power': '💪 قدرت', 'speed': '⚡ سرعت', 'iq': '🧠 هوش', 'popularity': '❤️ محبوبیت'}
        winner_text = "🏆 Challenger برنده!" if result["winner"] == "challenger" else "🏆 Opponent برنده!" if result["winner"] == "opponent" else "🤝 مساوی!"
        text = (
            f"⚔️ **راوند {result['round']}**\n\n"
            f"ویژگی: {stat_names[result['selected_stat']]}\n"
            f"Challenger: {result['challenger_value']}\nOpponent: {result['opponent_value']}\n"
            f"{winner_text}\n\n"
            f"امتیاز: Challenger {match['challenger_rounds_won']} — Opponent {match['opponent_rounds_won']}\n"
            f"💰 پات: {match['current_pot']} سکه"
        )
        if result["game_over"]:
            text += f"\n\n🎉 بازی تمام شد! برنده: {match['current_pot']} سکه" if result["winner_id"] else "\n\n🤝 بازی مساوی شد؛ کل پات تقسیم شد."
        if match.get("chat_id"):
            try:
                await context.bot.send_message(chat_id=match["chat_id"], text=text, parse_mode="Markdown")
            except Exception:
                pass
        if result["game_over"]:
            return
        for pid, card_ids in ((match["challenger_id"], match["challenger_cards"]), (match["opponent_id"], match["opponent_cards"])):
            cards = [self.db.get_card_by_id(cid) for cid in card_ids]
            keyboard = [[InlineKeyboardButton(f"🃏 {card.name}", callback_data=f"risk_card_{match_id}_{card.card_id}")]
                        for card in cards if card]
            try:
                await context.bot.send_message(
                    chat_id=pid, text=f"🎲 **راوند {match['current_round']}** — کارت انتخاب کن:",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown",
                )
            except Exception:
                pass
