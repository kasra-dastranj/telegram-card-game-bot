#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fusion Handlers
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




class FusionHandlersMixin:
    """Fusion Handlers"""

    async def fusion_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی اصلی Fusion"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        can_epic, normal_cards = self.fusion.can_fuse_to_epic(user_id)
        can_legend, epic_cards = self.fusion.can_fuse_to_legend(user_id)

        text = (
            "🔮 **سیستم Fusion**\n\n"
            "با ترکیب ۳ کارت، یکی از آن‌ها را ارتقا بده!\n\n"
            f"🟢 Normal: {len(normal_cards)} کارت "
            f"{'✅ (می‌توانی Fusion کنی)' if can_epic else f'❌ (حداقل ۳ نیاز است)'}\n"
            f"🟣 Epic: {len(epic_cards)} کارت "
            f"{'✅ (می‌توانی Fusion کنی)' if can_legend else f'❌ (حداقل ۳ نیاز است)'}\n\n"
            "کدام نوع Fusion می‌خواهی؟"
        )

        keyboard = []
        if can_epic:
            keyboard.append([InlineKeyboardButton("🟢→🟣 Normal به Epic", callback_data="fusion_start_epic")])
        else:
            keyboard.append([InlineKeyboardButton(f"🟢→🟣 Normal به Epic (نیاز: {3 - len(normal_cards)} کارت بیشتر)", callback_data="fusion_noop")])

        if can_legend:
            keyboard.append([InlineKeyboardButton("🟣→🟡 Epic به Legend", callback_data="fusion_start_legend")])
        else:
            keyboard.append([InlineKeyboardButton(f"🟣→🟡 Epic به Legend (نیاز: {3 - len(epic_cards)} کارت بیشتر)", callback_data="fusion_noop")])

        keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def fusion_noop_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دکمه‌های غیرفعال Fusion"""
        await update.callback_query.answer("❌ کارت کافی نداری!", show_alert=True)

    async def fusion_start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند انتخاب کارت برای Fusion — نمایش لیست کارت‌ها"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # fusion_start_epic یا fusion_start_legend
        fusion_type = query.data.split("_")[2]  # 'epic' یا 'legend'

        if fusion_type == "epic":
            _, cards = self.fusion.can_fuse_to_epic(user_id)
            rarity_label = "Normal"
            rarity_emoji = "🟢"
            target_label = "Epic 🟣"
        else:
            _, cards = self.fusion.can_fuse_to_legend(user_id)
            rarity_label = "Epic"
            rarity_emoji = "🟣"
            target_label = "Legend 🟡"

        # ذخیره state در context.user_data
        context.user_data['fusion_type'] = fusion_type
        context.user_data['fusion_selected'] = []

        text = (
            f"🔮 **Fusion {rarity_label} → {target_label}**\n\n"
            f"دقیقاً **۳ کارت {rarity_emoji} {rarity_label}** انتخاب کن.\n"
            f"بعد از انتخاب، تصمیم می‌گیری کدام یک ارتقا یابد.\n\n"
            f"کارت‌های انتخاب‌شده: ۰/۳"
        )

        keyboard = self._build_fusion_card_keyboard(cards, selected=[], fusion_type=fusion_type)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    def _build_fusion_card_keyboard(self, cards: list, selected: list, fusion_type: str) -> list:
        """ساخت keyboard انتخاب کارت برای Fusion"""
        keyboard = []
        for card in cards:
            is_sel = card.card_id in selected
            mark = "✅ " if is_sel else ""
            btn = InlineKeyboardButton(
                f"{mark}{card.name}",
                callback_data=f"fusion_pick_{fusion_type}_{card.card_id}"
            )
            keyboard.append([btn])

        # دکمه‌های پایین
        bottom = []
        if len(selected) == 3:
            bottom.append(InlineKeyboardButton("✅ تأیید انتخاب‌ها", callback_data=f"fusion_confirm_{fusion_type}"))
        bottom.append(InlineKeyboardButton("🔙 بازگشت", callback_data="fusion_menu"))
        keyboard.append(bottom)
        return keyboard

    async def fusion_pick_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب/لغو انتخاب یک کارت برای Fusion"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # fusion_pick_{type}_{card_id}
        parts = query.data.split("_", 3)
        fusion_type = parts[2]
        card_id = parts[3]

        selected: list = context.user_data.get('fusion_selected', [])

        if card_id in selected:
            selected.remove(card_id)
        elif len(selected) < 3:
            selected.append(card_id)
        else:
            await query.answer("❌ فقط ۳ کارت می‌توانی انتخاب کنی!", show_alert=True)
            return

        context.user_data['fusion_selected'] = selected

        if fusion_type == "epic":
            _, cards = self.fusion.can_fuse_to_epic(user_id)
            rarity_label, rarity_emoji, target_label = "Normal", "🟢", "Epic 🟣"
        else:
            _, cards = self.fusion.can_fuse_to_legend(user_id)
            rarity_label, rarity_emoji, target_label = "Epic", "🟣", "Legend 🟡"

        text = (
            f"🔮 **Fusion {rarity_label} → {target_label}**\n\n"
            f"دقیقاً **۳ کارت {rarity_emoji} {rarity_label}** انتخاب کن.\n\n"
            f"کارت‌های انتخاب‌شده: {len(selected)}/۳"
        )
        if selected:
            names = [c.name for c in cards if c.card_id in selected]
            text += "\n" + "\n".join(f"  ✅ {n}" for n in names)

        keyboard = self._build_fusion_card_keyboard(cards, selected, fusion_type)
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception:
            pass

    async def fusion_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تأیید ۳ کارت — حالا بازیکن انتخاب می‌کند کدام ارتقا یابد"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        fusion_type = query.data.split("_")[2]
        selected: list = context.user_data.get('fusion_selected', [])

        if len(selected) != 3:
            await query.answer("❌ دقیقاً ۳ کارت انتخاب کن!", show_alert=True)
            return

        # دریافت اطلاعات کارت‌ها
        cards = [self.db.get_card_by_id(cid) for cid in selected]
        cards = [c for c in cards if c]

        if len(cards) != 3:
            await query.answer("❌ خطا در دریافت کارت‌ها!", show_alert=True)
            return

        target_label = "Epic 🟣" if fusion_type == "epic" else "Legend 🟡"

        text = (
            f"🔮 **کدام کارت {target_label} شود؟**\n\n"
            "هر ۳ کارت مصرف می‌شوند.\n"
            "یکی از آن‌ها ارتقا می‌یابد.\n\n"
            "انتخاب کن:"
        )

        keyboard = []
        for card in cards:
            rarity_emoji = {"normal": "🟢", "epic": "🟣", "legend": "🟡"}.get(card.rarity.value, "⚪")
            keyboard.append([InlineKeyboardButton(
                f"{rarity_emoji} {card.name} (P:{card.power} S:{card.speed} IQ:{card.iq} Pop:{card.popularity})",
                callback_data=f"fusion_upgrade_{fusion_type}_{card.card_id}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"fusion_start_{fusion_type}")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def fusion_upgrade_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اجرای نهایی Fusion پس از انتخاب کارت ارتقایافته"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # fusion_upgrade_{type}_{card_id}
        parts = query.data.split("_", 3)
        fusion_type = parts[2]
        upgrade_card_id = parts[3]

        selected: list = context.user_data.get('fusion_selected', [])

        if len(selected) != 3 or upgrade_card_id not in selected:
            await query.answer("❌ خطا! دوباره از منوی Fusion شروع کن.", show_alert=True)
            return

        # اجرای Fusion
        if fusion_type == "epic":
            result = self.fusion.fuse_to_epic(user_id, selected, upgrade_card_id)
        else:
            result = self.fusion.fuse_to_legend(user_id, selected, upgrade_card_id)

        # پاک کردن state
        context.user_data.pop('fusion_selected', None)
        context.user_data.pop('fusion_type', None)

        if result.success:
            upgraded = result.upgraded_card
            consumed_names = [c.name for c in result.consumed_cards if c.card_id != upgrade_card_id]
            target_emoji = "🟣" if fusion_type == "epic" else "🟡"
            target_label = "Epic" if fusion_type == "epic" else "Legend"

            # اضافه کردن XP
            old_level, new_level = self.db.add_xp(user_id, 15 if fusion_type == "epic" else 30)
            xp_text = f"\n⬆️ Level Up! {old_level} → {new_level}" if new_level > old_level else ""

            text = (
                f"✨ **Fusion موفق!**\n\n"
                f"کارت‌های مصرف‌شده:\n"
                + "\n".join(f"  ❌ {n}" for n in consumed_names) +
                f"\n\n{target_emoji} **{upgraded.name}** حالا {target_label} شد! 🎉"
                f"{xp_text}"
            )
            keyboard = [
                [InlineKeyboardButton("🔮 Fusion دیگری", callback_data="fusion_menu")],
                [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")],
            ]
        else:
            text = f"❌ **Fusion ناموفق**\n\n{result.error}"
            keyboard = [
                [InlineKeyboardButton("🔙 بازگشت به Fusion", callback_data="fusion_menu")],
            ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ==================== RISK MODE HANDLERS ====================


