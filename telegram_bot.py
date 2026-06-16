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
from fusion_system import FusionSystem
from phase2_systems import LevelSystem, TierSystem, format_xp_bar, format_tier_badge
from economy_system import EconomySystem
from tier_decay_system import TierDecaySystem
from risk_mode_system import RiskModeSystem, RiskTable, RiskAction
from battle_system_3rounds import BattleSystem3Rounds, BattleState, ARENAS
from claim_system import ClaimSystem
from card_missions_system import CardMissionsSystem, MISSION_TYPES
from skins_system import SkinsSystem, SKIN_TYPES

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

class TelegramCardBot:
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

    # ==================== COMMAND HANDLERS ====================

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

    async def _init_3round_battle(self, context, fight_id: str, fight, query=None):
        """شروع سیستم ۳ راوندی بعد از انتخاب کارت‌ها"""
        import json as _json
        import sqlite3 as _sq

        challenger_card = self.db.get_card_by_id_for_player(fight.challenger_card_id, fight.challenger_id) \
                          or self.db.get_card_by_id(fight.challenger_card_id)
        opponent_card = self.db.get_card_by_id_for_player(fight.opponent_card_id, fight.opponent_id) \
                        or self.db.get_card_by_id(fight.opponent_card_id)

        if not challenger_card or not opponent_card:
            logger.error(f"Cards not found for fight {fight_id}")
            return

        # انتخاب زمین — اگه rarity برابر بود random، وگرنه بازیکن ضعیف‌تر انتخاب می‌کنه
        arena_id, selector_role = self.battle3.select_arena(challenger_card, opponent_card)

        if selector_role:
            # یه بازیکن باید زمین رو انتخاب کنه
            selector_id = fight.challenger_id if selector_role == "challenger" else fight.opponent_id
            # ذخیره موقت در context
            context.bot_data[f"arena_selector_{fight_id}"] = {
                "selector_id": selector_id,
                "fight_id": fight_id,
                "challenger_card": challenger_card,
                "opponent_card": opponent_card,
                "fight": fight,
                "query": None
            }
            # ارسال UI انتخاب زمین
            await self._send_arena_selection(context, fight_id, selector_id, fight.chat_id)
            if query:
                try:
                    await query.edit_message_text("✅ کارت انتخاب شد!\n⏳ منتظر انتخاب زمین...", parse_mode='Markdown')
                except Exception:
                    pass
            return

        # زمین random انتخاب شد — مستقیم شروع کن
        await self._start_battle_with_arena(context, fight_id, fight, challenger_card, opponent_card, arena_id, query)

    async def _send_arena_selection(self, context, fight_id: str, selector_id: int, chat_id: int):
        """ارسال UI انتخاب زمین به بازیکن ضعیف‌تر"""
        text = (
            "🏟️ **انتخاب زمین بازی**\n\n"
            "کارت تو ضعیف‌تره، پس تو زمین رو انتخاب می‌کنی!\n\n"
            "کدام زمین؟"
        )
        keyboard = []
        for arena_id, info in ARENAS.items():
            keyboard.append([InlineKeyboardButton(
                f"{info['emoji']} {info['name_fa']} — Boost: {info['boost_stat']}",
                callback_data=f"arena_pick_{fight_id}_{arena_id}"
            )])

        try:
            await context.bot.send_message(
                chat_id=selector_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send arena selection to {selector_id}: {e}")
            # fallback: random arena
            import random as _random
            arena_id = _random.choice(list(ARENAS.keys()))
            data = context.bot_data.get(f"arena_selector_{fight_id}", {})
            if data:
                await self._start_battle_with_arena(
                    context, fight_id, data['fight'],
                    data['challenger_card'], data['opponent_card'],
                    arena_id, None
                )

    async def arena_pick_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بازیکن زمین رو انتخاب کرد"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # arena_pick_{fight_id}_{arena_id}
        parts = query.data.split("_", 3)
        fight_id = parts[2]
        arena_id = parts[3]

        # بررسی اینکه این بازیکن selector هست
        data = context.bot_data.get(f"arena_selector_{fight_id}")
        if not data or data['selector_id'] != user_id:
            await query.answer("❌ این انتخاب مال تو نیست!", show_alert=True)
            return

        context.bot_data.pop(f"arena_selector_{fight_id}", None)

        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            await query.answer("❌ فایت یافت نشد!", show_alert=True)
            return

        challenger_card = data['challenger_card']
        opponent_card = data['opponent_card']

        arena_info = ARENAS[arena_id]
        await query.edit_message_text(
            f"✅ زمین انتخاب شد: {arena_info['emoji']} **{arena_info['name_fa']}**",
            parse_mode='Markdown'
        )

        await self._start_battle_with_arena(context, fight_id, fight, challenger_card, opponent_card, arena_id, None)

    async def _start_battle_with_arena(self, context, fight_id: str, fight, challenger_card, opponent_card, arena_id: str, query):
        """شروع بازی با زمین مشخص‌شده"""
        import json as _json
        import sqlite3 as _sq

        arena_info = ARENAS[arena_id]

        ch_stats = {"power": challenger_card.power, "speed": challenger_card.speed,
                    "iq": challenger_card.iq, "popularity": challenger_card.popularity}
        op_stats = {"power": opponent_card.power, "speed": opponent_card.speed,
                    "iq": opponent_card.iq, "popularity": opponent_card.popularity}

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO battle_states
            (fight_id, challenger_id, opponent_id, challenger_card_id, opponent_card_id,
             arena, current_round, challenger_rounds_won, opponent_rounds_won,
             challenger_used_stats, opponent_used_stats,
             challenger_current_stats, opponent_current_stats, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, 0, 0, '[]', '[]', ?, ?, 'round_1', ?)
        ''', (fight_id, fight.challenger_id, fight.opponent_id,
              fight.challenger_card_id, fight.opponent_card_id,
              arena_id, _json.dumps(ch_stats), _json.dumps(op_stats),
              datetime.now().isoformat()))
        conn.commit()
        conn.close()

        # اعلام زمین در گروه
        if fight.chat_id:
            arena_text = (
                f"⚔️ **فایت شروع شد!**\n\n"
                f"🏟️ زمین: {arena_info['emoji']} **{arena_info['name_fa']}**\n"
                f"💡 Boost: کارت‌های {arena_info['boost_stat']} در این زمین +۱ می‌گیرند\n\n"
                f"هر دو بازیکن در PV ویژگی راوند ۱ را انتخاب کنید!"
            )
            try:
                await context.bot.send_message(chat_id=fight.chat_id, text=arena_text, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Failed to send arena message: {e}")

        await self._send_round_stat_selection(context, fight_id, fight.challenger_id, challenger_card, arena_id, round_num=1, used_stats=[], opponent_card=opponent_card, ability_used=False)
        await self._send_round_stat_selection(context, fight_id, fight.opponent_id, opponent_card, arena_id, round_num=1, used_stats=[], opponent_card=challenger_card, ability_used=False)

        if query:
            try:
                await query.edit_message_text("✅ کارت انتخاب شد!\n⏳ منتظر شروع راوند ۱...", parse_mode='Markdown')
            except Exception:
                pass

    async def _send_round_stat_selection(self, context, fight_id: str, user_id: int,
                                          card, arena_id: str, round_num: int, used_stats: list,
                                          opponent_card=None, ability_used: bool = False):
        """ارسال UI انتخاب stat برای یک راوند"""
        from battle_system_3rounds import ABILITIES, get_card_ability
        
        arena_info = ARENAS[arena_id]
        boost_stat = arena_info['boost_stat']

        stat_labels = {
            "power": ("💪", "قدرت"),
            "speed": ("⚡", "سرعت"),
            "iq": ("🧠", "هوش"),
            "popularity": ("❤️", "محبوبیت")
        }

        keyboard = []
        for stat, (emoji, name) in stat_labels.items():
            if stat in used_stats:
                continue  # stat locking
            val = getattr(card, stat)
            boost_hint = " 🔥+8" if stat == boost_stat and getattr(card, 'card_type', '') == f"{stat.upper()}_TYPE" else ""
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {name}: {val}{boost_hint}",
                callback_data=f"r3_stat_{fight_id}_{stat}"
            )])

        # دکمه ابیلیتی (اگه هنوز مصرف نشده و کارت ابیلیتی داره)
        ability_info_text = ""
        card_ability = get_card_ability(card)
        if card_ability and not ability_used:
            ab = ABILITIES[card_ability]
            keyboard.append([InlineKeyboardButton(
                f"🪄 {ab['emoji']} {ab['name_fa']}: {ab['description']}",
                callback_data=f"r3_ability_{fight_id}_{card_ability}"
            )])
            ability_info_text = f"\n🪄 ابیلیتی: {ab['emoji']} {ab['name_fa']} (یک‌بار مصرف)"
        elif card_ability and ability_used:
            ability_info_text = "\n🪄 ابیلیتی: ✅ مصرف شده"

        # اطلاعات حریف
        opponent_info = ""
        if opponent_card:
            type_labels = {
                "POWER_TYPE": "💪 قدرت",
                "SPEED_TYPE": "⚡ سرعت",
                "IQ_TYPE": "🧠 هوش",
                "POPULARITY_TYPE": "❤️ محبوبیت"
            }
            rarity_labels = {"normal": "معمولی", "epic": "حماسی", "legend": "افسانه‌ای", "rare": "کمیاب"}
            op_rarity = opponent_card.rarity.value if hasattr(opponent_card.rarity, 'value') else opponent_card.rarity
            op_type = type_labels.get(getattr(opponent_card, 'card_type', ''), '❓')
            op_rarity_fa = rarity_labels.get(op_rarity, op_rarity)

            if round_num == 1:
                # راوند ۱: فقط نوع و کمیابی
                opponent_info = (
                    f"\n🎯 حریف: **{opponent_card.name}**\n"
                    f"   نوع: {op_type} | کمیابی: {op_rarity_fa}\n"
                )
            else:
                # راوند ۲ و ۳: نمایش همه stat‌ها
                opponent_info = (
                    f"\n🎯 حریف: **{opponent_card.name}**\n"
                    f"   نوع: {op_type} | کمیابی: {op_rarity_fa}\n"
                    f"   💪{opponent_card.power} ⚡{opponent_card.speed} "
                    f"🧠{opponent_card.iq} ❤️{opponent_card.popularity}\n"
                )

        text = (
            f"⚔️ **راوند {round_num}**\n\n"
            f"🎴 کارت تو: **{card.name}**\n"
            f"🏟️ زمین: {arena_info['emoji']} {arena_info['name_fa']}"
            f"{ability_info_text}"
            f"{opponent_info}\n"
            f"ویژگی این راوند را انتخاب کن:"
        )

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send stat selection to {user_id}: {e}")

    async def r3_stat_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب stat در سیستم ۳ راوندی"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # r3_stat_{fight_id}_{stat}
        parts = query.data.split("_", 3)
        fight_id = parts[2]
        stat = parts[3]

        import json as _json
        import sqlite3 as _sq

        # دریافت battle_state
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT challenger_id, opponent_id, challenger_card_id, opponent_card_id,
                   arena, current_round, challenger_rounds_won, opponent_rounds_won,
                   challenger_used_stats, opponent_used_stats,
                   challenger_current_stats, opponent_current_stats, status
            FROM battle_states WHERE fight_id = ?
        ''', (fight_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            await query.answer("❌ بازی یافت نشد!", show_alert=True)
            return

        (ch_id, op_id, ch_card_id, op_card_id, arena_id, current_round,
         ch_rounds_won, op_rounds_won, ch_used_raw, op_used_raw,
         ch_stats_raw, op_stats_raw, status) = row

        if status == 'completed':
            await query.answer("❌ این بازی تمام شده!", show_alert=True)
            return

        # تعیین نقش
        if user_id == ch_id:
            role = 'challenger'
        elif user_id == op_id:
            role = 'opponent'
        else:
            await query.answer("❌ این بازی مال تو نیست!", show_alert=True)
            return

        ch_used = _json.loads(ch_used_raw)
        op_used = _json.loads(op_used_raw)
        ch_stats = _json.loads(ch_stats_raw)
        op_stats = _json.loads(op_stats_raw)

        # بررسی stat locking
        my_used = ch_used if role == 'challenger' else op_used
        if stat in my_used:
            await query.answer("❌ این ویژگی را قبلاً استفاده کردی!", show_alert=True)
            return

        # ذخیره انتخاب موقت در context
        key = f"r3_{fight_id}_{role}_stat"
        context.bot_data[key] = stat

        await query.edit_message_text(
            f"✅ **{stat} انتخاب شد!**\n\n⏳ منتظر حریف...",
            parse_mode='Markdown'
        )

        # بررسی اینکه هر دو انتخاب کردن
        other_role = 'opponent' if role == 'challenger' else 'challenger'
        other_key = f"r3_{fight_id}_{other_role}_stat"
        other_stat = context.bot_data.get(other_key)

        if other_stat:
            # هر دو انتخاب کردن → resolve راوند
            ch_stat = stat if role == 'challenger' else other_stat
            op_stat = other_stat if role == 'challenger' else stat

            # پاک کردن state موقت
            context.bot_data.pop(f"r3_{fight_id}_challenger_stat", None)
            context.bot_data.pop(f"r3_{fight_id}_opponent_stat", None)

            await self._resolve_3round(context, fight_id, ch_stat, op_stat,
                                        ch_id, op_id, ch_card_id, op_card_id,
                                        arena_id, current_round,
                                        ch_rounds_won, op_rounds_won,
                                        ch_used, op_used, ch_stats, op_stats)

    async def r3_ability_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال‌سازی ابیلیتی کارت (یک‌بار مصرف در کل نبرد)"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        import json as _json
        import sqlite3 as _sq

        # r3_ability_{fight_id}_{ability_key}
        parts = query.data.split("_", 3)
        # data format: r3_ability_FIGHTID_ABILITYKEY
        # split on "_" max 3: ['r3', 'ability', 'FIGHTID_ABILITYKEY']
        # better: split manually
        prefix = "r3_ability_"
        rest = query.data[len(prefix):]
        # fight_id is 8 chars, ability_key is the rest
        # safer: find last underscore-separated ability key
        # fight_id could contain underscores... let's use a different approach
        # format is actually: r3_ability_{fight_id}_{ability_key} where fight_id is 8 chars
        fight_id = rest[:8]
        ability_key = rest[9:]  # skip the underscore after fight_id

        from battle_system_3rounds import ABILITIES, get_card_ability

        if ability_key not in ABILITIES:
            await query.answer("❌ ابیلیتی نامعتبر!", show_alert=True)
            return

        # دریافت battle_state
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT challenger_id, opponent_id, challenger_ability_used, opponent_ability_used
            FROM battle_states WHERE fight_id = ?
        ''', (fight_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            await query.answer("❌ بازی یافت نشد!", show_alert=True)
            return

        ch_id, op_id, ch_ab_used, op_ab_used = row

        # تعیین نقش
        if user_id == ch_id:
            role = 'challenger'
            already_used = bool(ch_ab_used)
        elif user_id == op_id:
            role = 'opponent'
            already_used = bool(op_ab_used)
        else:
            conn.close()
            await query.answer("❌ این بازی مال تو نیست!", show_alert=True)
            return

        if already_used:
            conn.close()
            await query.answer("❌ ابیلیتی قبلاً مصرف شده!", show_alert=True)
            return

        # ثبت ابیلیتی pending (برای اعمال در resolve)
        context.bot_data[f"r3_{fight_id}_{role}_ability"] = ability_key

        # ثبت در DB که ابیلیتی مصرف شد
        col = "challenger_ability_used" if role == "challenger" else "opponent_ability_used"
        cursor.execute(f'UPDATE battle_states SET {col} = 1 WHERE fight_id = ?', (fight_id,))
        conn.commit()
        conn.close()

        ab = ABILITIES[ability_key]
        await query.answer(f"🪄 {ab['name_fa']} فعال شد! حالا stat رو انتخاب کن.", show_alert=True)

        # دکمه ابیلیتی حذف شود — re-edit message بدون دکمه ابیلیتی
        # فقط متن تأیید بزنیم
        try:
            await query.edit_message_text(
                f"🪄 **{ab['emoji']} {ab['name_fa']} فعال شد!**\n\n"
                f"💡 {ab['description']}\n\n"
                f"حالا ویژگی راوند رو انتخاب کن ↓",
                parse_mode='Markdown'
            )
        except Exception:
            pass

    async def _resolve_3round(self, context, fight_id: str,
                               ch_stat: str, op_stat: str,
                               ch_id: int, op_id: int,
                               ch_card_id: str, op_card_id: str,
                               arena_id: str, current_round: int,
                               ch_rounds_won: int, op_rounds_won: int,
                               ch_used: list, op_used: list,
                               ch_stats: dict, op_stats: dict):
        """حل یک راوند و تصمیم‌گیری برای ادامه یا پایان"""
        import json as _json
        import sqlite3 as _sq

        arena_info = ARENAS[arena_id]
        boost_stat = arena_info['boost_stat']

        ch_card = self.db.get_card_by_id_for_player(ch_card_id, ch_id) or self.db.get_card_by_id(ch_card_id)
        op_card = self.db.get_card_by_id_for_player(op_card_id, op_id) or self.db.get_card_by_id(op_card_id)

        # مقادیر فعلی (کاهش‌یافته)
        ch_base = ch_stats.get(ch_stat, 0)
        op_base = op_stats.get(op_stat, 0)

        # محاسبه boost
        ch_boost = self.battle3.calculate_boost(ch_card, arena_id, ch_stat)
        op_boost = self.battle3.calculate_boost(op_card, arena_id, op_stat)

        # محاسبه بونوس برتری تایپ (Type Counter)
        from battle_system_3rounds import TYPE_COUNTER, TYPE_COUNTER_BONUS
        ch_type = getattr(ch_card, 'card_type', '') or ''
        op_type = getattr(op_card, 'card_type', '') or ''
        ch_counter = TYPE_COUNTER_BONUS if TYPE_COUNTER.get(ch_type) == op_type else 0
        op_counter = TYPE_COUNTER_BONUS if TYPE_COUNTER.get(op_type) == ch_type else 0

        ch_total = ch_base + ch_boost + ch_counter
        op_total = op_base + op_boost + op_counter

        # اعمال ابیلیتی‌های pending
        from battle_system_3rounds import ABILITIES
        ch_ability_key = context.bot_data.pop(f"r3_{fight_id}_challenger_ability", None)
        op_ability_key = context.bot_data.pop(f"r3_{fight_id}_opponent_ability", None)
        
        ability_texts = []
        if ch_ability_key:
            ch_total, op_total, ab_text = self.battle3.apply_ability(
                ch_ability_key, "challenger", ch_total, op_total,
                ch_base, op_base, ch_boost, op_boost)
            if ab_text:
                ability_texts.append(f"🪄 Challenger: {ab_text}")
        if op_ability_key:
            ch_total, op_total, ab_text = self.battle3.apply_ability(
                op_ability_key, "opponent", ch_total, op_total,
                ch_base, op_base, ch_boost, op_boost)
            if ab_text:
                ability_texts.append(f"🪄 Opponent: {ab_text}")

        # تعیین برنده راوند
        if ch_total > op_total:
            round_winner = 'challenger'
            win_margin = ch_total - op_total
        elif op_total > ch_total:
            round_winner = 'opponent'
            win_margin = op_total - ch_total
        else:
            round_winner = None
            win_margin = 0

        # کاهش stat بازنده (پررنگ‌تر شده)
        # اگه shield فعال شده، کاهش نصف بشه
        ch_has_shield = ch_ability_key == "shield"
        op_has_shield = op_ability_key == "shield"
        
        if round_winner == 'challenger':
            reduction = 8 if win_margin >= 15 else 5
            if op_has_shield:
                reduction = reduction // 2
            op_stats[op_stat] = max(0, op_stats[op_stat] - reduction)
            ch_rounds_won += 1
        elif round_winner == 'opponent':
            reduction = 8 if win_margin >= 15 else 5
            if ch_has_shield:
                reduction = reduction // 2
            ch_stats[ch_stat] = max(0, ch_stats[ch_stat] - reduction)
            op_rounds_won += 1
        else:
            ch_stats[ch_stat] = max(0, ch_stats[ch_stat] - 3)
            op_stats[op_stat] = max(0, op_stats[op_stat] - 3)

        # اضافه کردن به used_stats
        ch_used.append(ch_stat)
        op_used.append(op_stat)

        stat_names = {"power": "💪 قدرت", "speed": "⚡ سرعت", "iq": "🧠 هوش", "popularity": "❤️ محبوبیت"}

        if round_winner == 'challenger':
            winner_text = f"🏆 Challenger برنده راوند {current_round}!"
        elif round_winner == 'opponent':
            winner_text = f"🏆 Opponent برنده راوند {current_round}!"
        else:
            winner_text = f"🤝 راوند {current_round} مساوی!"

        # متن بونوس‌ها
        ch_bonus_text = f"{ch_base}"
        if ch_boost:
            ch_bonus_text += f" +{ch_boost}🔥"
        if ch_counter:
            ch_bonus_text += f" +{ch_counter}🔺"
        
        op_bonus_text = f"{op_base}"
        if op_boost:
            op_bonus_text += f" +{op_boost}🔥"
        if op_counter:
            op_bonus_text += f" +{op_counter}🔺"

        # متن ابیلیتی
        ability_section = ""
        if ability_texts:
            ability_section = "\n" + "\n".join(ability_texts) + "\n"

        round_text = (
            f"⚔️ **راوند {current_round} تموم شد!**\n\n"
            f"🏟️ {arena_info['emoji']} {arena_info['name_fa']}\n"
            f"{ability_section}\n"
            f"Challenger: {stat_names[ch_stat]} = {ch_bonus_text} = **{ch_total}**\n"
            f"Opponent: {stat_names[op_stat]} = {op_bonus_text} = **{op_total}**\n\n"
            f"{winner_text}\n"
            f"امتیاز: Challenger {ch_rounds_won} — Opponent {op_rounds_won}"
        )

        # بررسی پایان بازی
        game_over = ch_rounds_won >= 2 or op_rounds_won >= 2 or current_round >= 3

        if game_over:
            # تعیین برنده نهایی
            if ch_rounds_won > op_rounds_won:
                final_winner_id = ch_id
                final_loser_id = op_id
                final_result = "challenger_wins"
            elif op_rounds_won > ch_rounds_won:
                final_winner_id = op_id
                final_loser_id = ch_id
                final_result = "opponent_wins"
            else:
                final_winner_id = None
                final_loser_id = None
                final_result = "tie"

            # بروزرسانی battle_state
            conn = _sq.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE battle_states SET status='completed',
                challenger_rounds_won=?, opponent_rounds_won=?
                WHERE fight_id=?
            ''', (ch_rounds_won, op_rounds_won, fight_id))
            conn.commit()
            conn.close()

            round_text += f"\n\n{'🎉 بازی تموم شد!' if final_result != 'tie' else '🤝 مساوی نهایی!'}"

            # اعلام نتیجه نهایی در گروه
            fight = self.db.get_fight_by_id(fight_id)
            if fight and fight.chat_id:
                try:
                    await context.bot.send_message(chat_id=fight.chat_id, text=round_text, parse_mode='Markdown')
                except Exception:
                    pass

            # پاداش‌دهی
            await self._finalize_3round_battle(context, fight_id, fight,
                                                ch_card, op_card,
                                                final_winner_id, final_loser_id,
                                                final_result, ch_rounds_won, op_rounds_won)
        else:
            # راوند بعدی
            next_round = current_round + 1

            # بروزرسانی battle_state
            conn = _sq.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE battle_states SET
                current_round=?, challenger_rounds_won=?, opponent_rounds_won=?,
                challenger_used_stats=?, opponent_used_stats=?,
                challenger_current_stats=?, opponent_current_stats=?,
                status=?
                WHERE fight_id=?
            ''', (next_round, ch_rounds_won, op_rounds_won,
                  _json.dumps(ch_used), _json.dumps(op_used),
                  _json.dumps(ch_stats), _json.dumps(op_stats),
                  f'round_{next_round}', fight_id))
            conn.commit()
            conn.close()

            # اعلام نتیجه راوند در گروه
            fight = self.db.get_fight_by_id(fight_id)
            if fight and fight.chat_id:
                try:
                    await context.bot.send_message(chat_id=fight.chat_id, text=round_text, parse_mode='Markdown')
                except Exception:
                    pass

            # ارسال UI راوند بعدی
            # بررسی وضعیت ابیلیتی
            conn2 = _sq.connect(self.db.db_path)
            cursor2 = conn2.cursor()
            cursor2.execute('SELECT challenger_ability_used, opponent_ability_used FROM battle_states WHERE fight_id=?', (fight_id,))
            ab_row = cursor2.fetchone()
            conn2.close()
            ch_ab_used = bool(ab_row[0]) if ab_row else False
            op_ab_used = bool(ab_row[1]) if ab_row else False

            await self._send_round_stat_selection(context, fight_id, ch_id, ch_card, arena_id, next_round, ch_used, opponent_card=op_card, ability_used=ch_ab_used)
            await self._send_round_stat_selection(context, fight_id, op_id, op_card, arena_id, next_round, op_used, opponent_card=ch_card, ability_used=op_ab_used)

    async def _finalize_3round_battle(self, context, fight_id: str, fight,
                                       ch_card, op_card,
                                       winner_id, loser_id,
                                       result_type: str,
                                       ch_rounds_won: int, op_rounds_won: int):
        """پاداش‌دهی نهایی بازی ۳ راوندی"""
        from types import SimpleNamespace

        ch_id = fight.challenger_id
        op_id = fight.opponent_id

        # محاسبه امتیاز بر اساس rarity
        rarity_order = {CardRarity.NORMAL: 1, CardRarity.EPIC: 2, CardRarity.LEGEND: 3, CardRarity.RARE: 4}
        ch_rv = rarity_order.get(ch_card.rarity, 1)
        op_rv = rarity_order.get(op_card.rarity, 1)

        if result_type == "challenger_wins":
            score = 20 if ch_rv < op_rv else (10 if ch_rv == op_rv else 5)
            hearts_lost = 1
            ch_score, op_score = score, 0
            ch_hearts, op_hearts = 0, hearts_lost
        elif result_type == "opponent_wins":
            score = 20 if op_rv < ch_rv else (10 if op_rv == ch_rv else 5)
            hearts_lost = 1
            ch_score, op_score = 0, score
            ch_hearts, op_hearts = hearts_lost, 0
        else:  # tie
            ch_score, op_score = 0, 0
            ch_hearts, op_hearts = 0, 0

        # بروزرسانی بازیکنان
        ch_player = self.db.get_or_create_player(ch_id)
        op_player = self.db.get_or_create_player(op_id)
        ch_player.total_score += ch_score
        op_player.total_score += op_score
        ch_player.hearts = max(0, ch_player.hearts - ch_hearts)
        op_player.hearts = max(0, op_player.hearts - op_hearts)
        self.db.update_player(ch_player)
        self.db.update_player(op_player)

        # XP و Tier
        from phase2_systems import TierSystem, XP_SOURCES
        xp_src = XP_SOURCES
        if result_type == "challenger_wins":
            ch_xp, op_xp = xp_src["normal_win"], xp_src["normal_loss"]
        elif result_type == "opponent_wins":
            ch_xp, op_xp = xp_src["normal_loss"], xp_src["normal_win"]
        else:
            ch_xp = op_xp = xp_src["normal_loss"]

        ch_old_lv, ch_new_lv = self.db.add_xp(ch_id, ch_xp)
        op_old_lv, op_new_lv = self.db.add_xp(op_id, op_xp)

        ch_prog = self.db.get_or_create_progression(ch_id)
        op_prog = self.db.get_or_create_progression(op_id)
        if result_type != "tie":
            w_tier = ch_prog['current_tier'] if result_type == "challenger_wins" else op_prog['current_tier']
            l_tier = op_prog['current_tier'] if result_type == "challenger_wins" else ch_prog['current_tier']
            tp_gain, tp_loss = TierSystem.calculate_tp_change(w_tier, l_tier)
            if result_type == "challenger_wins":
                self.db.add_tier_points(ch_id, tp_gain)
                self.db.add_tier_points(op_id, -tp_loss)
            else:
                self.db.add_tier_points(op_id, tp_gain)
                self.db.add_tier_points(ch_id, -tp_loss)

        # ثبت در fight_history
        import sqlite3 as _sq
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        ch_result = "win" if result_type == "challenger_wins" else ("loss" if result_type == "opponent_wins" else "tie")
        op_result = "win" if result_type == "opponent_wins" else ("loss" if result_type == "challenger_wins" else "tie")
        cursor.execute('''INSERT INTO fight_history
            (user_id, user_card_id, opponent_card_id, result, score_gained, hearts_lost, fought_at, fight_type, opponent_user_id, xp_gained)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pvp', ?, ?)''',
            (ch_id, ch_card.card_id, op_card.card_id, ch_result, ch_score, ch_hearts, now, op_id, ch_xp))
        cursor.execute('''INSERT INTO fight_history
            (user_id, user_card_id, opponent_card_id, result, score_gained, hearts_lost, fought_at, fight_type, opponent_user_id, xp_gained)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pvp', ?, ?)''',
            (op_id, op_card.card_id, ch_card.card_id, op_result, op_score, op_hearts, now, ch_id, op_xp))
        conn.commit()
        conn.close()

        self.db.update_fight(fight_id, status='completed')

        # ==================== آپدیت ماموریت‌ها ====================
        # برای هر بازیکن، اگه کارتش ماموریت داره، progress رو آپدیت کن
        for uid, card, result_str, winning_stat in [
            (ch_id, ch_card, ch_result, None),
            (op_id, op_card, op_result, None)
        ]:
            try:
                match_data = {
                    "won": result_str == "win",
                    "match_type": "pvp",
                    "opponent_card_id": op_card.card_id if uid == ch_id else ch_card.card_id,
                }
                update = self.missions.check_and_update_mission(uid, card.card_id, match_data)
                if update and update.get('just_completed'):
                    try:
                        await context.bot.send_message(
                            chat_id=uid,
                            text=(
                                f"🎯 **ماموریت تکمیل شد!**\n\n"
                                f"کارت **{card.name}** ماموریتش رو تموم کرد!\n"
                                f"برو به منوی کارت‌ها و پاداش Legend رو بگیر! 🏆"
                            ),
                            parse_mode='Markdown'
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Mission update failed for {uid}: {e}")

        # اعلام نهایی در گروه
        if fight and fight.chat_id:
            if result_type == "tie":
                final_text = "🤝 **مساوی نهایی!**\n\nهیچ‌کدام برنده نشدند."
            else:
                winner_card = ch_card if result_type == "challenger_wins" else op_card
                winner_xp = ch_xp if result_type == "challenger_wins" else op_xp
                loser_xp = op_xp if result_type == "challenger_wins" else ch_xp
                level_up_text = ""
                if result_type == "challenger_wins" and ch_new_lv > ch_old_lv:
                    level_up_text = f"\n⬆️ Level Up! → {ch_new_lv}"
                elif result_type == "opponent_wins" and op_new_lv > op_old_lv:
                    level_up_text = f"\n⬆️ Level Up! → {op_new_lv}"

                victory_msg = get_victory_dialog(winner_card.name)
                final_text = (
                    f"🎉 **{winner_card.name}** برنده شد!\n"
                    f"💬 \"{victory_msg}\"\n\n"
                    f"📊 {ch_rounds_won} — {op_rounds_won}\n"
                    f"⭐ +{winner_xp} XP برنده  •  +{loser_xp} XP بازنده"
                    f"{level_up_text}"
                )

                # ارسال استیکر برنده
                import re
                card_key = re.sub(r'[^A-Z0-9]+', '_', winner_card.name.upper()).strip('_')
                sticker_path = os.path.join(os.getcwd(), 'stickers', f"{card_key}.webp")
                if os.path.exists(sticker_path):
                    try:
                        with open(sticker_path, 'rb') as sf:
                            await context.bot.send_sticker(chat_id=fight.chat_id, sticker=sf)
                    except Exception:
                        pass

            keyboard = [[InlineKeyboardButton("🥊 چالش جدید", callback_data="request_pvp_fight")]]
            try:
                await context.bot.send_message(
                    chat_id=fight.chat_id,
                    text=final_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send final result: {e}")

        self.db.delete_fight(fight_id)

    # ==================== SKINS HANDLERS ====================

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