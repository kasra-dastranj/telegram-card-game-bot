#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PvP Fight Handlers
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




class PvPHandlersMixin:
    """PvP Fight Handlers"""

    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            """مدیریت دستور /leaderboard"""
            # تشخیص نوع چت
            chat_type = update.effective_chat.type
            is_group = chat_type in ["group", "supergroup"]
            
            if is_group:
                # منوی لیدربورد گروه
                text = "🏆 **Leaderboard گروه**\n\nبازه زمانی را انتخاب کنید:"
                keyboard = [
                    [InlineKeyboardButton("📊 هفتگی", callback_data="lb_group_weekly_10")],
                    [InlineKeyboardButton("📊 ماهانه", callback_data="lb_group_monthly_10")],
                    [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_group_all_10")]
                ]
            else:
                # منوی لیدربورد جهانی
                text = "🏆 **Leaderboard جهانی**\n\nبازه زمانی را انتخاب کنید:"
                keyboard = [
                    [InlineKeyboardButton("📊 هفتگی", callback_data="lb_global_weekly_10")],
                    [InlineKeyboardButton("📊 ماهانه", callback_data="lb_global_monthly_10")],
                    [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_global_all_10")]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت دستور /leaderboard"""
        # تشخیص نوع چت
        chat_type = update.effective_chat.type
        is_group = chat_type in ["group", "supergroup"]
        
        if is_group:
            # منوی لیدربورد گروه
            text = "🏆 **Leaderboard گروه**\n\nبازه زمانی را انتخاب کنید:"
            keyboard = [
                [InlineKeyboardButton("📊 هفتگی", callback_data="lb_group_weekly_10")],
                [InlineKeyboardButton("📊 ماهانه", callback_data="lb_group_monthly_10")],
                [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_group_all_10")]
            ]
        else:
            # منوی لیدربورد جهانی
            text = "🏆 **Leaderboard جهانی**\n\nبازه زمانی را انتخاب کنید:"
            keyboard = [
                [InlineKeyboardButton("📊 هفتگی", callback_data="lb_global_weekly_10")],
                [InlineKeyboardButton("📊 ماهانه", callback_data="lb_global_monthly_10")],
                [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_global_all_10")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def fight_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور شروع چالش PvP در گروه"""
        # بررسی مجوز دستور
        if not self._is_command_allowed_in_chat("fight", update.effective_chat.type):
            await update.message.reply_text(
                "🚫 این دستور فقط در گروه‌ها قابل استفاده است.\n"
                "🥊 برای چالش PvP، ربات را به گروه اضافه کنید."
            )
            return

        challenger_id = update.effective_user.id
        chat_id = update.effective_chat.id

        # بررسی جان‌های بازیکن - اگر تمام شده باشد، نمی‌تواند فایت بسازد
        try:
            challenger_player = self.db.get_or_create_player(challenger_id)
            challenger_player = self.game.check_and_reset_hearts(challenger_player)
            if getattr(challenger_player, 'hearts', 5) <= 0:
                time_remaining = self.game.get_heart_reset_time_remaining(challenger_player)
                if time_remaining:
                    time_str = self.game.format_time_remaining(time_remaining)
                    message = f"💀 جان شما تمام شده!\n\n⏰ تا {time_str} دیگر نمی‌توانید بازی کنید.\n\n💝 هر ۲۴ ساعت یکبار ۵ جان شارژ می‌شود."
                else:
                    message = "💀 جان شما تمام شده! لطفاً چند لحظه صبر کنید تا جان‌ها ریست شوند."
                await update.message.reply_text(message)
                return
        except Exception:
            pass

        player_cards = self.db.get_player_cards(challenger_id)
        if not player_cards:
            await update.message.reply_text("🎴 ابتدا باید کارتی داشته باشید! در چت خصوصی ربات /start بزنید.")
            return

        active_fights = self.db.get_user_active_fights(challenger_id)
        if active_fights:
            await update.message.reply_text("⚠️ شما قبلاً یک چالش فعال دارید.")
            return

        fight_id = self.db.create_fight(challenger_id, 0, chat_id)
        challenger_name = update.effective_user.first_name
        
        text = (
            f"🥊 **چالش PvP!**\n\n"
            f"🔥 {challenger_name} همه را به مبارزه دعوت می‌کند!\n\n"
            f"آیا جرئت قبول این چالش را دارید؟\n\n"
            f"⚠️ **توجه**: اگر ربات را استارت نکرده‌اید، ابتدا @TelBattleBot را در پیوی استارت کنید!"
        )
        keyboard = [
            [InlineKeyboardButton("✊ قبول (نرمال)", callback_data=f"accept_pvp_{fight_id}")],
            [InlineKeyboardButton("🎲 قبول (تصادفی)", callback_data=f"accept_pvp_random_{fight_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    # ==================== PVP HANDLERS - FIXED ====================


    async def daily_claim_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت دریافت کارت روزانه"""
        query = update.callback_query
        await query.answer()
        
        # Check panel expiration
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        user_id = query.from_user.id
        success, card, error = self.game.claim_daily_card(user_id)
        
        if success and card:
            rarity_colors = {
                CardRarity.NORMAL: "🟢",
                CardRarity.EPIC: "🟣",
                CardRarity.LEGEND: "🟡"
            }
            color = rarity_colors[card.rarity]
            
            # ارسال تصویر کارت با یک دیالوگ کوتاه
            claim_dialog = get_victory_dialog(card.name)
            image_sent = await send_card_image_safely(query.message, card.name, self.config, f"🎉 {card.name}\n\n“{claim_dialog}”")
            
            # متن اطلاعات کارت
            text = (
                f"🎉 **کارت روزانه دریافت شد!**\n\n"
                f"{color} **{card.name}** ({card.rarity.value.title()})\n\n"
                f"📊 **آمار کارت:**\n"
                f"💪 قدرت: {card.power}\n"
                f"⚡ سرعت: {card.speed}\n"
                f"🧠 آی‌کیو: {card.iq}\n"
                f"❤️ محبوبیت: {card.popularity}\n"
                f"🎯 مجموع: {card.get_total_stats()}\n\n"
                f"✨ **ابیلیتی‌ها:**\n"
            )
            
            for ability in card.abilities:
                text += f"• {ability}\n"
            
            text += f"\n🕐 کلیم بعدی: {self.game.CLAIM_COOLDOWN_HOURS} ساعت دیگر"
            
            if not image_sent:
                text = f"🎴 (تصویر در دسترس نیست)\n\n" + text
            
            keyboard = [
                [InlineKeyboardButton("🎴 مشاهده کارت‌ها", callback_data="my_cards")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        else:
            text = f"⚠ **خطا در دریافت کارت**\n\n{error if error else 'خطای نامشخص!'}"
            
            keyboard = [
                [InlineKeyboardButton("🎴 مشاهده کارت‌ها", callback_data="my_cards")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def my_cards_navigation_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation بین دسته‌بندی‌ها و صفحات کارت‌های من"""
        query = update.callback_query
        await query.answer()
        
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        # my_cards_nav_{category}_{page}
        parts = query.data.split("_")
        category = parts[3]
        page = int(parts[4])
        user_id = query.from_user.id
        
        # ساخت کیبورد جدید
        keyboard = self._create_my_cards_keyboard(user_id, category=category, page=page)
        
        # متن پیام
        if category == "menu":
            cards = self.db.get_player_cards(user_id)
            text = f"🎴 **کارت‌های شما ({len(cards)} کارت)**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
        else:
            category_names = {
                "favorite": "⭐ مورد علاقه",
                "legend": "🟡 Legendary",
                "epic": "🟣 Epic",
                "normal": "🟢 Normal"
            }
            category_name = category_names.get(category, category)
            
            if category == "favorite":
                cards, total_count = self.db.get_favorite_cards(user_id, page=page, per_page=6)
            else:
                rarity_map = {
                    "legend": CardRarity.LEGEND,
                    "epic": CardRarity.EPIC,
                    "normal": CardRarity.NORMAL
                }
                rarity = rarity_map.get(category)
                cards, total_count = self.db.get_player_cards_by_rarity(user_id, rarity=rarity, page=page, per_page=6)
            
            total_pages = (total_count + 5) // 6
            text = f"🎴 **{category_name}** (صفحه {page}/{total_pages})\n\nلطفاً کارت را انتخاب کنید:"
        
        try:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception:
            pass


    async def request_pvp_fight_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """درخواست فایت PvP"""
        query = update.callback_query
        await query.answer()
        
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        challenger_id = query.from_user.id
        chat_id = query.message.chat_id

        # بررسی جان‌های بازیکن - اگر تمام شده باشد، نمی‌تواند فایت بسازد
        try:
            challenger_player = self.db.get_or_create_player(challenger_id)
            challenger_player = self.game.check_and_reset_hearts(challenger_player)
            if getattr(challenger_player, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, challenger_player)
                return
        except Exception:
            pass
        
        # بررسی نوع چت - باید گروه باشد
        if query.message.chat.type == 'private':
            text = "🚫 فایت PvP فقط در گروه‌ها امکان‌پذیر است!\n\nلطفاً این ربات را به گروه اضافه کنید."
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            return
        
        # بررسی داشتن کارت
        player_cards = self.db.get_player_cards(challenger_id)
        if not player_cards:
            text = "🎴 **ابتدا باید کارتی داشته باشید!**\n\nلطفاً اول کارت رایگان دریافت کنید."
            keyboard = [
                [InlineKeyboardButton("🎁 دریافت کارت اول", callback_data="daily_claim")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # بررسی فایت‌های فعال
        active_fights = self.db.get_user_active_fights(challenger_id)
        if active_fights:
            text = (
                "⚠️ **شما قبلاً چالش فعالی دارید!**\n\n"
                "لطفاً فایت فعلی را کامل کنید یا منتظر انقضای آن باشید."
            )
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # ایجاد فایت جدید - ابتدا فقط challenger_id
        fight_id = self.db.create_fight(challenger_id, 0, chat_id)  # opponent_id موقتاً 0
        
        challenger_name = query.from_user.first_name
        
        text = (
            f"🥊 **چالش PvP!**\n\n"
            f"🔥 {challenger_name} همه را به مبارزه دعوت می‌کند!\n\n"
            f"آیا جرئت قبول این چالش را دارید؟\n\n"
            f"⚠️ **توجه**: اگر ربات را استارت نکرده‌اید، ابتدا @TelBattleBot را در پیوی استارت کنید!"
        )
        
        keyboard = [
            [InlineKeyboardButton("✊ قبول (نرمال)", callback_data=f"accept_pvp_{fight_id}")],
            [InlineKeyboardButton("🎲 قبول (تصادفی)", callback_data=f"accept_pvp_random_{fight_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ارسال پیام در گروه
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # تایید برای چلنجر
        await query.edit_message_text(
            "✅ **چالش شما ارسال شد!**\n\nمنتظر قبول چالش در گروه باشید...",
            parse_mode='Markdown'
        )


    async def accept_pvp_random_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قبول چالش PvP به صورت تصادفی (انتخاب خودکار کارت‌ها)"""
        query = update.callback_query
        await query.answer()

        fight_id = query.data.split("_")[-1]
        opponent_id = query.from_user.id

        # بررسی اینکه آیا کاربر ربات را استارت کرده یا نه
        user_started = await check_user_started_bot(context, opponent_id)
        if not user_started:
            await query.answer(
                "🤖 ابتدا باید ربات را در پیام خصوصی استارت کنید!\n\n"
                "👆 روی @TelBattleBot کلیک کنید و /start بزنید، سپس دوباره تلاش کنید.",
                show_alert=True
            )
            return

        # بررسی جان‌های حریف (opponent)
        try:
            opponent_player = self.db.get_or_create_player(opponent_id)
            opponent_player = self.game.check_and_reset_hearts(opponent_player)
            if getattr(opponent_player, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, opponent_player)
                return
        except Exception:
            pass

        fight = self.db.get_fight_by_id(fight_id)
        if not fight or fight.status != FightStatus.WAITING_FOR_OPPONENT:
            await query.answer("❌ این چالش معتبر نیست!", show_alert=True)
            return
        if fight.challenger_id == opponent_id:
            await query.answer("❌ نمی‌توانید چالش خودتان را بپذیرید!", show_alert=True)
            return

        # بررسی داشتن کارت
        opponent_cards = self.db.get_player_cards(opponent_id)
        if not opponent_cards:
            await query.answer("❌ ابتدا باید کارتی داشته باشید! در خصوصی /start بزنید.", show_alert=True)
            return

        # تنظیم حریف به صورت اتمی
        claimed = self.db.claim_opponent_if_waiting(fight_id, opponent_id)
        if not claimed:
            await query.answer("❌ Someone already joined or fight is no longer valid.", show_alert=True)
            return

        # تمدید مهلت فایت به مدت 15 دقیقه پس از پذیرش
        try:
            new_expiry = datetime.now() + timedelta(minutes=15)
            self.db.update_fight(fight_id, expires_at=new_expiry.isoformat())
        except Exception as e:
            logger.warning(f"Failed to extend fight {fight_id} expiry: {e}")

        # انتخاب کارت تصادفی برای هر بازیکن از دک
        challenger_cards = self.db.get_player_cards(fight.challenger_id)
        ch_card = random.choice(challenger_cards)
        op_card = random.choice(opponent_cards)

        # بروزرسانی فایت: فقط کارت‌ها تصادفی انتخاب می‌شوند
        updated = self.db.update_fight(fight_id, 
                                     challenger_card_id=ch_card.card_id, 
                                     opponent_card_id=op_card.card_id)
        if not updated:
            await query.answer("❌ خطا در ثبت انتخاب تصادفی. لطفاً دوباره تلاش کنید.", show_alert=True)
            return

        # دریافت نام بازیکنان
        challenger = self.db.get_or_create_player(fight.challenger_id)
        opponent = self.db.get_or_create_player(opponent_id)

        # لینک پیوی ربات
        bot_link = "@TelBattleBot"

        # ارسال پیام قبولی در گروه
        text = (
            f"🎲 **فایت تصادفی تایید شد!**\n\n"
            f"🔥 {challenger.first_name} 🆚 {opponent.first_name}\n\n"
            f"کارت‌ها به صورت تصادفی انتخاب شدند.\n"
            f"هر دو بازیکن در پیام خصوصی ویژگی خود را انتخاب کنید.\n"
            f"👆 **برای انتخاب ویژگی:** {bot_link}\n"
            f"⏰ مهلت: 15 دقیقه"
        )

        reply_markup = None

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        # ارسال پیام خصوصی به challenger
        try:
            await context.bot.send_message(
                chat_id=fight.challenger_id,
                text=f"🎲 **کارت شما به صورت تصادفی انتخاب شد: {ch_card.name}**\n\nلطفاً ویژگی خود را انتخاب کنید:",
                reply_markup=self._create_stat_selection_keyboard(fight_id, ch_card),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to challenger {fight.challenger_id}: {e}")

        # ارسال پیام خصوصی به opponent
        try:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=f"🎲 **کارت شما به صورت تصادفی انتخاب شد: {op_card.name}**\n\nلطفاً ویژگی خود را انتخاب کنید:",
                reply_markup=self._create_stat_selection_keyboard(fight_id, op_card),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to opponent {opponent_id}: {e}")


    async def accept_pvp_fight_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قبول چالش PvP - FIXED"""
        query = update.callback_query
        await query.answer()
        
        
        fight_id = query.data.split("_")[-1]
        opponent_id = query.from_user.id

        # بررسی اینکه آیا کاربر ربات را استارت کرده یا نه
        user_started = await check_user_started_bot(context, opponent_id)
        if not user_started:
            await query.answer(
                "🤖 ابتدا باید ربات را در پیام خصوصی استارت کنید!\n\n"
                "👆 روی @TelBattleBot کلیک کنید و /start بزنید، سپس دوباره تلاش کنید.",
                show_alert=True
            )
            return

        # بررسی جان‌های حریف (opponent) - از hearts استفاده می‌کنیم
        try:
            opponent_player = self.db.get_or_create_player(opponent_id)
            opponent_player = self.game.check_and_reset_hearts(opponent_player)
            if getattr(opponent_player, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, opponent_player)
                return
        except Exception:
            pass
        
        logger.info(f"Accept PvP - Data: {query.data}, User: {opponent_id}")
        
        # دریافت فایت
        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            await query.answer("❌ چالش یافت نشد یا منقضی شده!", show_alert=True)
            return
        
        # بررسی اینکه challenger خودش نپذیرد
        if fight.challenger_id == opponent_id:
            await query.answer("❌ نمی‌توانید چالش خودتان را بپذیرید!", show_alert=True)
            return
        
        # بررسی داشتن کارت
        opponent_cards = self.db.get_player_cards(opponent_id)
        if not opponent_cards:
            await query.answer("❌ ابتدا کارتی باید داشته باشید! در خصوصی /start بزنید.", show_alert=True)
            return
        
        # بررسی وضعیت فایت
        if fight.status != FightStatus.WAITING_FOR_OPPONENT:
            await query.answer("❌ این چالش دیگر قابل قبول نیست!", show_alert=True)
            return
        
        # بروزرسانی اتمی جهت جلوگیری از شرایط رقابتی
        claimed = self.db.claim_opponent_if_waiting(fight_id, opponent_id)
        if not claimed:
            await query.answer("❌ Someone already joined or fight is no longer valid.", show_alert=True)
            return
        # تمدید مهلت فایت به مدت 15 دقیقه پس از پذیرش
        try:
            new_expiry = datetime.now() + timedelta(minutes=15)
            self.db.update_fight(fight_id, expires_at=new_expiry.isoformat())
        except Exception as e:
            logger.warning(f"Failed to extend fight {fight_id} expiry: {e}")
        # Log fight state after opponent claimed for debugging
        try:
            fstate = self.db.get_fight_by_id(fight_id)
            logger.info(f"Fight {fight_id} after claim: challenger={fstate.challenger_id}, opponent={fstate.opponent_id}, challenger_card={fstate.challenger_card_id}, opponent_card={fstate.opponent_card_id}, status={fstate.status}")
        except Exception:
            logger.warning(f"Could not fetch fight state for {fight_id} after claim")
        
        # دریافت نام بازیکنان
        challenger = self.db.get_or_create_player(fight.challenger_id)
        opponent = self.db.get_or_create_player(opponent_id)
        
        # لینک پیوی ربات
        bot_link = "@TelBattleBot"
        
        # ارسال پیام قبولی در گروه
        text = (
            f"⚔️ **فایت تایید شد!**\n\n"
            f"🔥 {challenger.first_name} 🆚 {opponent.first_name}\n\n"
            f"هر دو بازیکن در پیام خصوصی کارت و ویژگی خود را انتخاب کنید.\n"
            f"👆 **برای انتخاب کارت:** {bot_link}\n"
            f"⏰ مهلت: 15 دقیقه"
        )
        
        reply_markup = None
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        # ارسال پیام خصوصی به challenger
        try:
            await context.bot.send_message(
                chat_id=fight.challenger_id,
                text=f"✅ **{opponent.first_name} چالش شما را پذیرفت!**\n\n📋 **کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:",
                reply_markup=self._create_pvp_card_selection_keyboard(fight_id, fight.challenger_id, category="menu", page=1),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to challenger {fight.challenger_id}: {e}")
        
        # ارسال پیام خصوصی به opponent
        try:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=f"✅ **شما چالش {challenger.first_name} را پذیرفتید!**\n\n📋 **کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:",
                reply_markup=self._create_pvp_card_selection_keyboard(fight_id, opponent_id, category="menu", page=1),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to opponent {opponent_id}: {e}")




    async def _announce_pvp_result(self, context, result: dict):
        """اعلام نتیجه فایت PvP"""
        if not result.get("success"):
            return

        fight_id = result.get("fight_id")
        winner = result.get("winner")
        loser = result.get("loser")
        challenger = result.get("challenger")
        opponent = result.get("opponent")
        result_type = result.get("result_type", "tie")

        # دریافت fight برای chat_id
        fight = self.db.get_fight_by_id(fight_id)
        chat_id = fight.chat_id if fight else None

        stat_names = {"power": "💪 قدرت", "speed": "⚡ سرعت", "iq": "🧠 هوش", "popularity": "❤️ محبوبیت"}

        if result_type == "tie":
            text = (
                f"🤝 **مساوی!**\n\n"
                f"هیچ‌کدام برنده نشدند.\n\n"
                f"Challenger: {stat_names.get(challenger['stat'], challenger['stat'])} = {challenger['stat_value']}\n"
                f"Opponent: {stat_names.get(opponent['stat'], opponent['stat'])} = {opponent['stat_value']}"
            )
        else:
            winner_name = winner['card'].name if winner else "?"
            loser_name = loser['card'].name if loser else "?"
            text = (
                f"🎉 **{winner_name} برنده شد!**\n\n"
                f"⭐ +{winner.get('score_gained', 0)} امتیاز\n"
                f"💔 بازنده: -{loser.get('hearts_lost', 0)} جان\n\n"
                f"📊 جزئیات:\n"
                f"  برنده: {stat_names.get(winner['stat'], winner['stat'])} = {winner['stat_value']}\n"
                f"  بازنده: {stat_names.get(loser['stat'], loser['stat'])} = {loser['stat_value']}"
            )

            # XP info
            if winner.get('xp_gained'):
                text += f"\n\n⭐ +{winner['xp_gained']} XP برنده"
            if loser.get('xp_gained'):
                text += f" • +{loser['xp_gained']} XP بازنده"

            # Level up
            if challenger.get('level_up'):
                text += f"\n⬆️ Level Up! → {challenger['new_level']}"
            if opponent.get('level_up'):
                text += f"\n⬆️ Level Up! → {opponent['new_level']}"

        keyboard = [[InlineKeyboardButton("🥊 چالش جدید", callback_data="request_pvp_fight")]]

        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to announce PvP result: {e}")

        # پاک کردن فایت
        try:
            self.db.delete_fight(fight_id)
        except Exception:
            pass

    def _create_pvp_card_selection_keyboard(self, fight_id: str, user_id: int, category: str = "menu", page: int = 1):
        """ایجاد کیبورد انتخاب کارت برای PvP"""
        keyboard = []
        if category == "menu":
            rarity_counts = self.db.get_rarity_counts(user_id) if hasattr(self.db, 'get_rarity_counts') else {}
            keyboard.append([InlineKeyboardButton(f"🟡 Legendary ({rarity_counts.get('legend', 0)})", callback_data=f"pvp_cards_{fight_id}_legend_1")])
            keyboard.append([InlineKeyboardButton(f"🟣 Epic ({rarity_counts.get('epic', 0)})", callback_data=f"pvp_cards_{fight_id}_epic_1")])
            keyboard.append([InlineKeyboardButton(f"🟢 Normal ({rarity_counts.get('normal', 0)})", callback_data=f"pvp_cards_{fight_id}_normal_1")])
        else:
            rarity_map = {"legend": CardRarity.LEGEND, "epic": CardRarity.EPIC, "normal": CardRarity.NORMAL, "rare": CardRarity.RARE}
            rarity = rarity_map.get(category)
            cards, total_count = self.db.get_player_cards_by_rarity(user_id, rarity=rarity, page=page, per_page=6)
            rarity_colors = {CardRarity.NORMAL: "🟢", CardRarity.EPIC: "🟣", CardRarity.LEGEND: "🟡", CardRarity.RARE: "🔵"}
            for card in cards:
                color = rarity_colors.get(card.rarity, "⚪")
                stats = f"💪{card.power} ⚡{card.speed} 🧠{card.iq} ❤️{card.popularity}"
                keyboard.append([InlineKeyboardButton(f"{color} {card.name} ({stats})", callback_data=f"pvp_card_{fight_id}_{card.card_id}")])
            total_pages = (total_count + 5) // 6
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("« قبلی", callback_data=f"pvp_cards_{fight_id}_{category}_{page-1}"))
            nav_buttons.append(InlineKeyboardButton("🏠 منو", callback_data=f"pvp_cards_{fight_id}_menu_1"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("بعدی »", callback_data=f"pvp_cards_{fight_id}_{category}_{page+1}"))
            if nav_buttons:
                keyboard.append(nav_buttons)
        return InlineKeyboardMarkup(keyboard)

    async def pvp_cards_navigation_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation بین دسته‌بندی‌ها و صفحات کارت‌ها"""
        query = update.callback_query
        await query.answer()
        
        # pvp_cards_{fight_id}_{category}_{page}
        parts = query.data.split("_")
        fight_id = parts[2]
        category = parts[3]
        page = int(parts[4])
        user_id = query.from_user.id
        
        # ساخت کیبورد جدید
        keyboard = self._create_pvp_card_selection_keyboard(fight_id, user_id, category=category, page=page)
        
        # متن پیام
        if category == "menu":
            text = "📋 **کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
        else:
            category_names = {
                "favorite": "⭐ مورد علاقه",
                "legend": "🟡 Legendary",
                "epic": "🟣 Epic",
                "normal": "🟢 Normal"
            }
            category_name = category_names.get(category, category)
            
            if category == "favorite":
                cards, total_count = self.db.get_favorite_cards(user_id, page=page, per_page=6)
            else:
                rarity_map = {
                    "legend": CardRarity.LEGEND,
                    "epic": CardRarity.EPIC,
                    "normal": CardRarity.NORMAL
                }
                rarity = rarity_map.get(category)
                cards, total_count = self.db.get_player_cards_by_rarity(user_id, rarity=rarity, page=page, per_page=6)
            
            total_pages = (total_count + 5) // 6
            text = f"📋 **{category_name}** (صفحه {page}/{total_pages})\n\nلطفاً کارت خود را انتخاب کنید:"
        
        try:
            await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception:
            pass
    

    async def pvp_card_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب کارت در فایت PvP - FIXED"""
        query = update.callback_query
        await query.answer()

        
        parts = query.data.split("_")
        fight_id = parts[2]
        card_id = parts[3]
        user_id = query.from_user.id
        # Prevent users with 0 hearts from participating
        try:
            p = self.db.get_or_create_player(user_id)
            p = self.game.check_and_reset_hearts(p)
            if getattr(p, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, p)
                return
        except Exception:
            pass
        
        # دریافت فایت
        fight = self.db.get_fight_by_id(fight_id)
        logger.info(f"PvP Card Select - Data: {query.data}, User: {user_id}")
        if fight:
            logger.info(f"Fight before update: challenger={fight.challenger_id}, opponent={fight.opponent_id}")
        else:
            logger.warning(f"Fight {fight_id} not found at card select!")    
            
        if not fight:
            text = "❌ فایت یافت نشد!"
            await query.edit_message_text(text)
            return
        
        # تعیین اینکه کاربر challenger است یا opponent
        if user_id == fight.challenger_id:
            field_name = "challenger_card_id"
        elif user_id == fight.opponent_id:
            field_name = "opponent_card_id"
        else:
            await query.answer("❌ شما بخشی از این فایت نیستید!", show_alert=True)
            return
        
        # بروزرسانی انتخاب کارت
        update_data = {field_name: card_id}
        
        # دریافت وضعیت فعلی فایت برای تعیین وضعیت میانی یا نهایی
        current_fight = self.db.get_fight_by_id(fight_id)
        
        # اگر اولین انتخاب کارت توسط چلنجر است و حریف هنوز کارت ندارد
        if user_id == fight.challenger_id and not current_fight.opponent_card_id:
            update_data["status"] = FightStatus.CHALLENGER_CARD_SELECTED
        # اگر اولین انتخاب کارت توسط حریف است و چلنجر هنوز کارت ندارد
        if user_id == fight.opponent_id and not current_fight.challenger_card_id:
            update_data["status"] = FightStatus.OPPONENT_CARD_SELECTED
        
        # اگر با این انتخاب هر دو کارت موجود می‌شوند، وضعیت را به BOTH_CARDS_SELECTED ارتقا بده
        if user_id == fight.challenger_id and current_fight.opponent_card_id:
            update_data["status"] = FightStatus.BOTH_CARDS_SELECTED
        elif user_id == fight.opponent_id and current_fight.challenger_card_id:
            update_data["status"] = FightStatus.BOTH_CARDS_SELECTED
        
        updated_ok = self.db.update_fight(fight_id, **update_data)
        if not updated_ok:
            logger.error(f"Failed to update fight {fight_id} with {update_data}")
            try:
                await query.answer("❌ خطا در ثبت انتخاب. لطفاً دوباره تلاش کنید.", show_alert=True)
            except Exception:
                pass
            return
        
        # دریافت کارت انتخاب شده
        selected_card = self.db.get_card_by_id(card_id)
        
        # افزایش usage_count
        self.db.increment_card_usage(user_id, card_id)
        
        # بازخورد سریع برای کاربر
        try:
            await query.answer("✅ Card selected!")
        except Exception:
            pass
        
        text = (
            f"✅ **کارت انتخاب شد!**\n\n"
            f"🎴 {selected_card.name}\n\n"
            f"حالا ویژگی مورد نظر برای فایت را انتخاب کنید:"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"💪 قدرت ({selected_card.power})", callback_data=f"pvp_stat_{fight_id}_power")],
            [InlineKeyboardButton(f"⚡ سرعت ({selected_card.speed})", callback_data=f"pvp_stat_{fight_id}_speed")],
            [InlineKeyboardButton(f"🧠 آی‌کیو ({selected_card.iq})", callback_data=f"pvp_stat_{fight_id}_iq")],
            [InlineKeyboardButton(f"❤️ محبوبیت ({selected_card.popularity})", callback_data=f"pvp_stat_{fight_id}_popularity")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def pvp_stat_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب ویژگی در فایت PvP - COMPLETELY FIXED"""
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split("_")
        fight_id = parts[2]
        stat = parts[3]
        user_id = query.from_user.id
        
        logger.info(f"PvP Stat Select - Fight: {fight_id}, User: {user_id}, Stat: {stat}")
        # Prevent users with 0 hearts from selecting stats
        try:
            p = self.db.get_or_create_player(user_id)
            p = self.game.check_and_reset_hearts(p)
            if getattr(p, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, p)
                return
        except Exception:
            pass
        
        # دریافت فایت
        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            text = "❌ فایت یافت نشد!"
            await query.edit_message_text(text)
            logger.error(f"Fight {fight_id} not found")
            return
        
        # بررسی اولیه opponent_id
        if self.db.is_unclaimed(fight):
            logger.error(f"Fight {fight_id} has invalid opponent_id=0")
            await query.answer("❌ خطا: حریف معتبر نیست!", show_alert=True)
            return
        
        # تعیین اینکه کاربر challenger است یا opponent
        if user_id == fight.challenger_id:
            field_name = "challenger_stat"
            user_role = "challenger"
        elif user_id == fight.opponent_id:
            field_name = "opponent_stat"
            user_role = "opponent"
        else:
            await query.answer("❌ شما بخشی از این فایت نیستید!", show_alert=True)
            logger.warning(f"User {user_id} tried to select stat for fight {fight_id} but is not participant")
            return
        
        logger.info(f"User {user_id} is {user_role} selecting stat {stat}")
        
        # بروزرسانی انتخاب ویژگی
        update_data = {field_name: stat}
        success = self.db.update_fight(fight_id, **update_data)
        
        if not success:
            logger.error(f"Failed to update fight {fight_id} with {field_name}={stat}")
            await query.answer("❌ خطا در ذخیره انتخاب!", show_alert=True)
            return
        
        # دریافت وضعیت به‌روزشده
        updated_fight = self.db.get_fight_by_id(fight_id)
        if not updated_fight:
            logger.error(f"Fight {fight_id} disappeared after update")
            await query.answer("❌ خطای سیستمی!", show_alert=True)
            return
        
        # نام‌های ویژگی برای نمایش
        stat_names = {
            "power": "💪 قدرت",
            "speed": "⚡ سرعت",
            "iq": "🧠 آی‌کیو",
            "popularity": "❤️ محبوبیت"
        }
        
        selected_stat_name = stat_names.get(stat, f"ویژگی {stat}")
        
        logger.info(f"Fight {fight_id} status after update: "
                    f"challenger_stat={updated_fight.challenger_stat}, "
                    f"opponent_stat={updated_fight.opponent_stat}")
        
        # بررسی اینکه آیا هر دو بازیکن انتخاب کرده‌اند
        if updated_fight.challenger_stat and updated_fight.opponent_stat:
            # بازخورد سریع
            try:
                await query.answer("⚔️ Both stats selected! Resolving fight...")
            except Exception:
                pass
            # هر دو انتخاب کرده‌اند - باید فایت حل شود
            logger.info(f"Both players selected stats for fight {fight_id} - resolving")
            
            # اعلام شروع محاسبه
            text = f"✅ **{selected_stat_name} انتخاب شد!**\n\n⚔️ درحال محاسبه نتیجه فایت..."
            await query.edit_message_text(text, parse_mode='Markdown')
            
            # حل فایت
            try:
                result = self.game.resolve_pvp_fight(fight_id)
                
                if result.get("success"):
                    logger.info(f"Fight {fight_id} resolved successfully")
                    await self._announce_pvp_result(context, result)
                else:
                    error_msg = result.get("error", "خطای نامشخص در حل فایت")
                    logger.error(f"Fight {fight_id} resolution failed: {error_msg}")
                    
                    # اطلاع به کاربران در صورت خطا
                    if updated_fight.chat_id:
                        error_text = (
                            f"❌ **خطا در فایت!**\n\n"
                            f"متاسفانه فایت به دلیل خطای زیر لغو شد:\n"
                            f"`{error_msg}`\n\n"
                            f"لطفاً دوباره تلاش کنید."
                        )
                        try:
                            await context.bot.send_message(
                                chat_id=updated_fight.chat_id,
                                text=error_text,
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            logger.error(f"Failed to send error message to chat {updated_fight.chat_id}: {e}")
                    
                    # حذف فایت ناقص از دیتابیس
                    self.db.delete_fight(fight_id)
                    
            except Exception as e:
                logger.error(f"Exception in fight {fight_id} resolution: {e}", exc_info=True)
                
                # اطلاع به کاربران در صورت خطای سیستمی
                if updated_fight.chat_id:
                    system_error_text = (
                        f"💥 **خطای سیستمی!**\n\n"
                        f"متاسفانه فایت به دلیل خطای سیستمی لغو شد.\n"
                        f"لطفاً چند دقیقه دیگر دوباره تلاش کنید."
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=updated_fight.chat_id,
                            text=system_error_text,
                            parse_mode='Markdown'
                        )
                    except Exception as send_error:
                        logger.error(f"Failed to send system error message: {send_error}")
                
                # حذف فایت از دیتابیس
                self.db.delete_fight(fight_id)
        
        else:
            # فقط یکی انتخاب کرده - منتظر دیگری
            logger.info(f"Fight {fight_id}: Only {user_role} selected stat, waiting for other player")
            
            try:
                await query.answer("✅ Stat selected! Waiting for opponent ⏳")
            except Exception:
                pass

            text = (
                f"✅ **{selected_stat_name} انتخاب شد!**\n\n"
                f"⏳ منتظر انتخاب حریف...\n\n"
                f"نتیجه فایت در گروه اعلام خواهد شد."
            )
            await query.edit_message_text(text, parse_mode='Markdown')


    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت دستور /leaderboard"""
        # تشخیص نوع چت
        chat_type = update.effective_chat.type
        is_group = chat_type in ["group", "supergroup"]
        
        if is_group:
            # منوی لیدربورد گروه
            text = "🏆 **Leaderboard گروه**\n\nبازه زمانی را انتخاب کنید:"
            keyboard = [
                [InlineKeyboardButton("📊 هفتگی", callback_data="lb_group_weekly_10")],
                [InlineKeyboardButton("📊 ماهانه", callback_data="lb_group_monthly_10")],
                [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_group_all_10")]
            ]
        else:
            # منوی لیدربورد جهانی
            text = "🏆 **Leaderboard جهانی**\n\nبازه زمانی را انتخاب کنید:"
            keyboard = [
                [InlineKeyboardButton("📊 هفتگی", callback_data="lb_global_weekly_10")],
                [InlineKeyboardButton("📊 ماهانه", callback_data="lb_global_monthly_10")],
                [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_global_all_10")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def fight_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور شروع چالش PvP در گروه"""
        # بررسی مجوز دستور
        if not self._is_command_allowed_in_chat("fight", update.effective_chat.type):
            await update.message.reply_text(
                "🚫 این دستور فقط در گروه‌ها قابل استفاده است.\n"
                "🥊 برای چالش PvP، ربات را به گروه اضافه کنید."
            )
            return

        challenger_id = update.effective_user.id
        chat_id = update.effective_chat.id

        # بررسی جان‌های بازیکن - اگر تمام شده باشد، نمی‌تواند فایت بسازد
        try:
            challenger_player = self.db.get_or_create_player(challenger_id)
            challenger_player = self.game.check_and_reset_hearts(challenger_player)
            if getattr(challenger_player, 'hearts', 5) <= 0:
                time_remaining = self.game.get_heart_reset_time_remaining(challenger_player)
                if time_remaining:
                    time_str = self.game.format_time_remaining(time_remaining)
                    message = f"💀 جان شما تمام شده!\n\n⏰ تا {time_str} دیگر نمی‌توانید بازی کنید.\n\n💝 هر ۲۴ ساعت یکبار ۵ جان شارژ می‌شود."
                else:
                    message = "💀 جان شما تمام شده! لطفاً چند لحظه صبر کنید تا جان‌ها ریست شوند."
                await update.message.reply_text(message)
                return
        except Exception:
            pass

        player_cards = self.db.get_player_cards(challenger_id)
        if not player_cards:
            await update.message.reply_text("🎴 ابتدا باید کارتی داشته باشید! در چت خصوصی ربات /start بزنید.")
            return

        active_fights = self.db.get_user_active_fights(challenger_id)
        if active_fights:
            await update.message.reply_text("⚠️ شما قبلاً یک چالش فعال دارید.")
            return

        fight_id = self.db.create_fight(challenger_id, 0, chat_id)
        challenger_name = update.effective_user.first_name
        
        text = (
            f"🥊 **چالش PvP!**\n\n"
            f"🔥 {challenger_name} همه را به مبارزه دعوت می‌کند!\n\n"
            f"آیا جرئت قبول این چالش را دارید؟\n\n"
            f"⚠️ **توجه**: اگر ربات را استارت نکرده‌اید، ابتدا @TelBattleBot را در پیوی استارت کنید!"
        )
        keyboard = [
            [InlineKeyboardButton("✊ قبول (نرمال)", callback_data=f"accept_pvp_{fight_id}")],
            [InlineKeyboardButton("🎲 قبول (تصادفی)", callback_data=f"accept_pvp_random_{fight_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    # ==================== PVP HANDLERS - FIXED ====================


    async def daily_claim_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت دریافت کارت روزانه"""
        query = update.callback_query
        await query.answer()
        
        # Check panel expiration
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        user_id = query.from_user.id
        success, card, error = self.game.claim_daily_card(user_id)
        
        if success and card:
            rarity_colors = {
                CardRarity.NORMAL: "🟢",
                CardRarity.EPIC: "🟣",
                CardRarity.LEGEND: "🟡"
            }
            color = rarity_colors[card.rarity]
            
            # ارسال تصویر کارت با یک دیالوگ کوتاه
            claim_dialog = get_victory_dialog(card.name)
            image_sent = await send_card_image_safely(query.message, card.name, self.config, f"🎉 {card.name}\n\n“{claim_dialog}”")
            
            # متن اطلاعات کارت
            text = (
                f"🎉 **کارت روزانه دریافت شد!**\n\n"
                f"{color} **{card.name}** ({card.rarity.value.title()})\n\n"
                f"📊 **آمار کارت:**\n"
                f"💪 قدرت: {card.power}\n"
                f"⚡ سرعت: {card.speed}\n"
                f"🧠 آی‌کیو: {card.iq}\n"
                f"❤️ محبوبیت: {card.popularity}\n"
                f"🎯 مجموع: {card.get_total_stats()}\n\n"
                f"✨ **ابیلیتی‌ها:**\n"
            )
            
            for ability in card.abilities:
                text += f"• {ability}\n"
            
            text += f"\n🕐 کلیم بعدی: {self.game.CLAIM_COOLDOWN_HOURS} ساعت دیگر"
            
            if not image_sent:
                text = f"🎴 (تصویر در دسترس نیست)\n\n" + text
            
            keyboard = [
                [InlineKeyboardButton("🎴 مشاهده کارت‌ها", callback_data="my_cards")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        else:
            text = f"⚠ **خطا در دریافت کارت**\n\n{error if error else 'خطای نامشخص!'}"
            
            keyboard = [
                [InlineKeyboardButton("🎴 مشاهده کارت‌ها", callback_data="my_cards")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def my_cards_navigation_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation بین دسته‌بندی‌ها و صفحات کارت‌های من"""
        query = update.callback_query
        await query.answer()
        
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        # my_cards_nav_{category}_{page}
        parts = query.data.split("_")
        category = parts[3]
        page = int(parts[4])
        user_id = query.from_user.id
        
        # ساخت کیبورد جدید
        keyboard = self._create_my_cards_keyboard(user_id, category=category, page=page)
        
        # متن پیام
        if category == "menu":
            cards = self.db.get_player_cards(user_id)
            text = f"🎴 **کارت‌های شما ({len(cards)} کارت)**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
        else:
            category_names = {
                "favorite": "⭐ مورد علاقه",
                "legend": "🟡 Legendary",
                "epic": "🟣 Epic",
                "normal": "🟢 Normal"
            }
            category_name = category_names.get(category, category)
            
            if category == "favorite":
                cards, total_count = self.db.get_favorite_cards(user_id, page=page, per_page=6)
            else:
                rarity_map = {
                    "legend": CardRarity.LEGEND,
                    "epic": CardRarity.EPIC,
                    "normal": CardRarity.NORMAL
                }
                rarity = rarity_map.get(category)
                cards, total_count = self.db.get_player_cards_by_rarity(user_id, rarity=rarity, page=page, per_page=6)
            
            total_pages = (total_count + 5) // 6
            text = f"🎴 **{category_name}** (صفحه {page}/{total_pages})\n\nلطفاً کارت را انتخاب کنید:"
        
        try:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception:
            pass


    async def request_pvp_fight_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """درخواست فایت PvP"""
        query = update.callback_query
        await query.answer()
        
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        challenger_id = query.from_user.id
        chat_id = query.message.chat_id

        # بررسی جان‌های بازیکن - اگر تمام شده باشد، نمی‌تواند فایت بسازد
        try:
            challenger_player = self.db.get_or_create_player(challenger_id)
            challenger_player = self.game.check_and_reset_hearts(challenger_player)
            if getattr(challenger_player, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, challenger_player)
                return
        except Exception:
            pass
        
        # بررسی نوع چت - باید گروه باشد
        if query.message.chat.type == 'private':
            text = "🚫 فایت PvP فقط در گروه‌ها امکان‌پذیر است!\n\nلطفاً این ربات را به گروه اضافه کنید."
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            return
        
        # بررسی داشتن کارت
        player_cards = self.db.get_player_cards(challenger_id)
        if not player_cards:
            text = "🎴 **ابتدا باید کارتی داشته باشید!**\n\nلطفاً اول کارت رایگان دریافت کنید."
            keyboard = [
                [InlineKeyboardButton("🎁 دریافت کارت اول", callback_data="daily_claim")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # بررسی فایت‌های فعال
        active_fights = self.db.get_user_active_fights(challenger_id)
        if active_fights:
            text = (
                "⚠️ **شما قبلاً چالش فعالی دارید!**\n\n"
                "لطفاً فایت فعلی را کامل کنید یا منتظر انقضای آن باشید."
            )
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # ایجاد فایت جدید - ابتدا فقط challenger_id
        fight_id = self.db.create_fight(challenger_id, 0, chat_id)  # opponent_id موقتاً 0
        
        challenger_name = query.from_user.first_name
        
        text = (
            f"🥊 **چالش PvP!**\n\n"
            f"🔥 {challenger_name} همه را به مبارزه دعوت می‌کند!\n\n"
            f"آیا جرئت قبول این چالش را دارید؟\n\n"
            f"⚠️ **توجه**: اگر ربات را استارت نکرده‌اید، ابتدا @TelBattleBot را در پیوی استارت کنید!"
        )
        
        keyboard = [
            [InlineKeyboardButton("✊ قبول (نرمال)", callback_data=f"accept_pvp_{fight_id}")],
            [InlineKeyboardButton("🎲 قبول (تصادفی)", callback_data=f"accept_pvp_random_{fight_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ارسال پیام در گروه
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # تایید برای چلنجر
        await query.edit_message_text(
            "✅ **چالش شما ارسال شد!**\n\nمنتظر قبول چالش در گروه باشید...",
            parse_mode='Markdown'
        )


    async def accept_pvp_random_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قبول چالش PvP به صورت تصادفی (انتخاب خودکار کارت‌ها)"""
        query = update.callback_query
        await query.answer()

        fight_id = query.data.split("_")[-1]
        opponent_id = query.from_user.id

        # بررسی اینکه آیا کاربر ربات را استارت کرده یا نه
        user_started = await check_user_started_bot(context, opponent_id)
        if not user_started:
            await query.answer(
                "🤖 ابتدا باید ربات را در پیام خصوصی استارت کنید!\n\n"
                "👆 روی @TelBattleBot کلیک کنید و /start بزنید، سپس دوباره تلاش کنید.",
                show_alert=True
            )
            return

        # بررسی جان‌های حریف (opponent)
        try:
            opponent_player = self.db.get_or_create_player(opponent_id)
            opponent_player = self.game.check_and_reset_hearts(opponent_player)
            if getattr(opponent_player, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, opponent_player)
                return
        except Exception:
            pass

        fight = self.db.get_fight_by_id(fight_id)
        if not fight or fight.status != FightStatus.WAITING_FOR_OPPONENT:
            await query.answer("❌ این چالش معتبر نیست!", show_alert=True)
            return
        if fight.challenger_id == opponent_id:
            await query.answer("❌ نمی‌توانید چالش خودتان را بپذیرید!", show_alert=True)
            return

        # بررسی داشتن کارت
        opponent_cards = self.db.get_player_cards(opponent_id)
        if not opponent_cards:
            await query.answer("❌ ابتدا باید کارتی داشته باشید! در خصوصی /start بزنید.", show_alert=True)
            return

        # تنظیم حریف به صورت اتمی
        claimed = self.db.claim_opponent_if_waiting(fight_id, opponent_id)
        if not claimed:
            await query.answer("❌ Someone already joined or fight is no longer valid.", show_alert=True)
            return

        # تمدید مهلت فایت به مدت 15 دقیقه پس از پذیرش
        try:
            new_expiry = datetime.now() + timedelta(minutes=15)
            self.db.update_fight(fight_id, expires_at=new_expiry.isoformat())
        except Exception as e:
            logger.warning(f"Failed to extend fight {fight_id} expiry: {e}")

        # انتخاب کارت تصادفی برای هر بازیکن از دک
        challenger_cards = self.db.get_player_cards(fight.challenger_id)
        ch_card = random.choice(challenger_cards)
        op_card = random.choice(opponent_cards)

        # بروزرسانی فایت: فقط کارت‌ها تصادفی انتخاب می‌شوند
        updated = self.db.update_fight(fight_id, 
                                     challenger_card_id=ch_card.card_id, 
                                     opponent_card_id=op_card.card_id)
        if not updated:
            await query.answer("❌ خطا در ثبت انتخاب تصادفی. لطفاً دوباره تلاش کنید.", show_alert=True)
            return

        # دریافت نام بازیکنان
        challenger = self.db.get_or_create_player(fight.challenger_id)
        opponent = self.db.get_or_create_player(opponent_id)

        # لینک پیوی ربات
        bot_link = "@TelBattleBot"

        # ارسال پیام قبولی در گروه
        text = (
            f"🎲 **فایت تصادفی تایید شد!**\n\n"
            f"🔥 {challenger.first_name} 🆚 {opponent.first_name}\n\n"
            f"کارت‌ها به صورت تصادفی انتخاب شدند.\n"
            f"هر دو بازیکن در پیام خصوصی ویژگی خود را انتخاب کنید.\n"
            f"👆 **برای انتخاب ویژگی:** {bot_link}\n"
            f"⏰ مهلت: 15 دقیقه"
        )

        reply_markup = None

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        # ارسال پیام خصوصی به challenger
        try:
            await context.bot.send_message(
                chat_id=fight.challenger_id,
                text=f"🎲 **کارت شما به صورت تصادفی انتخاب شد: {ch_card.name}**\n\nلطفاً ویژگی خود را انتخاب کنید:",
                reply_markup=self._create_stat_selection_keyboard(fight_id, ch_card),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to challenger {fight.challenger_id}: {e}")

        # ارسال پیام خصوصی به opponent
        try:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=f"🎲 **کارت شما به صورت تصادفی انتخاب شد: {op_card.name}**\n\nلطفاً ویژگی خود را انتخاب کنید:",
                reply_markup=self._create_stat_selection_keyboard(fight_id, op_card),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to opponent {opponent_id}: {e}")


    async def accept_pvp_fight_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قبول چالش PvP - FIXED"""
        query = update.callback_query
        await query.answer()
        
        
        fight_id = query.data.split("_")[-1]
        opponent_id = query.from_user.id

        # بررسی اینکه آیا کاربر ربات را استارت کرده یا نه
        user_started = await check_user_started_bot(context, opponent_id)
        if not user_started:
            await query.answer(
                "🤖 ابتدا باید ربات را در پیام خصوصی استارت کنید!\n\n"
                "👆 روی @TelBattleBot کلیک کنید و /start بزنید، سپس دوباره تلاش کنید.",
                show_alert=True
            )
            return

        # بررسی جان‌های حریف (opponent) - از hearts استفاده می‌کنیم
        try:
            opponent_player = self.db.get_or_create_player(opponent_id)
            opponent_player = self.game.check_and_reset_hearts(opponent_player)
            if getattr(opponent_player, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, opponent_player)
                return
        except Exception:
            pass
        
        logger.info(f"Accept PvP - Data: {query.data}, User: {opponent_id}")
        
        # دریافت فایت
        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            await query.answer("❌ چالش یافت نشد یا منقضی شده!", show_alert=True)
            return
        
        # بررسی اینکه challenger خودش نپذیرد
        if fight.challenger_id == opponent_id:
            await query.answer("❌ نمی‌توانید چالش خودتان را بپذیرید!", show_alert=True)
            return
        
        # بررسی داشتن کارت
        opponent_cards = self.db.get_player_cards(opponent_id)
        if not opponent_cards:
            await query.answer("❌ ابتدا کارتی باید داشته باشید! در خصوصی /start بزنید.", show_alert=True)
            return
        
        # بررسی وضعیت فایت
        if fight.status != FightStatus.WAITING_FOR_OPPONENT:
            await query.answer("❌ این چالش دیگر قابل قبول نیست!", show_alert=True)
            return
        
        # بروزرسانی اتمی جهت جلوگیری از شرایط رقابتی
        claimed = self.db.claim_opponent_if_waiting(fight_id, opponent_id)
        if not claimed:
            await query.answer("❌ Someone already joined or fight is no longer valid.", show_alert=True)
            return
        # تمدید مهلت فایت به مدت 15 دقیقه پس از پذیرش
        try:
            new_expiry = datetime.now() + timedelta(minutes=15)
            self.db.update_fight(fight_id, expires_at=new_expiry.isoformat())
        except Exception as e:
            logger.warning(f"Failed to extend fight {fight_id} expiry: {e}")
        # Log fight state after opponent claimed for debugging
        try:
            fstate = self.db.get_fight_by_id(fight_id)
            logger.info(f"Fight {fight_id} after claim: challenger={fstate.challenger_id}, opponent={fstate.opponent_id}, challenger_card={fstate.challenger_card_id}, opponent_card={fstate.opponent_card_id}, status={fstate.status}")
        except Exception:
            logger.warning(f"Could not fetch fight state for {fight_id} after claim")
        
        # دریافت نام بازیکنان
        challenger = self.db.get_or_create_player(fight.challenger_id)
        opponent = self.db.get_or_create_player(opponent_id)
        
        # لینک پیوی ربات
        bot_link = "@TelBattleBot"
        
        # ارسال پیام قبولی در گروه
        text = (
            f"⚔️ **فایت تایید شد!**\n\n"
            f"🔥 {challenger.first_name} 🆚 {opponent.first_name}\n\n"
            f"هر دو بازیکن در پیام خصوصی کارت و ویژگی خود را انتخاب کنید.\n"
            f"👆 **برای انتخاب کارت:** {bot_link}\n"
            f"⏰ مهلت: 15 دقیقه"
        )
        
        reply_markup = None
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        # ارسال پیام خصوصی به challenger
        try:
            await context.bot.send_message(
                chat_id=fight.challenger_id,
                text=f"✅ **{opponent.first_name} چالش شما را پذیرفت!**\n\n📋 **کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:",
                reply_markup=self._create_pvp_card_selection_keyboard(fight_id, fight.challenger_id, category="menu", page=1),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to challenger {fight.challenger_id}: {e}")
        
        # ارسال پیام خصوصی به opponent
        try:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=f"✅ **شما چالش {challenger.first_name} را پذیرفتید!**\n\n📋 **کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:",
                reply_markup=self._create_pvp_card_selection_keyboard(fight_id, opponent_id, category="menu", page=1),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send private message to opponent {opponent_id}: {e}")


    async def pvp_cards_navigation_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation بین دسته‌بندی‌ها و صفحات کارت‌ها"""
        query = update.callback_query
        await query.answer()
        
        # pvp_cards_{fight_id}_{category}_{page}
        parts = query.data.split("_")
        fight_id = parts[2]
        category = parts[3]
        page = int(parts[4])
        user_id = query.from_user.id
        
        # ساخت کیبورد جدید
        keyboard = self._create_pvp_card_selection_keyboard(fight_id, user_id, category=category, page=page)
        
        # متن پیام
        if category == "menu":
            text = "📋 **کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
        else:
            category_names = {
                "favorite": "⭐ مورد علاقه",
                "legend": "🟡 Legendary",
                "epic": "🟣 Epic",
                "normal": "🟢 Normal"
            }
            category_name = category_names.get(category, category)
            
            if category == "favorite":
                cards, total_count = self.db.get_favorite_cards(user_id, page=page, per_page=6)
            else:
                rarity_map = {
                    "legend": CardRarity.LEGEND,
                    "epic": CardRarity.EPIC,
                    "normal": CardRarity.NORMAL
                }
                rarity = rarity_map.get(category)
                cards, total_count = self.db.get_player_cards_by_rarity(user_id, rarity=rarity, page=page, per_page=6)
            
            total_pages = (total_count + 5) // 6
            text = f"📋 **{category_name}** (صفحه {page}/{total_pages})\n\nلطفاً کارت خود را انتخاب کنید:"
        
        try:
            await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception:
            pass
    

    async def pvp_card_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب کارت در فایت PvP - FIXED"""
        query = update.callback_query
        await query.answer()

        
        parts = query.data.split("_")
        fight_id = parts[2]
        card_id = parts[3]
        user_id = query.from_user.id
        # Prevent users with 0 hearts from participating
        try:
            p = self.db.get_or_create_player(user_id)
            p = self.game.check_and_reset_hearts(p)
            if getattr(p, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, p)
                return
        except Exception:
            pass
        
        # دریافت فایت
        fight = self.db.get_fight_by_id(fight_id)
        logger.info(f"PvP Card Select - Data: {query.data}, User: {user_id}")
        if fight:
            logger.info(f"Fight before update: challenger={fight.challenger_id}, opponent={fight.opponent_id}")
        else:
            logger.warning(f"Fight {fight_id} not found at card select!")    
            
        if not fight:
            text = "❌ فایت یافت نشد!"
            await query.edit_message_text(text)
            return
        
        # تعیین اینکه کاربر challenger است یا opponent
        if user_id == fight.challenger_id:
            field_name = "challenger_card_id"
        elif user_id == fight.opponent_id:
            field_name = "opponent_card_id"
        else:
            await query.answer("❌ شما بخشی از این فایت نیستید!", show_alert=True)
            return
        
        # بروزرسانی انتخاب کارت
        update_data = {field_name: card_id}
        
        # دریافت وضعیت فعلی فایت برای تعیین وضعیت میانی یا نهایی
        current_fight = self.db.get_fight_by_id(fight_id)
        
        # اگر اولین انتخاب کارت توسط چلنجر است و حریف هنوز کارت ندارد
        if user_id == fight.challenger_id and not current_fight.opponent_card_id:
            update_data["status"] = FightStatus.CHALLENGER_CARD_SELECTED
        # اگر اولین انتخاب کارت توسط حریف است و چلنجر هنوز کارت ندارد
        if user_id == fight.opponent_id and not current_fight.challenger_card_id:
            update_data["status"] = FightStatus.OPPONENT_CARD_SELECTED
        
        # اگر با این انتخاب هر دو کارت موجود می‌شوند، وضعیت را به BOTH_CARDS_SELECTED ارتقا بده
        if user_id == fight.challenger_id and current_fight.opponent_card_id:
            update_data["status"] = FightStatus.BOTH_CARDS_SELECTED
        elif user_id == fight.opponent_id and current_fight.challenger_card_id:
            update_data["status"] = FightStatus.BOTH_CARDS_SELECTED
        
        updated_ok = self.db.update_fight(fight_id, **update_data)
        if not updated_ok:
            logger.error(f"Failed to update fight {fight_id} with {update_data}")
            try:
                await query.answer("❌ خطا در ثبت انتخاب. لطفاً دوباره تلاش کنید.", show_alert=True)
            except Exception:
                pass
            return
        
        # دریافت کارت انتخاب شده
        selected_card = self.db.get_card_by_id(card_id)
        
        # افزایش usage_count
        self.db.increment_card_usage(user_id, card_id)
        
        # بازخورد سریع برای کاربر
        try:
            await query.answer("✅ Card selected!")
        except Exception:
            pass
        
        text = (
            f"✅ **کارت انتخاب شد!**\n\n"
            f"🎴 {selected_card.name}\n\n"
            f"حالا ویژگی مورد نظر برای فایت را انتخاب کنید:"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"💪 قدرت ({selected_card.power})", callback_data=f"pvp_stat_{fight_id}_power")],
            [InlineKeyboardButton(f"⚡ سرعت ({selected_card.speed})", callback_data=f"pvp_stat_{fight_id}_speed")],
            [InlineKeyboardButton(f"🧠 آی‌کیو ({selected_card.iq})", callback_data=f"pvp_stat_{fight_id}_iq")],
            [InlineKeyboardButton(f"❤️ محبوبیت ({selected_card.popularity})", callback_data=f"pvp_stat_{fight_id}_popularity")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


    async def pvp_stat_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب ویژگی در فایت PvP - COMPLETELY FIXED"""
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split("_")
        fight_id = parts[2]
        stat = parts[3]
        user_id = query.from_user.id
        
        logger.info(f"PvP Stat Select - Fight: {fight_id}, User: {user_id}, Stat: {stat}")
        # Prevent users with 0 hearts from selecting stats
        try:
            p = self.db.get_or_create_player(user_id)
            p = self.game.check_and_reset_hearts(p)
            if getattr(p, 'hearts', 5) <= 0:
                await self.send_no_hearts_message(query, context, p)
                return
        except Exception:
            pass
        
        # دریافت فایت
        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            text = "❌ فایت یافت نشد!"
            await query.edit_message_text(text)
            logger.error(f"Fight {fight_id} not found")
            return
        
        # بررسی اولیه opponent_id
        if self.db.is_unclaimed(fight):
            logger.error(f"Fight {fight_id} has invalid opponent_id=0")
            await query.answer("❌ خطا: حریف معتبر نیست!", show_alert=True)
            return
        
        # تعیین اینکه کاربر challenger است یا opponent
        if user_id == fight.challenger_id:
            field_name = "challenger_stat"
            user_role = "challenger"
        elif user_id == fight.opponent_id:
            field_name = "opponent_stat"
            user_role = "opponent"
        else:
            await query.answer("❌ شما بخشی از این فایت نیستید!", show_alert=True)
            logger.warning(f"User {user_id} tried to select stat for fight {fight_id} but is not participant")
            return
        
        logger.info(f"User {user_id} is {user_role} selecting stat {stat}")
        
        # بروزرسانی انتخاب ویژگی
        update_data = {field_name: stat}
        success = self.db.update_fight(fight_id, **update_data)
        
        if not success:
            logger.error(f"Failed to update fight {fight_id} with {field_name}={stat}")
            await query.answer("❌ خطا در ذخیره انتخاب!", show_alert=True)
            return
        
        # دریافت وضعیت به‌روزشده
        updated_fight = self.db.get_fight_by_id(fight_id)
        if not updated_fight:
            logger.error(f"Fight {fight_id} disappeared after update")
            await query.answer("❌ خطای سیستمی!", show_alert=True)
            return
        
        # نام‌های ویژگی برای نمایش
        stat_names = {
            "power": "💪 قدرت",
            "speed": "⚡ سرعت",
            "iq": "🧠 آی‌کیو",
            "popularity": "❤️ محبوبیت"
        }
        
        selected_stat_name = stat_names.get(stat, f"ویژگی {stat}")
        
        logger.info(f"Fight {fight_id} status after update: "
                    f"challenger_stat={updated_fight.challenger_stat}, "
                    f"opponent_stat={updated_fight.opponent_stat}")
        
        # بررسی اینکه آیا هر دو بازیکن انتخاب کرده‌اند
        if updated_fight.challenger_stat and updated_fight.opponent_stat:
            # بازخورد سریع
            try:
                await query.answer("⚔️ Both stats selected! Resolving fight...")
            except Exception:
                pass
            # هر دو انتخاب کرده‌اند - باید فایت حل شود
            logger.info(f"Both players selected stats for fight {fight_id} - resolving")
            
            # اعلام شروع محاسبه
            text = f"✅ **{selected_stat_name} انتخاب شد!**\n\n⚔️ درحال محاسبه نتیجه فایت..."
            await query.edit_message_text(text, parse_mode='Markdown')
            
            # حل فایت
            try:
                result = self.game.resolve_pvp_fight(fight_id)
                
                if result.get("success"):
                    logger.info(f"Fight {fight_id} resolved successfully")
                    await self._announce_pvp_result(context, result)
                else:
                    error_msg = result.get("error", "خطای نامشخص در حل فایت")
                    logger.error(f"Fight {fight_id} resolution failed: {error_msg}")
                    
                    # اطلاع به کاربران در صورت خطا
                    if updated_fight.chat_id:
                        error_text = (
                            f"❌ **خطا در فایت!**\n\n"
                            f"متاسفانه فایت به دلیل خطای زیر لغو شد:\n"
                            f"`{error_msg}`\n\n"
                            f"لطفاً دوباره تلاش کنید."
                        )
                        try:
                            await context.bot.send_message(
                                chat_id=updated_fight.chat_id,
                                text=error_text,
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            logger.error(f"Failed to send error message to chat {updated_fight.chat_id}: {e}")
                    
                    # حذف فایت ناقص از دیتابیس
                    self.db.delete_fight(fight_id)
                    
            except Exception as e:
                logger.error(f"Exception in fight {fight_id} resolution: {e}", exc_info=True)
                
                # اطلاع به کاربران در صورت خطای سیستمی
                if updated_fight.chat_id:
                    system_error_text = (
                        f"💥 **خطای سیستمی!**\n\n"
                        f"متاسفانه فایت به دلیل خطای سیستمی لغو شد.\n"
                        f"لطفاً چند دقیقه دیگر دوباره تلاش کنید."
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=updated_fight.chat_id,
                            text=system_error_text,
                            parse_mode='Markdown'
                        )
                    except Exception as send_error:
                        logger.error(f"Failed to send system error message: {send_error}")
                
                # حذف فایت از دیتابیس
                self.db.delete_fight(fight_id)
        
        else:
            # فقط یکی انتخاب کرده - منتظر دیگری
            logger.info(f"Fight {fight_id}: Only {user_role} selected stat, waiting for other player")
            
            try:
                await query.answer("✅ Stat selected! Waiting for opponent ⏳")
            except Exception:
                pass

            text = (
                f"✅ **{selected_stat_name} انتخاب شد!**\n\n"
                f"⏳ منتظر انتخاب حریف...\n\n"
                f"نتیجه فایت در گروه اعلام خواهد شد."
            )
            await query.edit_message_text(text, parse_mode='Markdown')


    # ==================== SETUP METHODS ====================


