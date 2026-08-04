#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram interaction layer for the new Quick, Deck, and Easy modes."""

from __future__ import annotations

import json
import logging
import random
from urllib.parse import quote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Update,
)
from telegram.ext import ContextTypes

from systems.deck_system import DeckSystem
from systems.game_mode_system import (
    ABILITY_DEFINITIONS,
    EASY_CHOICE_TTL_SECONDS,
    EASY_LOBBY_TTL_SECONDS,
    QUICK_CHOICE_TTL_SECONDS,
    QUICK_GROUP_TTL_SECONDS,
    QUICK_INVITE_TTL_SECONDS,
)


logger = logging.getLogger(__name__)

STAT_LABELS = {
    "power": "💪 قدرت",
    "speed": "⚡ سرعت",
    "iq": "🧠 هوش",
    "popularity": "❤️ محبوبیت",
}


class GameModeHandlersMixin:
    """Handlers backed by :class:`systems.game_mode_system.GameModeSystem`."""

    async def fight_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the mode selector in both private chats and groups."""
        chat_type = update.effective_chat.type
        is_group = chat_type in ("group", "supergroup")
        user_id = update.effective_user.id
        if not self.db.get_player_cards(user_id):
            await update.message.reply_text("🎴 برای بازی ابتدا باید حداقل یک کارت داشته باشی.")
            return
        text, markup = self._game_mode_menu(is_group)
        await update.message.reply_text(text, reply_markup=markup)

    async def request_pvp_fight_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Replace the legacy PvP entry button with the explicit mode selector."""
        query = update.callback_query
        await query.answer()
        is_group = query.message.chat.type in ("group", "supergroup")
        text, markup = self._game_mode_menu(is_group)
        await query.edit_message_text(text, reply_markup=markup)

    @staticmethod
    def _game_mode_menu(is_group: bool):
        keyboard = [[InlineKeyboardButton("⚡ Quick Mode", callback_data="gm_mode_quick")]]
        if is_group:
            keyboard.extend(
                [
                    [InlineKeyboardButton("🃏 Deck Mode", callback_data="gm_mode_deck")],
                    [InlineKeyboardButton("🎉 Easy Mode", callback_data="gm_mode_easy")],
                ]
            )
        else:
            keyboard.append([InlineKeyboardButton("🗂 مدیریت دک‌ها", callback_data="deck_menu")])
        return "🎮 حالت بازی را انتخاب کن:", InlineKeyboardMarkup(keyboard)

    async def game_mode_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        mode = query.data.removeprefix("gm_mode_")
        is_group = query.message.chat.type in ("group", "supergroup")
        if mode == "easy":
            if not is_group:
                await query.answer("Easy Mode فقط داخل گروه اجرا می‌شود.", show_alert=True)
                return
            keyboard = [
                [InlineKeyboardButton(f"{rounds} راند", callback_data=f"gm_erounds_{rounds}")]
                for rounds in (1, 3, 5, 10)
            ]
            await query.edit_message_text(
                "🎉 Easy Mode\n\nتعداد راندها را انتخاب کن:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return
        if mode not in ("quick", "deck"):
            await query.answer("حالت نامعتبر است.", show_alert=True)
            return
        if mode == "deck" and not is_group:
            await query.answer("Deck Mode فعلاً از داخل گروه شروع می‌شود.", show_alert=True)
            return
        keyboard = [
            [InlineKeyboardButton("🎯 Normal", callback_data=f"gm_variant_{mode}_normal")],
            [InlineKeyboardButton("🎲 Random", callback_data=f"gm_variant_{mode}_random")],
        ]
        await query.edit_message_text(
            f"{'⚡ Quick' if mode == 'quick' else '🃏 Deck'} Mode\n\nنوع بازی را انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def game_variant_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        _, _, mode, variant = query.data.split("_", 3)
        is_group = query.message.chat.type in ("group", "supergroup")
        if is_group:
            request = self.modes.create_group_challenge(
                query.from_user.id, mode, variant, query.message.chat_id
            )
            mode_title = "Quick" if mode == "quick" else "Deck"
            variant_title = "Normal" if variant == "normal" else "Random"
            text = (
                f"⚔️ {query.from_user.first_name} یک چالش {mode_title} / {variant_title} ساخته!\n\n"
                "اولین بازیکنی که قبول کند وارد بازی می‌شود.\n"
                f"⏳ مهلت پذیرش: {QUICK_GROUP_TTL_SECONDS} ثانیه"
            )
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✊ قبول مبارزه", callback_data=f"gm_accept_{request['request_id']}")]]
                ),
            )
            self.modes.update_message_reference(
                request["request_id"], query.message.chat_id, query.message.message_id
            )
            self._schedule_mode_job(
                context,
                self.game_request_expire_job,
                QUICK_GROUP_TTL_SECONDS,
                {"request_id": request["request_id"]},
                f"gm-expire-{request['request_id']}",
            )
            return

        if mode != "quick":
            await query.answer("این حالت در پیوی فعال نیست.", show_alert=True)
            return
        keyboard = [
            [InlineKeyboardButton("🌍 حریف تصادفی", callback_data=f"gm_source_{mode}_{variant}_queue")],
            [InlineKeyboardButton("🔗 دعوت با لینک", callback_data=f"gm_source_{mode}_{variant}_invite")],
        ]
        await query.edit_message_text(
            "حریف را چطور پیدا کنیم؟", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def game_source_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        _, _, mode, variant, source = query.data.split("_", 4)
        user_id = query.from_user.id
        if source == "queue":
            status, request = self.modes.matchmake_random(user_id, mode, variant)
            if status == "waiting":
                await query.edit_message_text(
                    "🔎 در حال پیدا کردن حریف تصادفی…\n\n"
                    "مچ‌سازی بدون رتبه‌بندی و فقط در همین نوع بازی انجام می‌شود.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("❌ لغو", callback_data=f"gm_cancel_{request['request_id']}")]]
                    ),
                )
                self.modes.update_message_reference(
                    request["request_id"], query.message.chat_id, query.message.message_id
                )
                self._schedule_mode_job(
                    context,
                    self.game_request_expire_job,
                    QUICK_INVITE_TTL_SECONDS,
                    {"request_id": request["request_id"]},
                    f"gm-expire-{request['request_id']}",
                )
                return
            await query.edit_message_text("✅ حریف پیدا شد؛ بازی در حال شروع است…")
            await self._edit_request_panel(context, request, "✅ حریف پیدا شد؛ بازی شروع شد.")
            await self._launch_mode_match(context, request)
            return

        request = self.modes.create_invite(user_id, mode, variant, query.message.chat_id)
        username = context.bot.username or "TelBattleBot"
        deep_link = f"https://t.me/{username}?start=gm_{request['invite_token']}"
        share_url = f"https://t.me/share/url?url={quote(deep_link, safe='')}&text={quote('بیا با هم TelBattle بازی کنیم!', safe='')}"
        await query.edit_message_text(
            "🔗 لینک دعوت آماده شد.\n\n"
            "این لینک یک‌بارمصرف است و فقط ۵ دقیقه اعتبار دارد.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📨 ارسال لینک برای دوست", url=share_url)],
                    [InlineKeyboardButton("❌ لغو درخواست", callback_data=f"gm_cancel_{request['request_id']}")],
                ]
            ),
        )
        self.modes.update_message_reference(
            request["request_id"], query.message.chat_id, query.message.message_id
        )
        self._schedule_mode_job(
            context,
            self.game_request_expire_job,
            QUICK_INVITE_TTL_SECONDS,
            {"request_id": request["request_id"]},
            f"gm-expire-{request['request_id']}",
        )

    async def handle_game_invite_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Handle ``/start gm_TOKEN``. Returns True when the payload was ours."""
        if not context.args or not context.args[0].startswith("gm_"):
            return False
        token = context.args[0][3:]
        if not token:
            return False
        if not self.db.get_player_cards(update.effective_user.id):
            await update.message.reply_text("🎴 برای قبول دعوت ابتدا باید حداقل یک کارت داشته باشی.")
            return True
        ok, reason, request = self.modes.accept_invite(token, update.effective_user.id)
        if not ok:
            messages = {
                "self_accept": "❌ نمی‌توانی دعوت خودت را قبول کنی.",
                "expired": "⏳ زمان درخواست تمام شد.\nاین دعوت منقضی شده است.",
                "accepted": "❌ این دعوت قبلاً توسط بازیکن دیگری پذیرفته شده است.",
                "completed": "❌ این بازی قبلاً تمام شده است.",
                "cancelled": "❌ سازنده، این دعوت را لغو کرده است.",
            }
            await update.message.reply_text(messages.get(reason, "❌ این دعوت معتبر نیست."))
            return True
        await update.message.reply_text("✅ دعوت را پذیرفتی؛ بازی در حال شروع است…")
        await self._edit_request_panel(context, request, "✅ دعوت پذیرفته شد؛ بازی شروع شد.")
        await self._launch_mode_match(context, request)
        return True

    async def game_accept_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        request_id = query.data.removeprefix("gm_accept_")
        if not self.db.get_player_cards(query.from_user.id):
            await query.answer("ابتدا باید حداقل یک کارت داشته باشی.", show_alert=True)
            return
        ok, reason, request = self.modes.accept_request(request_id, query.from_user.id)
        if not ok:
            message = (
                "⏳ زمان درخواست تمام شد و درخواست منقضی شد."
                if reason == "expired"
                else "❌ این درخواست دیگر قابل پذیرش نیست."
            )
            await query.answer(message, show_alert=True)
            if reason == "expired":
                await query.edit_message_text("⏳ زمان درخواست تمام شد.\nاین درخواست منقضی شد.")
            return
        await query.edit_message_text("✅ چالش پذیرفته شد؛ ادامه‌ی بازی طبق حالت انتخاب‌شده انجام می‌شود.")
        await self._launch_mode_match(context, request)

    async def game_cancel_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        request_id = query.data.removeprefix("gm_cancel_")
        if self.modes.cancel_request(request_id, query.from_user.id):
            await query.answer("درخواست لغو شد.")
            await query.edit_message_text("❌ درخواست بازی لغو شد.")
        else:
            await query.answer("این درخواست قابل لغو نیست.", show_alert=True)

    @staticmethod
    def _schedule_mode_job(context, callback, seconds: int, data: dict, name: str):
        if context.job_queue:
            context.job_queue.run_once(callback, seconds, data=data, name=name)

    async def game_request_expire_job(self, context: ContextTypes.DEFAULT_TYPE):
        request_id = context.job.data["request_id"]
        request = self.modes.get_request(request_id)
        if not request or not self.modes.expire_request(request_id):
            return
        await self._edit_request_panel(
            context,
            request,
            "⏳ زمان درخواست تمام شد.\nاین درخواست منقضی شد.",
        )

    async def _edit_request_panel(self, context, request, text: str):
        chat_id = request.get("origin_chat_id")
        message_id = request.get("origin_message_id")
        if not chat_id or not message_id:
            return
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
        except Exception as exc:
            logger.debug("Could not edit request panel %s: %s", request.get("request_id"), exc)

    async def _launch_mode_match(self, context, request: dict):
        if request["mode"] == "quick":
            await self._launch_quick_match(context, request)
        elif request["mode"] == "deck":
            await self._launch_deck_match(context, request)

    async def _launch_quick_match(self, context, request: dict):
        try:
            state = self.modes.start_quick_match(request["request_id"])
        except ValueError as exc:
            logger.warning("Could not start Quick match %s: %s", request["request_id"], exc)
            return
        if state["phase"] == "card_selection":
            for user_id in state["players"]:
                await self._send_quick_card_page(context, request["request_id"], user_id, 0)
            self._schedule_mode_job(
                context,
                self.quick_phase_timeout_job,
                QUICK_CHOICE_TTL_SECONDS,
                {"request_id": request["request_id"], "phase": "card_selection"},
                f"gm-quick-card-{request['request_id']}",
            )
        else:
            await self._send_quick_ability_panels(context, request["request_id"], state)

    async def _send_quick_card_page(self, context, request_id: str, user_id: int, page: int, query=None):
        cards = self.db.get_player_cards(user_id)
        per_page = 8
        total_pages = max(1, (len(cards) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        selected = cards[page * per_page : (page + 1) * per_page]
        keyboard = [
            [InlineKeyboardButton(card.name, callback_data=f"gm_qcard_{request_id}_{card.card_id}")]
            for card in selected
        ]
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton("«", callback_data=f"gm_qpage_{request_id}_{page - 1}"))
        navigation.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page + 1 < total_pages:
            navigation.append(InlineKeyboardButton("»", callback_data=f"gm_qpage_{request_id}_{page + 1}"))
        keyboard.append(navigation)
        text = "🎴 کارت Quick خودت را انتخاب کن.\nاولین انتخاب نهایی است. ⏳ ۶۰ ثانیه"
        markup = InlineKeyboardMarkup(keyboard)
        try:
            if query:
                await query.edit_message_text(text, reply_markup=markup)
            else:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
        except Exception as exc:
            logger.warning("Could not send Quick card picker to %s: %s", user_id, exc)

    async def quick_card_page_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        _, _, request_id, page = query.data.split("_", 3)
        await self._send_quick_card_page(context, request_id, query.from_user.id, int(page), query=query)

    async def quick_card_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        _, _, request_id, card_id = query.data.split("_", 3)
        try:
            state, advanced = self.modes.select_quick_card(request_id, query.from_user.id, card_id)
        except ValueError as exc:
            message = "این انتخاب قبلاً ثبت شده و قابل تغییر نیست." if str(exc) == "choice_locked" else "انتخاب معتبر نیست."
            await query.answer(message, show_alert=True)
            return
        card = self.db.get_card_by_id(card_id)
        await query.answer("کارت ثبت شد.")
        await query.edit_message_text(f"✅ {card.name if card else 'کارت'} انتخاب شد.\nمنتظر حریف…")
        if advanced:
            await self._send_quick_ability_panels(context, request_id, state)

    def _quick_arena_text(self, state: dict) -> str:
        arena = self.modes._arena(state["arena"])
        modifiers = [f"{STAT_LABELS.get(stat, stat)} {delta:+d}" for stat, delta in arena.get("modifiers", {}).items()]
        rules = []
        if arena.get("disabled_stats"):
            rules.append("غیرفعال: " + "، ".join(STAT_LABELS.get(stat, stat) for stat in arena["disabled_stats"]))
        if not arena.get("abilities_enabled", True):
            rules.append("Ability غیرفعال است")
        if not arena.get("passives_enabled", True):
            rules.append("Passive غیرفعال است")
        details = "\n".join(modifiers + rules) or "بدون تغییر عددی یا قانون ویژه"
        return f"{arena['emoji']} زمین: {arena['name']}\n{details}"

    async def _send_quick_ability_panels(self, context, request_id: str, state: dict):
        arena = self.modes._arena(state["arena"])
        for user_id in state["players"]:
            abilities = self.modes.list_player_abilities(user_id) if arena.get("abilities_enabled", True) else []
            keyboard = [
                [InlineKeyboardButton(f"{item['title']} ×{item['quantity']}", callback_data=f"gm_qability_{request_id}_{item['ability_key']}")]
                for item in abilities
            ]
            keyboard.append([InlineKeyboardButton("بدون Ability", callback_data=f"gm_qability_{request_id}_skip")])
            text = self._quick_arena_text(state) + "\n\nیک Ability مصرفی انتخاب کن یا رد شو."
            try:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as exc:
                logger.warning("Could not send ability panel to %s: %s", user_id, exc)
        self._schedule_mode_job(
            context,
            self.quick_phase_timeout_job,
            30,
            {"request_id": request_id, "phase": "ability_selection"},
            f"gm-quick-ability-{request_id}",
        )

    async def quick_ability_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        _, _, request_id, ability_key = query.data.split("_", 3)
        try:
            state, advanced = self.modes.select_quick_ability(request_id, query.from_user.id, ability_key)
        except ValueError as exc:
            message = "این انتخاب قبلاً نهایی شده است." if str(exc) == "choice_locked" else "Ability قابل استفاده نیست."
            await query.answer(message, show_alert=True)
            return
        title = "بدون Ability" if ability_key == "skip" else ABILITY_DEFINITIONS[ability_key]["title"]
        await query.answer("انتخاب ثبت شد.")
        await query.edit_message_text(f"✅ {title}\nمنتظر حریف…")
        if advanced:
            await self._send_quick_stat_panels(context, request_id, state)

    async def _send_quick_stat_panels(self, context, request_id: str, state: dict):
        for user_id in state["players"]:
            actor_ability = state["ability_choices"].get(str(user_id))
            extra = ""
            if actor_ability == "reveal_opponent":
                opponent_id = next(pid for pid in state["players"] if pid != user_id)
                opponent_card = self.db.get_card_by_id(state["cards"][str(opponent_id)])
                if opponent_card:
                    extra = f"\n👁 کارت حریف: {opponent_card.name}"
            allowed = self.modes.allowed_quick_stats(state, user_id)
            keyboard = [
                [InlineKeyboardButton(STAT_LABELS[stat], callback_data=f"gm_qstat_{request_id}_{stat}")]
                for stat in allowed
            ]
            text = self._quick_arena_text(state) + extra + "\n\nویژگی خودت را انتخاب کن. ⏳ ۶۰ ثانیه"
            try:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as exc:
                logger.warning("Could not send stat panel to %s: %s", user_id, exc)
        self._schedule_mode_job(
            context,
            self.quick_phase_timeout_job,
            QUICK_CHOICE_TTL_SECONDS,
            {"request_id": request_id, "phase": "stat_selection"},
            f"gm-quick-stat-{request_id}",
        )

    async def quick_stat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        _, _, request_id, stat = query.data.split("_", 3)
        try:
            _, report = self.modes.select_quick_stat(request_id, query.from_user.id, stat)
        except ValueError as exc:
            message = "این انتخاب قبلاً نهایی شده است." if str(exc) == "choice_locked" else "این ویژگی در زمین فعلی مجاز نیست."
            await query.answer(message, show_alert=True)
            return
        await query.answer("ویژگی ثبت شد.")
        await query.edit_message_text(f"✅ {STAT_LABELS.get(stat, stat)} انتخاب شد.\nمنتظر حریف…")
        if report:
            await self._announce_quick_result(context, report)

    async def quick_phase_timeout_job(self, context: ContextTypes.DEFAULT_TYPE):
        request_id = context.job.data["request_id"]
        expected_phase = context.job.data["phase"]
        state = self.modes.get_state(request_id)
        if not state or state.get("phase") != expected_phase:
            return
        if expected_phase == "ability_selection":
            for user_id in state["players"]:
                latest = self.modes.get_state(request_id)
                if latest.get("phase") != "ability_selection":
                    break
                if str(user_id) not in latest.get("ability_choices", {}):
                    latest, advanced = self.modes.select_quick_ability(request_id, user_id, "skip")
                    if advanced:
                        await self._send_quick_stat_panels(context, request_id, latest)
            return
        choice_key = "cards" if expected_phase == "card_selection" else "stat_choices"
        missing = [uid for uid in state["players"] if str(uid) not in state.get(choice_key, {})]
        if not missing:
            return
        report = self.modes.forfeit_quick(request_id, missing, reason=f"{expected_phase}_timeout")
        await self._announce_quick_result(context, report)

    async def _announce_quick_result(self, context, report: dict):
        request = self.modes.get_request(report["request_id"])
        players = report["players"]
        names = {uid: self.db.get_or_create_player(uid).first_name for uid in players}
        if report.get("forfeit"):
            if report.get("winner_id"):
                text = f"🏆 {names[report['winner_id']]} برنده شد.\n⏳ حریف در زمان مقرر انتخاب خود را ثبت نکرد."
            else:
                text = "⏳ هیچ‌کدام در زمان مقرر انتخاب نکردند؛ بازی بدون برنده تمام شد."
        elif report.get("is_tie"):
            text = "🤝 نبرد Quick مساوی شد."
        else:
            winner_id = report["winner_id"]
            winner = report["breakdown"][str(winner_id)]
            text = f"🏆 {names[winner_id]} با کارت {winner['card_name']} برنده شد!"
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📋 مشاهده جزئیات", callback_data=f"gm_report_{report['request_id']}")]]
        )
        targets = (
            [request["origin_chat_id"]]
            if request and request.get("source") == "group_challenge"
            else players
        )
        for chat_id in dict.fromkeys(targets):
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
            except Exception as exc:
                logger.warning("Could not announce Quick result in %s: %s", chat_id, exc)

    async def game_report_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        request_id = query.data.removeprefix("gm_report_")
        report = self.modes.get_report(request_id)
        if not report or query.from_user.id not in report.get("players", report.get("winner_ids", [])):
            await query.answer("گزارش برای شما در دسترس نیست.", show_alert=True)
            return
        await query.answer()
        if report["mode"] == "quick":
            request = self.modes.get_request(request_id)
            lines = ["📋 گزارش کامل Quick", ""]
            if report.get("forfeit"):
                lines.append("نتیجه با پایان مهلت تعیین شد.")
            else:
                lines.append(f"زمین اولیه: {report.get('initial_arena')}")
                lines.append(f"زمین نهایی: {report.get('arena')}")
                for uid, item in report.get("breakdown", {}).items():
                    name = self.db.get_or_create_player(int(uid)).first_name
                    lines.extend(
                        [
                            "",
                            f"{name}: {item['card_name']}",
                            f"ویژگی: {STAT_LABELS.get(item['selected_stat'], item['selected_stat'])}",
                            f"عدد پایه: {item['base_value']} → نهایی: {item['final_value']}",
                            f"Ability: {item['ability_used']}",
                            f"Passive: {(item['passive'] or {}).get('name', 'فعال نشد')}",
                        ]
                    )
            await context.bot.send_message(chat_id=query.from_user.id, text="\n".join(lines))

    # -------------------- Deck Mode --------------------

    async def _launch_deck_match(self, context, request: dict):
        ch_id, op_id = request["creator_id"], request["opponent_id"]
        chat_id = request.get("origin_chat_id") or ch_id
        fight_id = self.db.create_fight(ch_id, op_id, chat_id)
        if request["variant"] == "normal":
            deck_system = DeckSystem(self.db)
            missing = [uid for uid in (ch_id, op_id) if not deck_system.get_valid_decks(uid)]
            if missing:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ یکی از بازیکنان دک کامل ندارد؛ ابتدا در پیوی یک دک سه‌کارته بسازید.",
                )
                self.db.delete_fight(fight_id)
                return
            await context.bot.send_message(chat_id=chat_id, text="🃏 هر دو بازیکن دک خود را در پیوی انتخاب کنند.")
            await self._send_deck_selection(context, fight_id, ch_id)
            await self._send_deck_selection(context, fight_id, op_id)
            return

        ch_cards = self.db.get_player_cards(ch_id)
        op_cards = self.db.get_player_cards(op_id)
        if len(ch_cards) < 3 or len(op_cards) < 3:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ برای Random Deck هر بازیکن حداقل سه کارت لازم دارد.")
            self.db.delete_fight(fight_id)
            return
        ch_ids = [card.card_id for card in random.sample(ch_cards, 3)]
        op_ids = [card.card_id for card in random.sample(op_cards, 3)]
        self.db.update_fight(fight_id, challenger_card_id=ch_ids[0], opponent_card_id=op_ids[0])
        conn = self.modes._connect()
        conn.execute(
            """
            INSERT OR IGNORE INTO battle_states
            (fight_id, challenger_id, opponent_id, challenger_card_id, opponent_card_id,
             arena, current_round, challenger_rounds_won, opponent_rounds_won,
             challenger_used_stats, opponent_used_stats, challenger_current_stats,
             opponent_current_stats, status, created_at)
            VALUES (?,?,?,?,?,?,1,0,0,'[]','[]','{}','{}','waiting_deck',datetime('now'))
            """,
            (fight_id, ch_id, op_id, "", "", ""),
        )
        conn.commit()
        conn.close()
        self.db.update_battle_deck_state(fight_id, "challenger", ch_ids, selected=True)
        self.db.update_battle_deck_state(fight_id, "opponent", op_ids, selected=True)
        self.db.init_battle_deck_cards(fight_id, ch_ids, op_ids)
        fight = self.db.get_fight_by_id(fight_id)
        await context.bot.send_message(chat_id=chat_id, text="🎲 دک‌های تصادفی ساخته شدند؛ نبرد شروع می‌شود.")
        await self._init_3round_battle(context, fight_id, fight)

    # -------------------- Easy Mode --------------------

    async def easy_round_count_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.message.chat.type not in ("group", "supergroup"):
            await query.answer("Easy Mode فقط در گروه است.", show_alert=True)
            return
        rounds = int(query.data.removeprefix("gm_erounds_"))
        request = self.modes.create_easy_lobby(query.from_user.id, query.message.chat_id, rounds)
        await query.edit_message_text(
            self._easy_lobby_text(request["request_id"]),
            reply_markup=self._easy_lobby_markup(request["request_id"]),
        )
        self.modes.update_message_reference(
            request["request_id"], query.message.chat_id, query.message.message_id
        )
        self._schedule_mode_job(
            context,
            self.easy_lobby_timeout_job,
            EASY_LOBBY_TTL_SECONDS,
            {"request_id": request["request_id"]},
            f"gm-easy-lobby-{request['request_id']}",
        )

    def _easy_lobby_text(self, request_id: str) -> str:
        state = self.modes.get_state(request_id) or {"players": [], "rounds": 1}
        return (
            f"🎉 Easy Mode — {state['rounds']} راند\n\n"
            f"بازیکنان آماده: {len(state['players'])}\n"
            "برای ورود Ready را بزنید. بازی پس از ۳۰ ثانیه خودکار شروع می‌شود."
        )

    @staticmethod
    def _easy_lobby_markup(request_id: str):
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Ready", callback_data=f"gm_eready_{request_id}")],
                [InlineKeyboardButton("▶️ شروع الان", callback_data=f"gm_estart_{request_id}")],
            ]
        )

    async def easy_ready_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        request_id = query.data.removeprefix("gm_eready_")
        if not self.db.get_player_cards(query.from_user.id):
            await query.answer("برای بازی حداقل یک کارت لازم داری.", show_alert=True)
            return
        ok, reason, _ = self.modes.join_easy_lobby(request_id, query.from_user.id)
        if not ok:
            await query.answer("لابی بسته یا منقضی شده است.", show_alert=True)
            return
        await query.answer("از قبل آماده بودی." if reason == "already_ready" else "آماده شدی!")
        try:
            await query.edit_message_text(
                self._easy_lobby_text(request_id), reply_markup=self._easy_lobby_markup(request_id)
            )
        except Exception:
            pass

    async def easy_start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        request_id = query.data.removeprefix("gm_estart_")
        request = self.modes.get_request(request_id)
        if not request or request["creator_id"] != query.from_user.id:
            await query.answer("فقط سازنده می‌تواند زودتر شروع کند.", show_alert=True)
            return
        await query.answer()
        await self._begin_easy_match(context, request_id)

    async def easy_lobby_timeout_job(self, context: ContextTypes.DEFAULT_TYPE):
        await self._begin_easy_match(context, context.job.data["request_id"])

    async def _begin_easy_match(self, context, request_id: str):
        ok, reason, state = self.modes.start_easy_match(request_id)
        request = self.modes.get_request(request_id)
        if not ok:
            if reason == "already_started":
                return
            if request:
                await self._edit_request_panel(
                    context,
                    request,
                    "⏳ زمان لابی تمام شد؛ برای شروع Easy Mode حداقل دو بازیکن لازم است.",
                )
            return
        await self._edit_request_panel(context, request, "✅ لابی بسته شد؛ Easy Mode شروع شد!")
        await self._send_easy_question(context, request_id, state)

    async def _send_easy_question(self, context, request_id: str, state: dict):
        request = self.modes.get_request(request_id)
        text = (
            f"🎯 راند {state['current_round']} از {state['rounds']}\n\n"
            f"{state['question']['text']}\n\n"
            "کارت را از منوی شخصی زیر انتخاب کن. اولین انتخاب نهایی است. ⏳ ۳۰ ثانیه"
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎴 انتخاب کارت", switch_inline_query_current_chat=f"easy {request_id}")]]
        )
        await context.bot.send_message(chat_id=request["origin_chat_id"], text=text, reply_markup=markup)
        self._schedule_mode_job(
            context,
            self.easy_round_timeout_job,
            EASY_CHOICE_TTL_SECONDS,
            {"request_id": request_id, "round": state["current_round"]},
            f"gm-easy-round-{request_id}-{state['current_round']}",
        )

    async def easy_inline_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        inline_query = update.inline_query
        parts = (inline_query.query or "").strip().split()
        if len(parts) != 2 or parts[0] != "easy":
            return
        request_id = parts[1]
        user_id = inline_query.from_user.id
        options = self.modes.get_easy_options(request_id, user_id)
        results = []
        for card in options:
            result_id = f"ez|{request_id}|{user_id}|{card.card_id}"
            sticker_file_id = await self._get_inline_card_sticker_file_id(context, user_id, card)
            if sticker_file_id:
                results.append(
                    InlineQueryResultCachedSticker(id=result_id, sticker_file_id=sticker_file_id)
                )
                continue
            photo_file_id = await self._get_inline_card_photo_file_id(context, user_id, card)
            if photo_file_id:
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=result_id,
                        photo_file_id=photo_file_id,
                        title=card.name,
                        caption=f"🎴 {card.name}",
                    )
                )
            else:
                results.append(
                    InlineQueryResultArticle(
                        id=result_id,
                        title=card.name,
                        description="انتخاب نهایی این راند",
                        input_message_content=InputTextMessageContent(f"🎴 {card.name}"),
                    )
                )
        if not results:
            results.append(
                InlineQueryResultArticle(
                    id="easy_no_cards",
                    title="کارت قابل انتخابی نیست",
                    input_message_content=InputTextMessageContent("⚠️ کارت قابل انتخابی نیست."),
                )
            )
        await inline_query.answer(results, cache_time=0, is_personal=True)

    async def easy_chosen_inline_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chosen = update.chosen_inline_result
        if not chosen.result_id.startswith("ez|"):
            return
        try:
            _, request_id, target_user, card_id = chosen.result_id.split("|", 3)
            target_user = int(target_user)
        except (ValueError, TypeError):
            return
        if chosen.from_user.id != target_user:
            return
        ok, reason, state = self.modes.select_easy_card(request_id, target_user, card_id)
        if not ok:
            logger.info("Ignored Easy selection %s: %s", chosen.result_id, reason)
            return
        if reason == "all_selected":
            await self._resolve_and_announce_easy(context, request_id)

    async def easy_round_timeout_job(self, context: ContextTypes.DEFAULT_TYPE):
        request_id = context.job.data["request_id"]
        expected_round = context.job.data["round"]
        state = self.modes.get_state(request_id)
        if not state or state.get("phase") != "selection" or state.get("current_round") != expected_round:
            return
        await self._resolve_and_announce_easy(context, request_id)

    async def _resolve_and_announce_easy(self, context, request_id: str):
        try:
            result = self.modes.resolve_easy_round(request_id)
        except ValueError:
            return
        request = self.modes.get_request(request_id)
        entries = result["round"]["entries"]
        lines = [f"🏁 نتیجه راند {result['round']['round']}"]
        for item in entries:
            name = self.db.get_or_create_player(item["user_id"]).first_name
            lines.append(f"+{item['points']} — {name} با {item['card_name']}")
        if not entries:
            lines.append("هیچ انتخاب معتبری ثبت نشد.")
        await context.bot.send_message(chat_id=request["origin_chat_id"], text="\n".join(lines))
        if result["completed"]:
            report = result["report"]
            score_lines = []
            for uid, score in sorted(report["scores"].items(), key=lambda pair: pair[1], reverse=True):
                name = self.db.get_or_create_player(int(uid)).first_name
                score_lines.append(f"{name}: {score}")
            winner_names = [self.db.get_or_create_player(uid).first_name for uid in report["winner_ids"]]
            await context.bot.send_message(
                chat_id=request["origin_chat_id"],
                text="🏆 پایان Easy Mode\n\n" + "\n".join(score_lines) + "\n\nبرنده: " + "، ".join(winner_names),
            )
        else:
            await self._send_easy_question(context, request_id, result["state"])
