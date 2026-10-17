#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🃏 Deck Management Handlers
منوی ساخت، مشاهده و حذف دک‌های بازیکن
"""

import logging
from typing import Optional
from telegram.helpers import escape_markdown

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

    async def _deck_panel(self, query, text, **kwargs):
        if getattr(getattr(query, 'message', None), 'photo', None):
            await query.edit_message_caption(caption=text, **kwargs)
        else:
            await query.edit_message_text(text, **kwargs)

    def _deck_buttons(self, deck_id):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🎴 تغییر کارت‌ها', callback_data=f'deck_edit_{deck_id}')],
            [InlineKeyboardButton('✏️ اسم دک', callback_data=f'deck_rename_{deck_id}'),
             InlineKeyboardButton('💬 شعار برد', callback_data=f'deck_slogan_{deck_id}')],
            [InlineKeyboardButton('🗑 حذف', callback_data=f'deck_delete_{deck_id}'),
             InlineKeyboardButton('🔙 دک‌های من', callback_data='deck_menu')]])

    async def _show_deck(self, context, user_id, deck_id):
        from bot.deck_visual_delivery import send_deck
        await send_deck(self, context, user_id, deck_id, self._deck_buttons(deck_id))

    def _deck_edit_locked(self, user_id):
        from systems.card_upgrade_system import CardUpgradeSystem
        return CardUpgradeSystem(self.db).is_management_locked(user_id)

    async def deck_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست دک‌های بازیکن"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        context.user_data.pop('deck_build', None)

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
                    deck['cards']
                )
                text += (
                    f"{status} **{escape_markdown(deck['deck_name'])}** — "
                    f"+{synergy['score']} بونس\n"
                )
                keyboard.append([
                    InlineKeyboardButton(f"👁 {deck['deck_name']}", callback_data=f"deck_view_{deck['deck_id']}"),
                    InlineKeyboardButton("🗑 حذف", callback_data=f"deck_delete_{deck['deck_id']}")
                ])

        if len(decks) < DeckSystem.MAX_DECKS:
            keyboard.append([InlineKeyboardButton("➕ ساخت دک جدید", callback_data="deck_create")])
        keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")])

        # A 50-deck list can exceed Telegram's caption limit on a photo callback.
        if getattr(getattr(query, 'message', None), 'photo', None):
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await self._deck_panel(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_view_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات یک دک"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        deck_id = query.data.split("deck_view_")[1]
        deck_data = self.db.get_deck_by_id(deck_id)

        if not deck_data or deck_data['player_id'] != user_id:
            await query.answer("❌ دک یافت نشد!", show_alert=True)
            return

        await self._show_deck(context, user_id, deck_id)

    async def deck_edit_handler(self, update, context):
        query = update.callback_query
        action, deck_id = query.data.split('_', 2)[1:]
        deck = self.db.get_deck_by_id(deck_id)
        if not deck or deck['player_id'] != query.from_user.id:
            await query.answer('این دک مال تو نیست یا حذف شده.', show_alert=True)
            return
        if self._deck_edit_locked(query.from_user.id):
            await query.answer('اول بازیت رو تموم کن، بعد دکت رو تغییر بده.', show_alert=True)
            return
        await query.answer()
        build = {'cards': [deck[f'card_id_{i}'] for i in range(1, 4)], 'edit_id': deck_id,
                 'name': deck['deck_name'], 'slogan': deck.get('victory_slogan', '')}
        context.user_data['deck_build'] = build
        if action == 'edit':
            build.update(cards=[], step=1)
            await self._send_deck_build_category_keyboard(query, query.from_user.id, 1)
        elif action == 'rename':
            build['waiting_name'] = True
            await self._deck_panel(query, '📝 اسم جدید دکت رو بنویس؛ تا ۲۰ کاراکتر.', reply_markup=self._deck_cancel_buttons())
        else:
            await self._ask_deck_slogan(context, self._deck_reply(query))

    def _deck_reply(self, query):
        async def reply(text, **kwargs):
            await self._deck_panel(query, text, **kwargs)
        return reply

    def _deck_cancel_buttons(self):
        return InlineKeyboardMarkup([[InlineKeyboardButton('❌ لغو', callback_data='deck_menu')]])

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

        build = context.user_data.get('deck_build')
        if not build or build.get('waiting_name') or build.get('waiting_slogan') or len(build.get('cards', [])) >= 3:
            await query.answer('این مرحله دیگه فعال نیست؛ از منوی دک‌ها ادامه بده.', show_alert=True)
            return
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
        await self._deck_panel(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_build_back_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Return to rarity categories without restarting or rewinding the draft."""
        query = update.callback_query
        build = context.user_data.get('deck_build')
        if not build or build.get('waiting_name') or len(build.get('cards', [])) >= 3:
            await query.answer('این مرحله دیگه فعال نیست؛ از منوی دک‌ها ادامه بده.', show_alert=True)
            return
        await query.answer()
        picked = build.get('cards', [])
        names = []
        for card_id in picked:
            card = self.db.get_card_by_id_for_player(card_id, query.from_user.id)
            names.append(card.name if card else card_id)
        await self._send_deck_build_category_keyboard(
            query, query.from_user.id, step=len(picked) + 1, selected_names=names,
        )

    async def deck_build_pick_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """یک کارت در فرآیند ساخت انتخاب شد
        callback: deck_build_pick_{card_id}
        """
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        card_id = query.data.split("deck_build_pick_")[1]
        build = context.user_data.get('deck_build')
        if not build or build.get('waiting_name') or build.get('waiting_slogan') or len(build.get('cards', [])) >= 3:
            await query.answer('این مرحله دیگه فعال نیست؛ از منوی دک‌ها ادامه بده.', show_alert=True)
            return
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

        if len(picked) == 3 and build.get('edit_id'):
            await self._finalize_deck_creation(user_id, context, build['name'], self._deck_reply(query))
        elif len(picked) < 3:
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
            await self._deck_panel(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def deck_build_skip_name_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ساخت دک بدون نام سفارشی"""
        query = update.callback_query
        await query.answer()
        build = context.user_data.get('deck_build', {})
        if not build.get('waiting_name'):
            return
        build['name'] = None
        await self._ask_deck_slogan(context, self._deck_reply(query))

    async def _ask_deck_slogan(self, context, reply_fn):
        build = context.user_data['deck_build']
        build.pop('waiting_name', None)
        build['waiting_slogan'] = True
        await reply_fn('💬 وقتی دکت می‌بره چی بگه؟\nیه شعار تا ۱۲۰ کاراکتر بنویس؛ زیر عکس برد میاد.',
                       reply_markup=InlineKeyboardMarkup([
                           [InlineKeyboardButton('همون شعار پیش‌فرض', callback_data='deck_build_skip_slogan')],
                           [InlineKeyboardButton('❌ لغو', callback_data='deck_menu')]]))

    async def deck_build_skip_slogan_handler(self, update, context):
        from systems.deck_presentation import DEFAULT_SLOGAN
        query = update.callback_query
        await query.answer()
        build = context.user_data.get('deck_build', {})
        if not build.get('waiting_slogan'):
            return
        build['slogan'] = DEFAULT_SLOGAN
        await self._finalize_deck_creation(query.from_user.id, context, build.get('name'), self._deck_reply(query))

    async def deck_name_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت نام دک از پیام متنی کاربر"""
        user_id = update.effective_user.id
        build = context.user_data.get('deck_build', {})
        if not build.get('waiting_name') and not build.get('waiting_slogan'):
            return  # این handler فقط در حالت ساخت دک فعال است

        if build.get('waiting_slogan'):
            from systems.deck_presentation import normalize_slogan
            try:
                build['slogan'] = normalize_slogan(update.message.text)
            except ValueError as error:
                await update.message.reply_text(str(error))
                return
            await self._finalize_deck_creation(user_id, context, build.get('name'), update.message.reply_text)
            return
        name = update.message.text.strip()
        if not name or len(name) > DeckSystem.MAX_NAME_LENGTH:
            await update.message.reply_text('یه اسم بین ۱ تا ۲۰ کاراکتر بنویس.')
            return
        build['name'] = name
        if build.get('edit_id'):
            await self._finalize_deck_creation(user_id, context, name, update.message.reply_text)
        else:
            await self._ask_deck_slogan(context, update.message.reply_text)

    async def _finalize_deck_creation(self, user_id: int, context, name: Optional[str], reply_fn):
        """ذخیره نهایی دک"""
        build = context.user_data.get('deck_build', {})
        card_ids = build.get('cards', [])

        if len(card_ids) != 3:
            await reply_fn("❌ خطا: باید دقیقاً ۳ کارت انتخاب شده باشد.", parse_mode='Markdown')
            return

        deck_system = DeckSystem(self.db)
        if self._deck_edit_locked(user_id):
            await reply_fn('اول بازیت رو تموم کن، بعد دکت رو ذخیره کن.', reply_markup=self._deck_cancel_buttons())
            return
        if build.get('edit_id'):
            ok, result = deck_system.update_deck(user_id, build['edit_id'], card_ids, name, build.get('slogan') or None)
            deck_id = build['edit_id']
        else:
            ok, result = deck_system.create_deck(user_id, card_ids, name, build.get('slogan'))
            deck_id = result

        # پاک کردن state
        if ok:
            context.user_data.pop('deck_build', None)
            keyboard = [[InlineKeyboardButton("🗂️ دک‌های من", callback_data="deck_menu")]]
            await reply_fn(
                '✅ دکت ذخیره شد!',
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            if hasattr(context, 'bot'):
                await self._show_deck(context, user_id, deck_id)
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
        await self._deck_panel(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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

        text = f"⚠️ حذف دک «{deck_name}»\n\nمطمئنی؟ نمی‌تونی برش گردونی."
        keyboard = [
            [InlineKeyboardButton("🗑 بله، حذف شود", callback_data=f"deck_delete_confirm_{deck_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="deck_menu")]
        ]
        await self._deck_panel(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

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
