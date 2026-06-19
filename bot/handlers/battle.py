#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Battle 3 Rounds Handlers
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




class BattleHandlersMixin:
    """Battle 3 Rounds Handlers"""

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


