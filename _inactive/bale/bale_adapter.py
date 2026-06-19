#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔌 Bale Adapter - لایه سازگاری با API بله
شبیه‌سازی interface کتابخانه python-telegram-bot برای استفاده با API بله
"""

import json
import logging
import requests
import asyncio
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

BALE_API_BASE = "https://tapi.bale.ai/bot{token}/{method}"


# ==================== DATA CLASSES (شبیه‌سازی telegram objects) ====================

@dataclass
class BaleUser:
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    is_bot: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "BaleUser":
        return cls(
            id=d.get("id", 0),
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            username=d.get("username", ""),
            is_bot=d.get("is_bot", False),
        )


@dataclass
class BaleChat:
    id: int
    type: str = "private"
    title: str = ""
    username: str = ""
    first_name: str = ""
    _bot: Any = field(default=None, repr=False)

    @property
    def chat_id(self):
        """سازگاری با telegram که chat_id داره"""
        return self.id

    @classmethod
    def from_dict(cls, d: dict) -> "BaleChat":
        return cls(
            id=d.get("id", 0),
            type=d.get("type", "private"),
            title=d.get("title", ""),
            username=d.get("username", ""),
            first_name=d.get("first_name", ""),
        )


class _DateWrapper:
    """wrapper برای unix timestamp که .timestamp() داره - سازگاری با telegram"""
    def __init__(self, unix_ts: int):
        self._ts = unix_ts or 0

    def timestamp(self):
        return float(self._ts)


@dataclass
class BaleMessage:
    message_id: int
    chat: BaleChat
    from_user: Optional[BaleUser] = None
    text: str = ""
    _date_raw: int = field(default=0, repr=False)
    reply_markup: Any = None

    @property
    def chat_id(self):
        return self.chat.id

    @property
    def date(self):
        """برمی‌گردونه یه object که .timestamp() داره - سازگار با telegram"""
        return _DateWrapper(self._date_raw)

    @classmethod
    def from_dict(cls, d: dict) -> "BaleMessage":
        return cls(
            message_id=d.get("message_id", 0),
            chat=BaleChat.from_dict(d.get("chat", {})),
            from_user=BaleUser.from_dict(d["from"]) if "from" in d else None,
            text=d.get("text", ""),
            _date_raw=d.get("date", 0),
        )

    async def reply_text(self, text: str, reply_markup=None, parse_mode: str = None) -> "BaleMessage":
        return await self.chat._bot.send_message(
            chat_id=self.chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    async def reply_sticker(self, sticker) -> "BaleMessage":
        """ارسال استیکر در بله با sendSticker"""
        return await self.chat._bot.send_sticker(
            chat_id=self.chat.id,
            sticker=sticker,
        )

    async def reply_document(self, document, caption: str = None) -> "BaleMessage":
        return await self.chat._bot.send_document(
            chat_id=self.chat.id,
            document=document,
            caption=caption,
        )


@dataclass
class BaleCallbackQuery:
    id: str
    from_user: BaleUser
    message: Optional[BaleMessage] = None
    data: str = ""
    _bot: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, d: dict, bot: "BaleBot") -> "BaleCallbackQuery":
        msg = None
        if "message" in d:
            msg = BaleMessage.from_dict(d["message"])
            msg.chat._bot = bot
        obj = cls(
            id=str(d.get("id", "")),
            from_user=BaleUser.from_dict(d.get("from", {})),
            message=msg,
            data=d.get("data", ""),
            _bot=bot,
        )
        return obj

    async def answer(self, text: str = "", show_alert: bool = False):
        """پاسخ به callback query"""
        try:
            await self._bot.answer_callback_query(
                callback_query_id=self.id,
                text=text,
                show_alert=show_alert,
            )
        except Exception as e:
            logger.warning(f"answer callback failed: {e}")

    async def edit_message_text(self, text: str, reply_markup=None, parse_mode: str = None):
        """ویرایش متن پیام"""
        if not self.message:
            return
        return await self._bot.edit_message_text(
            chat_id=self.message.chat.id,
            message_id=self.message.message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


@dataclass
class BaleUpdate:
    update_id: int
    message: Optional[BaleMessage] = None
    callback_query: Optional[BaleCallbackQuery] = None

    @property
    def effective_user(self) -> Optional[BaleUser]:
        if self.message and self.message.from_user:
            return self.message.from_user
        if self.callback_query:
            return self.callback_query.from_user
        return None

    @property
    def effective_chat(self) -> Optional[BaleChat]:
        if self.message:
            return self.message.chat
        if self.callback_query and self.callback_query.message:
            return self.callback_query.message.chat
        return None

    @classmethod
    def from_dict(cls, d: dict, bot: "BaleBot") -> "BaleUpdate":
        msg = None
        cbq = None

        if "message" in d:
            msg = BaleMessage.from_dict(d["message"])
            msg.chat._bot = bot

        if "callback_query" in d:
            cbq = BaleCallbackQuery.from_dict(d["callback_query"], bot)

        return cls(
            update_id=d.get("update_id", 0),
            message=msg,
            callback_query=cbq,
        )


# ==================== KEYBOARD CLASSES ====================

class InlineKeyboardButton:
    """دکمه inline - سازگار با telegram"""
    def __init__(self, text: str, callback_data: str = None, url: str = None, web_app=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url
        self.web_app = web_app

    def to_dict(self) -> dict:
        d = {"text": self.text}
        if self.callback_data:
            d["callback_data"] = self.callback_data
        if self.url:
            d["url"] = self.url
        return d


class InlineKeyboardMarkup:
    """کیبورد inline - سازگار با telegram"""
    def __init__(self, inline_keyboard):
        # اگه خودش InlineKeyboardMarkup بود، از داخلش بگیر
        if isinstance(inline_keyboard, InlineKeyboardMarkup):
            self.inline_keyboard = inline_keyboard.inline_keyboard
        else:
            self.inline_keyboard = inline_keyboard

    def to_dict(self) -> dict:
        # اگه inline_keyboard خودش InlineKeyboardMarkup باشه، از داخلش بگیر
        keyboard = self.inline_keyboard
        if isinstance(keyboard, InlineKeyboardMarkup):
            keyboard = keyboard.inline_keyboard
        return {
            "inline_keyboard": [
                [btn.to_dict() for btn in row]
                for row in keyboard
            ]
        }


# ==================== CONTEXT ====================

class BaleContext:
    """شبیه‌سازی ContextTypes.DEFAULT_TYPE"""
    def __init__(self, bot: "BaleBot", bot_data: dict = None):
        self.bot = bot
        self.job_queue = None
        self.bot_data = bot_data if bot_data is not None else {}


# ==================== MAIN BOT CLASS ====================

class BaleBot:
    """
    کلاس اصلی ربات بله
    با requests مستقیم با API بله ارتباط برقرار می‌کنه
    """

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.verify = False  # بله self-signed cert داره
        # suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._offset = 0
        self._handlers: List[Dict] = []  # list of {pattern, handler, type}
        self._command_handlers: Dict[str, Callable] = {}
        self._callback_handlers: List[Dict] = []  # list of {pattern, handler}
        self._error_handler: Optional[Callable] = None

    def _url(self, method: str) -> str:
        return BALE_API_BASE.format(token=self.token, method=method)

    def _post(self, method: str, data: dict = None, files: dict = None) -> dict:
        """ارسال درخواست به API بله"""
        url = self._url(method)
        # برای getUpdates timeout بیشتر
        timeout = 35 if method == "getUpdates" else 15
        try:
            if files:
                headers = {}
                response = self.session.post(url, data=data or {}, files=files,
                                             headers=headers, timeout=timeout)
            else:
                response = self.session.post(url, json=data or {}, timeout=timeout)

            # بله گاهی response خالی برمی‌گردونه
            if not response.content:
                return {"ok": False, "description": "empty response"}

            result = response.json()
            if not result.get("ok"):
                logger.warning(f"Bale API error [{method}]: {result.get('description', 'Unknown')}")
            return result
        except requests.exceptions.Timeout:
            # timeout در getUpdates نرماله
            if method != "getUpdates":
                logger.warning(f"Bale API timeout [{method}]")
            return {"ok": False, "description": "timeout"}
        except Exception as e:
            logger.error(f"Bale API request failed [{method}]: {e}")
            return {"ok": False, "description": str(e)}

    # ==================== API METHODS ====================

    async def get_me(self) -> Optional[BaleUser]:
        result = self._post("getMe")
        if result.get("ok"):
            return BaleUser.from_dict(result["result"])
        return None

    async def send_message(self, chat_id: int, text: str,
                           reply_markup=None, parse_mode: str = None) -> Optional[BaleMessage]:
        """ارسال پیام متنی"""
        # بله فقط Markdown پشتیبانی می‌کنه، HTML رو تبدیل می‌کنیم
        if parse_mode and parse_mode.upper() == "HTML":
            text = self._html_to_markdown(text)
            parse_mode = "Markdown"

        data = {
            "chat_id": chat_id,
            "text": text or "​",  # zero-width space اگه خالی بود
        }
        if reply_markup:
            data["reply_markup"] = reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
        if parse_mode:
            data["parse_mode"] = parse_mode

        result = self._post("sendMessage", data)
        if result.get("ok"):
            msg = BaleMessage.from_dict(result["result"])
            msg.chat._bot = self
            return msg
        return None

    async def send_photo(self, chat_id: int, photo, caption: str = None,
                         reply_markup=None, parse_mode: str = None) -> Optional[BaleMessage]:
        """ارسال تصویر"""
        if isinstance(photo, str):
            # URL یا file_id
            data = {"chat_id": chat_id, "photo": photo}
            if caption:
                data["caption"] = caption
            if reply_markup:
                data["reply_markup"] = reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
            result = self._post("sendPhoto", data)
        else:
            # فایل باینری
            form_data = {"chat_id": str(chat_id)}
            if caption:
                form_data["caption"] = caption
            if reply_markup:
                form_data["reply_markup"] = json.dumps(
                    reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
                )
            result = self._post("sendPhoto", data=form_data, files={"photo": photo})

        if result.get("ok"):
            msg = BaleMessage.from_dict(result["result"])
            msg.chat._bot = self
            return msg
        return None

    async def send_document(self, chat_id: int, document, caption: str = None,
                            reply_markup=None) -> Optional[BaleMessage]:
        """ارسال فایل/سند"""
        form_data = {"chat_id": str(chat_id)}
        if caption:
            form_data["caption"] = caption
        if reply_markup:
            form_data["reply_markup"] = json.dumps(
                reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
            )

        if hasattr(document, "read"):
            result = self._post("sendDocument", data=form_data, files={"document": document})
        else:
            form_data["document"] = document
            result = self._post("sendDocument", data=form_data)

        if result.get("ok"):
            msg = BaleMessage.from_dict(result["result"])
            msg.chat._bot = self
            return msg
        return None

    async def send_sticker(self, chat_id: int, sticker, reply_markup=None) -> Optional[BaleMessage]:
        """ارسال استیکر webp در بله"""
        form_data = {"chat_id": str(chat_id)}
        if reply_markup:
            form_data["reply_markup"] = json.dumps(
                reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
            )

        if hasattr(sticker, "read"):
            result = self._post("sendSticker", data=form_data, files={"sticker": sticker})
        else:
            form_data["sticker"] = sticker
            result = self._post("sendSticker", data=form_data)

        if result.get("ok"):
            msg = BaleMessage.from_dict(result["result"])
            msg.chat._bot = self
            return msg
        return None

    async def edit_message_text(self, chat_id: int, message_id: int, text: str,
                                reply_markup=None, parse_mode: str = None) -> Optional[BaleMessage]:
        """ویرایش پیام"""
        if parse_mode and parse_mode.upper() == "HTML":
            text = self._html_to_markdown(text)
            parse_mode = "Markdown"

        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text or "​",
        }
        if reply_markup:
            data["reply_markup"] = reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
        if parse_mode:
            data["parse_mode"] = parse_mode

        result = self._post("editMessageText", data)
        if result.get("ok"):
            msg = BaleMessage.from_dict(result["result"])
            msg.chat._bot = self
            return msg
        return None

    async def answer_callback_query(self, callback_query_id: str,
                                    text: str = "", show_alert: bool = False):
        """پاسخ به callback query"""
        # اگه callback_query_id با 1 شروع بشه = نسخه قدیمی بله
        if str(callback_query_id).startswith("1"):
            logger.debug(f"Old Bale client, skipping answerCallbackQuery")
            return
        # اگه text خالیه اصلاً نفرست - بله گاهی timeout می‌ده
        if not text:
            return
        data = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        }
        self._post("answerCallbackQuery", data)

    async def get_chat_member(self, chat_id, user_id: int):
        """دریافت اطلاعات عضو گروه"""
        result = self._post("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        if result.get("ok"):
            return result["result"]
        return None

    async def get_chat_member_count(self, chat_id) -> int:
        result = self._post("getChatMembersCount", {"chat_id": chat_id})
        if result.get("ok"):
            return result["result"]
        return 0

    async def get_chat_administrators(self, chat_id):
        result = self._post("getChatAdministrators", {"chat_id": chat_id})
        if result.get("ok"):
            for admin in result["result"]:
                yield BaleUser.from_dict(admin.get("user", {}))

    async def get_chat(self, chat_id) -> Optional[BaleChat]:
        result = self._post("getChat", {"chat_id": chat_id})
        if result.get("ok"):
            return BaleChat.from_dict(result["result"])
        return None

    async def send_chat_action(self, chat_id: int, action: str):
        self._post("sendChatAction", {"chat_id": chat_id, "action": action})

    async def set_my_commands(self, commands, scope=None):
        """تنظیم دستورات ربات - بله این رو پشتیبانی نمی‌کنه، نادیده می‌گیریم"""
        logger.debug("set_my_commands: not supported in Bale, skipping")

    async def delete_webhook(self, drop_pending_updates: bool = False):
        self._post("deleteWebhook")

    # ==================== POLLING ====================

    def _get_updates(self) -> List[dict]:
        """دریافت آپدیت‌های جدید"""
        data = {
            "offset": self._offset,
            "timeout": 30,
            "limit": 100,
        }
        result = self._post("getUpdates", data)
        if result.get("ok"):
            return result.get("result", [])
        return []

    async def process_update(self, update_dict: dict, app_handler: Callable):
        """پردازش یک آپدیت"""
        update = BaleUpdate.from_dict(update_dict, self)
        context = BaleContext(self)
        await app_handler(update, context)

    # ==================== HELPER METHODS ====================

    @staticmethod
    def _html_to_markdown(text: str) -> str:
        """تبدیل ساده HTML به Markdown برای بله"""
        import re
        # bold
        text = re.sub(r'<b>(.*?)</b>', r'*\1*', text, flags=re.DOTALL)
        text = re.sub(r'<strong>(.*?)</strong>', r'*\1*', text, flags=re.DOTALL)
        # italic
        text = re.sub(r'<i>(.*?)</i>', r'_\1_', text, flags=re.DOTALL)
        text = re.sub(r'<em>(.*?)</em>', r'_\1_', text, flags=re.DOTALL)
        # code
        text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
        # links
        text = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL)
        # strip remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        # unescape HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
        return text


# ==================== APPLICATION (شبیه‌سازی telegram Application) ====================

class BaleApplication:
    """
    شبیه‌سازی telegram.ext.Application برای بله
    """

    def __init__(self, token: str):
        self.bot = BaleBot(token)
        self._command_handlers: Dict[str, Callable] = {}
        self._callback_handlers: List[Dict] = []
        self._error_handler: Optional[Callable] = None
        self.job_queue = None
        self.post_init: Optional[Callable] = None
        self.bot_data: dict = {}  # shared state برای همه context ها

    def add_handler(self, handler):
        """اضافه کردن handler"""
        if isinstance(handler, BaleCommandHandler):
            self._command_handlers[handler.command] = handler.callback
        elif isinstance(handler, BaleCallbackQueryHandler):
            self._callback_handlers.append({
                "pattern": handler.pattern,
                "handler": handler.callback,
            })

    def add_error_handler(self, handler: Callable):
        self._error_handler = handler

    async def _dispatch(self, update: BaleUpdate, context: BaleContext):
        """توزیع آپدیت به handler مناسب"""
        try:
            # پیام متنی / دستور
            if update.message and update.message.text:
                text = update.message.text.strip()
                if text.startswith("/"):
                    cmd = text.split()[0].split("@")[0][1:].lower()
                    handler = self._command_handlers.get(cmd)
                    if handler:
                        await handler(update, context)
                        return

            # callback query
            if update.callback_query:
                data = update.callback_query.data or ""
                for entry in self._callback_handlers:
                    pattern = entry["pattern"]
                    import re
                    if re.search(pattern, data):
                        await entry["handler"](update, context)
                        return
                await update.callback_query.answer()

        except Exception as e:
            logger.error(f"Error dispatching update: {e}", exc_info=True)
            if self._error_handler:
                try:
                    await self._error_handler(update, context)
                except Exception:
                    pass

    def run_polling(self, drop_pending_updates: bool = False):
        """شروع polling loop"""
        asyncio.run(self._polling_loop(drop_pending_updates))

    async def _polling_loop(self, drop_pending_updates: bool = False):
        """حلقه اصلی polling"""
        # اجرای post_init
        if self.post_init:
            await self.post_init(self)

        # حذف آپدیت‌های قدیمی
        if drop_pending_updates:
            updates = self.bot._get_updates()
            if updates:
                self.bot._offset = updates[-1]["update_id"] + 1
                logger.info(f"Dropped {len(updates)} pending updates")

        logger.info("Bale bot polling started...")

        # شروع cleanup task به صورت موازی
        cleanup_task = asyncio.create_task(self._cleanup_loop())

        try:
            while True:
                try:
                    updates = self.bot._get_updates()
                    for update_dict in updates:
                        self.bot._offset = update_dict["update_id"] + 1
                        update = BaleUpdate.from_dict(update_dict, self.bot)
                        context = BaleContext(self.bot, self.bot_data)
                        await self._dispatch(update, context)

                    if not updates:
                        await asyncio.sleep(0.5)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Polling error: {e}", exc_info=True)
                    await asyncio.sleep(3)
        finally:
            cleanup_task.cancel()
            logger.info("Bot stopped")

    async def _cleanup_loop(self):
        """هر ۳۰ ثانیه فایت‌های منقضی رو پاک می‌کنه"""
        from game_core import DatabaseManager
        db = DatabaseManager()
        while True:
            try:
                await asyncio.sleep(30)
                deleted = db.cleanup_expired_fights(minutes=2)
                if deleted > 0:
                    logger.info(f"Cleanup: cancelled {deleted} expired fights")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")


# ==================== HANDLER CLASSES ====================

class BaleCommandHandler:
    def __init__(self, command: str, callback: Callable):
        self.command = command.lower()
        self.callback = callback


class BaleCallbackQueryHandler:
    def __init__(self, callback: Callable, pattern: str = None):
        self.callback = callback
        self.pattern = pattern or ".*"


class BaleFilters:
    """placeholder برای filters"""
    class TEXT:
        pass
    class COMMAND:
        pass


# ==================== BUILDER ====================

class BaleApplicationBuilder:
    def __init__(self):
        self._token = None

    def token(self, token: str) -> "BaleApplicationBuilder":
        self._token = token
        return self

    def build(self) -> BaleApplication:
        return BaleApplication(self._token)
