#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shop, Skins, Missions, Mining Handlers
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




class ShopHandlersMixin:
    """Shop, Skins, Missions, Mining Handlers"""

    async def skins_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی اسکین‌های یک کارت"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # skins_menu_{card_id}
        card_id = query.data.split("_", 2)[2]
        card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
        if not card:
            await query.answer("❌ کارت یافت نشد!", show_alert=True)
            return

        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)

        # اسکین‌های موجود برای این کارت
        all_skins = self.skins.get_card_skins(card_id)
        player_skins = {s['skin_id'] for s in self.skins.get_player_skins(user_id, card_id)}
        active_skin = self.skins.get_active_skin(user_id, card_id)

        if not all_skins:
            text = (
                f"🎨 **اسکین‌های {card.name}**\n\n"
                f"هنوز هیچ اسکینی برای این کارت موجود نیست."
            )
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"cardinfo_{card_id}")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        type_emoji = {"normal": "🎨", "special": "✨", "seasonal": "🌸", "event": "🎁", "premium": "💎"}
        text = (
            f"🎨 **اسکین‌های {card.name}**\n\n"
            f"💰 موجودی: {coins:,} سکه\n\n"
        )

        keyboard = []
        for skin in all_skins:
            owned = skin['skin_id'] in player_skins
            is_active = skin['skin_id'] == active_skin
            emoji = type_emoji.get(skin['skin_type'], "🎨")
            status = "✅ فعال" if is_active else ("🔓 دارم" if owned else f"🔒 {skin['price']} سکه")
            btn_text = f"{emoji} {skin['name']} — {status}"

            if is_active:
                cb = f"skin_deactivate_{card_id}"
            elif owned:
                cb = f"skin_activate_{card_id}_{skin['skin_id']}"
            else:
                cb = f"skin_buy_{card_id}_{skin['skin_id']}"

            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb)])

        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"cardinfo_{card_id}")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def skin_buy_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """خرید اسکین"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # skin_buy_{card_id}_{skin_id}
        parts = query.data.split("_", 3)
        card_id = parts[2]
        skin_id = parts[3]

        result = self.skins.unlock_skin(user_id, skin_id)

        if result['success']:
            skin = self.skins.get_skin(skin_id)
            text = (
                f"✅ **اسکین خریداری شد!**\n\n"
                f"🎨 {skin['name']}\n"
                f"💰 هزینه: {result['coins_spent']} سکه\n"
                f"💵 موجودی: {result['remaining_coins']:,} سکه"
            )
        else:
            text = f"❌ {result['error']}"

        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"skins_menu_{card_id}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def skin_activate_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال کردن اسکین"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # skin_activate_{card_id}_{skin_id}
        parts = query.data.split("_", 3)
        card_id = parts[2]
        skin_id = parts[3]

        result = self.skins.set_active_skin(user_id, card_id, skin_id)

        if result['success']:
            skin = self.skins.get_skin(skin_id)
            await query.answer(f"✅ اسکین {skin['name']} فعال شد!", show_alert=False)
        else:
            await query.answer(f"❌ {result['error']}", show_alert=True)

        # بازگشت به منوی اسکین
        query.data = f"skins_menu_{card_id}"
        await self.skins_menu_handler(update, context)

    async def skin_deactivate_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """غیرفعال کردن اسکین (بازگشت به پیش‌فرض)"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # skin_deactivate_{card_id}
        card_id = query.data.split("_", 2)[2]

        self.skins.set_active_skin(user_id, card_id, None)
        await query.answer("✅ اسکین پیش‌فرض فعال شد!", show_alert=False)

        query.data = f"skins_menu_{card_id}"
        await self.skins_menu_handler(update, context)

    # ==================== MISSION HANDLERS ====================

    async def mission_claim_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت پاداش ماموریت کارت"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        card_id = query.data.split("_")[2]

        result = self.missions.claim_mission_reward(user_id, card_id)

        if result['success']:
            # XP برای ارتقا به Legend
            self.db.add_xp(user_id, 30)
            text = (
                f"🏆 **پاداش ماموریت دریافت شد!**\n\n"
                f"🟡 **{result['card_name']}** حالا Legend شد!\n"
                f"⭐ +30 XP"
            )
        else:
            text = f"❌ {result['error']}"

        keyboard = [
            [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ==================== MINING HANDLER ====================

    async def mining_claim_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت ماینینگ روزانه"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # محاسبه ماینینگ
        coins_to_earn = self.economy.calculate_daily_mining(user_id)

        # بررسی cooldown
        can_claim, error_msg = self.economy.can_claim_mining(user_id)

        if not can_claim:
            # نمایش وضعیت بدون claim
            player = self.db.get_or_create_player(user_id)
            text = (
                f"⛏️ **ماینینگ روزانه**\n\n"
                f"⏳ {error_msg}\n\n"
                f"💰 موجودی فعلی: {getattr(player, 'coins', 0):,} سکه\n"
                f"📦 درآمد فردا: {coins_to_earn} سکه"
            )
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        if coins_to_earn == 0:
            text = (
                "⛏️ **ماینینگ روزانه**\n\n"
                "❌ کارت کافی نداری!\n\n"
                "برای ماینینگ حداقل **۵ کارت** (Normal/Epic/Legend) نیاز داری.\n"
                f"📦 کارت‌های فعلی تو: {len([c for c in self.db.get_player_cards(user_id)])}"
            )
            keyboard = [
                [InlineKeyboardButton("🎁 کلیم کارت", callback_data="daily_claim")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        # اجرای ماینینگ
        success, earned, err = self.economy.claim_daily_mining(user_id)

        if success:
            player = self.db.get_or_create_player(user_id)
            card_count = len(self.db.get_player_cards(user_id))
            text = (
                f"⛏️ **ماینینگ موفق!**\n\n"
                f"💰 +{earned} سکه دریافت کردی!\n\n"
                f"📦 کارت‌های تو: {card_count}\n"
                f"💵 موجودی جدید: {getattr(player, 'coins', 0):,} سکه\n\n"
                f"⏰ ماینینگ بعدی: فردا"
            )
            keyboard = [
                [InlineKeyboardButton("🔮 Fusion", callback_data="fusion_menu")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
            ]
        else:
            text = f"❌ خطا در ماینینگ: {err}"
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ==================== SHOP HANDLERS ====================

    async def shop_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی اصلی شاپ"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)
        max_hearts = getattr(player, 'max_hearts', 10)

        text = (
            f"🛒 **شاپ**\n\n"
            f"💰 موجودی: {coins:,} سکه\n\n"
            f"چی می‌خوای بخری؟"
        )

        keyboard = [
            [InlineKeyboardButton(
                f"❤️ +۱ قلب دائمی — 200 سکه ({max_hearts}/15)",
                callback_data="shop_buy_heart"
            )],
            [InlineKeyboardButton(
                "🟢→🟣 ارتقای Normal به Epic — 100 سکه",
                callback_data="shop_upgrade_epic"
            )],
            [InlineKeyboardButton(
                "🟣→🟡 ارتقای Epic به Legend — 500 سکه",
                callback_data="shop_upgrade_legend"
            )],
            [InlineKeyboardButton(
                "💱 تبدیل امتیاز به سکه",
                callback_data="shop_convert_score"
            )],
            [InlineKeyboardButton(
                "🎨 اسکین‌های کارت‌ها",
                callback_data="shop_skins_list"
            )],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def shop_buy_heart_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """خرید +۱ قلب دائمی"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        success, error = self.economy.buy_heart_increase(user_id)

        if success:
            player = self.db.get_or_create_player(user_id)
            new_max = getattr(player, 'max_hearts', 10)
            # قلب فعلی رو هم آپدیت کن
            player.hearts = min(player.hearts + 1, new_max)
            self.db.update_player(player)
            text = (
                f"✅ **خرید موفق!**\n\n"
                f"❤️ حداکثر قلب: {new_max}\n"
                f"💰 موجودی: {getattr(player, 'coins', 0):,} سکه"
            )
        else:
            text = f"❌ **خرید ناموفق**\n\n{error}"

        keyboard = [
            [InlineKeyboardButton("🛒 ادامه خرید", callback_data="shop_menu")],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def shop_upgrade_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """خرید ارتقای کارت با سکه — انتخاب کارت"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # shop_upgrade_epic یا shop_upgrade_legend
        upgrade_type = query.data.split("_")[2]  # 'epic' یا 'legend'

        if upgrade_type == "epic":
            source_rarity = CardRarity.NORMAL
            price = self.economy.PRICES['upgrade_normal_to_epic']
            target_label = "Epic 🟣"
            eco_key = "normal_to_epic"
        else:
            source_rarity = CardRarity.EPIC
            price = self.economy.PRICES['upgrade_epic_to_legend']
            target_label = "Legend 🟡"
            eco_key = "epic_to_legend"

        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)

        if coins < price:
            await query.edit_message_text(
                f"❌ سکه کافی نداری!\n\nنیاز: {price} سکه\nموجودی: {coins:,} سکه",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")]]),
                parse_mode='Markdown'
            )
            return

        # نمایش کارت‌های قابل ارتقا
        cards = self.db.get_player_cards(user_id)
        eligible = [c for c in cards if c.rarity == source_rarity]

        if not eligible:
            rarity_name = "Normal" if upgrade_type == "epic" else "Epic"
            await query.edit_message_text(
                f"❌ هیچ کارت {rarity_name} نداری!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")]]),
                parse_mode='Markdown'
            )
            return

        text = (
            f"🛒 **ارتقا به {target_label}**\n\n"
            f"قیمت: {price} سکه\n"
            f"موجودی: {coins:,} سکه\n\n"
            f"کدام کارت را ارتقا بدی؟"
        )
        keyboard = []
        for card in eligible:
            keyboard.append([InlineKeyboardButton(
                f"{card.name} (P:{card.power} S:{card.speed} IQ:{card.iq})",
                callback_data=f"shop_confirm_{eco_key}_{card.card_id}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def shop_confirm_upgrade_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تأیید و اجرای ارتقای کارت با سکه"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # shop_confirm_{eco_key}_{card_id}
        parts = query.data.split("_", 3)
        eco_key = parts[2]       # normal_to_epic یا epic_to_legend
        card_id = parts[3]

        card = self.db.get_card_by_id_for_player(card_id, user_id)
        if not card:
            await query.answer("❌ کارت یافت نشد!", show_alert=True)
            return

        # کسر سکه
        success, error = self.economy.buy_card_upgrade(user_id, eco_key)
        if not success:
            await query.edit_message_text(
                f"❌ {error}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")]]),
                parse_mode='Markdown'
            )
            return

        # اعمال ارتقا با rarity_override
        new_rarity = "epic" if eco_key == "normal_to_epic" else "legend"
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE player_cards SET rarity_override = ? WHERE user_id = ? AND card_id = ?',
            (new_rarity, user_id, card_id)
        )
        conn.commit()
        conn.close()

        # XP برای ارتقا
        xp_amount = 15 if eco_key == "normal_to_epic" else 30
        old_lv, new_lv = self.db.add_xp(user_id, xp_amount)
        level_text = f"\n⬆️ Level Up! → {new_lv}" if new_lv > old_lv else ""

        player = self.db.get_or_create_player(user_id)
        target_emoji = "🟣" if new_rarity == "epic" else "🟡"
        target_label = "Epic" if new_rarity == "epic" else "Legend"

        text = (
            f"✅ **ارتقا موفق!**\n\n"
            f"{target_emoji} **{card.name}** حالا {target_label} شد!\n"
            f"⭐ +{xp_amount} XP{level_text}\n"
            f"💰 موجودی: {getattr(player, 'coins', 0):,} سکه"
        )
        keyboard = [
            [InlineKeyboardButton("🛒 ادامه خرید", callback_data="shop_menu")],
            [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def shop_convert_score_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تبدیل امتیاز به سکه"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        player = self.db.get_or_create_player(user_id)
        score = player.total_score
        rate = self.economy.SCORE_TO_COIN_RATE  # هر 100 امتیاز = 1 سکه
        max_convertible = (score // rate) * rate
        coins_to_earn = score // rate

        if coins_to_earn == 0:
            text = (
                f"💱 **تبدیل امتیاز به سکه**\n\n"
                f"🏆 امتیاز فعلی: {score}\n"
                f"❌ حداقل {rate} امتیاز برای تبدیل نیاز است."
            )
            keyboard = [[InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        text = (
            f"💱 **تبدیل امتیاز به سکه**\n\n"
            f"🏆 امتیاز فعلی: {score:,}\n"
            f"💰 موجودی سکه: {getattr(player, 'coins', 0):,}\n\n"
            f"نرخ: هر {rate} امتیاز = ۱ سکه\n\n"
            f"✅ می‌توانی **{max_convertible:,} امتیاز** را به **{coins_to_earn} سکه** تبدیل کنی.\n\n"
            f"ادامه می‌دهی؟"
        )
        keyboard = [
            [InlineKeyboardButton(f"✅ تبدیل {coins_to_earn} سکه", callback_data=f"shop_do_convert_{max_convertible}")],
            [InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def shop_skins_list_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لیست اسکین‌های قابل خرید در شاپ"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        player = self.db.get_or_create_player(user_id)
        coins = getattr(player, 'coins', 0)

        # دریافت همه کارت‌های بازیکن که اسکین دارن
        player_cards = self.db.get_player_cards(user_id)
        cards_with_skins = []
        for card in player_cards:
            skins = self.skins.get_card_skins(card.card_id)
            if skins:
                cards_with_skins.append((card, skins))

        if not cards_with_skins:
            text = (
                f"🎨 **اسکین‌های شاپ**\n\n"
                f"💰 موجودی: {coins:,} سکه\n\n"
                f"هنوز هیچ اسکینی برای کارت‌های شما موجود نیست."
            )
            keyboard = [[InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")]]
        else:
            text = (
                f"🎨 **اسکین‌های شاپ**\n\n"
                f"💰 موجودی: {coins:,} سکه\n\n"
                f"کارت مورد نظر را انتخاب کن:"
            )
            keyboard = []
            for card, skins in cards_with_skins[:10]:
                rarity_emoji = {"normal": "🟢", "epic": "🟣", "legend": "🟡"}.get(card.rarity.value, "⚪")
                keyboard.append([InlineKeyboardButton(
                    f"{rarity_emoji} {card.name} ({len(skins)} اسکین)",
                    callback_data=f"skins_menu_{card.card_id}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 شاپ", callback_data="shop_menu")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def shop_do_convert_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اجرای تبدیل امتیاز به سکه"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        score_amount = int(query.data.split("_")[3])

        success, earned, error = self.economy.convert_score_to_coins(user_id, score_amount)

        if success:
            player = self.db.get_or_create_player(user_id)
            text = (
                f"✅ **تبدیل موفق!**\n\n"
                f"💰 +{earned} سکه دریافت کردی!\n"
                f"💵 موجودی جدید: {getattr(player, 'coins', 0):,} سکه\n"
                f"🏆 امتیاز باقیمانده: {player.total_score:,}"
            )
        else:
            text = f"❌ {error}"

        keyboard = [
            [InlineKeyboardButton("🛒 ادامه خرید", callback_data="shop_menu")],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ==================== FUSION HANDLERS ====================


