#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Utility Functions - توابع کمکی ربات
"""

import json
import os
import logging
import random
from typing import Optional, List, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Required channel for bot usage
REQUIRED_CHANNEL = '@KhasteNews'

# Panel expiration timeout (15 minutes)
PANEL_TIMEOUT = 15 * 60


async def check_user_started_bot(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """بررسی اینکه آیا کاربر ربات را استارت کرده یا نه"""
    try:
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
    """دریافت مسیر تصویر کارت"""
    if not config.get('image_settings', {}).get('enable_images', False):
        return None

    images_path = config.get('image_settings', {}).get('card_images_path', '/root/card game/card_images/')
    default_image = config.get('image_settings', {}).get('default_card_image', '/root/card game/card_images/default.png')

    os.makedirs(images_path, exist_ok=True)

    card_filename = card_name.lower().replace(' ', '_').replace('-', '_')
    possible_extensions = ['.png', '.jpg', '.jpeg', '.webp']

    for ext in possible_extensions:
        card_image = os.path.join(images_path, f"{card_filename}{ext}")
        if os.path.exists(card_image):
            return card_image

    if os.path.exists(default_image):
        return default_image

    return None


def get_victory_dialog(card_name: str) -> str:
    """Gets a random victory dialog for a card."""
    dialogs_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "card_dialogs.json")

    if os.path.exists(dialogs_file):
        try:
            with open(dialogs_file, 'r', encoding='utf-8') as f:
                all_dialogs = json.load(f)
                entry = all_dialogs.get(card_name)
                lines: List[str] = []
                if isinstance(entry, list):
                    lines = entry
                elif isinstance(entry, dict):
                    vl = entry.get('victory_lines', [])
                    if isinstance(vl, list):
                        lines = vl
                    elif isinstance(vl, str) and vl:
                        lines = [vl]
                if lines:
                    return random.choice(lines)
        except Exception:
            pass

    generic = [
        "Another victory!",
        "No one can defeat me!",
        "This was just the beginning!",
        "True power is here!"
    ]
    return random.choice(generic)


async def send_card_image_safely(message, card_name: str, config: Dict, caption: str = None, match_id: str = None, dialog_text: str = None) -> bool:
    """ارسال امن تصویر کارت"""
    try:
        image_path = get_card_image_path(card_name, config)
        if not image_path or not os.path.exists(image_path):
            return False

        if image_path.lower().endswith('.webp'):
            with open(image_path, 'rb') as sticker:
                await message.reply_sticker(sticker)
        else:
            with open(image_path, 'rb') as photo:
                await message.reply_photo(photo, caption=caption, parse_mode='Markdown')

        return True
    except Exception as e:
        logger.error(f"Error sending card image for {card_name}: {e}")
        return False


def ensure_not_expired(query, db=None, context=None) -> bool:
    """بررسی منقضی نشدن پنل"""
    import time
    try:
        msg_date = query.message.date
        if msg_date:
            import datetime as dt
            now = dt.datetime.now(dt.timezone.utc)
            if hasattr(msg_date, 'timestamp'):
                age = now.timestamp() - msg_date.timestamp()
            else:
                age = 0
            if age > PANEL_TIMEOUT:
                return False
    except Exception:
        pass
    return True
