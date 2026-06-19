#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Card Game Bot with PvP Support - فاز ۱ (Enhanced & Fixed)
ربات تلگرام کامل بازی کارت با قابلیت PvP اصلاح شده + بررسی عضویت کانال
"""

import json
import os
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import telegram
import telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, BotCommand, BotCommandScope, BotCommandScopeDefault, BotCommandScopeAllGroupChats, WebAppInfo
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)

# وارد کردن سیستم‌های پایه
from game_core import DatabaseManager, GameLogic, CardManager, StatType, Card, CardRarity, Player, PvPFight, FightStatus

# وارد کردن سیستم‌های فاز ۲
from systems.fusion_system import FusionSystem
from systems.phase2_systems import LevelSystem, TierSystem, format_xp_bar, format_tier_badge
from systems.economy_system import EconomySystem
from systems.tier_decay_system import TierDecaySystem
from systems.risk_mode_system import RiskModeSystem, RiskTable, RiskAction
from systems.battle_system_3rounds import BattleSystem3Rounds, BattleState, ARENAS
from systems.claim_system import ClaimSystem
from systems.card_missions_system import CardMissionsSystem, MISSION_TYPES
from systems.skins_system import SkinsSystem, SKIN_TYPES

# تنظیم لاگینگ  
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================

# Required channel for bot usage
REQUIRED_CHANNEL = '@KhasteNews'

# Panel expiration timeout (15 minutes)
PANEL_TIMEOUT = 15 * 60

# Command scope definitions
PRIVATE_CHAT_COMMANDS = [
    BotCommand("start", "شروع بازی و نمایش منوی اصلی"),
    BotCommand("profile", "نمایش پروفایل و آمار شخصی"),
    BotCommand("cards", "مشاهده کارت‌های جمع‌آوری شده"),
    BotCommand("claim", "دریافت کارت روزانه رایگان"),
    BotCommand("leaderboard", "مشاهده لیست برترین بازیکنان"),
    BotCommand("help", "راهنمای بازی و دستورات"),
    BotCommand("story", "داستان سینماتیک بازی")
]

GROUP_CHAT_COMMANDS = [
    BotCommand("fight", "شروع چالش PvP در گروه"),
    BotCommand("claim", "دریافت کارت روزانه رایگان"),
    BotCommand("leaderboard", "مشاهده لیست برترین بازیکنان"),
    BotCommand("help", "راهنمای بازی")
]

DEFAULT_CONFIG = {
    "bot_settings": {
        "token": "8494533147:AAGKuMEg0gyIEiInzBqU9pSwIUyE_Lum6h4",
        "admin_user_ids": [5735941901, 1431545583],
        "webhook_url": None,
        "webhook_port": 8443
    },
    "game_settings": {
        "daily_hearts": 5,
        "heart_reset_hours": 24,
        "claim_cooldown_hours": 24,
        "ability_cooldown_hours": 24,
        "max_cards_per_page": 8
    },
    "image_settings": {
        "card_images_path": "/root/card game/card_images/",
        "default_card_image": "/root/card game/card_images/default.png",
        "enable_images": True
    },
    "texts": {
        "help": None  # قابل پیکربندی؛ اگر None باشد از متن پیش‌فرض استفاده می‌شود
    }
}

# ==================== UTILITY FUNCTIONS ====================

async def check_user_started_bot(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """بررسی اینکه آیا کاربر ربات را استارت کرده یا نه"""
    try:
        # تلاش برای ارسال یک پیام تست
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        return True
    except Exception:
        return False

async def handle_user_not_started(query, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت حالتی که کاربر ربات را استارت نکرده"""
    user_name = query.from_user.first_name or query.from_user.username or "کاربر"
    text = (
        f"🤖 **{user_name}** برای شرکت در بازی باید ابتدا ربات را استارت کند!\n\n"
        f"👆 روی دکمه زیر کلیک کنید و /start بزنید:"
    )
    keyboard = [[InlineKeyboardButton("🚀 استارت ربات", url="https://t.me/TelBattleBot?start=pvp")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception:
        pass
    
    await query.answer(
        "🤖 ابتدا باید ربات را در پیام خصوصی استارت کنید!",
        show_alert=True
    )

def ensure_text_content(text: str, fallback: str = "📱 پیام بدون محتوا") -> str:
    """اطمینان از وجود محتوای متنی برای تلگرام"""
    if not text or text.strip() == "":
        return fallback
    return text.strip()

def get_card_image_path(card_name: str, config: Dict) -> Optional[str]:
    """دریافت مسیر تصویر کارت با بررسی دقیق‌تر"""
    if not config.get('image_settings', {}).get('enable_images', False):
        logger.debug(f"Images disabled in config for card: {card_name}")
        return None
    
    images_path = config.get('image_settings', {}).get('card_images_path', '/root/card game/card_images/')
    default_image = config.get('image_settings', {}).get('default_card_image', '/root/card game/card_images/default.png')
    
    # اطمینان از وجود پوشه
    os.makedirs(images_path, exist_ok=True)
    os.makedirs(os.path.dirname(default_image), exist_ok=True)
    
    # جستجو برای تصویر کارت با چندین فرمت
    card_filename = card_name.lower().replace(' ', '_').replace('-', '_')
    possible_extensions = ['.png', '.jpg', '.jpeg', '.webp']
    
    for ext in possible_extensions:
        card_image = os.path.join(images_path, f"{card_filename}{ext}")
        if os.path.exists(card_image):
            logger.debug(f"Found card image: {card_image}")
            return card_image
    
    # اگر تصویر کارت پیدا نشد، از تصویر پیش‌فرض استفاده کن
    if os.path.exists(default_image):
        logger.debug(f"Using default image: {default_image}")
        return default_image
    
    logger.warning(f"No image found for card: {card_name}, checked: {images_path}")
    return None

def get_victory_dialog(card_name: str) -> str:
    """Gets a random victory dialog for a card. Supports both old and new formats."""
    dialogs_file = "card_dialogs.json"
    
    # Try to read from the json file
    if os.path.exists(dialogs_file):
        try:
            with open(dialogs_file, 'r', encoding='utf-8') as f:
                all_dialogs = json.load(f)
                entry = all_dialogs.get(card_name)
                lines: List[str] = []
                if isinstance(entry, list):
                    # Old format: list of lines
                    lines = entry
                elif isinstance(entry, dict):
                    # New format: { biography: str, victory_lines: list }
                    vl = entry.get('victory_lines', [])
                    if isinstance(vl, list):
                        lines = vl
                    elif isinstance(vl, str) and vl:
                        lines = [vl]
                if lines:
                    return random.choice(lines)
        except Exception:
            pass  # Fallback to generic
    
    # Generic dialogs as a fallback
    generic = [
        "Another victory!",
        "No one can defeat me!",
        "This was just the beginning!",
        "True power is here!"
    ]
    return random.choice(generic)

async def send_card_image_safely(message, card_name: str, config: Dict, caption: str = None, match_id: str = None, dialog_text: str = None) -> bool:
    try:
        image_path = get_card_image_path(card_name, config)
        if not image_path or not os.path.exists(image_path):
            logger.warning(f'Image not found for {card_name}')
            return False

        # Check if the image is a webp file
        if image_path.lower().endswith('.webp'):
            with open(image_path, 'rb') as sticker:
                await message.reply_sticker(sticker)
                logger.info(f'Sticker sent for {card_name}')
            if match_id and dialog_text:
                text_to_send = f'🎴 {card_name}\n\n💬 {dialog_text}'
                keyboard = [[InlineKeyboardButton('ℹ️ اطلاعات بیشتر', callback_data=f'match_info_{match_id}')]]
                await message.reply_text(text_to_send, reply_markup=InlineKeyboardMarkup(keyboard))
            elif caption:
                await message.reply_text(caption)
        else:
            with open(image_path, 'rb') as photo:
                await message.reply_document(document=photo, caption=caption)
                logger.info(f'Sent document for {card_name}')
        return True

    except Exception as e:
        logger.error(f'Failed to send image/sticker for {card_name}: {e}')
        return False

# ==================== PANEL EXPIRATION FUNCTIONS ====================

def ensure_not_expired(query, db: DatabaseManager = None, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    """Check if a callback query is from an expired panel. Auto-expires after 15 minutes in any chat.
    Also cancels ghost fights in DB and notifies group if possible.
    """
    try:
        if not query.message or not query.message.date:
            return True
        message_age = datetime.now().timestamp() - query.message.date.timestamp()
        if message_age > PANEL_TIMEOUT:
            # پاکسازی فایت‌های منقضی و لغو آن‌ها
            try:
                (db or DatabaseManager()).cleanup_expired_fights(15)
            except Exception as e:
                logger.warning(f"Cleanup on expiration failed: {e}")
            
            # تلاش برای استخراج fight_id از callback برای اطلاع‌رسانی
            try:
                data = query.data or ""
                fight_id = None
                for prefix in ["accept_pvp_", "accept_pvp_random_", "pvp_card_", "pvp_stat_"]:
                    if data.startswith(prefix):
                        parts = data.split("_")
                        fight_id = parts[2] if prefix in ["pvp_card_", "pvp_stat_"] else parts[-1]
                        break
                
                # Schedule notification as a background task
                if fight_id and context:
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        loop.create_task(
                            context.bot.send_message(
                                chat_id=query.message.chat_id, 
                                text="⏰ چالش منقضی شد"
                            )
                        )
                        logger.info(f"Scheduled expiration notification for chat {query.message.chat_id}")
                    except Exception as e:
                        logger.warning(f"Failed to schedule expiration notification: {e}")

            except Exception as e:
                logger.error(f"Error during expiration notification logic: {e}")

            return False
        return True
    except Exception as e:
        logger.error(f"Error checking panel expiration: {e}")
        return True

# ==================== MAIN BOT CLASS ====================

from bot.handlers.basic import BasicHandlersMixin
from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.shop import ShopHandlersMixin
from bot.handlers.fusion import FusionHandlersMixin
from bot.handlers.risk import RiskHandlersMixin
from bot.handlers.pvp import PvPHandlersMixin


class TelegramCardBot(
    BasicHandlersMixin,
    BattleHandlersMixin,
    ShopHandlersMixin,
    FusionHandlersMixin,
    RiskHandlersMixin,
    PvPHandlersMixin,
):
    def __init__(self, config_path: str = "game_config.json"):
        # بارگیری تنظیمات
        self.config = self._load_config(config_path)
        
        # راه‌اندازی سیستم‌های پایه
        self.db = DatabaseManager()
        self.game = GameLogic(self.db, self.config)
        self.card_manager = CardManager(self.db)

        # سیستم‌های فاز ۲
        self.fusion = FusionSystem(self.db)
        self.economy = EconomySystem(self.db)
        self.tier_decay = TierDecaySystem(self.db)
        self.risk = RiskModeSystem(self.db)
        self.battle3 = BattleSystem3Rounds(self.db)
        self.claim_sys = ClaimSystem(self.db)
        self.missions = CardMissionsSystem(self.db)
        self.skins = SkinsSystem(self.db)

        # حافظه موقت برای خلاصه مبارزات اخیر (برای دکمه اطلاعات بیشتر)
        self.recent_matches: Dict[str, Dict[str, Any]] = {}
        
        # تنظیمات ربات — env var اولویت داره (برای Railway)
        self.bot_token = (
            os.environ.get("BOT_TOKEN")
            or self.config.get('bot_settings', {}).get('token', '')
        )
        self.admin_ids = self.config['bot_settings']['admin_user_ids']
        
        if self.bot_token == "YOUR_BOT_TOKEN_HERE":
            raise ValueError("⚠ لطفاً توکن ربات را در game_config.json تنظیم کنید!")
        
        print(f"✅ ربات آماده شد با {len(self.admin_ids)} ادمین")
    
    def _load_config(self, config_path: str) -> Dict:
        """بارگیری یا ایجاد فایل تنظیمات"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # ایجاد فایل تنظیمات پیش‌فرض
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return DEFAULT_CONFIG

    # ==================== COMMAND SETUP ====================
    
    async def setup_bot_commands(self, application: Application):
        """تنظیم دستورات ربات برای محدوده‌های مختلف"""
        try:
            # تنظیم دستورات برای چت‌های خصوصی
            await application.bot.set_my_commands(
                commands=PRIVATE_CHAT_COMMANDS,
                scope=BotCommandScopeDefault()
            )
            logger.info(f"Set {len(PRIVATE_CHAT_COMMANDS)} commands for private chats")
            
            # تنظیم دستورات برای گروه‌ها
            await application.bot.set_my_commands(
                commands=GROUP_CHAT_COMMANDS,
                scope=BotCommandScopeAllGroupChats()
            )
            logger.info(f"Set {len(GROUP_CHAT_COMMANDS)} commands for group chats")
            
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")
    
    def _is_command_allowed_in_chat(self, command: str, chat_type: str) -> bool:
        """بررسی اینکه آیا دستور در نوع چت مجاز است"""
        if chat_type == 'private':
            allowed_commands = [cmd.command for cmd in PRIVATE_CHAT_COMMANDS]
        elif chat_type in ['group', 'supergroup']:
            allowed_commands = [cmd.command for cmd in GROUP_CHAT_COMMANDS]
        else:
            return False
        
        return command in allowed_commands

    # ==================== CHANNEL MEMBERSHIP CHECK ====================

    async def is_user_in_channel(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """بررسی عضویت کاربر در کانال الزامی"""
        try:
            if not REQUIRED_CHANNEL:
                return True
            member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            if member.status in ["member", "administrator", "creator"]:
                return True
            return False
        except telegram.error.BadRequest as e:
            logger.error(f"Error checking membership for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking channel membership: {e}")
            return False
    
    async def send_channel_join_message(self, update: Update) -> None:
        """ارسال پیام درخواست عضویت در کانال"""
        text = (
            f"📢 **عضویت در کانال الزامی است!**\n\n"
            f"برای استفاده از ربات، ابتدا باید در کانال رسمی ما عضو شوید:\n"
            f"👆 **{REQUIRED_CHANNEL}**\n\n"
            f"🔹 روی لینک بالا کلیک کنید\n"
            f"🔹 در کانال عضو شوید\n"
            f"🔹 سپس دوباره /start بزنید\n\n"
            f"✨ با عضویت در کانال از آخرین اخبار و به‌روزرسانی‌های بازی باخبر خواهید شد!"
        )
        
        keyboard = [
            [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
            [InlineKeyboardButton("🔄 بررسی عضویت", callback_data="check_membership")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Support both message updates and callback_query updates
        try:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            elif hasattr(update, 'callback_query') and update.callback_query:
                try:
                    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                except Exception:
                    # if edit fails (maybe message is not editable), send a new message
                    await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                # Fallback: send a direct message via bot if possible
                try:
                    await self.db  # noop to keep style consistent
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to send channel join message: {e}", exc_info=True)

    # Handler methods inherited from Mixin classes in bot/handlers/

    def setup_handlers(self, app: Application):
        """تنظیم هندلرهای ربات"""
        # دستورات اصلی
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("profile", self.profile_command))
        app.add_handler(CommandHandler("cards", self.cards_command))
        app.add_handler(CommandHandler("mycards", self.mycards_command))
        app.add_handler(CommandHandler("claim", self.claim_command))
        app.add_handler(CommandHandler("leaderboard", self.leaderboard_command))
        app.add_handler(CommandHandler("fight", self.fight_command))
        app.add_handler(CommandHandler("story", self.story_command))
        app.add_handler(CommandHandler("recalc", self.recalc_command))
        
        # کالبک‌های اصلی
        app.add_handler(CallbackQueryHandler(self.daily_claim_handler, pattern="^daily_claim$"))
        app.add_handler(CallbackQueryHandler(self.my_cards_handler, pattern="^my_cards$"))
        app.add_handler(CallbackQueryHandler(self.my_cards_navigation_handler, pattern="^my_cards_nav_"))
        app.add_handler(CallbackQueryHandler(self.start_game_handler, pattern="^start_game$"))
        
        # AI fight handlers removed - AI fights are no longer supported
        
        # فایت PvP
        app.add_handler(CallbackQueryHandler(self.request_pvp_fight_handler, pattern="^request_pvp_fight$"))
        app.add_handler(CallbackQueryHandler(self.accept_pvp_random_handler, pattern="^accept_pvp_random_"))
        app.add_handler(CallbackQueryHandler(self.accept_pvp_fight_handler, pattern="^accept_pvp_"))
        app.add_handler(CallbackQueryHandler(self.pvp_cards_navigation_handler, pattern="^pvp_cards_"))
        app.add_handler(CallbackQueryHandler(self.pvp_card_select_handler, pattern="^pvp_card_"))
        app.add_handler(CallbackQueryHandler(self.pvp_stat_select_handler, pattern="^pvp_stat_"))
        
        # عضویت کانال
        app.add_handler(CallbackQueryHandler(self.check_membership_handler, pattern="^check_membership$"))
        
        # مدیریت کارت‌ها
        app.add_handler(CallbackQueryHandler(self.mycards_navigation_handler, pattern="^mycards_"))
        app.add_handler(CallbackQueryHandler(self.cardinfo_handler, pattern="^cardinfo_"))
        app.add_handler(CallbackQueryHandler(self.toggle_favorite_handler, pattern="^toggle_fav_"))

        # ==================== فاز ۲: 3-Round Battle ====================
        app.add_handler(CallbackQueryHandler(self.r3_stat_select_handler, pattern="^r3_stat_"))
        app.add_handler(CallbackQueryHandler(self.r3_ability_handler, pattern="^r3_ability_"))
        app.add_handler(CallbackQueryHandler(self.arena_pick_handler, pattern="^arena_pick_"))

        # ==================== فاز ۲: Missions ====================
        app.add_handler(CallbackQueryHandler(self.mission_claim_handler, pattern="^mission_claim_"))

        # ==================== فاز ۲: Skins ====================
        app.add_handler(CallbackQueryHandler(self.skins_menu_handler, pattern="^skins_menu_"))
        app.add_handler(CallbackQueryHandler(self.skin_buy_handler, pattern="^skin_buy_"))
        app.add_handler(CallbackQueryHandler(self.skin_activate_handler, pattern="^skin_activate_"))
        app.add_handler(CallbackQueryHandler(self.skin_deactivate_handler, pattern="^skin_deactivate_"))
        
        # لیدربورد
        app.add_handler(CallbackQueryHandler(self.leaderboard_handler, pattern="^leaderboard$"))
        app.add_handler(CallbackQueryHandler(self.leaderboard_display_handler, pattern="^lb_global_"))
        app.add_handler(CallbackQueryHandler(self.leaderboard_display_handler, pattern="^lb_group_"))
        
        # سایر کالبک‌ها
        app.add_handler(CallbackQueryHandler(self.help_command, pattern="^help$"))
        app.add_handler(CallbackQueryHandler(self.card_view_handler, pattern="^card_view_"))
        app.add_handler(CallbackQueryHandler(self.back_to_main_handler, pattern="^back_to_main$"))
        app.add_handler(CallbackQueryHandler(self.match_info_handler, pattern="^match_info_"))
        app.add_handler(CallbackQueryHandler(self.cooldown_card_handler, pattern="^cooldown_card_"))

        # ==================== فاز ۲: Fusion ====================
        app.add_handler(CallbackQueryHandler(self.fusion_menu_handler, pattern="^fusion_menu$"))
        app.add_handler(CallbackQueryHandler(self.fusion_noop_handler, pattern="^fusion_noop$"))
        app.add_handler(CallbackQueryHandler(self.fusion_start_handler, pattern="^fusion_start_"))
        app.add_handler(CallbackQueryHandler(self.fusion_pick_handler, pattern="^fusion_pick_"))
        app.add_handler(CallbackQueryHandler(self.fusion_confirm_handler, pattern="^fusion_confirm_"))
        app.add_handler(CallbackQueryHandler(self.fusion_upgrade_handler, pattern="^fusion_upgrade_"))

        # ==================== فاز ۲: Mining ====================
        app.add_handler(CallbackQueryHandler(self.mining_claim_handler, pattern="^mining_claim$"))

        # ==================== فاز ۲: Shop ====================
        app.add_handler(CallbackQueryHandler(self.shop_menu_handler, pattern="^shop_menu$"))
        app.add_handler(CallbackQueryHandler(self.shop_buy_heart_handler, pattern="^shop_buy_heart$"))
        app.add_handler(CallbackQueryHandler(self.shop_upgrade_handler, pattern="^shop_upgrade_"))
        app.add_handler(CallbackQueryHandler(self.shop_confirm_upgrade_handler, pattern="^shop_confirm_"))
        app.add_handler(CallbackQueryHandler(self.shop_convert_score_handler, pattern="^shop_convert_score$"))
        app.add_handler(CallbackQueryHandler(self.shop_do_convert_handler, pattern="^shop_do_convert_"))
        app.add_handler(CallbackQueryHandler(self.shop_skins_list_handler, pattern="^shop_skins_list$"))

        # ==================== فاز ۲: Risk Mode ====================
        app.add_handler(CallbackQueryHandler(self.risk_menu_handler, pattern="^risk_menu$"))
        app.add_handler(CallbackQueryHandler(self.risk_noop_handler, pattern="^risk_noop$"))
        app.add_handler(CallbackQueryHandler(self.risk_challenge_handler, pattern="^risk_challenge_"))
        app.add_handler(CallbackQueryHandler(self.risk_accept_handler, pattern="^risk_accept_"))
        app.add_handler(CallbackQueryHandler(self.risk_card_select_handler, pattern="^risk_card_"))
        app.add_handler(CallbackQueryHandler(self.risk_bluff_handler, pattern="^risk_bluff_"))
        

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """هندلر خطاها"""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

    async def cleanup_task(self, context: ContextTypes.DEFAULT_TYPE):
        """تسک تمیزکردن فایت‌های منقضی"""
        deleted_count = self.db.cleanup_expired_fights()
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired PvP fights")

    async def reset_lives_task(self, context: ContextTypes.DEFAULT_TYPE):
        """Daily task: reset all players' lives to default if needed"""
        try:
            updated = self.db.reset_all_player_lives()
            if updated > 0:
                logger.info(f"Reset lives for {updated} players")
        except Exception as e:
            logger.error(f"Error running reset_lives_task: {e}")

    async def tier_decay_task(self, context: ContextTypes.DEFAULT_TYPE):
        """تسک روزانه Tier Decay"""
        try:
            stats = self.tier_decay.apply_decay_to_all_players()
            logger.info(
                f"Tier Decay applied: {stats['decayed_players']}/{stats['total_players']} players, "
                f"{stats['tier_changes']} tier changes, {stats['total_tp_lost']} TP lost"
            )
        except Exception as e:
            logger.error(f"Error in tier_decay_task: {e}", exc_info=True)

    async def weekly_leaderboard_task(self, context: ContextTypes.DEFAULT_TYPE):
        """تسک هفتگی — پاداش لیدربرد"""
        try:
            rewards = {1: 100, 2: 50, 3: 30}
            rank_4_10 = 10

            leaderboard = self.db.get_leaderboard_by_timeframe(timeframe="weekly", limit=10)
            if not leaderboard:
                logger.info("Weekly leaderboard: no players found")
                return

            awarded = []
            for i, player_data in enumerate(leaderboard[:10], 1):
                uid = player_data['user_id']
                coins = rewards.get(i, rank_4_10 if i <= 10 else 0)
                if coins > 0:
                    self.db.add_coins(uid, coins)
                    self.db.add_xp(uid, {1: 100, 2: 50, 3: 30}.get(i, 0))
                    awarded.append((i, uid, coins))

            logger.info(f"Weekly leaderboard rewards distributed: {awarded}")

            # اطلاع‌رسانی به بازیکنان برتر
            for rank, uid, coins in awarded[:3]:
                rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}[rank]
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=(
                            f"{rank_emoji} **لیدربرد هفتگی**\n\n"
                            f"رتبه {rank} هفته گذشته!\n"
                            f"💰 +{coins} سکه به حسابت اضافه شد!"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error in weekly_leaderboard_task: {e}", exc_info=True)

# ==================== IMAGE SETUP HELPER ====================


def setup_image_directories(config: Dict):
    """ایجاد پوشه‌های مورد نیاز برای تصاویر"""
    image_settings = config.get('image_settings', {})
    
    if not image_settings.get('enable_images', False):
        return
    
    # ایجاد پوشه‌های مورد نیاز
    cards_path = image_settings.get('card_images_path', '/root/card game/card_images/')
    os.makedirs(cards_path, exist_ok=True)
    os.makedirs(os.path.dirname(cards_path), exist_ok=True)
    
    print(f"🖼 پوشه‌های تصاویر آماده شد:")
    print(f"   🎴 کارت‌ها: {cards_path}")

# ==================== MAIN FUNCTION ====================

def main():
    """اجرای ربات - ورژن کامل و اصلاح شده با PvP + بررسی کانال"""
    # print("🤖 شروع راه‌اندازی ربات...")
    
    try:
        # ایجاد ربات
        bot = TelegramCardBot()
        
        # تنظیم پوشه‌های تصاویر
        setup_image_directories(bot.config)
        
        # بررسی وجود کارت‌ها
        cards = bot.db.get_all_cards()
        if not cards:
            print("📦 ایجاد کارت‌های نمونه...")
            added = bot.card_manager.create_sample_cards()
            print(f"✅ {added} کارت اضافه شد!")
        else:
            print(f"✅ {len(cards)} کارت در دیتابیس موجود است")
        
        # ایجاد اپلیکیشن
        application = Application.builder().token(bot.bot_token).build()
        
        # تنظیم هندلرها
        bot.setup_handlers(application)
        application.add_error_handler(bot.error_handler)
        
        # تنظیم تسک تمیزکردن (اگر JobQueue در دسترس باشد)
        if application.job_queue:
            application.job_queue.run_repeating(bot.cleanup_task, interval=3600, first=10)
            application.job_queue.run_repeating(bot.reset_lives_task, interval=86400, first=20)
            application.job_queue.run_repeating(bot.tier_decay_task, interval=86400, first=30)
            application.job_queue.run_repeating(bot.weekly_leaderboard_task, interval=604800, first=60)
            print("✅ تسک‌های تمیزکاری، Tier Decay و لیدربرد هفتگی فعال شدند")
        else:
            print("⚠️ JobQueue در دسترس نیست - تمیزکاری خودکار غیرفعال")
        
        # اطلاعات راه‌اندازی
        print("🎮 ربات بازی کارت تلگرام با قابلیت PvP اصلاح شده")
        print("=" * 50)
        print(f"✅ ربات آماده است!")
        print(f"🎴 تعداد کارت‌ها: {len(bot.db.get_all_cards())}")
        print(f"👥 تعداد ادمین‌ها: {len(bot.admin_ids)}")
        print(f"🖼️ پشتیبانی از تصاویر: {'✅' if bot.config.get('image_settings', {}).get('enable_images', False) else '❌'}")
        print(f"🥊 قابلیت PvP: ✅ فعال و اصلاح شده")
        print(f"⏰ پنل‌ها منقضی می‌شوند بعد از: {PANEL_TIMEOUT // 60} دقیقه")
        print(f"🔧 مشکل انتخاب کارت در PvP: ✅ برطرف شده")
        print(f"📢 کانال الزامی: {REQUIRED_CHANNEL}")
        print(f"🔒 بررسی عضویت: ✅ فعال")
        print(f"🔥 برای شروع در تلگرام /start بزنید!")
        print("=" * 50)
        
        # تنظیم رویداد بعد از راه‌اندازی برای تنظیم دستورات
        async def post_init(app):
            await bot.setup_bot_commands(app)
            print("✅ دستورات ربات برای محدوده‌های مختلف تنظیم شد")
        
        application.post_init = post_init
        
        # شروع ربات
        print("🚀 ربات در حال اجرا...")
        application.run_polling(drop_pending_updates=True)
        
    except KeyboardInterrupt:
        print("\n👋 ربات متوقف شد!")
    except Exception as e:
        print(f"\n⚠ خطای کلی: {e}")
        logger.error(f"Critical error: {e}", exc_info=True)

if __name__ == "__main__":
    # اجرای ربات
    main()