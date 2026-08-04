#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🃏 Deck Management Handlers
منوی ساخت، مشاهده و حذف دک‌های بازیکن
"""

import json
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from game_core import Card, CardRarity
from systems.deck_system import DeckSystem

logger = logging.getLogger(__name__)

RARITY_EMOJI = {'normal': '🟢', 'epic': '🟣', 'legend': '🟡', 'rare': '🔵'}
RARITY_FA    = {'normal': 'معمولی', 'epic': 'حماسی', 'legend': 'افسانه‌ای', 'rare': 'کمیاب'}


def _rarity_val(card: Card) -> str:
    return card.rarity.value if hasattr(card.rarity, 'value') else str(card.rarity)


class DeckHandlersMixin:
    """Mixin برای handler های مدیریت دک"""

    # ==================== MENU ====================

    async def deck_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست دک‌های بازیکن"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        deck_system = DeckSystem(self.db)
        decks = deck_system.get_player_decks(user_id)

        keyboard = []
        text = f"🗂️ **دک‌های من** ({len(decks)}/{DeckSystem.MAX_DECKS})\n\n"

        if not decks:
            text += "هنوز هیچ دکی نساختید!\n\nبرای فایت PvP باید حداقل یک دک ۳ کارته داشته باشید."
        else:
            for deck in decks:
                status = "✅" if deck['is_valid'] else "⚠️"
                synergy = self.modes.calculate_deck_synergy(
                    card.card_id for card in deck['cards']
                )
                card_line = "  ".join(
                    f"{RARITY_EMOJI.get(_rarity_val(c), '⚪')}{c.name[:10]}"
                    for c in deck['cards']
                )
                text += (
                    f"{status} **{deck['deck_name']}** — "
                    f"+{synergy['score']} هم‌افزایی\n└ {card_line}\n\n"
                )
                keyboard.append([
                    InlineKeyboardButton(f"👁 {deck['deck_name']}", callback_data=f"deck_view_{deck['deck_id']}"),
                    InlineKeyboardButton("🗑 حذف", callback_data=f"deck_delete_{deck['deck_id']}")
                ])

        if len(decks) < DeckSystem.MAX_DECKS:
            keyboard.append([InlineKeyboardButton("➕ ساخت دک جدید", callback_data="deck_create")])
        keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_view_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات یک دک"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        deck_id = query.data.split("deck_view_")[1]
        deck_system = DeckSystem(self.db)
        cards = deck_system.get_deck_cards(deck_id, user_id)
        deck_data = self.db.get_deck_by_id(deck_id)

        if not deck_data or deck_data['player_id'] != user_id:
            await query.answer("❌ دک یافت نشد!", show_alert=True)
            return

        text = f"🃏 **{deck_data['deck_name']}**\n\n"
        for card in cards:
            rv = _rarity_val(card)
            emoji = RARITY_EMOJI.get(rv, '⚪')
            text += (
                f"{emoji} **{card.name}** ({RARITY_FA.get(rv, rv)})\n"
                f"   💪{card.power}  ⚡{card.speed}  🧠{card.iq}  ❤️{card.popularity}\n\n"
            )

        keyboard = [
            [InlineKeyboardButton("🗑 حذف این دک", callback_data=f"deck_delete_{deck_id}")],
            [InlineKeyboardButton("🔙 دک‌های من", callback_data="deck_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ==================== CREATE DECK ====================

    async def deck_create_start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند ساخت دک — انتخاب دسته کارت اول"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # بررسی ظرفیت
        if self.db.count_player_decks(user_id) >= DeckSystem.MAX_DECKS:
            await query.answer(
                f"❌ حداکثر {DeckSystem.MAX_DECKS} دک مجاز است. یک دک را حذف کنید.",
                show_alert=True,
            )
            return

        # ریست state ساخت دک
        context.user_data['deck_build'] = {'cards': [], 'step': 1}

        await self._send_deck_build_category_keyboard(query, user_id, step=1)

    async def deck_build_category_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب دسته (rarity) برای یک کارت در مرحله ساخت
        callback: deck_build_cat_{rarity}_{page}
        """
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        # deck_build_cat_{rarity}_{page}
        parts = query.data.split("_")
        rarity = parts[3]
        page = int(parts[4])

        build = context.user_data.get('deck_build', {'cards': [], 'step': 1})
        step = build.get('step', 1)
        already_picked = build.get('cards', [])

        # دریافت کارت‌های این rarity با pagination
        rarity_map = {'legend': CardRarity.LEGEND, 'epic': CardRarity.EPIC,
                      'normal': CardRarity.NORMAL, 'rare': CardRarity.RARE}
        r = rarity_map.get(rarity)
        cards, total = self.db.get_player_cards_by_rarity(user_id, rarity=r, page=page, per_page=6)

        keyboard = []
        for card in cards:
            if card.card_id in already_picked:
                continue  # قبلاً انتخاب شده
            rv = _rarity_val(card)
            emoji = RARITY_EMOJI.get(rv, '⚪')
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {card.name}  💪{card.power} ⚡{card.speed} 🧠{card.iq} ❤️{card.popularity}",
                callback_data=f"deck_build_pick_{card.card_id}"
            )])

        # navigation
        total_pages = (total + 5) // 6
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("«", callback_data=f"deck_build_cat_{rarity}_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("»", callback_data=f"deck_build_cat_{rarity}_{page+1}"))
        if nav:
            keyboard.append(nav)
        keyboard.append([InlineKeyboardButton("🔙 دسته‌بندی‌ها", callback_data=f"deck_build_back_step{step}")])

        text = f"🃏 **ساخت دک — کارت {step} از ۳**\n\nکارتی از {RARITY_FA.get(rarity, rarity)} انتخاب کن:"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_build_pick_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """یک کارت در فرآیند ساخت انتخاب شد
        callback: deck_build_pick_{card_id}
        """
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        card_id = query.data.split("deck_build_pick_")[1]
        build = context.user_data.get('deck_build', {'cards': [], 'step': 1})
        picked = build.get('cards', [])

        if card_id in picked:
            await query.answer("❌ این کارت را قبلاً انتخاب کردی!", show_alert=True)
            return

        # اضافه کردن به لیست
        picked.append(card_id)
        build['cards'] = picked
        build['step'] = len(picked) + 1
        context.user_data['deck_build'] = build

        card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
        card_name = card.name if card else card_id

        if len(picked) < 3:
            # انتخاب کارت بعدی
            await self._send_deck_build_category_keyboard(query, user_id, step=len(picked) + 1,
                                                          selected_names=[
                                                              (self.db.get_card_by_id(c) or type('', (), {'name': c})()).name
                                                              for c in picked
                                                          ])
        else:
            # ۳ کارت انتخاب شد — درخواست نام
            names = []
            for cid in picked:
                c = self.db.get_card_by_id_for_player(cid, user_id) or self.db.get_card_by_id(cid)
                names.append(c.name if c else cid)

            text = (
                f"✅ **سه کارت انتخاب شدند:**\n\n"
                + "\n".join(f"• {n}" for n in names) +
                "\n\n📝 **نام دک را وارد کنید** (حداکثر ۲۰ کاراکتر)\n"
                f"یا روی «بدون نام» بزنید:"
            )
            keyboard = [[InlineKeyboardButton("✅ بدون نام", callback_data="deck_build_skip_name")]]
            context.user_data['deck_build']['waiting_name'] = True
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_build_skip_name_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ساخت دک بدون نام سفارشی"""
        query = update.callback_query
        await query.answer()
        await self._finalize_deck_creation(query.from_user.id, context, name=None,
                                            reply_fn=query.edit_message_text)

    async def deck_name_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت نام دک از پیام متنی کاربر"""
        user_id = update.effective_user.id
        build = context.user_data.get('deck_build', {})
        if not build.get('waiting_name'):
            return  # این handler فقط در حالت ساخت دک فعال است

        name = update.message.text.strip()
        await self._finalize_deck_creation(user_id, context, name=name,
                                            reply_fn=update.message.reply_text)

    async def _finalize_deck_creation(self, user_id: int, context, name: Optional[str], reply_fn):
        """ذخیره نهایی دک"""
        build = context.user_data.get('deck_build', {})
        card_ids = build.get('cards', [])

        if len(card_ids) != 3:
            await reply_fn("❌ خطا: باید دقیقاً ۳ کارت انتخاب شده باشد.", parse_mode='Markdown')
            return

        deck_system = DeckSystem(self.db)
        ok, result = deck_system.create_deck(user_id, card_ids, name)

        # پاک کردن state
        context.user_data.pop('deck_build', None)

        if ok:
            keyboard = [[InlineKeyboardButton("🗂️ دک‌های من", callback_data="deck_menu")]]
            await reply_fn(
                f"✅ **دک با موفقیت ساخته شد!**\n\nبرای مدیریت دک‌هایت به منو برو.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            keyboard = [[InlineKeyboardButton("🔙 دک‌های من", callback_data="deck_menu")]]
            await reply_fn(
                f"❌ **خطا در ساخت دک:**\n{result}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

    async def _send_deck_build_category_keyboard(self, query, user_id: int, step: int,
                                                  selected_names=None):
        """ارسال keyboard انتخاب دسته برای یک مرحله ساخت دک"""
        selected_names = selected_names or []
        rarity_counts = self.db.get_rarity_counts(user_id) if hasattr(self.db, 'get_rarity_counts') else {}

        selected_text = ""
        if selected_names:
            selected_text = "انتخاب‌شده‌ها: " + " · ".join(selected_names) + "\n\n"

        text = (
            f"🃏 **ساخت دک — کارت {step} از ۳**\n\n"
            f"{selected_text}"
            f"دسته کارت را انتخاب کن:"
        )
        keyboard = [
            [InlineKeyboardButton(f"🟡 افسانه‌ای ({rarity_counts.get('legend', 0)})", callback_data=f"deck_build_cat_legend_1")],
            [InlineKeyboardButton(f"🟣 حماسی ({rarity_counts.get('epic', 0)})",       callback_data=f"deck_build_cat_epic_1")],
            [InlineKeyboardButton(f"🟢 معمولی ({rarity_counts.get('normal', 0)})",    callback_data=f"deck_build_cat_normal_1")],
            [InlineKeyboardButton("❌ لغو",                                            callback_data="deck_menu")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # ==================== DELETE DECK ====================

    async def deck_delete_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """درخواست حذف دک — نمایش تأییدیه"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        deck_id = query.data.split("deck_delete_")[1]
        deck = self.db.get_deck_by_id(deck_id)
        if not deck or deck['player_id'] != user_id:
            await query.answer("❌ دک یافت نشد!", show_alert=True)
            return
        deck_name = deck['deck_name'] if deck else "دک"

        text = f"⚠️ **حذف دک «{deck_name}»**\n\nمطمئنی؟ این عمل برگشت‌پذیر نیست."
        keyboard = [
            [InlineKeyboardButton("🗑 بله، حذف شود", callback_data=f"deck_delete_confirm_{deck_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="deck_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_delete_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تأیید حذف دک"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        deck_id = query.data.split("deck_delete_confirm_")[1]
        deck_system = DeckSystem(self.db)
        ok, msg = deck_system.delete_deck(user_id, deck_id)

        if ok:
            await query.answer("✅ دک حذف شد!", show_alert=False)
        else:
            await query.answer(f"❌ {msg}", show_alert=True)

        # برگشت به منوی دک
        await self.deck_menu_handler(update, context)

    # ==================== NOOP ====================

    async def noop_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """handler بی‌عمل برای دکمه‌های اطلاعاتی"""
        if update.callback_query:
            await update.callback_query.answer()
