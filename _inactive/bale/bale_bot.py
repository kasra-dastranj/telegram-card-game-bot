#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging, os, json, sys
from bale_adapter import BaleApplicationBuilder, BaleCommandHandler, BaleCallbackQueryHandler
from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup

# ==================== PATCH telegram برای بله ====================
import telegram as _tg
_tg.InlineKeyboardButton = InlineKeyboardButton
_tg.InlineKeyboardMarkup = InlineKeyboardMarkup
try:
    import telegram._inline.inlinekeyboardbutton as _m
    _m.InlineKeyboardButton = InlineKeyboardButton
except Exception:
    pass
try:
    import telegram._inline.inlinekeyboardmarkup as _m2
    _m2.InlineKeyboardMarkup = InlineKeyboardMarkup
except Exception:
    pass

from telegram_bot import TelegramCardBot
import telegram_bot as _tb_module

# فقط InlineKeyboardButton و InlineKeyboardMarkup رو patch کن
_tb_module.InlineKeyboardButton = InlineKeyboardButton
_tb_module.InlineKeyboardMarkup = InlineKeyboardMarkup

# مطمئن بشیم import های ضروری دست نخوردن
import sqlite3 as _sqlite3
import datetime as _datetime
_tb_module.sqlite3 = _sqlite3

# patch کردن send_card_image_safely برای استفاده از sendSticker بله
async def _bale_send_card_image_safely(message, card_name: str, config, caption=None, match_id=None, dialog_text=None):
    """نسخه بله - از sendSticker استفاده می‌کنه"""
    try:
        # اول دنبال استیکر webp بگرد
        sticker_name = card_name.upper().replace(' ', '_').replace('-', '_')
        sticker_path = os.path.join("stickers", f"{sticker_name}.webp")
        if not os.path.exists(sticker_path):
            # جستجوی case-insensitive
            for f in os.listdir("stickers"):
                if f.lower() == f"{sticker_name.lower()}.webp" and "(2)" not in f:
                    sticker_path = os.path.join("stickers", f)
                    break
            else:
                sticker_path = None

        if sticker_path and os.path.exists(sticker_path):
            with open(sticker_path, "rb") as sticker:
                await message.reply_sticker(sticker)
            if match_id and dialog_text:
                text_to_send = f"🎴 {card_name}\n\n💬 {dialog_text}"
                keyboard = [[InlineKeyboardButton("ℹ️ اطلاعات بیشتر", callback_data=f"match_info_{match_id}")]]
                await message.reply_text(text_to_send, reply_markup=InlineKeyboardMarkup(keyboard))
            elif caption:
                await message.reply_text(caption)
            return True

        # fallback: تصویر png
        images_path = config.get("image_settings", {}).get("card_images_path", "card_images/")
        card_filename = card_name.lower().replace(" ", "_").replace("-", "_")
        png_path = os.path.join(images_path, f"{card_filename}.png")
        if os.path.exists(png_path):
            with open(png_path, "rb") as photo:
                await message.chat._bot.send_photo(chat_id=message.chat.id, photo=photo, caption=caption)
            return True

        return False
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Bale send_card_image_safely error: {e}")
        return False

