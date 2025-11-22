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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, BotCommand, BotCommandScope, BotCommandScopeDefault, BotCommandScopeAllGroupChats
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
            logger.warning(f'Image not found for {card_name} at path: {image_path}')
            return False

        logger.info(f'Attempting to send image for {card_name} in chat {message.chat.id} (type: {message.chat.type})')
        
        # Check if the image is a webp file
        if image_path.lower().endswith('.webp'):
            with open(image_path, 'rb') as sticker:
                await message.reply_sticker(sticker)
                logger.info(f'Sticker sent successfully for {card_name}')
            if match_id and dialog_text:
                text_to_send = f'🎴 {card_name}\n\n💬 {dialog_text}'
                keyboard = [[InlineKeyboardButton('ℹ️ اطلاعات بیشتر', callback_data=f'match_info_{match_id}')]]
                await message.reply_text(text_to_send, reply_markup=InlineKeyboardMarkup(keyboard))
            elif caption:
                await message.reply_text(caption)
        else:
            with open(image_path, 'rb') as photo:
                await message.reply_document(document=photo, caption=caption)
                logger.info(f'Document sent successfully for {card_name}')
        return True

    except Exception as e:
        logger.error(f'Failed to send image/sticker for {card_name} in chat {message.chat.id}: {type(e).__name__}: {e}', exc_info=True)
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

        # حافظه موقت برای خلاصه مبارزات اخیر (برای دکمه اطلاعات بیشتر)
        self.recent_matches: Dict[str, Dict[str, Any]] = {}
        
        # تنظیمات ربات
        self.bot_token = self.config['bot_settings']['token']
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
            
            logger.info(f"Checking membership for user {user_id} in channel {REQUIRED_CHANNEL}")
            member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
            logger.info(f"User {user_id} status in channel: {member.status}")
            
            if member.status in ["member", "administrator", "creator"]:
                return True
            
            logger.warning(f"User {user_id} has status '{member.status}' - not a member")
            return False
            
        except telegram.error.BadRequest as e:
            logger.error(f"BadRequest checking membership for user {user_id} in {REQUIRED_CHANNEL}: {e}")
            # اگه خطای BadRequest بود، احتمالاً بات در کانال نیست یا کانال اشتباهه
            # در این صورت بهتره True برگردونیم تا بازی قفل نشه
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error checking channel membership for user {user_id}: {type(e).__name__}: {e}")
            # در صورت خطای غیرمنتظره، True برگردون تا بازی قفل نشه
            return True
    
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

            keyboard = [
                [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
                [InlineKeyboardButton("⚔️ چالش PvP", callback_data="request_pvp_fight")],
                [InlineKeyboardButton("🎁 کلیم روزانه", callback_data="daily_claim")],
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
                "📖 **راهنمای بازی TelBattle**\n\n"
                "🎯 **کارت جمع کن، مبارزه کن، امتیاز بگیر!**\n\n"
                "❓ **چطوری بازی کنم؟**\n"
                "۱- بازی با دستور /fight تو گروه‌ها شروع میشه\n"
                "۲- هرکی بخواد بازی کنه از بین گزینه‌های مبارزه نورمال یا مبارزه تصادفی یکی رو انتخاب میکنه\n"
                "۳- حالا اگه بازی تصادفی رو انتخاب کنی ربات بصورت رندوم برات یه کارت از بین کارت‌هایی که داری انتخاب میکنه، اگه بازی نورمال باشه به پیوی ربات میری و قهرمانت رو انتخاب میکنی\n"
                "۴- حالا از بین ویژگی‌های قهرمانت (قدرت، سرعت، آیکیو، محبوبیت) یکی رو انتخاب میکنی\n"
                "۵- وقتی هردو بازیکن انتخابشون رو کردن نتیجه بازی در گروه اعلام میشه\n\n"
                "❓ **امتیاز دهی‌ها به چه صورته و به چه دردی میخوره؟**\n"
                "▫️ امتیازها شمارو در لیدربرد گروهی و لیدربرد جهانی دسته‌بندی میکنن، تو اپدیت‌های بعدی ارزش‌های دیگه‌ای هم پیدا میکنن و جوایزی براش درنظر گرفته شده\n"
                "▫️ برای دیدن رتبه و امتیازتون میتونین تو پیوی ربات از دستور /profile استفاده کنین\n"
                "▫️ اگه تو پیوی ربات گزینه /leaderboard رو بزنین تو بخش جهانی رتبه‌ها نمایش داده میشه، اگه تو گروه ازین گزینه استفاده کنین افراد گروه رو رتبه‌بندی میکنه\n"
                "▫️ امتیاز دهی‌ها بر اساس درجه نوع کارتی که دارین به برنده داده میشه؛ مثلا اگه کارت لجند بر کارت نورمال پیروز بشه طبیعتا امتیاز کمتری میگیره تا اینکه کارت نورمال از کارت لجند پیروزی کسب کنه\n\n"
                "❓ **چطوری کارت دریافت کنم و اهمیت کارت‌ها به چه صورته؟**\n"
                "🎁 روزی یبار میتونی با دستور /claim در ربات یا گروه کارت جدید بگیری، روز جدید از ساعت ۱۲ نیمه شب دوباره شروع میشه\n"
                "🃏 اهمیت کارت‌ها به صورت زیره:\n"
                "🟢 Normal • 🟣 Epic • 🟡 Legend\n"
                "▫️ همونطور که معلومه احتمال دریافت کارت لجند از همه کمتره، بعدش هم کارت اپیک قرار میگیره و کارت نورمال هم بیشترین گوناگونی رو داره\n\n"
                "❓ **چرا بعضی موقعا نمیتونم بازی کنم یا از بعضی کارتام استفاده کنم؟**\n"
                "❤️ شما ۱۰ تا جون دارید و اگه ده بار مبارزه‌ای رو شکست بخورید تا ۲۴ ساعت از زمان آخرین باختی که داشتی نمیتونی بازی کنی\n"
                "▫️ اگه با کارت‌های خیلی قوی از کارت‌های ضعیف شکست بخوری بیشتر از یه جون ازت کم میشه، همینطور اگه حریف کارت خیلی قوی داشته باشه و تو کارتت ضعیف باشه جونی ازت کم نمیشه\n"
                "▫️ برای عادلانه شدن بازی، اگه بیش از حد از کارت خیلی قوی استفاده کنی و همش پیروز بشی اون کارت تا زمان معینی قفل میشه\n\n"
                "❓ **چرا ربات برام کار نمیکنه؟**\n"
                "این گزینه‌هارو چک کن:\n"
                "▫️ باید تو کانالی که ربات روش قفل شده جوین شده باشی\n"
                "▫️ برای بازی کردن با رفیقت باید هردو ربات رو استارت کرده باشین\n"
                "▫️ اگه هیچ کدوم اینا نبود حتما مشکل از سرور رباته که تو کانال پشتیبان اطلاع‌رسانیش میکنیم\n\n"
                "👨‍💻 اگه سوال دیگه‌ای داشتی یا باگی تو ربات پیدا کردی حتما عضو گروه تل بتل شو و اونجا باهامون در میون بزار، مام خوشحال میشیم❤️"
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
        # بررسی مجوز دستور
        if not self._is_command_allowed_in_chat("profile", update.effective_chat.type):
            await update.message.reply_text(
                "🚫 این دستور فقط در چت خصوصی قابل استفاده است.\n"
                "📱 برای مشاهده پروفایل خود، از پیوی ربات استفاده کنید."
            )
            return
            
        user = update.effective_user
        
        # بررسی عضویت کانال
        if not await self.is_user_in_channel(user.id, context):
            await self.send_channel_join_message(update)
            return

        player = self.db.get_or_create_player(user.id, user.username, user.first_name)
        card_count = len(self.db.get_player_cards(user.id))
        stats_windows = self.db.get_player_stats(user.id)
        rank = self.db.get_player_rank(user.id)
        card_counts = self.db.get_player_card_counts(user.id)

        # Choose nice defaults
        rank_text = f"#{rank}" if rank else "N/A"

        total_stats = stats_windows.get('total', {'games_played': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'win_rate': 0})

        text = (
            f"👤 **پروفایل شما: {user.first_name}**\n\n"
            f"📊 **آمار کلی:**\n"
            f"🏆 امتیاز کل: {player.total_score}  •  رتبه: {rank_text}\n"
            f"💀 جان‌ها: {getattr(player, 'hearts', self.game.DAILY_HEARTS)}/{self.game.DAILY_HEARTS}\n"
            f"🎴 کارت‌ها: {card_counts.get('total', card_count)} (🟢{card_counts.get('normal',0)} • 🟣{card_counts.get('epic',0)} • 🟡{card_counts.get('legend',0)})\n\n"
            f"⚔️ **آمار فایت (کلی):**\n"
            f"  - کل بازی‌ها: {total_stats['games_played']}\n"
            f"  - برد: {total_stats['wins']}\n"
            f"  - باخت: {total_stats['losses']}\n"
            f"  - مساوی: {total_stats['ties']}\n"
            f"  - نرخ برد: {int(total_stats['win_rate'])}%\n"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

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
        
        # بررسی عضویت کانال
        if not await self.is_user_in_channel(user.id, context):
            await self.send_channel_join_message(update)
            return
            
        user_id = user.id
        success, card, error = self.game.claim_daily_card(user_id)
        
        if success and card:
            rarity_colors = {
                CardRarity.NORMAL: "🟢",
                CardRarity.EPIC: "🟣",
                CardRarity.LEGEND: "🟡"
            }
            color = rarity_colors[card.rarity]
            
            text = (
                f"🎉 **کارت روزانه دریافت شد!**\n\n"
                f"{color} **{card.name}** ({card.rarity.value.title()})\n\n"
                f"📊 **آمار کارت:**\n"
                f"💪 قدرت: {card.power}\n"
                f"⚡ سرعت: {card.speed}\n"
                f"🧠 آی‌کیو: {card.iq}\n"
                f"❤️ محبوبیت: {card.popularity}\n"
            )
            await update.message.reply_text(text, parse_mode='Markdown')
            await send_card_image_safely(update.message, card.name, self.config, f"🎉 {card.name}")
        else:
            text = f"⚠️ **خطا در دریافت کارت**\n\n{error if error else 'خطای نامشخص!'}"
            await update.message.reply_text(text, parse_mode='Markdown')

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

    def _create_my_cards_keyboard(self, user_id: int, category: str = "menu", page: int = 1) -> InlineKeyboardMarkup:
        """ایجاد کیبورد نمایش کارت‌های من با دسته‌بندی و pagination"""
        keyboard = []
        
        if category == "menu":
            # منوی اصلی - نمایش دسته‌بندی‌ها
            rarity_counts = self.db.get_rarity_counts(user_id)
            favorite_cards, fav_count = self.db.get_favorite_cards(user_id, page=1, per_page=1)
            
            if fav_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"⭐ مورد علاقه ({fav_count})",
                        callback_data=f"my_cards_nav_favorite_1"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    f"🟡 Legendary ({rarity_counts.get(CardRarity.LEGEND.value, 0)})",
                    callback_data=f"my_cards_nav_legend_1"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"🟣 Epic ({rarity_counts.get(CardRarity.EPIC.value, 0)})",
                    callback_data=f"my_cards_nav_epic_1"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"🟢 Normal ({rarity_counts.get(CardRarity.NORMAL.value, 0)})",
                    callback_data=f"my_cards_nav_normal_1"
                )
            ])
            keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])
            
        else:
            # نمایش کارت‌های یک دسته خاص
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
                keyboard.append([
                    InlineKeyboardButton(
                        f"{color} {card.name} — جزئیات",
                        callback_data=f"card_view_{card.card_id}"
                    )
                ])
            
            # دکمه‌های navigation
            total_pages = (total_count + 5) // 6
            nav_buttons = []
            
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton("« قبلی", callback_data=f"my_cards_nav_{category}_{page-1}")
                )
            
            nav_buttons.append(
                InlineKeyboardButton("🏠 منو", callback_data=f"my_cards_nav_menu_1")
            )
            
            if page < total_pages:
                nav_buttons.append(
                    InlineKeyboardButton("بعدی »", callback_data=f"my_cards_nav_{category}_{page+1}")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])
        
        return keyboard

    def _create_pvp_card_selection_keyboard(self, fight_id: str, user_id: int, category: str = "menu", page: int = 1) -> InlineKeyboardMarkup:
        """ایجاد کیبورد انتخاب کارت برای PvP با دسته‌بندی و pagination"""
        keyboard = []
        
        if category == "menu":
            # منوی اصلی - نمایش دسته‌بندی‌ها
            rarity_counts = self.db.get_rarity_counts(user_id)
            favorite_cards, fav_count = self.db.get_favorite_cards(user_id, page=1, per_page=1)
            
            if fav_count > 0:
                keyboard.append([
                    InlineKeyboardButton(
                        f"⭐ مورد علاقه ({fav_count})",
                        callback_data=f"pvp_cards_{fight_id}_favorite_1"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    f"🟡 Legendary ({rarity_counts.get(CardRarity.LEGEND.value, 0)})",
                    callback_data=f"pvp_cards_{fight_id}_legend_1"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"🟣 Epic ({rarity_counts.get(CardRarity.EPIC.value, 0)})",
                    callback_data=f"pvp_cards_{fight_id}_epic_1"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    f"🟢 Normal ({rarity_counts.get(CardRarity.NORMAL.value, 0)})",
                    callback_data=f"pvp_cards_{fight_id}_normal_1"
                )
            ])
            
        else:
            # نمایش کارت‌های یک دسته خاص
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
                
                # بررسی cooldown کارت
                is_in_cooldown, cooldown_until = self.game.is_card_in_cooldown(user_id, card.card_id)
                if is_in_cooldown:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"❄️ {card.name} (Cooldown)",
                            callback_data=f"cooldown_card_{card.card_id}"
                        )
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{color} {card.name} ({stats})",
                            callback_data=f"pvp_card_{fight_id}_{card.card_id}"
                        )
                    ])
            
            # دکمه‌های navigation
            total_pages = (total_count + 5) // 6
            nav_buttons = []
            
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton("« قبلی", callback_data=f"pvp_cards_{fight_id}_{category}_{page-1}")
                )
            
            nav_buttons.append(
                InlineKeyboardButton("🏠 منو", callback_data=f"pvp_cards_{fight_id}_menu_1")
            )
            
            if page < total_pages:
                nav_buttons.append(
                    InlineKeyboardButton("بعدی »", callback_data=f"pvp_cards_{fight_id}_{category}_{page+1}")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        return InlineKeyboardMarkup(keyboard)

    def _create_stat_selection_keyboard(self, fight_id: str, card: Card) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton(f"💪 قدرت ({card.power})", callback_data=f"pvp_stat_{fight_id}_power")],
            [InlineKeyboardButton(f"⚡ سرعت ({card.speed})", callback_data=f"pvp_stat_{fight_id}_speed")],
            [InlineKeyboardButton(f"🧠 آی‌کیو ({card.iq})", callback_data=f"pvp_stat_{fight_id}_iq")],
            [InlineKeyboardButton(f"❤️ محبوبیت ({card.popularity})", callback_data=f"pvp_stat_{fight_id}_popularity")]
        ]
        return InlineKeyboardMarkup(keyboard)

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

    async def _announce_pvp_result(self, context: ContextTypes.DEFAULT_TYPE, result: Dict):
        """اعلام نتیجه فایت PvP در گروه"""
        try:
            fight_id = result["fight_id"]
            fight = self.db.get_fight_by_id(fight_id)
            if not fight or not fight.chat_id:
                logger.error(f"Cannot announce PvP result: fight {fight_id} not found or no chat_id")
                return

            # Store full result for the "More Info" button
            self.recent_matches[str(fight_id)] = result

            result_type = result["result_type"]

            if result_type == "tie":
                # Handle tie result
                text = "🤝 **مساوی!**\n\nدر این مبارزه هیچ یک از طرفین برنده نشدند."
                keyboard = [
                    [InlineKeyboardButton("ℹ️ اطلاعات بیشتر", callback_data=f"match_info_{fight_id}")],
                    [InlineKeyboardButton("🥊 چالش جدید", callback_data="request_pvp_fight")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=fight.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                # Handle win/loss result
                winner_data = result.get("winner")
                if not winner_data:
                    logger.error(f"Winner data not found for fight {fight_id}")
                    return
                
                winner_card = winner_data["card"]
                winner_card_name = winner_card.name

                # 1. Send winner's sticker
                # Normalize card name to uppercase and sanitize for filesystem (spaces -> _)
                import re
                winner_card_key = re.sub(r'[^A-Z0-9]+', '_', winner_card_name.upper()).strip('_')

                # Try configured stickers path first (if exists in config), then fallback to workspace 'stickers' dir
                stickers_path_candidates = []
                try:
                    cfg_images = self.config.get('image_settings', {})
                    # If a stickers path is set explicitly (legacy), use it
                    cfg_stickers = cfg_images.get('stickers_path')
                    if cfg_stickers:
                        stickers_path_candidates.append(cfg_stickers)
                except Exception:
                    pass

                # Common locations
                stickers_path_candidates.append(os.path.join(os.getcwd(), 'stickers'))
                stickers_path_candidates.append(os.path.join(os.sep, 'root', 'card game', 'stickers'))

                sticker_sent = False
                for base in stickers_path_candidates:
                    sticker_path = os.path.join(base, f"{winner_card_key}.webp")
                    try:
                        if os.path.exists(sticker_path):
                            with open(sticker_path, 'rb') as sticker_file:
                                await context.bot.send_sticker(chat_id=fight.chat_id, sticker=sticker_file)
                            sticker_sent = True
                            break
                    except Exception as e:
                        logger.warning(f"Failed to send sticker from {sticker_path}: {e}")

                if not sticker_sent:
                    # Friendly fallback message
                    await context.bot.send_message(chat_id=fight.chat_id, text=f"❌ Sticker for {winner_card_name} not found.")

                # 2. Send victory message
                victory_message = get_victory_dialog(winner_card_name)
                text = f'🎉 {winner_card_name} won!\n💬 "{victory_message}"'
                
                # 3. Add "More Info" button
                keyboard = [[InlineKeyboardButton("ℹ️ More Info", callback_data=f"match_info_{fight_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    chat_id=fight.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

            # Cleanup the fight from the database
            self.db.delete_fight(fight_id)

        except Exception as e:
            logger.error(f"Error announcing PvP result: {e}", exc_info=True)

    # ==================== EXISTING CALLBACK HANDLERS ====================

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
            # آپدیت اسم‌های "بازیکن" از Telegram API
            for player_info in leaderboard[:30]:  # فقط 30 نفر اول
                first_name = player_info.get('first_name', '').strip()
                if not first_name or first_name == "بازیکن":
                    await self.ensure_player_name(player_info['user_id'], context)
            
            # دوباره لیدربورد رو بگیر با اسم‌های آپدیت شده
            leaderboard = self.db.get_leaderboard_by_timeframe(
                timeframe=timeframe,
                limit=limit if not is_group else 1000,
                chat_id=chat_id if is_group else None
            )
            
            if is_group:
                # فیلتر کردن برای گروه
                filtered_leaderboard = []
                for player in leaderboard:
                    if player['user_id'] in group_fighter_ids:
                        filtered_leaderboard.append(player)
                leaderboard = filtered_leaderboard
            
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
                elif first_name and first_name != "بازیکن":
                    # escape کردن کاراکترهای خاص HTML
                    name = first_name[:15].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                else:
                    # اگه هنوز "بازیکن" هست، user_id رو نشون بده
                    name = f"User_{player_info['user_id']}"
                
                score = player_info.get('period_score', 0)
                
                text += f"{medal} {name} - {score} امتیاز\n"
            
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
        
        # Robust extraction of fight_id from callback_data
        data = (query.data or "")
        fight_id = None
        if data.startswith('match_info_'):
            fight_id = data[len('match_info_'):]

        if not fight_id:
            await query.answer("❌ داده نامعتبر", show_alert=True)
            return

        # چک کردن اینکه قبلاً این اطلاعات فرستاده شده یا نه
        info_sent_key = f"info_sent_{fight_id}"
        if hasattr(self, 'match_info_sent'):
            if info_sent_key in self.match_info_sent:
                await query.answer("ℹ️ اطلاعات قبلاً نمایش داده شده است.", show_alert=True)
                return
        else:
            self.match_info_sent = set()
        
        # علامت‌گذاری که اطلاعات فرستاده شده
        self.match_info_sent.add(info_sent_key)
        await query.answer()
        
        result = self.recent_matches.get(str(fight_id))
        if not result:
            # Provide a clear inline alert and a fallback message in chat
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
        
        # دریافت وضعیت فعلی
        player = self.db.get_or_create_player(user_id)
        
        card_count = len(self.db.get_player_cards(user_id))
        
        text = (
            f"🎮 **منوی اصلی**\n\n"
            f"سلام {user.first_name}! 👋\n\n"
            f"📊 **وضعیت شما:**\n"
            f"💀 جان‌ها: {player.hearts}/{self.game.DAILY_HEARTS}\n"
            f"🎴 کارت‌ها: {card_count}\n"
            f"🏆 امتیاز: {player.total_score}\n\n"
            f"عملیات مورد نظر را انتخاب کنید:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
            [InlineKeyboardButton("⚔️ چالش PvP", callback_data="request_pvp_fight")],
            [InlineKeyboardButton("🎁 کلیم روزانه", callback_data="daily_claim")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def ensure_player_name(self, user_id: int, context) -> None:
        """اطمینان از اینکه بازیکن اسم درست داره، اگه نداره از Telegram API بگیر"""
        player = self.db.get_or_create_player(user_id)
        
        # اگه اسم "بازیکن" هست یا خالیه، از Telegram API بگیر
        if not player.first_name or player.first_name == "بازیکن":
            try:
                chat = await context.bot.get_chat(user_id)
                if chat.first_name:
                    player.first_name = chat.first_name
                    player.username = chat.username or ""
                    self.db.update_player(player)
            except Exception:
                pass  # اگه نتونست بگیره، مشکلی نیست

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
        
        card = self.db.get_card_by_id(card_id)
        if not card:
            await query.answer("❌ کارت یافت نشد!", show_alert=True)
            return
        
        # بررسی وضعیت favorite
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT is_favorite, usage_count FROM player_cards WHERE user_id = ? AND card_id = ?', (user_id, card_id))
        result = cursor.fetchone()
        conn.close()
        
        is_favorite = result[0] if result else 0
        usage_count = result[1] if result else 0
        
        rarity_colors = {
            CardRarity.NORMAL: "🟢",
            CardRarity.EPIC: "🟣",
            CardRarity.LEGEND: "🟡"
        }
        color = rarity_colors.get(card.rarity, "⚪")
        
        text = (
            f"{color} **{card.name}**\n\n"
            f"💪 قدرت: {card.power}\n"
            f"⚡ سرعت: {card.speed}\n"
            f"🧠 آی‌کیو: {card.iq}\n"
            f"❤️ محبوبیت: {card.popularity}\n\n"
            f"🎮 تعداد استفاده: {usage_count} بار\n"
            f"{'⭐ مورد علاقه' if is_favorite else ''}"
        )
        
        fav_text = "💔 حذف از علاقه‌مندی‌ها" if is_favorite else "⭐ افزودن به علاقه‌مندی‌ها"
        
        keyboard = [
            [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav_{card_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="mycards_menu_1")]
        ]
        
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
            # Reset lives once every 24 hours
            application.job_queue.run_repeating(bot.reset_lives_task, interval=86400, first=20)
            print("✅ تسک تمیزکاری فعال شد")
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