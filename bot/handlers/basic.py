#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Basic Handlers - start, help, profile, cards, claim, leaderboard
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




class BasicHandlersMixin:
    """Basic Handlers - start, help, profile, cards, claim, leaderboard"""

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور شروع بازی - یکبار اجرا می‌شود"""
        user = update.effective_user
        chat_type = update.effective_chat.type
        logger.info(f"start_command invoked by user_id={getattr(user,'id',None)} chat_type={chat_type}")

        try:
            # Ensure player exists in private chats
            card_count = 0
            if chat_type == 'private':
                player = self.db.get_or_create_player(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name
                )
                player = self.game.check_and_reset_hearts(player)
                card_count = len(self.db.get_player_cards(user.id))

                # Grant starter cards once if player has none
                try:
                    if card_count == 0:
                        # Use normalized starter names and tolerate DB capitalization differences
                        default_names = ["John Wick", "Heisenberg", "Rehi"]
                        granted = []
                        for nm in default_names:
                            card_obj = self.db.get_card_by_name(nm)
                            if not card_obj:
                                # Fallback: scan all cards case-insensitively
                                for card in self.db.get_all_cards():
                                    if card.name.lower() == nm.lower():
                                        card_obj = card
                                        break
                            if card_obj:
                                added = self.db.add_card_to_player(user.id, card_obj.card_id)
                                if added:
                                    granted.append(card_obj.name)
                        if granted:
                            try:
                                if hasattr(update, 'message') and update.message:
                                    await update.message.reply_text(
                                        f"🎴 کارت‌های شروعی بهت داده شد: {', '.join(granted)}"
                                    )
                                elif hasattr(update, 'callback_query') and update.callback_query:
                                    await update.callback_query.message.reply_text(
                                        f"🎴 کارت‌های شروعی بهت داده شد: {', '.join(granted)}"
                                    )
                            except Exception:
                                pass
                        # refresh card count after granting
                        card_count = len(self.db.get_player_cards(user.id))
                except Exception as e:
                    logger.warning(f"Failed to grant starter cards to {user.id}: {e}")
            else:
                player = None

            # Channel membership check
            if not await self.is_user_in_channel(user.id, context):
                await self.send_channel_join_message(update)
                return

            # Group behavior
            if chat_type in ['group', 'supergroup']:
                active = self.db.get_active_fight_for_group(update.effective_chat.id)
                if active:
                    await update.message.reply_text("🥊 یک چالش فعال در این گروه جریان دارد. از پنل موجود استفاده کنید.")
                else:
                    await update.message.reply_text("ℹ️ برای شروع بازی از پیوی استفاده کن.")
                return

            # Private: send welcome/menu
            welcome_text = (
                '🎮 به نبرد افسانه‌ها خوش اومدی!\n'
                'دنیایی که قهرمان‌هاش از تمام دنیاهای خیالی جمع شدن...\n'
                '📜 برای دیدن داستان بازی بنویسید: /story'
            )

            miniapp_url = (
                os.environ.get("MINIAPP_URL")
                or self.config.get("miniapp_url", "")
            )
            keyboard = [
                *([[InlineKeyboardButton("🎮 Solo vs آسو", web_app=WebAppInfo(url=miniapp_url))]] if miniapp_url else []),
                [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
                [InlineKeyboardButton("⚔️ چالش PvP", callback_data="request_pvp_fight"),
                 InlineKeyboardButton("🎲 Risk Mode", callback_data="risk_menu")],
                [InlineKeyboardButton("🎁 کلیم روزانه", callback_data="daily_claim"),
                 InlineKeyboardButton("⛏️ ماینینگ", callback_data="mining_claim")],
                [InlineKeyboardButton("🔮 Fusion کارت‌ها", callback_data="fusion_menu"),
                 InlineKeyboardButton("🛒 شاپ", callback_data="shop_menu")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                if hasattr(update, 'message') and update.message:
                    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
                elif hasattr(update, 'callback_query') and update.callback_query:
                    try:
                        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
                    except Exception:
                        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send welcome text in start_command: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Unhandled exception in start_command: {e}", exc_info=True)
            try:
                if hasattr(update, 'message') and update.message:
                    await update.message.reply_text("❌ خطا در اجرای دستور /start. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.")
                elif hasattr(update, 'callback_query') and update.callback_query:
                    await update.callback_query.message.reply_text("❌ خطا در اجرای درخواست. لطفاً دوباره /start را در پیوی بزنید.")
            except Exception:
                pass

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """راهنمای بازی"""
        cfg_help = self.config.get('texts', {}).get('help')
        if cfg_help and isinstance(cfg_help, str) and cfg_help.strip():
            help_text = cfg_help
        else:
            help_text = (
                "📖 **راهنمای بازی کارت‌ها**\n\n"
                "🎯 کارت جمع کن، مبارزه کن، امتیاز بگیر!\n\n"
                "🃏 رریتی‌ها: 🟢 Normal • 🟣 Epic • 🟡 Legend\n"
                f"🎁 کارت روزانه هر {self.game.CLAIM_COOLDOWN_HOURS} ساعت\n"
                "🥊 PvP در گروه‌ها: چالش بده یا قبول کن\n"
                "⚙️ در مساوی امتیاز/قلبی کم یا زیاد نمی‌شود\n"
            )
        
        if update.callback_query:
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_text(
                help_text, reply_markup=reply_markup, parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(help_text, parse_mode='Markdown')

    async def story_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ارسال داستان سینماتیک بازی (/story)"""
        story_text = (
            '🤖 در آینده‌ای نه‌چندان دور، هوش مصنوعی به مرحله‌ای می‌رسه که می‌تونه تمام سریال‌ها، فیلم‌ها، انیمیشن‌ها و بازی‌ها رو آنالیز کنه.\n'
            'از دل این الگوریتم‌ها شخصیت‌های افسانه‌ای بیرون میان...\n\n'
            '⚔️ این فقط بازسازی نیست — این دعوت به نبرده!\n\n'
            'همه‌ی نمادهای دنیای سرگرمی، از دارث ویدر تا پدرخوانده، از جوکر تا هالک، از گاس فرینگ تا هوم‌لندر، وارد یک دنیای بی‌پایان می‌شن.\n'
            'قانون فقط یکیه: قدرت واقعی رو کارت‌ها تعیین می‌کنن.\n\n'
            '🎴 تو انتخاب می‌کنی.\n'
            '🎮 تو بازی می‌کنی.\n'
            '🔥 تو تصمیم می‌گیری کدوم نماد، افسانه‌ی نهایی بشه.\n\n'
            '🕹 بازی شروع شده...'
        )

        try:
            await update.message.reply_text(story_text, parse_mode='Markdown')
        except Exception:
            # fallback: plain text
            await update.message.reply_text(story_text)
    
    async def recalc_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور admin برای recalculate کردن total_score ها"""
        user_id = update.effective_user.id
        
        # فقط admin ها می‌تونن استفاده کنن
        admin_ids = [1685691201, 5735941901]  # IDs شما
        if user_id not in admin_ids:
            await update.message.reply_text("❌ شما مجوز استفاده از این دستور را ندارید.")
            return
        
        await update.message.reply_text("🔄 در حال محاسبه مجدد امتیازات...")
        
        try:
            updated_count = self.db.recalculate_all_total_scores()
            await update.message.reply_text(f"✅ امتیازات {updated_count} بازیکن بروزرسانی شد!")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {str(e)}")

    async def check_membership_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بررسی عضویت کاربر بعد از کلیک دکمه"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        if await self.is_user_in_channel(user.id, context):
            # کاربر عضو شده - شروع بازی
            text = (
                f"✅ **عالی! شما باموفقیت در کانال عضو شدید.**\n\n"
                f"🎉 خوش آمدید {user.first_name}!\n"
                f"🎮 حالا می‌توانید از ربات استفاده کنید.\n\n"
                f"برای شروع دوباره /start بزنید."
            )
            keyboard = [[InlineKeyboardButton("🎮 شروع بازی", callback_data="start_game")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            # هنوز عضو نشده
            await query.answer("❌ هنوز در کانال عضو نشده‌اید. لطفاً ابتدا عضو شوید.", show_alert=True)

    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش پروفایل کاربر"""
        if not self._is_command_allowed_in_chat("profile", update.effective_chat.type):
            await update.message.reply_text(
                "🚫 این دستور فقط در چت خصوصی قابل استفاده است.\n"
                "📱 برای مشاهده پروفایل خود، از پیوی ربات استفاده کنید."
            )
            return

        user = update.effective_user

        if not await self.is_user_in_channel(user.id, context):
            await self.send_channel_join_message(update)
            return

        player = self.db.get_or_create_player(user.id, user.username, user.first_name)
        card_counts = self.db.get_player_card_counts(user.id)
        stats = self.db.get_player_stats(user.id)
        rank = self.db.get_player_rank(user.id)
        prog = self.db.get_or_create_progression(user.id)

        # Level & XP
        level = prog['level']
        total_xp = prog['total_xp']
        tier = prog['current_tier']
        tp = prog['tier_points']

        if level < 30:
            cur_lv, xp_in, xp_needed = LevelSystem.get_xp_progress(total_xp)
            xp_bar = format_xp_bar(xp_in, xp_needed)
            xp_text = f"{xp_bar} ({xp_in}/{xp_needed})"
        else:
            xp_text = "MAX LEVEL ✨"

        tier_badge = format_tier_badge(tier)
        rank_text = f"#{rank}" if rank else "N/A"
        total_stats = stats.get('total', {'games_played': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'win_rate': 0})

        text = (
            f"👤 **{user.first_name}**\n\n"
            f"⭐ Level {level}  {tier_badge} {tier}  •  {tp} TP\n"
            f"📈 XP: {xp_text}\n\n"
            f"💰 سکه: {getattr(player, 'coins', 0):,}\n"
            f"❤️ جان: {player.hearts}/{getattr(player, 'max_hearts', self.game.DAILY_HEARTS)}\n"
            f"🏆 امتیاز: {player.total_score}  •  رتبه: {rank_text}\n"
            f"🎴 کارت‌ها: {card_counts.get('total', 0)} "
            f"(🟢{card_counts.get('normal',0)} 🟣{card_counts.get('epic',0)} 🟡{card_counts.get('legend',0)})\n\n"
            f"⚔️ **آمار فایت:**\n"
            f"  بازی: {total_stats['games_played']}  •  "
            f"برد: {total_stats['wins']}  •  "
            f"باخت: {total_stats['losses']}  •  "
            f"نرخ برد: {int(total_stats['win_rate'])}%"
        )

        keyboard = [
            [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards"),
             InlineKeyboardButton("🏆 لیدربرد", callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def start_game_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline 'شروع بازی' button by invoking the start command flow."""
        query = update.callback_query
        await query.answer()

        # Perform the start flow directly for callback queries to avoid potential update/message differences
        try:
            user = query.from_user
            chat = query.message.chat

            # Ensure player exists and reset hearts
            player = self.db.get_or_create_player(user.id, user.username, user.first_name)
            player = self.game.check_and_reset_hearts(player)

            # Grant starter cards if none
            try:
                card_count = len(self.db.get_player_cards(user.id))
                if card_count == 0:
                    default_names = ["John Wick", "Heisenberg", "Rehi"]
                    granted = []
                    for nm in default_names:
                        card_obj = self.db.get_card_by_name(nm)
                        if not card_obj:
                            for card in self.db.get_all_cards():
                                if card.name.lower() == nm.lower():
                                    card_obj = card
                                    break
                        if card_obj:
                            added = self.db.add_card_to_player(user.id, card_obj.card_id)
                            if added:
                                granted.append(card_obj.name)
                    if granted:
                        await context.bot.send_message(chat_id=chat.id, text=f"🎴 کارت‌های شروعی بهت داده شد: {', '.join(granted)}")
            except Exception as e:
                logger.warning(f"Failed to grant starter cards in callback start_game for {user.id}: {e}")

            # Send the welcome/menu (same as private start)
            welcome_text = (
                '🎮 به نبرد افسانه‌ها خوش اومدی!\n'
                'دنیایی که قهرمان‌هاش از تمام دنیاهای خیالی جمع شدن...\n'
                '📜 برای دیدن داستان بازی بنویسید: /story'
            )

            keyboard = [
                [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
                [InlineKeyboardButton("⚔️ چالش PvP", callback_data="request_pvp_fight")],
                [InlineKeyboardButton("🎁 کلیم روزانه", callback_data="daily_claim")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(chat_id=chat.id, text=welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in start_game_handler: {e}", exc_info=True)
            try:
                await query.message.reply_text("❌ خطا در اجرای شروع بازی. لطفاً دوباره /start را تایپ کنید.")
            except Exception:
                pass

    async def cards_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش کارت‌های کاربر از طریق دستور با pagination"""
        # بررسی مجوز دستور
        if not self._is_command_allowed_in_chat("cards", update.effective_chat.type):
            await update.message.reply_text(
                "🚫 این دستور فقط در چت خصوصی قابل استفاده است.\n"
                "🃏 برای مشاهده کارت‌های خود، از پیوی ربات استفاده کنید."
            )
            return
        
        user = update.effective_user
        
        # بررسی عضویت کانال
        if not await self.is_user_in_channel(user.id, context):
            await self.send_channel_join_message(update)
            return
        
        user_id = update.effective_user.id
        cards = self.db.get_player_cards(user_id)
        
        if not cards:
            text = "🔭 هنوز کارتی ندارید! برای شروع، با دستور /claim اولین کارت خود را رایگان دریافت کنید."
            await update.message.reply_text(text)
        else:
            # نمایش منوی دسته‌بندی با pagination
            keyboard = self._create_my_cards_keyboard(user_id, category="menu", page=1)
            text = f"🎴 **کارت‌های شما ({len(cards)} کارت)**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def mycards_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش کارت‌ها با امکان مدیریت"""
        if not self._is_command_allowed_in_chat("mycards", update.effective_chat.type):
            await update.message.reply_text("🚫 این دستور فقط در چت خصوصی قابل استفاده است.")
            return
        
        user_id = update.effective_user.id
        keyboard = self._create_mycards_keyboard(user_id, category="menu", page=1)
        
        text = "📋 **مدیریت کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    
    def _create_mycards_keyboard(self, user_id: int, category: str = "menu", page: int = 1) -> InlineKeyboardMarkup:
        """ایجاد کیبورد مدیریت کارت‌ها"""
        keyboard = []
        
        if category == "menu":
            # منوی اصلی
            rarity_counts = self.db.get_rarity_counts(user_id)
            favorite_cards, fav_count = self.db.get_favorite_cards(user_id, page=1, per_page=1)
            
            if fav_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"⭐ مورد علاقه ({fav_count})",
                        callback_data=f"mycards_favorite_1"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    f"🟡 Legendary ({rarity_counts.get(CardRarity.LEGEND.value, 0)})",
                    callback_data=f"mycards_legend_1"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"🟣 Epic ({rarity_counts.get(CardRarity.EPIC.value, 0)})",
                    callback_data=f"mycards_epic_1"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"🟢 Normal ({rarity_counts.get(CardRarity.NORMAL.value, 0)})",
                    callback_data=f"mycards_normal_1"
                )
            ])
            
        else:
            # نمایش کارت‌های یک دسته
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
            
            rarity_colors = {
                CardRarity.NORMAL: "🟢",
                CardRarity.EPIC: "🟣",
                CardRarity.LEGEND: "🟡"
            }
            
            for card in cards:
                color = rarity_colors.get(card.rarity, "⚪")
                stats = f"💪{card.power} ⚡{card.speed} 🧠{card.iq} ❤️{card.popularity}"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{color} {card.name} ({stats})",
                        callback_data=f"cardinfo_{card.card_id}"
                    )
                ])
            
            # دکمه‌های navigation
            total_pages = (total_count + 5) // 6
            nav_buttons = []
            
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton("« قبلی", callback_data=f"mycards_{category}_{page-1}")
                )
            
            nav_buttons.append(
                InlineKeyboardButton("🏠 منو", callback_data=f"mycards_menu_1")
            )
            
            if page < total_pages:
                nav_buttons.append(
                    InlineKeyboardButton("بعدی »", callback_data=f"mycards_{category}_{page+1}")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        return InlineKeyboardMarkup(keyboard)

    async def claim_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت دستور /claim"""
        user = update.effective_user
        
        if not await self.is_user_in_channel(user.id, context):
            await self.send_channel_join_message(update)
            return
            
        user_id = user.id
        success, card, error = self.claim_sys.claim_card(user_id)
        
        if success and card:
            type_labels = {"POWER_TYPE": "💪", "SPEED_TYPE": "⚡", "IQ_TYPE": "🧠", "POPULARITY_TYPE": "❤️"}
            type_icon = type_labels.get(getattr(card, 'card_type', ''), "")
            
            text = (
                f"🎉 **کارت روزانه دریافت شد!**\n\n"
                f"🟢 **{card.name}** (Normal) {type_icon}\n\n"
                f"💪 {card.power}  ⚡ {card.speed}  🧠 {card.iq}  ❤️ {card.popularity}\n"
                f"📊 مجموع: {card.get_total_stats()}\n\n"
                f"⏰ کلیم بعدی: فردا ساعت ۰۰:۰۰"
            )
            
            if not image_sent:
                text = "🎴 (تصویر در دسترس نیست)\n\n" + text
            
            keyboard = [
                [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards"),
                 InlineKeyboardButton("🔮 Fusion", callback_data="fusion_menu")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            
        else:
            text = f"⚠️ **{error if error else 'خطای نامشخص!'}**"
            keyboard = [
                [InlineKeyboardButton("⛏️ ماینینگ", callback_data="mining_claim")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def my_cards_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش کارت‌های کاربر با pagination"""
        query = update.callback_query
        await query.answer()
        
        # Check panel expiration
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است. لطفاً دوباره /start بزنید.", show_alert=True)
            return
        
        user_id = query.from_user.id
        cards = self.db.get_player_cards(user_id)
        
        if not cards:
            text = (
                "🔭 **هنوز کارتی ندارید!**\n\n"
                "برای شروع، اولین کارت خود را رایگان دریافت کنید."
            )
            keyboard = [
                [InlineKeyboardButton("🎁 دریافت کارت اول", callback_data="daily_claim")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            # نمایش منوی دسته‌بندی
            keyboard = self._create_my_cards_keyboard(user_id, category="menu", page=1)
            text = f"🎴 **کارت‌های شما ({len(cards)} کارت)**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    def _get_card_bio(self, name: str) -> str:
        bios = {
            "Heisenberg": "شیمیدان نابغه که به مسیر تاریک قدم گذاشت.",
            "Spongebob": "اسفنج پرانرژی از زیر آب که همیشه آماده است.",
            "Kangfupanda": "پاندای رزمی‌کار با قلب بزرگ.",
            "Homelander": "قهرمان قدرتمند با چهره‌ای پیچیده.",
            "Thanos": "تایتان مجنون در جستجوی تعادل کائنات."
        }
        return bios.get(name, "بیوگرافی در دسترس نیست.")

    def _get_card_stats_summary(self, user_id: int, card_id: str) -> Dict[str, Any]:
        import sqlite3
        wins = losses = ties = 0
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT result, COUNT(*) FROM fight_history WHERE user_id=? AND user_card_id=? GROUP BY result",
                (user_id, card_id)
            )
            for res, cnt in cursor.fetchall():
                if res == 'win':
                    wins = cnt
                elif res == 'lose':
                    losses = cnt
                elif res == 'tie':
                    ties = cnt
            conn.close()
        except Exception:
            pass
        total = wins + losses + ties
        wp = round((wins / total) * 100) if total else 0
        lp = round((losses / total) * 100) if total else 0
        tp = round((ties / total) * 100) if total else 0
        return {"wins": wins, "losses": losses, "ties": ties, "total": total, "wp": wp, "lp": lp, "tp": tp}

    async def card_view_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not ensure_not_expired(query, self.db, context):
            await query.answer("⏰ این پنل منقضی شده است.", show_alert=True)
            return
        parts = query.data.split("_")
        card_id = parts[-1]
        card = self.db.get_card_by_id(card_id)
        if not card:
            await query.edit_message_text("❌ کارت یافت نشد!")
            return
        user_id = query.from_user.id
        stats = self.db.get_player_card_stats(card_id, user_id)
        rarity_map = {
            CardRarity.NORMAL: "🟢 Normal",
            CardRarity.EPIC: "🟣 Epic",
            CardRarity.LEGEND: "🟡 Legend"
        }
        header = f"{rarity_map.get(card.rarity, '🔶 Card')} — {card.name}"
        text = (
            f"{header}\n"
            f"💪 {card.power} ⚡ {card.speed} 🧠 {card.iq} ❤️ {card.popularity}\n"
            f"📊 بازی‌ها: {stats['games_played']}\n"
            f"🏆 برد: {stats['wins']} | ❌ باخت: {stats['losses']} | 🤝 مساوی: {stats['ties']}\n"
            f"📈 Win Rate: {int(stats['win_rate'])}%\n\n"
            f"📝 **Biography:**\n{card.biography}"
        )
        # ارسال تصویر
        await send_card_image_safely(query.message, card.name, self.config)
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data="my_cards")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # AI fight handler removed - AI fights are no longer supported

    # ai_select_card_handler removed - AI fights are no longer supported

    # ai_show_abilities_handler removed - AI fights are no longer supported

    # ai_fight_handler and _show_ai_fight_result removed - AI fights are no longer supported

    async def leaderboard_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی اصلی لیدربورد"""
        query = update.callback_query
        await query.answer()
        
        # تشخیص نوع چت
        chat_type = query.message.chat.type if query.message else "private"
        is_group = chat_type in ["group", "supergroup"]
        
        if is_group:
            # منوی لیدربورد گروه
            text = "🏆 <b>Leaderboard گروه</b>\n\nبازه زمانی را انتخاب کنید:"
            keyboard = [
                [InlineKeyboardButton("📊 هفتگی", callback_data="lb_group_weekly_10")],
                [InlineKeyboardButton("📊 ماهانه", callback_data="lb_group_monthly_10")],
                [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_group_all_10")]
            ]
        else:
            # منوی لیدربورد جهانی
            text = "🏆 <b>Leaderboard جهانی</b>\n\nبازه زمانی را انتخاب کنید:"
            keyboard = [
                [InlineKeyboardButton("📊 هفتگی", callback_data="lb_global_weekly_10")],
                [InlineKeyboardButton("📊 ماهانه", callback_data="lb_global_monthly_10")],
                [InlineKeyboardButton("📊 کل زمان‌ها", callback_data="lb_global_all_10")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    
    async def leaderboard_display_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیدربورد با فیلتر"""
        query = update.callback_query
        await query.answer()
        
        # Parse callback_data: lb_{scope}_{timeframe}_{limit}
        parts = query.data.split("_")
        scope = parts[1]  # "global" or "group"
        timeframe = parts[2]  # "weekly", "monthly", "all"
        limit = int(parts[3]) if len(parts) > 3 else 10
        
        chat_id = query.message.chat.id if scope == "group" else None
        is_group = scope == "group"
        
        # اگه گروهه، اول لیست اعضای گروه رو بگیر
        group_member_ids = set()
        if is_group:
            try:
                # دریافت اعضای گروه از Telegram API
                async for member in context.bot.get_chat_administrators(chat_id):
                    group_member_ids.add(member.user.id)
                
                # دریافت تعداد اعضای گروه (محدود به 200 نفر اول)
                member_count = await context.bot.get_chat_member_count(chat_id)
                if member_count <= 200:  # فقط برای گروه‌های کوچک
                    # این API محدود هست، فقط برای گروه‌های کوچک کار می‌کنه
                    try:
                        # متاسفانه Telegram API برای دریافت همه اعضا محدودیت داره
                        # پس فقط admin ها رو می‌گیریم و بقیه رو از دیتابیس
                        pass
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Could not get group members for chat {chat_id}: {e}")
        
        # دریافت لیدربورد
        leaderboard = self.db.get_leaderboard_by_timeframe(
            timeframe=timeframe,
            limit=limit if not is_group else 1000,
            chat_id=None  # فعلا همه رو بگیر، بعدا فیلتر می‌کنیم
        )
        
        # اگه گروهه، فقط اعضای گروه که بازی کردن رو نگه دار
        if is_group:
            # چون نمی‌تونیم همه اعضای گروه رو بگیریم، از روش دیگه استفاده می‌کنیم:
            # فقط کسایی که در این گروه فعالیت داشتن (fight کردن) رو نشون میدیم
            filtered_leaderboard = []
            
            # دریافت user_id هایی که در این گروه fight کردن
            group_fighters = self.db.get_group_fighters(chat_id)
            group_fighter_ids = {fighter['user_id'] for fighter in group_fighters}
            
            for player in leaderboard:
                if player['user_id'] in group_fighter_ids:
                    filtered_leaderboard.append(player)
            
            leaderboard = filtered_leaderboard
        
        # عنوان
        timeframe_names = {
            "weekly": "هفتگی",
            "monthly": "ماهانه",
            "all": "کل زمان‌ها"
        }
        scope_name = "گروه" if is_group else "جهانی"
        
        if not leaderboard:
            text = f"🏆 <b>Leaderboard {scope_name} - {timeframe_names[timeframe]}</b>\n\nهنوز کسی بازی نکرده!"
        else:
            text = f"🏆 <b>Leaderboard {scope_name} - {timeframe_names[timeframe]}</b>\n\n"
            
            medals = ["🥇", "🥈", "🥉"]
            
            # محدود کردن تعداد نمایش برای جلوگیری از متن طولانی
            display_limit = min(limit, 30)  # حداکثر 30 نفر نشون بده
            
            for i, player_info in enumerate(leaderboard[:display_limit]):
                if i < 3:
                    medal = medals[i]
                else:
                    medal = f"{i+1}."
                
                # نام بازیکن - escape کردن کاراکترهای HTML
                first_name = player_info.get('first_name', '').strip()
                username = player_info.get('username', '').strip()
                
                if username:
                    # حذف @ از username اگر وجود داشت
                    username = username.lstrip('@')
                    name = f"@{username[:15]}"
                elif first_name:
                    # escape کردن کاراکترهای خاص HTML
                    name = first_name[:15].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                else:
                    name = "بازیکن"
                
                score = player_info.get('period_score', 0)
                
                # Level و Tier
                try:
                    prog = self.db.get_or_create_progression(player_info['user_id'])
                    tier_badge = format_tier_badge(prog['current_tier'])
                    level = prog['level']
                    extra = f" {tier_badge}Lv{level}"
                except Exception:
                    extra = ""
                
                text += f"{medal} {name}{extra} — {score} امتیاز\n"
            
            # رتبه کاربر از لیدربورد فیلتر شده
            user_id = query.from_user.id
            user_rank = None
            user_score = 0
            
            for i, player in enumerate(leaderboard):
                if player['user_id'] == user_id:
                    user_rank = i + 1
                    user_score = player['period_score']
                    break
            
            if user_rank:
                text += f"\n📍 رتبه شما: #{user_rank} ({user_score} امتیاز)"
        
        # دکمه‌ها
        keyboard = []
        
        if not is_group:
            # برای جهانی: دکمه‌های تعداد نمایش
            if limit == 10:
                keyboard.append([
                    InlineKeyboardButton("🥈 Top 50", callback_data=f"lb_global_{timeframe}_50"),
                    InlineKeyboardButton("🥉 Top 100", callback_data=f"lb_global_{timeframe}_100")
                ])
            elif limit == 50:
                keyboard.append([
                    InlineKeyboardButton("🥇 Top 10", callback_data=f"lb_global_{timeframe}_10"),
                    InlineKeyboardButton("🥉 Top 100", callback_data=f"lb_global_{timeframe}_100")
                ])
            else:  # 100
                keyboard.append([
                    InlineKeyboardButton("🥇 Top 10", callback_data=f"lb_global_{timeframe}_10"),
                    InlineKeyboardButton("🥈 Top 50", callback_data=f"lb_global_{timeframe}_50")
                ])
            
            # دکمه بازگشت برای private chat
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="leaderboard")])
            keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])
        else:
            # دکمه بازگشت برای گروه
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="leaderboard")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to edit leaderboard message: {e}")
            # اگر edit نشد، پیام جدید بفرست
            try:
                await query.message.reply_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
            except Exception:
                pass

    async def match_info_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش اطلاعات کامل مبارزه پس از کلیک روی دکمه 'ℹ️ اطلاعات بیشتر'"""
        query = update.callback_query
        await query.answer()
        # Robust extraction of fight_id from callback_data
        data = (query.data or "")
        fight_id = None
        if data.startswith('match_info_'):
            fight_id = data[len('match_info_'):]

        if not fight_id:
            await query.answer("❌ داده نامعتبر", show_alert=True)
            return

        result = self.recent_matches.get(str(fight_id))
        if not result:
            # Provide a clear inline alert and a fallback message in chat
            try:
                await query.answer("ℹ️ اطلاعات این مبارزه در دسترس نیست یا منقضی شده است.", show_alert=True)
            except Exception:
                pass
            try:
                await context.bot.send_message(chat_id=query.message.chat_id, text="ℹ️ اطلاعات این مبارزه در دسترس نیست یا منقضی شده است.")
            except Exception:
                logger.info(f"Could not send fallback match info missing message to chat {getattr(query.message, 'chat_id', 'unknown')}")
            return

        try:
            # The result dict comes from game_core.resolve_pvp_fight and contains 'challenger' and 'opponent'
            challenger = result.get('challenger', {})
            opponent = result.get('opponent', {})
            winner_ref = result.get('winner') or {}

            # Determine winner and loser records
            winner_user_id = winner_ref.get('user_id')
            if winner_user_id == challenger.get('user_id'):
                winner_data = challenger
                loser_data = opponent
            elif winner_user_id == opponent.get('user_id'):
                winner_data = opponent
                loser_data = challenger
            else:
                # Fallback: infer from result_type
                rt = result.get('result_type', '')
                if rt == 'challenger_wins':
                    winner_data = challenger
                    loser_data = opponent
                elif rt == 'opponent_wins':
                    winner_data = opponent
                    loser_data = challenger
                elif rt == 'tie':
                    # حالت مساوی - هیچ برنده‌ای نیست
                    await self.handle_tie_match_info(query, context, result, fight_id)
                    return
                else:
                    await context.bot.send_message(chat_id=query.message.chat_id, text="ℹ️ اطلاعات کامل این مبارزه در دسترس نیست.")
                    return

            winner_card = winner_data.get('card')
            loser_card = loser_data.get('card')

            # دریافت نام‌ها - اولویت با username برای جلوگیری از مشکل encoding
            winner_username = "بازیکن"
            loser_username = "بازیکن"
            
            try:
                winner_chat = await context.bot.get_chat(winner_data.get('user_id'))
                # اولویت با username برای جلوگیری از مشکل نام‌های فارسی
                if winner_chat.username:
                    winner_username = winner_chat.username
                elif winner_chat.first_name:
                    winner_username = winner_chat.first_name
            except Exception:
                # اگر نتوانست از API بگیرد، از دیتابیس استفاده کن
                winner_player = self.db.get_or_create_player(winner_data.get('user_id'))
                winner_username_raw = getattr(winner_player, 'username', '').strip()
                winner_first_name = getattr(winner_player, 'first_name', '').strip()
                
                if winner_username_raw:
                    winner_username = winner_username_raw
                elif winner_first_name and winner_first_name != 'بازیکن':
                    winner_username = winner_first_name
            
            try:
                loser_chat = await context.bot.get_chat(loser_data.get('user_id'))
                # اولویت با username برای جلوگیری از مشکل نام‌های فارسی
                if loser_chat.username:
                    loser_username = loser_chat.username
                elif loser_chat.first_name:
                    loser_username = loser_chat.first_name
            except Exception:
                # اگر نتوانست از API بگیرد، از دیتابیس استفاده کن
                loser_player = self.db.get_or_create_player(loser_data.get('user_id'))
                loser_username_raw = getattr(loser_player, 'username', '').strip()
                loser_first_name = getattr(loser_player, 'first_name', '').strip()
                
                if loser_username_raw:
                    loser_username = loser_username_raw
                elif loser_first_name and loser_first_name != 'بازیکن':
                    loser_username = loser_first_name

            winner_stat = winner_data.get('stat_type') or winner_data.get('stat')
            loser_stat = loser_data.get('stat_type') or loser_data.get('stat')

            # Safely fetch numeric stat values
            v1 = getattr(winner_card, winner_stat, 0) if winner_card and winner_stat else 0
            v2 = getattr(winner_card, loser_stat, 0) if winner_card and loser_stat else 0
            sum_winner = v1 + v2

            v3 = getattr(loser_card, loser_stat, 0) if loser_card and loser_stat else 0
            v4 = getattr(loser_card, winner_stat, 0) if loser_card and winner_stat else 0
            sum_loser = v3 + v4

            text = (
                f"👑 Winner: @{winner_username} «{getattr(winner_card, 'name', 'Unknown')}»\n"
                f"🏆 Score gained: +{winner_data.get('score_gained', 0)} — «{getattr(winner_card, 'name', 'Unknown')}»\n\n"
                f"💀 Loser: @{loser_username}\n"
                f"❤️ Hearts lost: {loser_data.get('hearts_lost', 1)}\n"
                f"📉 @{loser_username} lost {abs(loser_data.get('score_gained', 0))} points\n\n"
                f"🎯 Choices:\n"
                f"• @{winner_username} → {winner_stat or 'N/A'}\n"
                f"• @{loser_username} → {loser_stat or 'N/A'}\n\n"
                f"📊 Comparison:\n"
                f"{getattr(winner_card, 'name', 'Winner')} → {winner_stat or 'stat'} {v1} + {loser_stat or 'stat'} {v2} = {sum_winner}\n"
                f"{getattr(loser_card, 'name', 'Loser')} → {loser_stat or 'stat'} {v3} + {winner_stat or 'stat'} {v4} = {sum_loser}"
            )

            keyboard = [[InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in match_info_handler for fight {fight_id}: {e}", exc_info=True)
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ یک خطای پیش‌بینی نشده رخ داد.")
    
    async def send_no_hearts_message(self, query, context, player):
        """ارسال پیام عدم وجود جان به کاربر"""
        time_remaining = self.game.get_heart_reset_time_remaining(player)
        if time_remaining:
            time_str = self.game.format_time_remaining(time_remaining)
            full_message = f"💀 جان شما تمام شده!\n\n⏰ تا {time_str} دیگر نمی‌توانید بازی کنید.\n\n💝 هر ۲۴ ساعت یکبار ۵ جان شارژ می‌شود."
            short_message = f"💀 جان تمام شده! تا {time_str} صبر کنید."
        else:
            full_message = "💀 جان شما تمام شده! لطفاً چند لحظه صبر کنید تا جان‌ها ریست شوند."
            short_message = "💀 جان تمام شده!"
        
        # نمایش popup کوتاه
        await query.answer(short_message, show_alert=True)
        
        # ارسال پیام کامل در پی‌وی
        try:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=full_message
            )
        except Exception:
            pass  # اگر نتوانست پیام پی‌وی بفرستد
    
    async def handle_tie_match_info(self, query, context, result, fight_id):
        """نمایش اطلاعات کامل برای نتایج مساوی"""
        try:
            challenger = result.get('challenger', {})
            opponent = result.get('opponent', {})
            
            challenger_card = challenger.get('card')
            opponent_card = opponent.get('card')
            
            # دریافت نام‌ها
            challenger_username = "بازیکن"
            opponent_username = "بازیکن"
            
            try:
                challenger_chat = await context.bot.get_chat(challenger.get('user_id'))
                if challenger_chat.username:
                    challenger_username = challenger_chat.username
                elif challenger_chat.first_name:
                    challenger_username = challenger_chat.first_name
            except Exception:
                challenger_player = self.db.get_or_create_player(challenger.get('user_id'))
                challenger_username_raw = getattr(challenger_player, 'username', '').strip()
                challenger_first_name = getattr(challenger_player, 'first_name', '').strip()
                
                if challenger_username_raw:
                    challenger_username = challenger_username_raw
                elif challenger_first_name and challenger_first_name != 'بازیکن':
                    challenger_username = challenger_first_name
            
            try:
                opponent_chat = await context.bot.get_chat(opponent.get('user_id'))
                if opponent_chat.username:
                    opponent_username = opponent_chat.username
                elif opponent_chat.first_name:
                    opponent_username = opponent_chat.first_name
            except Exception:
                opponent_player = self.db.get_or_create_player(opponent.get('user_id'))
                opponent_username_raw = getattr(opponent_player, 'username', '').strip()
                opponent_first_name = getattr(opponent_player, 'first_name', '').strip()
                
                if opponent_username_raw:
                    opponent_username = opponent_username_raw
                elif opponent_first_name and opponent_first_name != 'بازیکن':
                    opponent_username = opponent_first_name
            
            challenger_stat = challenger.get('stat_type') or challenger.get('stat')
            opponent_stat = opponent.get('stat_type') or opponent.get('stat')
            
            # محاسبه امتیازات
            c1 = getattr(challenger_card, challenger_stat, 0) if challenger_card and challenger_stat else 0
            c2 = getattr(challenger_card, opponent_stat, 0) if challenger_card and opponent_stat else 0
            challenger_sum = c1 + c2
            
            o1 = getattr(opponent_card, opponent_stat, 0) if opponent_card and opponent_stat else 0
            o2 = getattr(opponent_card, challenger_stat, 0) if opponent_card and challenger_stat else 0
            opponent_sum = o1 + o2
            
            text = (
                f"🤝 **مساوی!**\n\n"
                f"🔥 @{challenger_username} 🆚 @{opponent_username}\n\n"
                f"🎯 انتخاب‌ها:\n"
                f"• @{challenger_username} → {challenger_stat or 'N/A'}\n"
                f"• @{opponent_username} → {opponent_stat or 'N/A'}\n\n"
                f"📊 مقایسه:\n"
                f"{getattr(challenger_card, 'name', 'کارت')} → {challenger_stat or 'stat'} {c1} + {opponent_stat or 'stat'} {c2} = {challenger_sum}\n"
                f"{getattr(opponent_card, 'name', 'کارت')} → {opponent_stat or 'stat'} {o1} + {challenger_stat or 'stat'} {o2} = {opponent_sum}\n\n"
                f"🤝 نتیجه: {challenger_sum} = {opponent_sum}\n"
                f"💫 هیچ یک از بازیکنان امتیاز یا قلب از دست نداد!"
            )
            
            keyboard = [
                [InlineKeyboardButton("🥊 چالش جدید", callback_data="request_pvp_fight")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in handle_tie_match_info for fight {fight_id}: {e}", exc_info=True)
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ خطا در نمایش اطلاعات مساوی.")
    
    async def cooldown_card_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش پیام cooldown کارت"""
        query = update.callback_query
        await query.answer()
        
        # استخراج card_id از callback_data
        data = query.data
        if not data.startswith("cooldown_card_"):
            return
        
        card_id = data[len("cooldown_card_"):]
        user_id = query.from_user.id
        
        # دریافت اطلاعات cooldown
        is_in_cooldown, cooldown_until = self.game.is_card_in_cooldown(user_id, card_id)
        
        if is_in_cooldown and cooldown_until:
            time_remaining = cooldown_until - datetime.now()
            if time_remaining.total_seconds() > 0:
                time_str = self.game.format_time_remaining(time_remaining)
                message = f"❄️ این کارت در حالت Cooldown است!\n\n⏰ تا {time_str} دیگر نمی‌توانید از آن استفاده کنید.\n\n💡 کارت‌های Epic و Legend پس از 10 برد وارد Cooldown می‌شوند."
            else:
                message = "❄️ این کارت در حالت Cooldown بود اما اکنون آزاد شده است. لطفاً دوباره تلاش کنید."
        else:
            message = "❄️ این کارت در حالت Cooldown نیست."
        
        # ارسال پیام در پی‌وی
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )
            await query.answer("پیام در پی‌وی ارسال شد.", show_alert=False)
        except Exception:
            await query.answer(message, show_alert=True)
    
    async def back_to_main_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بازگشت به منوی اصلی"""
        query = update.callback_query
        await query.answer()
        
        # No expiration check needed for back_to_main as it should always work
        
        user = query.from_user
        user_id = user.id
        
        player = self.db.get_or_create_player(user_id)
        card_count = len(self.db.get_player_cards(user_id))
        prog = self.db.get_or_create_progression(user_id)
        tier_badge = format_tier_badge(prog['current_tier'])

        text = (
            f"🎮 **منوی اصلی**\n\n"
            f"سلام {user.first_name}! 👋\n\n"
            f"⭐ Level {prog['level']}  {tier_badge} {prog['current_tier']}\n"
            f"❤️ جان: {player.hearts}/{getattr(player, 'max_hearts', self.game.DAILY_HEARTS)}  "
            f"💰 سکه: {getattr(player, 'coins', 0):,}\n"
            f"🎴 کارت‌ها: {card_count}  •  🏆 امتیاز: {player.total_score}\n\n"
            f"عملیات مورد نظر را انتخاب کنید:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
            [InlineKeyboardButton("⚔️ چالش PvP", callback_data="request_pvp_fight"),
             InlineKeyboardButton("🎲 Risk Mode", callback_data="risk_menu")],
            [InlineKeyboardButton("🎁 کلیم روزانه", callback_data="daily_claim"),
             InlineKeyboardButton("⛏️ ماینینگ", callback_data="mining_claim")],
            [InlineKeyboardButton("🔮 Fusion کارت‌ها", callback_data="fusion_menu"),
             InlineKeyboardButton("🛒 شاپ", callback_data="shop_menu")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # ==================== MYCARDS HANDLERS ====================
    
    async def mycards_navigation_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation در mycards"""
        query = update.callback_query
        await query.answer()
        
        # mycards_{category}_{page}
        parts = query.data.split("_")
        category = parts[1]
        page = int(parts[2])
        user_id = query.from_user.id
        
        keyboard = self._create_mycards_keyboard(user_id, category=category, page=page)
        
        if category == "menu":
            text = "📋 **مدیریت کارت‌های من**\n\nلطفاً دسته مورد نظر را انتخاب کنید:"
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
            text = f"📋 **{category_name}** (صفحه {page}/{total_pages})\n\nروی کارت کلیک کنید تا جزئیات آن را ببینید:"
        
        try:
            await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception:
            pass
    
    async def cardinfo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش اطلاعات کارت با امکان favorite"""
        query = update.callback_query
        await query.answer()
        
        card_id = query.data.split("_")[1]
        user_id = query.from_user.id
        
        # با rarity_override بازیکن
        card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
        if not card:
            await query.answer("❌ کارت یافت نشد!", show_alert=True)
            return
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT is_favorite, usage_count FROM player_cards WHERE user_id = ? AND card_id = ?', (user_id, card_id))
        result = cursor.fetchone()
        conn.close()
        
        is_favorite = result[0] if result else 0
        usage_count = result[1] if result else 0
        
        rarity_colors = {
            CardRarity.NORMAL: "🟢", CardRarity.EPIC: "🟣",
            CardRarity.LEGEND: "🟡", CardRarity.RARE: "🌟"
        }
        color = rarity_colors.get(card.rarity, "⚪")
        
        # card_type نمایش
        type_labels = {
            "POWER_TYPE": "💪 قدرت",
            "SPEED_TYPE": "⚡ سرعت",
            "IQ_TYPE": "🧠 هوش",
            "POPULARITY_TYPE": "❤️ محبوبیت"
        }
        type_label = type_labels.get(getattr(card, 'card_type', ''), "❓")
        
        # بیوگرافی کوتاه
        bio = getattr(card, 'biography', '') or ''
        bio_text = f"\n📖 _{bio[:80]}{'...' if len(bio) > 80 else ''}_\n" if bio else ""
        
        text = (
            f"{color} **{card.name}** ({card.rarity.value.title()})\n"
            f"🏷️ تایپ: {type_label}\n"
            f"{bio_text}\n"
            f"💪 قدرت: {card.power}  ⚡ سرعت: {card.speed}\n"
            f"🧠 هوش: {card.iq}  ❤️ محبوبیت: {card.popularity}\n"
            f"📊 مجموع: {card.get_total_stats()}\n\n"
            f"🎮 استفاده: {usage_count} بار"
            f"{'  ⭐' if is_favorite else ''}"
        )
        
        fav_text = "💔 حذف از علاقه‌مندی‌ها" if is_favorite else "⭐ افزودن به علاقه‌مندی‌ها"
        
        keyboard = [
            [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav_{card_id}")],
        ]
        
        # اگه کارت Epic هست، ماموریت رو نشون بده
        if card.rarity == CardRarity.EPIC:
            mission_progress = self.missions.get_player_mission_progress(user_id, card_id)
            if mission_progress:
                prog = mission_progress['current_progress']
                tgt = mission_progress['target']
                pct = mission_progress['progress_percent']
                mission_line = f"\n\n🎯 **ماموریت:** {mission_progress['description']}\n📈 پیشرفت: {prog}/{tgt} ({pct}%)"
                text += mission_line
                
                if mission_progress['completed'] and not mission_progress.get('reward_claimed'):
                    keyboard.append([InlineKeyboardButton(
                        "🏆 دریافت پاداش Legend!", callback_data=f"mission_claim_{card_id}"
                    )])
        
        # دکمه اسکین
        all_skins = self.skins.get_card_skins(card_id)
        if all_skins:
            keyboard.append([InlineKeyboardButton("🎨 اسکین‌ها", callback_data=f"skins_menu_{card_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="mycards_menu_1")])
        
        try:
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception:
            pass
    
    async def toggle_favorite_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تغییر وضعیت favorite کارت"""
        query = update.callback_query
        
        card_id = query.data.split("_")[2]
        user_id = query.from_user.id
        
        success = self.db.toggle_favorite_card(user_id, card_id)
        
        if success:
            await query.answer("✅ وضعیت کارت تغییر کرد!", show_alert=False)
            # بروزرسانی پیام
            await self.cardinfo_handler(update, context)
        else:
            await query.answer("❌ خطا در تغییر وضعیت!", show_alert=True)

    # ==================== 3-ROUND BATTLE SYSTEM ====================