_tb_module.send_card_image_safely = _bale_send_card_image_safely

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bale_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class BaleTelegramCardBot(TelegramCardBot):
    async def is_user_in_channel(self, user_id: int, context) -> bool:
        return True

    async def start_command(self, update, context):
        """نسخه بله - starter cards + claim اولیه"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup

        user = update.effective_user
        if not user:
            return

        # ساخت یا دریافت player
        player = self.db.get_or_create_player(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        player = self.game.check_and_reset_hearts(player)

        # اگه کارت نداره، starter cards بده
        card_count = len(self.db.get_player_cards(user.id))
        if card_count == 0:
            starter_names = ["John Wick", "Heisenberg", "Rehi"]
            granted = []
            all_cards = self.db.get_all_cards()
            for nm in starter_names:
                card_obj = next(
                    (c for c in all_cards if c.name.lower() == nm.lower()),
                    None
                )
                if card_obj:
                    if self.db.add_card_to_player(user.id, card_obj.card_id):
                        granted.append(card_obj.name)

            if granted:
                try:
                    if update.message:
                        await update.message.reply_text(
                            f"🎴 کارت‌های شروعی دریافت شد:\n" +
                            "\n".join(f"• {n}" for n in granted) +
                            "\n\nیه کلیم رایگان هم داری — از منو استفاده کن!"
                        )
                except Exception:
                    pass

        # منوی اصلی
        welcome_text = (
            "🎮 به نبرد افسانه‌ها خوش اومدی!\n"
            "دنیایی که قهرمان‌هاش از تمام دنیاهای خیالی جمع شدن...\n\n"
            "📜 برای دیدن داستان بازی بنویسید: /story"
        )
        keyboard = [
            [InlineKeyboardButton("🎴 کارت‌های من", callback_data="my_cards")],
            [InlineKeyboardButton("⚔️ چالش PvP", callback_data="request_pvp_fight"),
             InlineKeyboardButton("🎲 Risk Mode", callback_data="risk_menu")],
            [InlineKeyboardButton("🎁 کلیم روزانه", callback_data="daily_claim"),
             InlineKeyboardButton("⛏️ ماینینگ", callback_data="mining_claim")],
            [InlineKeyboardButton("🔮 Fusion", callback_data="fusion_menu"),
             InlineKeyboardButton("🛒 شاپ", callback_data="shop_menu")],
        ]
        markup = InlineKeyboardMarkup(keyboard)

        try:
            if update.message:
                await update.message.reply_text(welcome_text, reply_markup=markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(welcome_text, reply_markup=markup)
        except Exception as e:
            logger.error(f"start_command error: {e}")

    async def _get_bot_link(self, context) -> str:
        return "ble.ir/Balebattlebot"

    async def request_pvp_fight_handler(self, update, context):
        """نسخه بله - فایت در پیوی هم کار می‌کنه"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        query = update.callback_query
        await query.answer()

        challenger_id = query.from_user.id
        chat_id = query.message.chat.id

        # بررسی جان
        try:
            challenger_player = self.db.get_or_create_player(challenger_id)
            challenger_player = self.game.check_and_reset_hearts(challenger_player)
            if getattr(challenger_player, 'hearts', 5) <= 0:
                await query.edit_message_text("💀 جان شما تمام شده! فردا دوباره بیا.")
                return
        except Exception:
            pass

        # بررسی کارت
        player_cards = self.db.get_player_cards(challenger_id)
        if not player_cards:
            keyboard = [[InlineKeyboardButton("🎁 دریافت کارت اول", callback_data="daily_claim"),
                         InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]]
            await query.edit_message_text(
                "🎴 ابتدا باید کارتی داشته باشید!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # بررسی فایت فعال
        active_fights = self.db.get_user_active_fights(challenger_id)
        if active_fights:
            keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
            await query.edit_message_text(
                "⚠️ شما قبلاً چالش فعالی دارید!\nمنتظر انقضای آن باشید (۲ دقیقه).",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # ساخت فایت
        fight_id = self.db.create_fight(challenger_id, 0, chat_id)
        challenger_name = query.from_user.first_name

        text = (
            f"🥊 چالش PvP!\n\n"
            f"🔥 {challenger_name} همه را به مبارزه دعوت می‌کند!\n\n"
            f"آیا جرئت قبول این چالش را دارید؟\n\n"
            f"⚠️ توجه: اگر ربات را استارت نکرده‌اید، ابتدا @Balebattlebot را در پیوی استارت کنید!"
        )
        keyboard = [
            [InlineKeyboardButton("✊ قبول (نرمال)", callback_data=f"accept_pvp_{fight_id}")],
            [InlineKeyboardButton("🎲 قبول (تصادفی)", callback_data=f"accept_pvp_random_{fight_id}")]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.edit_message_text("✅ چالش شما ارسال شد!\nمنتظر قبول چالش باشید...")

    async def _announce_pvp_result(self, context, result: dict):
        """اعلام نتیجه فایت به هر دو بازیکن"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup

        fight_id    = result.get("fight_id", "")
        result_type = result.get("result_type", "")
        challenger  = result.get("challenger", {})
        opponent    = result.get("opponent", {})
        winner      = result.get("winner")

        stat_icons = {
            "power": "💪 قدرت",
            "speed": "⚡ سرعت",
            "iq": "🧠 هوش",
            "popularity": "❤️ محبوبیت"
        }
        rarity_icons = {
            "normal": "🟢", "epic": "🟣", "legend": "🟡"
        }

        def card_line(data: dict) -> str:
            card = data.get("card")
            if not card:
                return "نامشخص"
            rarity = str(getattr(card, "rarity", "normal")).lower().replace("cardrarity.", "")
            icon = rarity_icons.get(rarity, "⚪")
            return f"{icon} {card.name}"

        def stat_line(data: dict) -> str:
            stat = data.get("stat_type") or data.get("stat", "")
            val  = data.get("stat_value", "?")
            label = stat_icons.get(stat, stat)
            return f"{label}: {val}"

        ch_card_line = card_line(challenger)
        op_card_line = card_line(opponent)
        ch_stat_line = stat_line(challenger)
        op_stat_line = stat_line(opponent)

        ch_score  = challenger.get("score_gained", 0)
        op_score  = opponent.get("score_gained", 0)
        ch_hearts = challenger.get("hearts_lost", 0)
        op_hearts = opponent.get("hearts_lost", 0)
        ch_xp     = challenger.get("xp_gained", 0)
        op_xp     = opponent.get("xp_gained", 0)
        ch_lvlup  = challenger.get("level_up", False)
        op_lvlup  = opponent.get("level_up", False)

        # نام بازیکنان
        try:
            ch_player = self.db.get_or_create_player(challenger.get("user_id"))
            op_player = self.db.get_or_create_player(opponent.get("user_id"))
            ch_name = ch_player.first_name or "چلنجر"
            op_name = op_player.first_name or "حریف"
        except Exception:
            ch_name = "چلنجر"
            op_name = "حریف"

        # هدر نتیجه
        if result_type == "tie":
            header = "🤝 نتیجه: مساوی!"
        elif result_type == "challenger_wins":
            header = f"🏆 برنده: {ch_name}"
        else:
            header = f"🏆 برنده: {op_name}"

        # خط امتیاز و جان
        def rewards_line(score, hearts, xp, lvlup) -> str:
            parts = []
            if score > 0:
                parts.append(f"+{score} امتیاز")
            if xp > 0:
                parts.append(f"+{xp} XP")
            if hearts > 0:
                parts.append(f"-{hearts} ❤️")
            if lvlup:
                parts.append("⬆️ Level Up!")
            return "  |  ".join(parts) if parts else "—"

        ch_rewards = rewards_line(ch_score, ch_hearts, ch_xp, ch_lvlup)
        op_rewards = rewards_line(op_score, op_hearts, op_xp, op_lvlup)

        text = (
            f"{header}\n"
            f"{'─' * 24}\n"
            f"⚔️  {ch_name}\n"
            f"    کارت: {ch_card_line}\n"
            f"    ویژگی: {ch_stat_line}\n"
            f"    {ch_rewards}\n"
            f"{'─' * 24}\n"
            f"🛡️  {op_name}\n"
            f"    کارت: {op_card_line}\n"
            f"    ویژگی: {op_stat_line}\n"
            f"    {op_rewards}\n"
        )

        keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
        markup = InlineKeyboardMarkup(keyboard)

        # ذخیره برای match_info
        self.recent_matches[fight_id] = result

        ch_id = challenger.get("user_id")
        op_id = opponent.get("user_id")

        for uid in [ch_id, op_id]:
            if uid:
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=text,
                        reply_markup=markup
                    )
                except Exception as e:
                    logger.warning(f"Could not send result to user {uid}: {e}")

        # ارسال به گروه اگه chat_id داریم
        try:
            fight = self.db.get_fight_by_id(fight_id)
            if fight and fight.chat_id and fight.chat_id not in [ch_id, op_id]:
                await context.bot.send_message(
                    chat_id=fight.chat_id,
                    text=text
                )
        except Exception as e:
            logger.warning(f"Could not send result to group: {e}")

    async def pvp_card_select_handler(self, update, context):
        """نسخه بله - بعد از انتخاب هر دو کارت، سیستم ۳ راوندی رو شروع می‌کنه"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        from game_core import FightStatus
        query = update.callback_query
        await query.answer()

        parts = query.data.split("_")
        fight_id = parts[2]
        card_id = parts[3]
        user_id = query.from_user.id

        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            await query.edit_message_text("❌ فایت یافت نشد!")
            return

        # تعیین نقش
        if user_id == fight.challenger_id:
            field_name = "challenger_card_id"
        elif user_id == fight.opponent_id:
            field_name = "opponent_card_id"
        else:
            await query.answer("❌ شما بخشی از این فایت نیستید!", show_alert=True)
            return

        # بروزرسانی کارت انتخابی
        current_fight = self.db.get_fight_by_id(fight_id)
        update_data = {field_name: card_id}

        if user_id == fight.challenger_id and not current_fight.opponent_card_id:
            update_data["status"] = FightStatus.CHALLENGER_CARD_SELECTED
        elif user_id == fight.opponent_id and not current_fight.challenger_card_id:
            update_data["status"] = FightStatus.OPPONENT_CARD_SELECTED
        elif user_id == fight.challenger_id and current_fight.opponent_card_id:
            update_data["status"] = FightStatus.BOTH_CARDS_SELECTED
        elif user_id == fight.opponent_id and current_fight.challenger_card_id:
            update_data["status"] = FightStatus.BOTH_CARDS_SELECTED

        self.db.update_fight(fight_id, **update_data)
        self.db.increment_card_usage(user_id, card_id)

        selected_card = self.db.get_card_by_id(card_id)
        card_name = selected_card.name if selected_card else "کارت"

        # بررسی اینکه هر دو کارت انتخاب شدن
        updated_fight = self.db.get_fight_by_id(fight_id)
        if updated_fight.challenger_card_id and updated_fight.opponent_card_id:
            await query.edit_message_text(
                f"✅ کارت {card_name} انتخاب شد!\n\n⏳ در حال شروع بازی ۳ راوندی..."
            )
            await self._init_3round_battle(context, fight_id, updated_fight, query=None)
        else:
            await query.edit_message_text(
                f"✅ کارت {card_name} انتخاب شد!\n\n⏳ منتظر انتخاب کارت حریف..."
            )

    def _create_stat_selection_keyboard(self, fight_id: str, card):
        """کیبورد انتخاب ویژگی برای PvP تصادفی"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [
            [InlineKeyboardButton(f"💪 قدرت ({card.power})", callback_data=f"pvp_stat_{fight_id}_power")],
            [InlineKeyboardButton(f"⚡ سرعت ({card.speed})", callback_data=f"pvp_stat_{fight_id}_speed")],
            [InlineKeyboardButton(f"🧠 هوش ({card.iq})", callback_data=f"pvp_stat_{fight_id}_iq")],
            [InlineKeyboardButton(f"❤️ محبوبیت ({card.popularity})", callback_data=f"pvp_stat_{fight_id}_popularity")],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def accept_pvp_fight_handler(self, update, context):
        """نسخه بله - بدون check_user_started_bot"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        from game_core import FightStatus
        from datetime import datetime, timedelta
        query = update.callback_query
        await query.answer()

        fight_id = query.data.split("_")[-1]
        opponent_id = query.from_user.id

        # بررسی جان
        try:
            opponent_player = self.db.get_or_create_player(opponent_id)
            opponent_player = self.game.check_and_reset_hearts(opponent_player)
            if getattr(opponent_player, 'hearts', 5) <= 0:
                await query.answer("💀 جان شما تمام شده!", show_alert=True)
                return
        except Exception:
            pass

        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            await query.answer("❌ چالش یافت نشد یا منقضی شده!", show_alert=True)
            return

        if fight.challenger_id == opponent_id:
            await query.answer("❌ نمی‌توانید چالش خودتان را بپذیرید!", show_alert=True)
            return

        opponent_cards = self.db.get_player_cards(opponent_id)
        if not opponent_cards:
            await query.answer("❌ ابتدا کارتی باید داشته باشید!", show_alert=True)
            return

        if fight.status != FightStatus.WAITING_FOR_OPPONENT:
            await query.answer("❌ این چالش دیگر قابل قبول نیست!", show_alert=True)
            return

        claimed = self.db.claim_opponent_if_waiting(fight_id, opponent_id)
        if not claimed:
            await query.answer("❌ این چالش قبلاً پذیرفته شده.", show_alert=True)
            return

        # تمدید مهلت به ۱۵ دقیقه برای انتخاب کارت
        new_expiry = datetime.now() + timedelta(minutes=15)
        self.db.update_fight(fight_id, expires_at=new_expiry.isoformat())

        challenger = self.db.get_or_create_player(fight.challenger_id)
        opponent = self.db.get_or_create_player(opponent_id)

        text = (
            f"⚔️ فایت تایید شد!\n\n"
            f"🔥 {challenger.first_name} vs {opponent.first_name}\n\n"
            f"هر دو بازیکن در پیوی کارت خود را انتخاب کنید.\n"
            f"👆 برای انتخاب کارت: @Balebattlebot\n"
            f"⏰ مهلت: ۱۵ دقیقه"
        )
        keyboard = [[InlineKeyboardButton("🤖 رفتن به پیوی ربات", url="https://ble.ir/Balebattlebot")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        # ارسال پیوی به challenger
        try:
            await context.bot.send_message(
                chat_id=fight.challenger_id,
                text=f"✅ {opponent.first_name} چالش شما را پذیرفت!\n\nکارت خود را انتخاب کنید:",
                reply_markup=self._create_pvp_card_selection_keyboard(fight_id, fight.challenger_id)
            )
        except Exception as e:
            logger.warning(f"Could not send private message to challenger: {e}")

        # ارسال پیوی به opponent
        try:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=f"✅ شما چالش {challenger.first_name} را پذیرفتید!\n\nکارت خود را انتخاب کنید:",
                reply_markup=self._create_pvp_card_selection_keyboard(fight_id, opponent_id)
            )
        except Exception as e:
            logger.warning(f"Could not send private message to opponent: {e}")

    async def accept_pvp_random_handler(self, update, context):
        """نسخه بله - قبول تصادفی بدون check_user_started_bot"""
        import random
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        from game_core import FightStatus
        from datetime import datetime, timedelta
        query = update.callback_query
        await query.answer()

        fight_id = query.data.split("_")[-1]
        opponent_id = query.from_user.id

        try:
            opponent_player = self.db.get_or_create_player(opponent_id)
            opponent_player = self.game.check_and_reset_hearts(opponent_player)
            if getattr(opponent_player, 'hearts', 5) <= 0:
                await query.answer("💀 جان شما تمام شده!", show_alert=True)
                return
        except Exception:
            pass

        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            await query.answer("❌ چالش یافت نشد!", show_alert=True)
            return

        if fight.challenger_id == opponent_id:
            await query.answer("❌ نمی‌توانید چالش خودتان را بپذیرید!", show_alert=True)
            return

        if fight.status != FightStatus.WAITING_FOR_OPPONENT:
            await query.answer("❌ این چالش دیگر قابل قبول نیست!", show_alert=True)
            return

        claimed = self.db.claim_opponent_if_waiting(fight_id, opponent_id)
        if not claimed:
            await query.answer("❌ این چالش قبلاً پذیرفته شده.", show_alert=True)
            return

        # انتخاب تصادفی کارت برای هر دو
        ch_cards = self.db.get_player_cards(fight.challenger_id)
        op_cards = self.db.get_player_cards(opponent_id)

        if not ch_cards or not op_cards:
            await query.answer("❌ یکی از بازیکنان کارت ندارد!", show_alert=True)
            return

        ch_card = random.choice(ch_cards)
        op_card = random.choice(op_cards)

        self.db.update_fight(fight_id,
            challenger_card_id=ch_card.card_id,
            opponent_card_id=op_card.card_id,
            status='both_cards_selected'
        )

        new_expiry = datetime.now() + timedelta(minutes=15)
        self.db.update_fight(fight_id, expires_at=new_expiry.isoformat())

        challenger = self.db.get_or_create_player(fight.challenger_id)
        opponent = self.db.get_or_create_player(opponent_id)

        text = (
            f"⚔️ فایت تصادفی تایید شد!\n\n"
            f"🔥 {challenger.first_name} vs {opponent.first_name}\n\n"
            f"کارت‌ها به صورت تصادفی انتخاب شدند.\n"
            f"هر دو بازیکن ویژگی خود را انتخاب کنید.\n"
            f"👆 برای انتخاب ویژگی: @Balebattlebot\n"
            f"⏰ مهلت: ۱۵ دقیقه"
        )
        bot_btn = [[InlineKeyboardButton("🤖 رفتن به پیوی ربات", url="https://ble.ir/Balebattlebot")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(bot_btn))

        try:
            await context.bot.send_message(
                chat_id=fight.challenger_id,
                text=f"🎲 کارت شما: {ch_card.name}\n\nویژگی خود را انتخاب کنید:",
                reply_markup=self._create_stat_selection_keyboard(fight_id, ch_card)
            )
        except Exception as e:
            logger.warning(f"Could not send to challenger: {e}")

        try:
            await context.bot.send_message(
                chat_id=opponent_id,
                text=f"🎲 کارت شما: {op_card.name}\n\nویژگی خود را انتخاب کنید:",
                reply_markup=self._create_stat_selection_keyboard(fight_id, op_card)
            )
        except Exception as e:
            logger.warning(f"Could not send to opponent: {e}")

    def _create_stat_selection_keyboard(self, fight_id: str, card):
        """کیبورد انتخاب ویژگی برای PvP تصادفی"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [
            [InlineKeyboardButton(f"💪 قدرت ({card.power})", callback_data=f"pvp_stat_{fight_id}_power")],
            [InlineKeyboardButton(f"⚡ سرعت ({card.speed})", callback_data=f"pvp_stat_{fight_id}_speed")],
            [InlineKeyboardButton(f"🧠 هوش ({card.iq})", callback_data=f"pvp_stat_{fight_id}_iq")],
            [InlineKeyboardButton(f"❤️ محبوبیت ({card.popularity})", callback_data=f"pvp_stat_{fight_id}_popularity")],
        ]
        return InlineKeyboardMarkup(keyboard)

    def _create_pvp_card_selection_keyboard(self, fight_id: str, user_id: int, category: str = "menu", page: int = 1):
        """ایجاد کیبورد انتخاب کارت برای PvP"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        from game_core import CardRarity
        
        keyboard = []
        
        if category == "menu":
            # منوی اصلی - دسته‌بندی‌ها
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

    def setup_handlers(self, app):
        app.add_handler(BaleCommandHandler("start", self.start_command))
        app.add_handler(BaleCommandHandler("help", self.help_command))
        app.add_handler(BaleCommandHandler("profile", self.profile_command))
        app.add_handler(BaleCommandHandler("cards", self.cards_command))
        app.add_handler(BaleCommandHandler("claim", self.claim_command))
        app.add_handler(BaleCommandHandler("leaderboard", self.leaderboard_command))
        app.add_handler(BaleCommandHandler("fight", self.fight_command))
        app.add_handler(BaleCommandHandler("story", self.story_command))
        app.add_handler(BaleCommandHandler("id", self._id_command))
        callbacks = [
            ("^daily_claim$", self.daily_claim_handler),
            ("^my_cards$", self.my_cards_handler),
            ("^my_cards_nav_", self.my_cards_navigation_handler),
            ("^start_game$", self.start_game_handler),
            ("^request_pvp_fight$", self.request_pvp_fight_handler),
            ("^accept_pvp_random_", self.accept_pvp_random_handler),
            ("^accept_pvp_", self.accept_pvp_fight_handler),
            ("^pvp_cards_", self.pvp_cards_navigation_handler),
            ("^pvp_card_", self.pvp_card_select_handler),
            ("^pvp_stat_", self.pvp_stat_select_handler),
            ("^check_membership$", self.check_membership_handler),
            ("^mycards_", self.mycards_navigation_handler),
            ("^cardinfo_", self.cardinfo_handler),
            ("^toggle_fav_", self.toggle_favorite_handler),
            ("^r3_stat_", self.r3_stat_select_handler),
            ("^arena_pick_", self.arena_pick_handler),
            ("^mission_claim_", self.mission_claim_handler),
            ("^skins_menu_", self.skins_menu_handler),
            ("^skin_buy_", self.skin_buy_handler),
            ("^skin_activate_", self.skin_activate_handler),
            ("^skin_deactivate_", self.skin_deactivate_handler),
            ("^leaderboard$", self.leaderboard_handler),
            ("^lb_global_", self.leaderboard_display_handler),
            ("^lb_group_", self.leaderboard_display_handler),
            ("^help$", self.help_command),
            ("^card_view_", self.card_view_handler),
            ("^back_to_main$", self.back_to_main_handler),
            ("^match_info_", self.match_info_handler),
            ("^cooldown_card_", self.cooldown_card_handler),
            ("^fusion_menu$", self.fusion_menu_handler),
            ("^fusion_noop$", self.fusion_noop_handler),
            ("^fusion_start_", self.fusion_start_handler),
            ("^fusion_pick_", self.fusion_pick_handler),
            ("^fusion_confirm_", self.fusion_confirm_handler),
            ("^fusion_upgrade_", self.fusion_upgrade_handler),
            ("^mining_claim$", self.mining_claim_handler),
            ("^shop_menu$", self.shop_menu_handler),
            ("^shop_buy_heart$", self.shop_buy_heart_handler),
            ("^shop_upgrade_", self.shop_upgrade_handler),
            ("^shop_confirm_", self.shop_confirm_upgrade_handler),
            ("^shop_convert_score$", self.shop_convert_score_handler),
            ("^shop_do_convert_", self.shop_do_convert_handler),
            ("^shop_skins_list$", self.shop_skins_list_handler),
            ("^risk_menu$", self.risk_menu_handler),
            ("^risk_noop$", self.risk_noop_handler),
            ("^risk_challenge_", self.risk_challenge_handler),
            ("^risk_accept_", self.risk_accept_handler),
            ("^risk_card_", self.risk_card_select_handler),
            ("^risk_bluff_", self.risk_bluff_handler),
        ]
        for pattern, handler in callbacks:
            app.add_handler(BaleCallbackQueryHandler(handler, pattern=pattern))
        app.add_error_handler(self.error_handler)

    # ==================== ALIAS های متدهای مفقود ====================
    # telegram_bot.py از این نام‌ها استفاده می‌کنه ولی تعریف نشدن

    async def fight_command(self, update, context):
        """نسخه بله - دستور /fight در گروه"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        from game_core import FightStatus

        challenger_id = update.effective_user.id
        chat_id = update.effective_chat.id

        try:
            challenger_player = self.db.get_or_create_player(challenger_id)
            challenger_player = self.game.check_and_reset_hearts(challenger_player)
            if getattr(challenger_player, 'hearts', 5) <= 0:
                await update.message.reply_text("💀 جان شما تمام شده! فردا دوباره بیا.")
                return
        except Exception:
            pass

        player_cards = self.db.get_player_cards(challenger_id)
        if not player_cards:
            await update.message.reply_text(
                "🎴 ابتدا باید کارتی داشته باشید!\n"
                "در پیوی ربات /start بزنید: @Balebattlebot"
            )
            return

        active_fights = self.db.get_user_active_fights(challenger_id)
        if active_fights:
            await update.message.reply_text("⚠️ شما قبلاً چالش فعالی دارید!\nمنتظر انقضای آن باشید (۲ دقیقه).")
            return

        fight_id = self.db.create_fight(challenger_id, 0, chat_id)
        challenger_name = update.effective_user.first_name

        text = (
            f"🥊 چالش PvP!\n\n"
            f"🔥 {challenger_name} همه را به مبارزه دعوت می‌کند!\n\n"
            f"آیا جرئت قبول این چالش را دارید؟\n\n"
            f"⚠️ توجه: اگر ربات را استارت نکرده‌اید، ابتدا @Balebattlebot را در پیوی استارت کنید!"
        )
        keyboard = [
            [InlineKeyboardButton("✊ قبول (نرمال)", callback_data=f"accept_pvp_{fight_id}")],
            [InlineKeyboardButton("🎲 قبول (تصادفی)", callback_data=f"accept_pvp_random_{fight_id}")]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cardinfo_handler(self, update, context):
        """نمایش اطلاعات کارت + استیکر در بله"""
        import sqlite3
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        from game_core import CardRarity

        query = update.callback_query
        await query.answer()

        card_id = query.data.split("_")[1]
        user_id = query.from_user.id

        card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
        if not card:
            await query.answer("❌ کارت یافت نشد!", show_alert=True)
            return

        # دریافت is_favorite و usage_count
        conn = sqlite3.connect(self.db.db_path)
        c = conn.cursor()
        c.execute("SELECT is_favorite, usage_count FROM player_cards WHERE user_id=? AND card_id=?", (user_id, card_id))
        row = c.fetchone()
        conn.close()
        is_favorite = row[0] if row else 0
        usage_count = row[1] if row else 0

        rarity_colors = {
            CardRarity.NORMAL: "🟢", CardRarity.EPIC: "🟣",
            CardRarity.LEGEND: "🟡"
        }
        color = rarity_colors.get(card.rarity, "⚪")

        type_labels = {
            "POWER_TYPE": "💪 قدرت", "SPEED_TYPE": "⚡ سرعت",
            "IQ_TYPE": "🧠 هوش", "POPULARITY_TYPE": "❤️ محبوبیت"
        }
        type_label = type_labels.get(getattr(card, "card_type", ""), "❓")

        bio = getattr(card, "biography", "") or ""
        bio_text = f"\n📖 {bio[:100]}{'...' if len(bio) > 100 else ''}\n" if bio else ""

        text = (
            f"{color} {card.name} ({card.rarity.value.title()})\n"
            f"🏷️ تایپ: {type_label}\n"
            f"{bio_text}\n"
            f"💪 قدرت: {card.power}   ⚡ سرعت: {card.speed}\n"
            f"🧠 هوش: {card.iq}   ❤️ محبوبیت: {card.popularity}\n"
            f"📊 مجموع: {card.get_total_stats()}\n\n"
            f"🎮 استفاده: {usage_count} بار"
            f"{'   ⭐' if is_favorite else ''}"
        )

        fav_text = "💔 حذف از علاقه‌مندی‌ها" if is_favorite else "⭐ افزودن به علاقه‌مندی‌ها"
        keyboard = [
            [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav_{card_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="mycards_menu_1")]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        # ارسال استیکر کارت
        sticker_name = card.name.upper().replace(" ", "_").replace("-", "_")
        sticker_path = os.path.join("stickers", f"{sticker_name}.webp")
        if not os.path.exists(sticker_path):
            for f in os.listdir("stickers"):
                if f.lower() == f"{sticker_name.lower()}.webp" and "(2)" not in f:
                    sticker_path = os.path.join("stickers", f)
                    break
            else:
                sticker_path = None

        if sticker_path and os.path.exists(sticker_path):
            try:
                with open(sticker_path, "rb") as sticker:
                    await context.bot.send_sticker(chat_id=user_id, sticker=sticker)
            except Exception as e:
                logger.warning(f"Could not send sticker for {card.name}: {e}")

        # ویرایش پیام با اطلاعات کارت
        try:
            await query.edit_message_text(text=text, reply_markup=markup)
        except Exception:
            try:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
            except Exception:
                pass

    async def _id_command(self, update, context):
        """نمایش user_id کاربر"""
        user = update.effective_user
        text = f"🆔 User ID شما: {user.id}\n👤 نام: {user.first_name}"
        if update.message:
            await update.message.reply_text(text)

    def _get_bale_sticker_path(self, card_name: str) -> str:
        """پیدا کردن مسیر استیکر webp برای بله"""
        sticker_name = card_name.upper().replace(' ', '_').replace('-', '_')
        sticker_path = os.path.join("stickers", f"{sticker_name}.webp")
        if os.path.exists(sticker_path):
            return sticker_path
        # fallback: جستجوی case-insensitive
        try:
            for f in os.listdir("stickers"):
                if f.lower() == f"{sticker_name.lower()}.webp" and "(2)" not in f:
                    return os.path.join("stickers", f)
        except Exception:
            pass
        return None

    def _create_my_cards_keyboard(self, user_id: int, category: str = "menu", page: int = 1):
        """alias برای _create_mycards_keyboard"""
        return self._create_mycards_keyboard(user_id, category=category, page=page)

    def _is_command_allowed_in_chat(self, command: str, chat_type: str) -> bool:
        """در بله همه دستورات در همه چت‌ها مجازند"""
        return True

    async def send_no_hearts_message(self, query, context, player):
        """پیام تمام شدن جان"""
        from bale_adapter import InlineKeyboardButton, InlineKeyboardMarkup
        text = "💀 جان شما تمام شده!\n\nفردا دوباره بیا یا از شاپ جان بخر."
        keyboard = [[InlineKeyboardButton("🛒 شاپ", callback_data="shop_menu"),
                     InlineKeyboardButton("🔙 منو", callback_data="back_to_main")]]
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            try:
                await query.answer(text, show_alert=True)
            except Exception:
                pass


def main():
    bale_token = os.getenv("BALE_TOKEN")
    if not bale_token:
        try:
            with open("game_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            bale_token = config.get("bale_settings", {}).get("token")
        except Exception:
            pass
    if not bale_token:
        print("BALE_TOKEN not found. Set it in .env or game_config.json under bale_settings.token")
        return
    bot = BaleTelegramCardBot("game_config.json")
    cards = bot.db.get_all_cards()
    print(f"{len(cards)} cards in database")
    application = BaleApplicationBuilder().token(bale_token).build()
    bot.setup_handlers(application)
    async def post_init(app):
        me = await app.bot.get_me()
        if me:
            print(f"Bale bot ready: @{me.username or me.first_name}")
    application.post_init = post_init
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()