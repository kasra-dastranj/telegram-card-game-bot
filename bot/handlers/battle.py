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
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle,
    InlineQueryResultCachedPhoto, InlineQueryResultCachedSticker,
    InputTextMessageContent, Update, Bot, WebAppInfo,
)
from telegram.ext import Application, ContextTypes

from game_core import DatabaseManager, GameLogic, CardManager, StatType, Card, CardRarity, Player, PvPFight, FightStatus
from systems.fusion_system import FusionSystem
from systems.phase2_systems import LevelSystem, TierSystem, format_xp_bar, format_tier_badge
from systems.economy_system import EconomySystem
from systems.tier_decay_system import TierDecaySystem
from systems.risk_mode_system import RiskModeSystem, RiskTable, RiskAction
from systems.battle_system_3rounds import (
    BattleSystem3Rounds, BattleState, ARENAS, get_dominant_attr, beats,
    BEATS_MAP, BEATS_REASON, ATTR_NAMES_FA, get_dominant_attr_from_stats,
    apply_drain_to_stats, apply_reflect_reduction, select_arena_shift_role,
)
from systems.claim_system import ClaimSystem
from systems.card_missions_system import CardMissionsSystem, MISSION_TYPES
from systems.skins_system import SkinsSystem, SKIN_TYPES

logger = logging.getLogger(__name__)

DECK_TURN_TIMEOUT_SECONDS = 60
DECK_TRAIT_LABELS = {
    "god": "خدا",
    "monster": "هیولا",
    "hero": "قهرمان",
    "warrior": "جنگجو",
    "villain": "شرور",
    "assassin": "آدمکش",
    "funny": "کمدی",
    "detective": "کارآگاه",
    "mage": "جادوگر",
    "leader": "رهبر",
}

from bot.utils import (check_user_started_bot, handle_user_not_started, ensure_text_content,
    get_card_image_path, get_victory_dialog, send_card_image_safely, ensure_not_expired,
    REQUIRED_CHANNEL, PANEL_TIMEOUT)




class BattleHandlersMixin:
    """Battle 3 Rounds Handlers"""

    @staticmethod
    def _env_flag(name: str, default: bool = True) -> bool:
        fallback = "1" if default else "0"
        return os.getenv(name, fallback).strip().casefold() not in {"0", "false", "off", "no"}

    def _arena_runtime(self, arena_id: str, mode: str = "three_round") -> Dict[str, Any]:
        registry = getattr(self, "arena_registry", None)
        if registry and self._env_flag("ARENA_REGISTRY_READS"):
            runtime = registry.runtime(arena_id, mode, "telegram")
            if runtime:
                return runtime
        if registry and self._env_flag("ARENA_REGISTRY_READS") and not self._env_flag("ARENA_REGISTRY_FALLBACK_SEED"):
            return {}
        logger.warning("arena_registry_static_fallback arena=%s mode=%s", arena_id, mode)
        return ARENAS.get(arena_id, ARENAS["power_arena"])

    def _active_arenas(self, mode: str = "three_round") -> Dict[str, Dict[str, Any]]:
        registry = getattr(self, "arena_registry", None)
        if registry and self._env_flag("ARENA_REGISTRY_READS"):
            active = registry.list_active(mode, "telegram")
            if active:
                return {item["arena_id"]: item for item in active}
            logger.error("arena_registry_empty_pool mode=%s platform=telegram", mode)
            if not self._env_flag("ARENA_REGISTRY_FALLBACK_SEED"):
                return {}
        return ARENAS

    def _random_arena_id(self, mode: str, exclude_ids: Optional[List[str]] = None) -> Optional[str]:
        registry = getattr(self, "arena_registry", None)
        if registry and self._env_flag("ARENA_REGISTRY_READS"):
            selected = registry.select_for_match(mode, "telegram", exclude_ids=exclude_ids)
            if selected:
                logger.info("arena_selected arena=%s mode=%s platform=telegram", selected["arena_id"], mode)
                return selected["arena_id"]
            if not self._env_flag("ARENA_REGISTRY_FALLBACK_SEED"):
                return None
        pool = [key for key in ARENAS if key not in set(exclude_ids or [])] or list(ARENAS)
        return random.choice(pool) if pool else None

    def _fight_arena_mode(self, fight_id: str) -> str:
        """Keep Deck-only arena rules out of classic three-round matches."""
        try:
            deck_state = self.db.get_battle_deck_state(fight_id)
            if deck_state.get("challenger_deck_cards") or deck_state.get("opponent_deck_cards"):
                return "deck"
        except Exception:
            pass
        return "three_round"

    def _should_use_deck_resolver(self, fight_id: str, challenger_card: Any, opponent_card: Any) -> bool:
        return self._fight_arena_mode(fight_id) == "deck" and challenger_card is not None and opponent_card is not None

    def _battle_arena_snapshot(self, fight_id: str) -> Optional[Dict[str, Any]]:
        import sqlite3
        db_path = getattr(getattr(self, "db", None), "db_path", None)
        if not db_path:
            return None
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT arena_snapshot FROM battle_states WHERE fight_id=?", (fight_id,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None
        except (sqlite3.Error, TypeError, ValueError):
            return None
        finally:
            conn.close()

    def _arena_runtime_for_fight(self, fight_id: str, arena_id: str, mode: str) -> Dict[str, Any]:
        snapshot = self._battle_arena_snapshot(fight_id)
        if snapshot and snapshot.get("arena_id") == arena_id and snapshot.get("mode") == mode:
            return snapshot
        return self._arena_runtime(arena_id, mode)

    def _battle_player_name(self, user_id: int, fallback: str = "Player") -> str:
        """Short display name for compact group battle messages."""
        try:
            player = self.db.get_or_create_player(user_id)
            name = player.first_name or player.username or fallback
        except Exception:
            name = fallback
        return str(name).replace("\n", " ").strip()[:12] or fallback

    def _battle_attr_label(self, attr: str) -> str:
        return ATTR_NAMES_FA.get(attr, attr)

    def _deck_card_label(self, card) -> str:
        """Show the owned card form whenever a Deck result names a card."""
        rarity = getattr(getattr(card, "rarity", None), "value", getattr(card, "rarity", None))
        form = {
            "normal": "🟢 Normal",
            "epic": "🟣 Epic",
            "legend": "🟡 Legend",
            "rare": "🔵 Rare",
        }.get(rarity, str(rarity or "?"))
        return f"{card.name} ({form})"

    def _deck_arena_rule_text(self, arena_id: str, fight_id: Optional[str] = None) -> str:
        arena = self._arena_runtime_for_fight(fight_id, arena_id, "deck") if fight_id else self._arena_runtime(arena_id, "deck")
        compare_stat = arena.get("compare_stat", arena.get("boost_stat", "power"))
        tiers = []
        for index, tier in enumerate(arena.get("trait_ranks", []), start=1):
            labels = "/".join(DECK_TRAIT_LABELS.get(str(value), str(value)) for value in tier)
            tiers.append(f"T{index} {labels}")
        tier_line = "، ".join(tiers) or "بدون اولویت Trait"
        return (
            f"🏟️ زمین: {arena['emoji']} {arena['name_fa']} — برای هر ۳ راند ثابت\n"
            f"📐 معیار برد: اول Tierِ Trait زمین؛ سپس {self._battle_attr_label(compare_stat)} بیشتر\n"
            f"🧬 اولویت Trait: {tier_line}"
        )

    def _deck_status_header(
        self,
        fight_id: str,
        arena_id: str,
        round_num: int,
        challenger_wins: int,
        opponent_wins: int,
    ) -> str:
        fight = self.db.get_fight_by_id(fight_id)
        ch_name = self._battle_player_name(fight.challenger_id, "Blue") if fight else "Blue"
        op_name = self._battle_player_name(fight.opponent_id, "Red") if fight else "Red"
        return (
            "⚔️ Deck Battle\n"
            f"📊 🔵 {ch_name} {challenger_wins} — {opponent_wins} {op_name} 🔴\n"
            f"🎴 راند {round_num} از ۳\n\n"
            f"{self._deck_arena_rule_text(arena_id, fight_id)}"
        )

    async def _upsert_deck_status_message(
        self,
        context,
        fight_id: str,
        chat_id: int,
        text: str,
        reply_markup=None,
        allow_create: bool = True,
    ) -> Optional[int]:
        """Create Deck's single status message once, then edit it in place."""
        inline_message_id = context.bot_data.get(f"deck_{fight_id}_inline_message_id")
        if inline_message_id:
            try:
                await context.bot.edit_message_text(
                    inline_message_id=inline_message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                if "message is not modified" not in str(exc).casefold():
                    logger.warning("Could not edit inline Deck status for %s: %s", fight_id, exc)
            return None

        key = f"deck_{fight_id}_status_message"
        reference = context.bot_data.get(key) or {}
        message_id = reference.get("message_id")
        if message_id and reference.get("chat_id") == chat_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return message_id
            except Exception as exc:
                if "message is not modified" in str(exc).casefold():
                    return message_id
                logger.warning("Could not edit Deck status message for %s: %s", fight_id, exc)
                if not allow_create:
                    return message_id
                context.bot_data.pop(key, None)

        if not allow_create:
            logger.warning(
                "Deck status message reference is missing for %s; skipped duplicate message creation",
                fight_id,
            )
            return None

        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        sent_message_id = getattr(sent, "message_id", None)
        if sent_message_id:
            context.bot_data[key] = {"chat_id": chat_id, "message_id": sent_message_id}
        return sent_message_id

    def _resolve_card_sticker_path(self, card) -> Optional[str]:
        """Find the Telegram sticker asset for a card before falling back to card art."""
        if not card:
            return None

        card_name = str(getattr(card, 'name', '') or '').strip()
        if not card_name:
            return None

        normalized = card_name.upper().replace('-', '_')
        variants = []
        rarity = str(getattr(getattr(card, 'rarity', ''), 'value', getattr(card, 'rarity', '')) or '').upper()
        base_stems = (
            normalized.replace(' ', '_'),
            normalized,
            normalized.replace(' ', ''),
        )
        # Form-specific stickers win over the old single shared asset.
        for stem in [*(f"{value}_{rarity}" for value in base_stems if rarity), *base_stems]:
            variants.extend([
                f"{stem}.webp",
                f"{stem} (2).webp",
            ])

        sticker_dirs = [
            os.path.join(os.getcwd(), 'assets', 'stickers'),
            os.path.join(os.getcwd(), 'stickers'),
        ]
        for sticker_dir in sticker_dirs:
            for filename in variants:
                path = os.path.join(sticker_dir, filename)
                if os.path.exists(path):
                    return path
        return None

    def _resolve_card_media_path(self, card) -> Optional[str]:
        """Prefer sticker assets, then DB image_path, then configured card image lookup."""
        if not card:
            return None

        sticker_path = self._resolve_card_sticker_path(card)
        if sticker_path:
            return sticker_path

        db_path = getattr(card, 'image_path', '') or ''
        if db_path:
            candidates = [db_path]
            if not os.path.isabs(db_path):
                candidates.append(os.path.join(os.getcwd(), db_path))
                candidates.append(os.path.join(os.getcwd(), 'assets', 'card_images', db_path))
            for path in candidates:
                if path and os.path.exists(path):
                    return path

        return get_card_image_path(card.name, self.config)

    def _resolve_card_photo_path(self, card) -> Optional[str]:
        """Resolve a local bitmap image path for inline photo upload/cache."""
        if not card:
            return None

        db_path = getattr(card, 'image_path', '') or ''
        candidates = []
        if db_path:
            candidates.append(db_path)
            if not os.path.isabs(db_path):
                candidates.extend([
                    os.path.join(os.getcwd(), db_path),
                    os.path.join(os.getcwd(), 'assets', db_path),
                    os.path.join(os.getcwd(), 'assets', 'card_images', os.path.basename(db_path)),
                ])

        card_name = str(getattr(card, 'name', '') or '').strip()
        if card_name:
            filename = card_name.lower().replace(' ', '_').replace('-', '_')
            for ext in ('.png', '.jpg', '.jpeg', '.webp'):
                candidates.append(os.path.join(os.getcwd(), 'assets', 'card_images', f"{filename}{ext}"))

        configured = get_card_image_path(card.name, self.config) if card_name else None
        if configured:
            candidates.append(configured)

        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    async def _get_inline_card_photo_file_id(self, context, user_id: int, card) -> Optional[str]:
        """Get or lazily upload/cache a Telegram photo file_id for inline results."""
        rarity = str(getattr(getattr(card, "rarity", None), "value", getattr(card, "rarity", "normal")))
        cached = self.db.get_card_variant_media_file_id(card.card_id, rarity, "photo")
        if cached:
            return cached

        photo_path = self._resolve_card_photo_path(card)
        if not photo_path:
            logger.warning(f"Inline card photo not found for {card.name}")
            return None

        try:
            cache_chat_id = (
                self.config.get('image_settings', {}).get('inline_cache_chat_id')
                or (self.admin_ids[0] if getattr(self, 'admin_ids', None) else user_id)
                or user_id
            )
            with open(photo_path, 'rb') as photo:
                msg = await context.bot.send_photo(
                    chat_id=cache_chat_id,
                    photo=photo,
                    caption=f"cache: {card.name}",
                    disable_notification=True,
                )
            file_id = msg.photo[-1].file_id if msg.photo else None
            if file_id:
                self.db.set_card_variant_media_file_id(card.card_id, rarity, file_id, "photo")
            try:
                await context.bot.delete_message(chat_id=cache_chat_id, message_id=msg.message_id)
            except Exception:
                pass
            return file_id
        except Exception as e:
            logger.warning(f"Failed to cache inline photo for {card.name}: {e}")
            return None

    async def _get_inline_card_sticker_file_id(self, context, user_id: int, card) -> Optional[str]:
        """Get or lazily upload/cache a Telegram sticker file_id for inline results."""
        rarity = str(getattr(getattr(card, "rarity", None), "value", getattr(card, "rarity", "normal")))
        cached = self.db.get_card_variant_media_file_id(card.card_id, rarity, "sticker")
        if cached:
            return cached

        sticker_path = self._resolve_card_sticker_path(card)
        if not sticker_path:
            return None

        try:
            cache_chat_id = (
                self.config.get('image_settings', {}).get('inline_cache_chat_id')
                or (self.admin_ids[0] if getattr(self, 'admin_ids', None) else user_id)
                or user_id
            )
            with open(sticker_path, 'rb') as sticker:
                msg = await context.bot.send_sticker(
                    chat_id=cache_chat_id,
                    sticker=sticker,
                    disable_notification=True,
                )
            file_id = msg.sticker.file_id if msg.sticker else None
            if file_id:
                self.db.set_card_variant_media_file_id(card.card_id, rarity, file_id, "sticker")
            try:
                await context.bot.delete_message(chat_id=cache_chat_id, message_id=msg.message_id)
            except Exception:
                pass
            return file_id
        except Exception as e:
            logger.warning(f"Failed to cache inline sticker for {card.name}: {e}")
            return None

    async def _send_round_winner_card_media(self, context, chat_id: int, winner_card) -> bool:
        """Send winning card media before the compact round result."""
        media_path = self._resolve_card_media_path(winner_card)
        if not media_path or not os.path.exists(media_path):
            card_name = getattr(winner_card, 'name', 'unknown')
            logger.warning(f"Round winner media not found for {card_name}: {media_path}")
            return False

        try:
            with open(media_path, 'rb') as media:
                if media_path.lower().endswith('.webp'):
                    await context.bot.send_sticker(chat_id=chat_id, sticker=media)
                else:
                    await context.bot.send_photo(chat_id=chat_id, photo=media)
            return True
        except Exception as e:
            card_name = getattr(winner_card, 'name', 'unknown')
            logger.warning(f"Failed to send round winner media for {card_name}: {e}")
            return False

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

        # Deck همیشه یک زمین تصادفی و ثابت برای هر سه راوند دارد.
        arena_mode = self._fight_arena_mode(fight_id)
        arena_id = self._random_arena_id(arena_mode)
        if not arena_id:
            logger.error("battle_start_blocked_empty_arena_pool fight_id=%s mode=%s", fight_id, arena_mode)
            return
        await self._start_battle_with_arena(context, fight_id, fight, challenger_card, opponent_card, arena_id, query)

    async def _send_arena_selection(self, context, fight_id: str, selector_id: int, chat_id: int):
        """ارسال UI انتخاب زمین به بازیکن ضعیف‌تر"""
        text = (
            "🏟️ **انتخاب زمین بازی**\n\n"
            "کارت تو ضعیف‌تره، پس تو زمین رو انتخاب می‌کنی!\n\n"
            "کدام زمین؟"
        )
        keyboard = []
        arena_mode = self._fight_arena_mode(fight_id)
        for arena_id, info in self._active_arenas(arena_mode).items():
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
            arena_id = self._random_arena_id(self._fight_arena_mode(fight_id))
            data = context.bot_data.get(f"arena_selector_{fight_id}", {})
            if data and arena_id:
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

        arena_info = self._arena_runtime_for_fight(fight_id, arena_id, "three_round")
        await query.edit_message_text(
            f"✅ زمین انتخاب شد: {arena_info['emoji']} **{arena_info['name_fa']}**",
            parse_mode='Markdown'
        )

        await self._start_battle_with_arena(context, fight_id, fight, challenger_card, opponent_card, arena_id, None)

    async def _start_battle_with_arena(self, context, fight_id: str, fight, challenger_card, opponent_card, arena_id: str, query):
        """شروع بازی با زمین مشخص‌شده"""
        import json as _json
        import sqlite3 as _sq

        arena_mode = self._fight_arena_mode(fight_id)
        arena_info = self._arena_runtime(arena_id, arena_mode)
        registry = getattr(self, "arena_registry", None)
        arena_snapshot = registry.snapshot_for_match(arena_id, arena_mode, "telegram") if registry and self._env_flag("ARENA_REGISTRY_READS") else None
        arena_snapshot = arena_snapshot or {"arena_id": arena_id, "version": None, "mode": arena_mode, **arena_info}

        ch_stats = {"power": challenger_card.power, "speed": challenger_card.speed,
                    "iq": challenger_card.iq, "popularity": challenger_card.popularity}
        op_stats = {"power": opponent_card.power, "speed": opponent_card.speed,
                    "iq": opponent_card.iq, "popularity": opponent_card.popularity}

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()

        # بررسی وجود battle_state — اگر deck system قبلاً ایجادش کرده، فقط آپدیت کن
        cursor.execute('SELECT fight_id FROM battle_states WHERE fight_id=?', (fight_id,))
        existing = cursor.fetchone()

        if existing:
            # deck data موجود است — فقط arena و status را آپدیت کن، remaining_cards دست نخور
            cursor.execute('''
                UPDATE battle_states SET
                    arena=?, arena_version=?, arena_snapshot=?, current_round=1,
                    challenger_rounds_won=0, opponent_rounds_won=0,
                    challenger_used_stats='[]', opponent_used_stats='[]',
                    challenger_current_stats=?, opponent_current_stats=?,
                    status='round_1', arena_history='[]'
                WHERE fight_id=?
            ''', (arena_id, arena_snapshot.get("version"), _json.dumps(arena_snapshot, ensure_ascii=False), _json.dumps(ch_stats), _json.dumps(op_stats), fight_id))
        else:
            # اولین بار — INSERT کامل (بدون deck data)
            cursor.execute('''
                INSERT INTO battle_states
                (fight_id, challenger_id, opponent_id, challenger_card_id, opponent_card_id,
                 arena, arena_version, arena_snapshot, current_round, challenger_rounds_won, opponent_rounds_won,
                 challenger_used_stats, opponent_used_stats,
                 challenger_current_stats, opponent_current_stats, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0, '[]', '[]', ?, ?, 'round_1', ?)
            ''', (fight_id, fight.challenger_id, fight.opponent_id,
                  fight.challenger_card_id, fight.opponent_card_id,
                  arena_id, arena_snapshot.get("version"), _json.dumps(arena_snapshot, ensure_ascii=False), _json.dumps(ch_stats), _json.dumps(op_stats),
                  datetime.now().isoformat()))

        cursor.execute(
            "UPDATE active_fights SET arena_type=?, arena_version=?, arena_snapshot=? WHERE fight_id=?",
            (arena_id, arena_snapshot.get("version"), _json.dumps(arena_snapshot, ensure_ascii=False), fight_id),
        )

        conn.commit()
        conn.close()

        context.bot_data[f"r3_{fight_id}_next_first_role"] = "challenger"
        context.bot_data[f"r3_{fight_id}_phase"] = "card_selection"
        context.bot_data.pop(f"r3_{fight_id}_expected_role", None)
        context.bot_data.pop(f"r3_{fight_id}_effect_expected_role", None)

        # دریافت remaining_cards از battle_states (deck-based)
        deck_state = self.db.get_battle_deck_state(fight_id)
        ch_remaining = deck_state.get('challenger_remaining_cards', [])
        op_remaining = deck_state.get('opponent_remaining_cards', [])

        # اعلام شروع؛ Deck از همین پیام به‌عنوان وضعیت ثابت کل مسابقه استفاده می‌کند.
        if fight.chat_id:
            ch_name = self._battle_player_name(fight.challenger_id, "Blue")
            op_name = self._battle_player_name(fight.opponent_id, "Red")
            try:
                if ch_remaining and op_remaining:
                    arena_text = (
                        self._deck_status_header(fight_id, arena_id, 1, 0, 0)
                        + "\n\n⏳ آماده‌سازی انتخاب کارت راند اول..."
                    )
                    await self._upsert_deck_status_message(
                        context, fight_id, fight.chat_id, arena_text
                    )
                else:
                    arena_text = (
                        f"⚔️ شروع فایت — {arena_info['name_fa']} {arena_info['emoji']}\n\n"
                        f"🔵 {ch_name}\n"
                        f"🔴 {op_name}\n\n"
                        f"🎴 راوند ۱ در گروه"
                    )
                    await context.bot.send_message(chat_id=fight.chat_id, text=arena_text)
            except Exception as e:
                logger.warning(f"Failed to send arena message: {e}")

        if ch_remaining and op_remaining:
            # deck-based: یک پنل مشترک در گروه برای هر دو بازیکن
            await self._send_round_card_selection_panel(
                context, fight_id,
                fight.challenger_id, fight.opponent_id,
                ch_remaining, op_remaining,
                arena_id, round_num=1
            )
        else:
            # fallback به stat selection قدیمی (اگه deck نداشت)
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
        from systems.battle_system_3rounds import ABILITIES, get_card_ability
        
        arena_mode = self._fight_arena_mode(fight_id)
        arena_info = self._arena_runtime_for_fight(fight_id, arena_id, arena_mode)
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
            type_matches = (
                not arena_info.get("requires_card_type_match", True)
                or getattr(card, 'card_type', '') == f"{stat.upper()}_TYPE"
            )
            boost_hint = f" 🔥+{arena_info.get('boost_amount', 0)}" if stat == boost_stat and type_matches else ""
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

        from systems.battle_system_3rounds import ABILITIES, get_card_ability

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

        arena_info = self._arena_runtime_for_fight(fight_id, arena_id, "three_round")
        boost_stat = arena_info['boost_stat']

        ch_card = self.db.get_card_by_id_for_player(ch_card_id, ch_id) or self.db.get_card_by_id(ch_card_id)
        op_card = self.db.get_card_by_id_for_player(op_card_id, op_id) or self.db.get_card_by_id(op_card_id)

        active_effects = []
        ch_effect_key = context.bot_data.pop(f"r3_{fight_id}_challenger_effect", None)
        op_effect_key = context.bot_data.pop(f"r3_{fight_id}_opponent_effect", None)

        # مسیر Deck فقط Trait tier و Stat ثابت زمین را مقایسه می‌کند.
        # هیچ Card Effect، Ability، Passive، Boost یا تغییر زمینی در آن دخیل نیست.
        if self._should_use_deck_resolver(fight_id, ch_card, op_card):
            await self._resolve_deck_round(
                context, fight_id, ch_id, op_id, ch_card, op_card,
                arena_id, current_round, ch_rounds_won, op_rounds_won,
                ch_used, op_used, ch_stats, op_stats,
            )
            return

        # Drain قبل از resolve، صفت غالب حریف را هدف می‌گیرد.
        arena_snapshot = self._battle_arena_snapshot(fight_id)
        dom_ch_initial = get_dominant_attr_from_stats(ch_stats, arena_id, arena_snapshot)
        dom_op_initial = get_dominant_attr_from_stats(op_stats, arena_id, arena_snapshot)

        if ch_effect_key == "drain":
            before_value = op_stats.get(dom_op_initial, 0)
            op_stats, drained_attr = apply_drain_to_stats(ch_card, op_stats, dom_op_initial)
            if drained_attr:
                after_value = op_stats.get(drained_attr, 0)
                active_effects.append(
                    f"🧛 درین 🔴 {self._battle_attr_label(drained_attr)} {before_value}→{after_value}"
                )
        if op_effect_key == "drain":
            before_value = ch_stats.get(dom_ch_initial, 0)
            ch_stats, drained_attr = apply_drain_to_stats(op_card, ch_stats, dom_ch_initial)
            if drained_attr:
                after_value = ch_stats.get(drained_attr, 0)
                active_effects.append(
                    f"🧛 درین 🔵 {self._battle_attr_label(drained_attr)} {before_value}→{after_value}"
                )

        # محاسبه dominant attribute بعد از Drain
        from systems.battle_system_3rounds import beats, BEATS_REASON, ABILITIES
        dom_ch = get_dominant_attr_from_stats(ch_stats, arena_id, arena_snapshot)
        dom_op = get_dominant_attr_from_stats(op_stats, arena_id, arena_snapshot)
        ch_stat = dom_ch
        op_stat = dom_op

        # مقادیر فعلی (کاهش‌یافته و بعد از Drain)
        ch_base = ch_stats.get(ch_stat, 0)
        op_base = op_stats.get(op_stat, 0)

        # محاسبه boost
        ch_boost = self.battle3.calculate_boost(ch_card, arena_id, ch_stat, arena_snapshot)
        op_boost = self.battle3.calculate_boost(op_card, arena_id, op_stat, arena_snapshot)

        ch_total = ch_base + ch_boost
        op_total = op_base + op_boost

        # اعمال ابیلیتی‌های pending
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

        # تعیین برنده راوند — اول Beats Map، بعد fallback به مجموع
        beats_win = False
        beats_reason_text = ""
        if beats(dom_ch, dom_op):
            round_winner = 'challenger'
            beats_win = True
            beats_reason_text = BEATS_REASON.get((dom_ch, dom_op), f"{dom_ch} بر {dom_op} برتری داشت")
        elif beats(dom_op, dom_ch):
            round_winner = 'opponent'
            beats_win = True
            beats_reason_text = BEATS_REASON.get((dom_op, dom_ch), f"{dom_op} بر {dom_ch} برتری داشت")
        elif ch_total > op_total:
            round_winner = 'challenger'
        elif op_total > ch_total:
            round_winner = 'opponent'
        else:
            round_winner = None

        win_margin = abs(ch_total - op_total)

        # کاهش stat بازنده — shield نصف می‌کند، سپس Reflect می‌تواند آن را برگرداند.
        ch_has_shield = ch_ability_key == "shield"
        op_has_shield = op_ability_key == "shield"
        ch_reduction = 0
        op_reduction = 0

        if round_winner == 'challenger':
            op_reduction = 8 if win_margin >= 15 else 5
            if op_has_shield:
                op_reduction = op_reduction // 2
            ch_rounds_won += 1
        elif round_winner == 'opponent':
            ch_reduction = 8 if win_margin >= 15 else 5
            if ch_has_shield:
                ch_reduction = ch_reduction // 2
            op_rounds_won += 1
        else:
            ch_reduction = 3
            op_reduction = 3

        ch_reduction, op_reduction, reflected_by = apply_reflect_reduction(
            round_winner,
            ch_card if ch_effect_key == "reflect" else None,
            op_card if op_effect_key == "reflect" else None,
            ch_stat, op_stat,
            ch_reduction, op_reduction,
        )
        if reflected_by:
            reflect_color = "🔵" if reflected_by == "challenger" else "🔴"
            active_effects.append(f"🪞 ریفلکت {reflect_color} کاهش را برگرداند")

        if ch_reduction:
            ch_stats[ch_stat] = max(0, ch_stats[ch_stat] - ch_reduction)
        if op_reduction:
            op_stats[op_stat] = max(0, op_stats[op_stat] - op_reduction)

        if ch_effect_key == "arena_shift" and op_effect_key == "arena_shift":
            arena_shift_role = round_winner or "challenger"
        elif ch_effect_key == "arena_shift":
            arena_shift_role = "challenger"
        elif op_effect_key == "arena_shift":
            arena_shift_role = "opponent"
        else:
            arena_shift_role = None
        if arena_shift_role:
            shift_color = "🔵" if arena_shift_role == "challenger" else "🔴"
            active_effects.append(f"🌀 تغییر زمین {shift_color}")

        # used_stats هنوز برای ابیلیتی‌ها نگه می‌داریم
        ch_used.append(ch_stat)
        op_used.append(op_stat)

        stat_names = {"power": "💪 قدرت", "speed": "⚡ سرعت", "iq": "🧠 هوش", "popularity": "❤️ محبوبیت"}

        ch_name = self._battle_player_name(ch_id, "Blue")
        op_name = self._battle_player_name(op_id, "Red")

        # نتیجه راوند
        if round_winner == 'challenger':
            result_line = f"🏆 {ch_name}  |  {ch_rounds_won} — {op_rounds_won}"
        elif round_winner == 'opponent':
            result_line = f"🏆 {op_name}  |  {ch_rounds_won} — {op_rounds_won}"
        else:
            result_line = f"🤝 مساوی  |  {ch_rounds_won} — {op_rounds_won}"

        round_text = (
            f"⚔️ راوند {current_round} — {arena_info['name_fa']} {arena_info['emoji']}\n\n"
            f"🔵 {ch_name:<12} {self._battle_attr_label(dom_ch)} — {ch_total}\n"
            f"🔴 {op_name:<12} {self._battle_attr_label(dom_op)} — {op_total}\n\n"
            f"{'  '.join(dict.fromkeys(active_effects)) + chr(10) if active_effects else ''}"
            f"{result_line}"
        )

        if round_winner == 'challenger':
            winner_round_card = ch_card
        elif round_winner == 'opponent':
            winner_round_card = op_card
        else:
            winner_round_card = None
        cards_revealed = bool(
            context.bot_data.pop(f"r3_{fight_id}_round_{current_round}_cards_revealed", False)
        )
        if round_winner in ("challenger", "opponent"):
            context.bot_data[f"r3_{fight_id}_next_first_role"] = round_winner

        # بررسی پایان بازی — بعد از هر راوند چک کن
        # اگر یکی ۲ راوند برده یا راوند ۳ (آخر) تازه تموم شد
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

            # پیام راوند فقط وقتی نه auto-select بوده به گروه بفرست
            # (اگر هر دو راوند برنده مشخص باشه، پیام راوند را نشون بده)
            fight = self.db.get_fight_by_id(fight_id)
            if fight and fight.chat_id:
                try:
                    if winner_round_card and not cards_revealed:
                        await self._send_round_winner_card_media(context, fight.chat_id, winner_round_card)
                    await context.bot.send_message(chat_id=fight.chat_id, text=round_text)
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
                    if winner_round_card and not cards_revealed:
                        await self._send_round_winner_card_media(context, fight.chat_id, winner_round_card)
                    await context.bot.send_message(chat_id=fight.chat_id, text=round_text)
                except Exception as msg_err:
                    logger.warning(f"Failed to send round text: {msg_err}")

            if arena_shift_role:
                selector_id = ch_id if arena_shift_role == 'challenger' else op_id
                context.bot_data[f"arena_shift_{fight_id}"] = {
                    "selector_id": selector_id,
                    "ch_id": ch_id,
                    "op_id": op_id,
                    "next_round": next_round,
                }
                sent = await self._send_arena_shift_selection(
                    context, fight_id, selector_id, arena_id
                )
                if sent:
                    return

            await self._send_next_round_card_selection(
                context, fight_id, ch_id, op_id, next_round, arena_id
            )

    async def _send_next_round_card_selection(
        self, context, fight_id: str, ch_id: int, op_id: int,
        round_num: int, arena_id: str
    ):
        """ارسال UI انتخاب کارت برای راوند بعدی بعد از نتیجه یا Arena Shift."""
        deck_state = self.db.get_battle_deck_state(fight_id)
        ch_remaining = deck_state.get('challenger_remaining_cards', [])
        op_remaining = deck_state.get('opponent_remaining_cards', [])

        ch_played = [c for c in deck_state.get('challenger_deck_cards', []) if c not in ch_remaining]
        op_played = [c for c in deck_state.get('opponent_deck_cards', []) if c not in op_remaining]

        op_played_names = []
        for cid in op_played:
            c = self.db.get_card_by_id(cid)
            if c:
                op_played_names.append(c.name)

        ch_played_names = []
        for cid in ch_played:
            c = self.db.get_card_by_id(cid)
            if c:
                ch_played_names.append(c.name)

        await self._send_round_card_selection_panel(
            context, fight_id, ch_id, op_id,
            ch_remaining, op_remaining,
            arena_id, round_num,
            challenger_played_cards=ch_played_names,
            opponent_played_cards=op_played_names,
        )

    async def _send_arena_shift_selection(
        self, context, fight_id: str, selector_id: int, current_arena_id: str
    ) -> bool:
        """ارسال انتخاب زمین جدید برای Arena Shift در گروه، قفل‌شده برای صاحب افکت."""
        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            return False

        selector_name = self._battle_player_name(selector_id, "Player")
        selector_role = "challenger" if selector_id == fight.challenger_id else "opponent"
        selector_color = "🔵" if selector_role == "challenger" else "🔴"

        deck_state = self.db.get_battle_deck_state(fight_id)
        remaining_key = (
            "challenger_remaining_cards"
            if selector_role == "challenger"
            else "opponent_remaining_cards"
        )
        remaining_names = []
        for card_id in deck_state.get(remaining_key, []):
            card = (
                self.db.get_card_by_id_for_player(card_id, selector_id)
                or self.db.get_card_by_id(card_id)
            )
            if card:
                remaining_names.append(card.name)

        keyboard = []
        arena_mode = self._fight_arena_mode(fight_id)
        for arena_id, info in self._active_arenas(arena_mode).items():
            if arena_id == current_arena_id:
                continue
            boost_label = self._battle_attr_label(info.get('boost_stat', ''))
            keyboard.append([InlineKeyboardButton(
                f"{info['emoji']} {info['name_fa']} — {boost_label}",
                callback_data=f"arena_shift_pick_{fight_id}_{arena_id}"
            )])

        current = self._arena_runtime_for_fight(fight_id, current_arena_id, arena_mode)
        remaining_line = "، ".join(remaining_names) if remaining_names else "نامشخص"
        text = (
            f"🌀 تغییر زمین\n\n"
            f"نوبت: {selector_color} {selector_name}\n"
            f"زمین فعلی: {current.get('emoji', '')} {current.get('name_fa', current_arena_id)}\n"
            f"کارت‌های باقی‌مانده تو: {remaining_line}\n\n"
            f"زمین راوند بعدی را انتخاب کن:"
        )
        try:
            await context.bot.send_message(
                chat_id=fight.chat_id if fight.chat_id else selector_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to send arena shift selection to {selector_id}: {e}")
            return False

    async def arena_shift_pick_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب زمین جدید توسط صاحب کارت arena_shift."""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        prefix = "arena_shift_pick_"
        rest = query.data[len(prefix):]
        fight_id = rest[:8]
        arena_id = rest[9:]

        pending = context.bot_data.get(f"arena_shift_{fight_id}")
        if not pending:
            await query.answer("❌ انتخاب زمین منقضی شده.", show_alert=True)
            return
        if pending.get("selector_id") != user_id:
            await query.answer("❌ این انتخاب مال تو نیست.", show_alert=True)
            return
        arena_mode = self._fight_arena_mode(fight_id)
        if arena_id not in self._active_arenas(arena_mode):
            await query.answer("❌ زمین نامعتبر است.", show_alert=True)
            return

        context.bot_data.pop(f"arena_shift_{fight_id}", None)

        import sqlite3 as _sq
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        registry = getattr(self, "arena_registry", None)
        snapshot = registry.snapshot_for_match(arena_id, arena_mode, "telegram") if registry and self._env_flag("ARENA_REGISTRY_READS") else None
        if not snapshot:
            snapshot = {"arena_id": arena_id, "version": None, "mode": arena_mode, **self._arena_runtime(arena_id, arena_mode)}
        prior_row = cursor.execute("SELECT arena_snapshot, arena_history FROM battle_states WHERE fight_id=?", (fight_id,)).fetchone()
        history = []
        if prior_row:
            try:
                history = json.loads(prior_row[1] or "[]")
            except (TypeError, ValueError):
                history = []
            if prior_row[0]:
                try:
                    history.append(json.loads(prior_row[0]))
                except (TypeError, ValueError):
                    pass
        cursor.execute(
            "UPDATE battle_states SET arena=?, arena_version=?, arena_snapshot=?, arena_history=? WHERE fight_id=?",
            (arena_id, snapshot.get("version"), json.dumps(snapshot, ensure_ascii=False), json.dumps(history, ensure_ascii=False), fight_id),
        )
        cursor.execute(
            "UPDATE active_fights SET arena_type=?, arena_version=?, arena_snapshot=? WHERE fight_id=?",
            (arena_id, snapshot.get("version"), json.dumps(snapshot, ensure_ascii=False), fight_id),
        )
        conn.commit()
        conn.close()

        arena_info = self._arena_runtime_for_fight(fight_id, arena_id, arena_mode)
        try:
            await query.edit_message_text(f"✅ زمین جدید: {arena_info['emoji']} {arena_info['name_fa']}")
        except Exception:
            pass

        fight = self.db.get_fight_by_id(fight_id)
        if fight and fight.chat_id:
            try:
                await context.bot.send_message(
                    chat_id=fight.chat_id,
                    text=f"🌀 زمین جدید — {arena_info['name_fa']} {arena_info['emoji']}"
                )
            except Exception:
                pass

        await self._send_next_round_card_selection(
            context, fight_id,
            pending["ch_id"], pending["op_id"],
            pending["next_round"], arena_id
        )

    async def _resolve_deck_round(
        self, context, fight_id: str,
        ch_id: int, op_id: int,
        ch_card, op_card,
        arena_id: str, current_round: int,
        ch_rounds_won: int, op_rounds_won: int,
        ch_used: list, op_used: list,
        ch_stats: dict, op_stats: dict,
    ):
        """Resolve a Deck round and continue until all three rounds are played."""
        import json as _json
        import sqlite3 as _sq

        result = self.battle3.resolve_deck_cards(ch_card, op_card, arena_id, self._battle_arena_snapshot(fight_id))
        round_winner = result["winner"]
        if round_winner == "challenger":
            ch_rounds_won += 1
        elif round_winner == "opponent":
            op_rounds_won += 1

        compare_stat = result["compare_stat"]
        ch_used.append(compare_stat)
        op_used.append(compare_stat)
        ch_name = self._battle_player_name(ch_id, "Blue")
        op_name = self._battle_player_name(op_id, "Red")
        arena_info = self._arena_runtime_for_fight(fight_id, arena_id, "deck")
        stat_label = self._battle_attr_label(compare_stat)
        ch_rank = result["challenger_trait_rank"]
        op_rank = result["opponent_trait_rank"]

        if result["reason"] == "trait":
            comparison_line = (
                f"🧬 Trait tier: 🔵 {('T' + str(ch_rank)) if ch_rank else '—'} | "
                f"🔴 {('T' + str(op_rank)) if op_rank else '—'}"
            )
        else:
            comparison_line = (
                f"{stat_label}: 🔵 {result['challenger_value']} | "
                f"🔴 {result['opponent_value']}"
            )

        same_character_different_form = (
            ch_card.card_id == op_card.card_id
            and ch_card.rarity != op_card.rarity
        )
        form_note = (
            "\nℹ️ شخصیت یکسان است، اما فرم کارت‌ها متفاوت است؛ عدد هر فرم جدا حساب می‌شود."
            if same_character_different_form and result["reason"] == "stat" else ""
        )

        if round_winner == "challenger":
            result_line = f"🏆 {ch_name} برنده‌ی راند شد"
        elif round_winner == "opponent":
            result_line = f"🏆 {op_name} برنده‌ی راند شد"
        else:
            result_line = "🤝 این راند مساوی شد"
        round_text = (
            f"⚔️ راند {current_round} — {arena_info['name_fa']} {arena_info['emoji']}\n\n"
            f"🔵 {self._deck_card_label(ch_card)}\n"
            f"🔴 {self._deck_card_label(op_card)}\n\n"
            f"{comparison_line}{form_note}\n"
            f"{result_line}\n"
            f"برد راندها: {ch_rounds_won} — {op_rounds_won}"
        )

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO round_history
               (fight_id, round_number, challenger_stat, opponent_stat,
                challenger_value, opponent_value, challenger_boost, opponent_boost,
                challenger_total, opponent_total, winner, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
            (
                fight_id, current_round, compare_stat, compare_stat,
                result["challenger_value"], result["opponent_value"],
                result["challenger_value"], result["opponent_value"],
                round_winner, datetime.now().isoformat(),
            ),
        )

        game_over = current_round >= 3
        if game_over:
            deck_state = self.db.get_battle_deck_state(fight_id)
            ch_synergy = self.modes.calculate_deck_synergy(
                deck_state.get("challenger_deck_cards", [])
            )
            op_synergy = self.modes.calculate_deck_synergy(
                deck_state.get("opponent_deck_cards", [])
            )
            ch_points = ch_rounds_won * 5 + ch_synergy["score"]
            op_points = op_rounds_won * 5 + op_synergy["score"]
            cursor.execute(
                """UPDATE battle_states SET status='completed',
                          challenger_rounds_won=?, opponent_rounds_won=?,
                          challenger_used_stats=?, opponent_used_stats=?
                     WHERE fight_id=?""",
                (
                    ch_rounds_won, op_rounds_won,
                    _json.dumps(ch_used), _json.dumps(op_used), fight_id,
                ),
            )
            conn.commit()
            conn.close()

            ch_bonus = "، ".join(ch_synergy["reasons"]) or "بدون بونس"
            op_bonus = "، ".join(op_synergy["reasons"]) or "بدون بونس"
            score_text = (
                f"\n\n🧩 امتیاز ساخت دک\n"
                f"🔵 {ch_name}: {ch_rounds_won * 5} + {ch_synergy['score']} = {ch_points}\n"
                f"   {ch_bonus}\n"
                f"🔴 {op_name}: {op_rounds_won * 5} + {op_synergy['score']} = {op_points}\n"
                f"   {op_bonus}"
            )
            fight = self.db.get_fight_by_id(fight_id)

            if ch_points > op_points:
                winner_id, loser_id, result_type = ch_id, op_id, "challenger_wins"
            elif op_points > ch_points:
                winner_id, loser_id, result_type = op_id, ch_id, "opponent_wins"
            else:
                winner_id = loser_id = None
                result_type = "tie"
            await self._finalize_3round_battle(
                context, fight_id, fight, ch_card, op_card,
                winner_id, loser_id, result_type, ch_points, op_points,
                deck_summary=(
                    self._deck_arena_rule_text(arena_id, fight_id)
                    + "\n\n"
                    + round_text
                    + score_text
                ),
            )
            return

        next_round = current_round + 1
        cursor.execute(
            """UPDATE battle_states SET current_round=?,
                      challenger_rounds_won=?, opponent_rounds_won=?,
                      challenger_used_stats=?, opponent_used_stats=?,
                      challenger_current_stats=?, opponent_current_stats=?, status=?
                 WHERE fight_id=?""",
            (
                next_round, ch_rounds_won, op_rounds_won,
                _json.dumps(ch_used), _json.dumps(op_used),
                _json.dumps(ch_stats), _json.dumps(op_stats),
                f"round_{next_round}", fight_id,
            ),
        )
        conn.commit()
        conn.close()

        context.bot_data[f"deck_{fight_id}_last_round_summary"] = round_text
        context.bot_data[f"r3_{fight_id}_next_first_role"] = (
            "opponent" if next_round == 2 else "challenger"
        )
        context.bot_data[f"r3_{fight_id}_phase"] = "card_selection"
        await self._send_next_round_card_selection(
            context, fight_id, ch_id, op_id, next_round, arena_id,
        )

    async def _finalize_3round_battle(self, context, fight_id: str, fight,
                                       ch_card, op_card,
                                       winner_id, loser_id,
                                       result_type: str,
                                       ch_rounds_won: int, op_rounds_won: int,
                                       deck_summary: Optional[str] = None):
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
        from systems.phase2_systems import TierSystem, XP_SOURCES
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
            ch_name = self._battle_player_name(ch_id, "Blue")
            op_name = self._battle_player_name(op_id, "Red")
            if result_type == "tie":
                final_line = f"🤝 مساوی  |  {ch_rounds_won} — {op_rounds_won}"
                xp_line = f"⭐ +{ch_xp} / +{op_xp} XP"
            else:
                winner_name = ch_name if result_type == "challenger_wins" else op_name
                winner_xp = ch_xp if result_type == "challenger_wins" else op_xp
                loser_xp = op_xp if result_type == "challenger_wins" else ch_xp
                level_up_text = ""
                if result_type == "challenger_wins" and ch_new_lv > ch_old_lv:
                    level_up_text = f"\n⬆️ Level Up! → {ch_new_lv}"
                elif result_type == "opponent_wins" and op_new_lv > op_old_lv:
                    level_up_text = f"\n⬆️ Level Up! → {op_new_lv}"
                final_line = f"🏆 {winner_name}  |  {ch_rounds_won} — {op_rounds_won}"
                xp_line = f"⭐ +{winner_xp} / +{loser_xp} XP{level_up_text}"

            if deck_summary:
                final_text = (
                    f"🏁 نتیجه نهایی Deck\n\n"
                    f"{deck_summary}\n\n"
                    f"{final_line}\n"
                    f"{xp_line}"
                )
            else:
                final_text = (
                    f"🏁 نتیجه نهایی\n\n"
                    f"🔵 {ch_name:<12} {ch_rounds_won}\n"
                    f"🔴 {op_name:<12} {op_rounds_won}\n\n"
                    f"{final_line}\n"
                    f"{xp_line}"
                )

            if context.bot_data.get(f"deck_{fight_id}_inline_message_id"):
                keyboard = [[InlineKeyboardButton("🥊 بازی دوباره", switch_inline_query_current_chat="game")]]
            else:
                keyboard = [[InlineKeyboardButton("🥊 چالش جدید", callback_data="request_pvp_fight")]]
            try:
                if deck_summary:
                    await self._upsert_deck_status_message(
                        context,
                        fight_id,
                        fight.chat_id,
                        final_text,
                        InlineKeyboardMarkup(keyboard),
                        allow_create=False,
                    )
                    context.bot_data.pop(f"deck_{fight_id}_status_message", None)
                    context.bot_data.pop(f"deck_{fight_id}_inline_message_id", None)
                    context.bot_data.pop(f"deck_{fight_id}_last_round_summary", None)
                else:
                    await context.bot.send_message(
                        chat_id=fight.chat_id,
                        text=final_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
            except Exception as e:
                logger.error(f"Failed to send final result: {e}")

        self.db.delete_fight(fight_id)

    # ==================== SKINS HANDLERS ====================



    # ==================== DECK-BASED ROUND CARD SELECTION ====================

    def _round_role_for_user(self, user_id: int, challenger_id: int, opponent_id: int) -> Optional[str]:
        if user_id == challenger_id:
            return "challenger"
        if user_id == opponent_id:
            return "opponent"
        return None

    def _round_user_for_role(self, role: str, challenger_id: int, opponent_id: int) -> Optional[int]:
        if role == "challenger":
            return challenger_id
        if role == "opponent":
            return opponent_id
        return None

    def _other_round_role(self, role: str) -> str:
        return "opponent" if role == "challenger" else "challenger"

    async def _send_round_card_selection_panel(
        self, context, fight_id: str,
        challenger_id: int, opponent_id: int,
        challenger_remaining_card_ids: list, opponent_remaining_card_ids: list,
        arena_id: str, round_num: int,
        challenger_played_cards: list = None,
        opponent_played_cards: list = None,
    ):
        """Send the group picker for the player whose turn it is."""
        deck_state = self.db.get_battle_deck_state(fight_id)
        ch_wins = deck_state.get("challenger_rounds_won", 0)
        op_wins = deck_state.get("opponent_rounds_won", 0)
        context.bot_data[f"r3_{fight_id}_phase"] = "card_selection"

        ch_name = self._battle_player_name(challenger_id, "Blue")
        op_name = self._battle_player_name(opponent_id, "Red")
        selected = {
            "challenger": bool(context.bot_data.get(f"r3_{fight_id}_challenger_card")),
            "opponent": bool(context.bot_data.get(f"r3_{fight_id}_opponent_card")),
        }
        final_deck_round = (
            round_num == 3
            and len(challenger_remaining_card_ids) == 1
            and len(opponent_remaining_card_ids) == 1
            and self._fight_arena_mode(fight_id) == "deck"
        )

        if selected["challenger"] and selected["opponent"]:
            await self._advance_round_card_turn_or_start_effects(context, fight_id)
            return

        expected_role = context.bot_data.get(f"r3_{fight_id}_expected_role")
        if expected_role not in ("challenger", "opponent") or selected.get(expected_role):
            first_role = context.bot_data.get(f"r3_{fight_id}_next_first_role", "challenger")
            if first_role not in ("challenger", "opponent"):
                first_role = "challenger"
            expected_role = first_role if not selected.get(first_role) else self._other_round_role(first_role)

        if selected.get(expected_role):
            expected_role = "opponent" if not selected["opponent"] else "challenger"

        expected_user_id = self._round_user_for_role(expected_role, challenger_id, opponent_id)
        expected_name = ch_name if expected_role == "challenger" else op_name
        context.bot_data[f"r3_{fight_id}_expected_role"] = expected_role

        color = "🔵" if expected_role == "challenger" else "🔴"
        keyboard = [[InlineKeyboardButton(
                f"{color} {expected_name}",
                switch_inline_query_current_chat=(
                    f"r3pick {fight_id} {self._inline_user_token(expected_user_id)}"
                ),
            )]]

        ch_last = challenger_played_cards[-1] if challenger_played_cards else None
        op_last = opponent_played_cards[-1] if opponent_played_cards else None
        ch_status = "انتخاب شد" if selected["challenger"] else f"{len(challenger_remaining_card_ids)} کارت"
        op_status = "انتخاب شد" if selected["opponent"] else f"{len(opponent_remaining_card_ids)} کارت"
        if final_deck_round:
            for role in ("challenger", "opponent"):
                if not selected[role]:
                    continue
                card_id = context.bot_data[f"r3_{fight_id}_{role}_card"]
                user_id = challenger_id if role == "challenger" else opponent_id
                card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
                if role == "challenger":
                    ch_status = self._deck_card_label(card) if card else card_id
                else:
                    op_status = self._deck_card_label(card) if card else card_id

        lines = [
            self._deck_status_header(fight_id, arena_id, round_num, ch_wins, op_wins),
        ]
        last_round_summary = context.bot_data.get(f"deck_{fight_id}_last_round_summary")
        if last_round_summary:
            lines.extend(["", "── نتیجه راند قبل ──", last_round_summary])
        lines.extend([
            "",
            "── انتخاب کارت ──",
            f"نوبت: {color} {expected_name}",
            "",
            f"🔵 {ch_name} — {ch_status}",
            f"🔴 {op_name} — {op_status}",
        ])
        if ch_last or op_last:
            lines.append("")
            if ch_last:
                lines.append(f"آخرین 🔵 {ch_last}")
            if op_last:
                lines.append(f"آخرین 🔴 {op_last}")
        if final_deck_round:
            lines.extend([
                "",
                "کارت آخر را انتخاب کنید؛ نام و تصویر هر کارت پس از انتخاب همان بازیکن نمایش داده می‌شود.",
            ])
        else:
            lines.extend(["", "انتخاب بازیکن شروع‌کننده در گروه دیده می‌شود؛ انتخاب نهایی است."])

        try:
            fight = self.db.get_fight_by_id(fight_id)
            chat_id = fight.chat_id if fight and fight.chat_id else challenger_id
            await self._upsert_deck_status_message(
                context,
                fight_id,
                chat_id,
                "\n".join(lines),
                InlineKeyboardMarkup(keyboard),
            )
            if context.job_queue:
                context.job_queue.run_once(
                    self.deck_turn_timeout_job,
                    DECK_TURN_TIMEOUT_SECONDS,
                    data={
                        "fight_id": fight_id,
                        "round": round_num,
                        "expected_role": expected_role,
                    },
                    name=f"deck_timeout_{fight_id}_{round_num}_{expected_role}",
                )
        except Exception as e:
            logger.error(f"Failed to send shared round card selection for {fight_id}: {e}")

    async def deck_turn_timeout_job(self, context):
        """A missed 60-second Deck turn forfeits the entire match."""
        import sqlite3 as _sq

        data = context.job.data
        fight_id = data["fight_id"]
        expected_role = data["expected_role"]
        if context.bot_data.get(f"r3_{fight_id}_phase") != "card_selection":
            return
        if context.bot_data.get(f"r3_{fight_id}_expected_role") != expected_role:
            return

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT challenger_id, opponent_id, current_round,
                      challenger_rounds_won, opponent_rounds_won, arena, status
                 FROM battle_states WHERE fight_id=?""",
            (fight_id,),
        )
        row = cursor.fetchone()
        if not row or row[2] != data["round"] or row[6] == "completed":
            conn.close()
            return
        cursor.execute(
            "UPDATE battle_states SET status='completed' WHERE fight_id=? AND status!='completed'",
            (fight_id,),
        )
        claimed = cursor.rowcount == 1
        conn.commit()
        conn.close()
        if not claimed:
            return

        ch_id, op_id, _, ch_wins, op_wins, arena_id, _ = row
        loser_id = ch_id if expected_role == "challenger" else op_id
        winner_id = op_id if expected_role == "challenger" else ch_id
        result_type = "opponent_wins" if expected_role == "challenger" else "challenger_wins"
        fight = self.db.get_fight_by_id(fight_id)
        if not fight:
            return
        ch_card = self.db.get_card_by_id(fight.challenger_card_id)
        op_card = self.db.get_card_by_id(fight.opponent_card_id)
        if not ch_card or not op_card:
            self.db.delete_fight(fight_id)
            return

        loser_name = self._battle_player_name(loser_id, "Player")
        ch_points = ch_wins * 5
        op_points = op_wins * 5
        if expected_role == "challenger":
            op_points = max(op_points, ch_points + 5)
        else:
            ch_points = max(ch_points, op_points + 5)
        await self._finalize_3round_battle(
            context, fight_id, fight, ch_card, op_card,
            winner_id, loser_id, result_type,
            ch_points, op_points,
            deck_summary=(
                f"{self._deck_arena_rule_text(arena_id, fight_id)}\n\n"
                f"⏱ زمان ۶۰ ثانیه‌ای انتخاب {loser_name} تمام شد؛ کل بازی را باخت.\n"
                f"📊 امتیاز نهایی: 🔵 {ch_points} — {op_points} 🔴"
            ),
        )

    async def _send_round_card_selection(
        self, context, fight_id: str, user_id: int,
        remaining_card_ids: list, arena_id: str, round_num: int,
        opponent_played_cards: list = None
    ):
        """ارسال UI انتخاب دستی کارت برای یک راوند از کارت‌های باقیمانده دک."""
        import json as _json
        from systems.battle_system_3rounds import (
            CARD_EFFECTS, ATTR_NAMES_FA, get_card_effects, get_dominant_attr,
        )
        from systems.battle_system_3rounds import ABILITIES, get_card_ability

        arena_info = self._arena_runtime_for_fight(fight_id, arena_id, "deck")
        rarity_emoji = {'normal': '🟢', 'epic': '🟣', 'legend': '🟡', 'rare': '🔵'}

        player_name = self._battle_player_name(user_id, "Player")
        user_token = self._inline_user_token(user_id)
        keyboard = [[InlineKeyboardButton(
            "🎴 باز کردن دست کارت‌ها",
            switch_inline_query_current_chat=f"r3pick {fight_id} {user_token}",
        )]]

        # نمایش اطلاعات حریف
        opp_info = ""
        if opponent_played_cards:
            opp_info = f"\n🔍 حریف: {len(remaining_card_ids)} کارت باقی مانده\n"
            for prev in opponent_played_cards[-1:]:  # فقط آخرین کارت حریف
                opp_info += f"   آخرین کارت حریف: **{prev}**\n"

        text = (
            f"⚔️ راوند {round_num} — {arena_info['name_fa']} {arena_info['emoji']}\n\n"
            f"🎴 نوبت انتخاب کارت: {player_name}\n"
            f"{opp_info}\n"
            f"دکمه پایین را بزن و کارتت را از لیست تصویری انتخاب کن."
        )

        try:
            fight = self.db.get_fight_by_id(fight_id)
            chat_id = fight.chat_id if fight and fight.chat_id else user_id
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            logger.error(f"Failed to send round card selection to {user_id}: {e}")

    def _inline_user_token(self, user_id: int) -> str:
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        value = int(user_id)
        if value == 0:
            return "0"
        chars = []
        while value:
            value, rem = divmod(value, 36)
            chars.append(alphabet[rem])
        return "".join(reversed(chars))

    def _parse_inline_user_token(self, token: str) -> Optional[int]:
        try:
            return int(str(token), 36)
        except (TypeError, ValueError):
            return None

    def _inline_card_result_id(self, fight_id: str, user_id: int, card_id: str) -> str:
        return f"r3c|{fight_id}|{self._inline_user_token(user_id)}|{card_id}"

    def _inline_confirm_callback_data(self, fight_id: str, user_id: int, card_id: str) -> str:
        return f"r3i|{fight_id}|{self._inline_user_token(user_id)}|{card_id}"

    def _inline_effect_result_id(self, fight_id: str, user_id: int, effect_key: str) -> str:
        return f"r3e|{fight_id}|{self._inline_user_token(user_id)}|{effect_key}"

    def _inline_effect_confirm_callback_data(self, fight_id: str, user_id: int, effect_key: str) -> str:
        return f"r3e|{fight_id}|{self._inline_user_token(user_id)}|{effect_key}"

    def _inline_deck_result_id(self, fight_id: str, user_id: int, deck_id: str) -> str:
        return f"pvpd|{fight_id}|{self._inline_user_token(user_id)}|{deck_id}"

    def _parse_inline_card_result_id(self, result_id: str) -> Optional[tuple]:
        parts = (result_id or "").split("|", 3)
        if len(parts) == 4 and parts[0] == "r3c":
            target_user_id = self._parse_inline_user_token(parts[2])
            if target_user_id is None:
                return None
            return parts[1], target_user_id, parts[3]
        if len(parts) == 3 and parts[0] == "r3c":
            return parts[1], None, parts[2]
        return None

    def _parse_inline_confirm_callback_data(self, data: str) -> Optional[tuple]:
        parts = (data or "").split("|", 3)
        if len(parts) != 4 or parts[0] != "r3i":
            return None
        target_user_id = self._parse_inline_user_token(parts[2])
        if target_user_id is None:
            return None
        return parts[1], target_user_id, parts[3]

    def _parse_inline_effect_result_id(self, result_id: str) -> Optional[tuple]:
        parts = (result_id or "").split("|", 3)
        if len(parts) != 4 or parts[0] != "r3e":
            return None
        target_user_id = self._parse_inline_user_token(parts[2])
        if target_user_id is None:
            return None
        return parts[1], target_user_id, parts[3]

    def _parse_inline_deck_result_id(self, result_id: str) -> Optional[tuple]:
        parts = (result_id or "").split("|", 3)
        if len(parts) != 4 or parts[0] != "pvpd":
            return None
        target_user_id = self._parse_inline_user_token(parts[2])
        if target_user_id is None:
            return None
        return parts[1], target_user_id, parts[3]

    def _round_card_description(self, card, arena_id: str) -> str:
        from systems.battle_system_3rounds import (
            CARD_EFFECTS, ATTR_NAMES_FA, get_card_effects, get_dominant_attr,
        )
        dom = get_dominant_attr(card, arena_id)
        effects = get_card_effects(card)
        effect_text = " ".join(f"{CARD_EFFECTS[e]['emoji']} {CARD_EFFECTS[e]['name_fa']}" for e in effects)
        return f"{ATTR_NAMES_FA.get(dom, dom)} · {effect_text}".strip(" ·")

    async def _record_round_card_selection(
        self, context, fight_id: str, user_id: int, card_id: str
    ) -> tuple:
        """Validate and store one player's round card selection."""
        import json as _json
        import sqlite3 as _sq

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT challenger_id, opponent_id,
                   challenger_remaining_cards, opponent_remaining_cards,
                   status
            FROM battle_states WHERE fight_id=?
        ''', (fight_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, None, "بازی یافت نشد"

        ch_id, op_id, ch_rem_raw, op_rem_raw, status = row
        if status == 'completed':
            return False, None, "این بازی تمام شده"

        if user_id == ch_id:
            role = 'challenger'
            remaining = _json.loads(ch_rem_raw or '[]')
        elif user_id == op_id:
            role = 'opponent'
            remaining = _json.loads(op_rem_raw or '[]')
        else:
            return False, None, "این انتخاب مال تو نیست"

        expected_role = context.bot_data.get(f"r3_{fight_id}_expected_role")
        if expected_role in ("challenger", "opponent") and role != expected_role:
            return False, None, "هنوز نوبت انتخاب تو نیست"

        if card_id not in remaining:
            return False, None, "این کارت دیگر قابل انتخاب نیست"

        if context.bot_data.get(f"r3_{fight_id}_{role}_card"):
            return False, None, "برای این راوند کارت انتخاب شده"

        card = (
            self.db.get_card_by_id_for_player(card_id, user_id)
            or self.db.get_card_by_id(card_id)
        )
        context.bot_data[f"r3_{fight_id}_{role}_card"] = card_id
        return True, card, role

    async def _after_round_card_selected(
        self, context, fight_id: str, user_id: int, role: str, card
    ):
        """Show a final Deck fallback pick immediately, then continue the round."""
        media_key = f"r3_{fight_id}_{role}_media_sent"
        if not context.bot_data.get(media_key) and self._fight_arena_mode(fight_id) == "deck":
            deck_state = self.db.get_battle_deck_state(fight_id)
            if deck_state.get("current_round") == 3:
                await self._send_selected_round_card_media(context, fight_id, user_id, card)
                context.bot_data[media_key] = True
        await self._advance_round_card_turn_or_start_effects(context, fight_id)

    async def _send_round_effect_prompt(
        self, context, fight_id: str, user_id: int, role: str, card
    ):
        """Ask the current player to make a hidden effect decision."""
        from systems.battle_system_3rounds import get_card_effects

        effects = get_card_effects(card)
        if not effects:
            context.bot_data[f"r3_{fight_id}_{role}_effect"] = None
            await self._advance_round_effect_turn_or_resolve(context, fight_id)
            return

        context.bot_data[f"r3_{fight_id}_{role}_effect_pending"] = True
        keyboard = [[InlineKeyboardButton(
            "✨ انتخاب تصمیم افکت",
            switch_inline_query_current_chat=(
                f"r3effect {fight_id} {self._inline_user_token(user_id)}"
            ),
        )]]

        fight = self.db.get_fight_by_id(fight_id)
        chat_id = fight.chat_id if fight and fight.chat_id else user_id
        player_name = self._battle_player_name(user_id, "Player")
        text = (
            f"✨ {player_name}\n"
            f"تصمیم افکت این راوند را مخفی انتخاب کن."
        )
        try:
            deck_state = self.db.get_battle_deck_state(fight_id)
            if deck_state.get("challenger_deck_cards") and deck_state.get("opponent_deck_cards"):
                deck_text = (
                    self._deck_status_header(
                        fight_id,
                        deck_state.get("arena"),
                        deck_state.get("current_round", 1),
                        deck_state.get("challenger_rounds_won", 0),
                        deck_state.get("opponent_rounds_won", 0),
                    )
                    + f"\n\n── تصمیم افکت ──\n{text}"
                )
                await self._upsert_deck_status_message(
                    context,
                    fight_id,
                    chat_id,
                    deck_text,
                    InlineKeyboardMarkup(keyboard),
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception as e:
            logger.warning(f"Failed to send effect prompt for {fight_id}: {e}")
            context.bot_data.pop(f"r3_{fight_id}_{role}_effect_pending", None)
            context.bot_data[f"r3_{fight_id}_{role}_effect"] = None
            await self._advance_round_effect_turn_or_resolve(context, fight_id)

    async def _send_round_cards_reveal(self, context, fight_id: str) -> None:
        """Reveal both selected cards together before effect decisions and resolve."""
        import sqlite3 as _sq

        ch_card_id = context.bot_data.get(f"r3_{fight_id}_challenger_card")
        op_card_id = context.bot_data.get(f"r3_{fight_id}_opponent_card")
        if not ch_card_id or not op_card_id:
            return

        if context.bot_data.get(f"r3_{fight_id}_phase") != "effect_selection":
            return

        fight = self.db.get_fight_by_id(fight_id)
        if not fight or not fight.chat_id:
            return

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT challenger_id, opponent_id, current_round FROM battle_states WHERE fight_id=?",
            (fight_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return

        ch_id, op_id, current_round = row
        reveal_key = f"r3_{fight_id}_round_{current_round}_cards_revealed"
        if context.bot_data.get(reveal_key):
            return

        context.bot_data[reveal_key] = True
        ch_card = self.db.get_card_by_id_for_player(ch_card_id, ch_id) or self.db.get_card_by_id(ch_card_id)
        op_card = self.db.get_card_by_id_for_player(op_card_id, op_id) or self.db.get_card_by_id(op_card_id)
        ch_media_sent = bool(context.bot_data.pop(f"r3_{fight_id}_challenger_media_sent", False))
        op_media_sent = bool(context.bot_data.pop(f"r3_{fight_id}_opponent_media_sent", False))

        if ch_media_sent and op_media_sent:
            return

        # Peer private inline games cannot receive a new bot message in the
        # players' chat. Reveal the two previously inserted generic selection
        # messages in place once both choices have been confirmed.
        if context.bot_data.get(f"deck_{fight_id}_inline_message_id"):
            if not ch_media_sent:
                await self._reveal_hidden_inline_round_card(
                    context, fight_id, "challenger", ch_id, ch_card
                )
            if not op_media_sent:
                await self._reveal_hidden_inline_round_card(
                    context, fight_id, "opponent", op_id, op_card
                )
            return

        if not ch_media_sent:
            await self._send_selected_round_card_media(context, fight_id, ch_id, ch_card)
        if not op_media_sent:
            await self._send_selected_round_card_media(context, fight_id, op_id, op_card)

    async def _reveal_hidden_inline_round_card(
        self, context, fight_id: str, role: str, user_id: int, card
    ) -> None:
        """Reveal a hidden final pick by editing its peer-chat inline message."""
        message_key = f"r3_{fight_id}_{role}_hidden_inline_message_id"
        inline_message_id = context.bot_data.pop(message_key, None)
        if not inline_message_id or not card:
            return

        player_name = self._battle_player_name(user_id, "Player")
        caption = f"🎴 {player_name}: {card.name}"
        try:
            photo_file_id = await self._get_inline_card_photo_file_id(
                context, user_id, card
            )
            if photo_file_id:
                try:
                    await context.bot.edit_message_media(
                        inline_message_id=inline_message_id,
                        media=telegram.InputMediaPhoto(
                            media=photo_file_id,
                            caption=caption,
                        ),
                    )
                    return
                except Exception as media_exc:
                    logger.warning(
                        "Could not replace hidden inline message with card media for %s/%s: %s",
                        fight_id,
                        role,
                        media_exc,
                    )

            await context.bot.edit_message_text(
                inline_message_id=inline_message_id,
                text=caption,
                reply_markup=None,
            )
        except Exception as exc:
            logger.warning(
                "Could not reveal hidden inline card for %s/%s: %s",
                fight_id,
                role,
                exc,
            )

    async def _advance_round_card_turn_or_start_effects(self, context, fight_id: str):
        """Move from first card turn to second, then reveal cards and start effects."""
        import json as _json
        import sqlite3 as _sq

        ch_card_id = context.bot_data.get(f"r3_{fight_id}_challenger_card")
        op_card_id = context.bot_data.get(f"r3_{fight_id}_opponent_card")

        if ch_card_id and op_card_id:
            context.bot_data.pop(f"r3_{fight_id}_expected_role", None)
            context.bot_data[f"r3_{fight_id}_phase"] = "effect_selection"
            await self._send_round_cards_reveal(context, fight_id)
            context.bot_data[f"r3_{fight_id}_challenger_effect"] = None
            context.bot_data[f"r3_{fight_id}_opponent_effect"] = None
            await self._check_both_cards_selected(context, fight_id)
            return

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT challenger_id, opponent_id,
                   challenger_remaining_cards, opponent_remaining_cards,
                   arena, current_round
            FROM battle_states WHERE fight_id=?
        ''', (fight_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return

        ch_id, op_id, ch_rem_raw, op_rem_raw, arena_id, round_num = row
        first_role = context.bot_data.get(f"r3_{fight_id}_next_first_role", "challenger")
        if first_role not in ("challenger", "opponent"):
            first_role = "challenger"
        first_selected = ch_card_id if first_role == "challenger" else op_card_id
        next_role = first_role if not first_selected else self._other_round_role(first_role)
        context.bot_data[f"r3_{fight_id}_expected_role"] = next_role

        await self._send_round_card_selection_panel(
            context, fight_id, ch_id, op_id,
            _json.loads(ch_rem_raw or '[]'),
            _json.loads(op_rem_raw or '[]'),
            arena_id, round_num,
        )

    async def _advance_round_effect_turn_or_resolve(self, context, fight_id: str):
        """Run optional card effects in order, then resolve the round."""
        import sqlite3 as _sq

        if context.bot_data.get(f"r3_{fight_id}_phase") != "effect_selection":
            return

        if (
            context.bot_data.get(f"r3_{fight_id}_challenger_effect_pending")
            or context.bot_data.get(f"r3_{fight_id}_opponent_effect_pending")
        ):
            return

        ch_effect_key = f"r3_{fight_id}_challenger_effect"
        op_effect_key = f"r3_{fight_id}_opponent_effect"
        if ch_effect_key in context.bot_data and op_effect_key in context.bot_data:
            context.bot_data.pop(f"r3_{fight_id}_effect_expected_role", None)
            await self._check_both_cards_selected(context, fight_id)
            return

        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT challenger_id, opponent_id FROM battle_states WHERE fight_id=?",
            (fight_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return

        ch_id, op_id = row
        first_role = context.bot_data.get(f"r3_{fight_id}_next_first_role", "challenger")
        if first_role not in ("challenger", "opponent"):
            first_role = "challenger"

        order = [first_role, self._other_round_role(first_role)]
        for role in order:
            effect_key = f"r3_{fight_id}_{role}_effect"
            card_id = context.bot_data.get(f"r3_{fight_id}_{role}_card")
            if effect_key in context.bot_data or not card_id:
                continue

            user_id = self._round_user_for_role(role, ch_id, op_id)
            card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
            context.bot_data[f"r3_{fight_id}_effect_expected_role"] = role
            await self._send_round_effect_prompt(context, fight_id, user_id, role, card)
            return

        context.bot_data.pop(f"r3_{fight_id}_effect_expected_role", None)
        await self._check_both_cards_selected(context, fight_id)

    async def _send_selected_round_card_media(self, context, fight_id: str, user_id: int, card) -> None:
        """Send the selected card media into the group for the fallback button path."""
        # In a peer private chat the selected inline result is already the
        # visible card message. Bots do not receive that peer chat_id, so a
        # normal send would incorrectly land in the creator's bot DM.
        if context.bot_data.get(f"deck_{fight_id}_inline_message_id"):
            return
        fight = self.db.get_fight_by_id(fight_id)
        if not fight or not fight.chat_id or not card:
            return

        player_name = self._battle_player_name(user_id, "Player")
        media_path = self._resolve_card_media_path(card)
        try:
            if media_path and os.path.exists(media_path):
                with open(media_path, 'rb') as media:
                    if media_path.lower().endswith('.webp'):
                        await context.bot.send_sticker(chat_id=fight.chat_id, sticker=media)
                        await context.bot.send_message(
                            chat_id=fight.chat_id,
                            text=f"🎴 {player_name}: {card.name}"
                        )
                    else:
                        await context.bot.send_photo(
                            chat_id=fight.chat_id,
                            photo=media,
                            caption=f"🎴 {player_name}: {card.name}"
                        )
            else:
                await context.bot.send_message(
                    chat_id=fight.chat_id,
                    text=f"🎴 {player_name}: {card.name}"
                )
        except Exception as e:
            logger.warning(f"Failed to send selected round card media for {card.name}: {e}")

    async def _record_round_effect_selection(
        self, context, fight_id: str, user_id: int, effect_key: str
    ) -> tuple:
        """Validate and store one player's hidden effect decision."""
        import sqlite3 as _sq
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT challenger_id, opponent_id FROM battle_states WHERE fight_id=?', (fight_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False, None, "بازی یافت نشد"

        ch_id, op_id = row
        if user_id == ch_id:
            role = 'challenger'
        elif user_id == op_id:
            role = 'opponent'
        else:
            return False, None, "این انتخاب مال تو نیست"

        if context.bot_data.get(f"r3_{fight_id}_phase") != "effect_selection":
            return False, None, "اول باید هر دو کارت این راوند انتخاب شوند"

        expected_role = context.bot_data.get(f"r3_{fight_id}_effect_expected_role")
        if expected_role in ("challenger", "opponent") and role != expected_role:
            return False, None, "هنوز نوبت تصمیم افکت تو نیست"

        pending_key = f"r3_{fight_id}_{role}_effect_pending"
        if not context.bot_data.get(pending_key):
            return False, None, "این انتخاب منقضی شده"

        card_id = context.bot_data.get(f"r3_{fight_id}_{role}_card")
        card = (
            self.db.get_card_by_id_for_player(card_id, user_id)
            or self.db.get_card_by_id(card_id)
        )
        from systems.battle_system_3rounds import get_card_effects
        allowed = get_card_effects(card)
        if effect_key != "none" and effect_key not in allowed:
            return False, None, "این افکت برای کارت تو نیست"

        context.bot_data.pop(pending_key, None)
        context.bot_data[f"r3_{fight_id}_{role}_effect"] = None if effect_key == "none" else effect_key
        return True, role, None

    async def r3_effect_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Choose whether to activate the selected card effect for this round."""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        prefix = "r3_effect_"
        rest = query.data[len(prefix):]
        fight_id = rest[:8]
        effect_key = rest[9:]

        ok, role, info = await self._record_round_effect_selection(
            context, fight_id, user_id, effect_key
        )
        if not ok:
            await query.answer(f"❌ {info}", show_alert=True)
            return

        try:
            await query.edit_message_text("✅ تصمیم افکت ثبت شد.")
        except Exception:
            pass

        await self._advance_round_effect_turn_or_resolve(context, fight_id)

    async def _answer_r3_effect_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Personal inline picker for hidden effect decisions."""
        query = update.inline_query
        raw_query = (query.query or "").strip()
        user_id = query.from_user.id
        query_parts = raw_query.split()
        results = []

        if len(query_parts) < 3:
            results.append(InlineQueryResultArticle(
                id="old_effect_picker",
                title="این دکمه قدیمی است",
                input_message_content=InputTextMessageContent("❌ این دکمه قدیمی است.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        fight_id = query_parts[1].strip()[:8]
        target_user_id = self._parse_inline_user_token(query_parts[2].strip())
        if target_user_id is None or user_id != target_user_id:
            results.append(InlineQueryResultArticle(
                id="locked_effect_picker",
                title="این انتخاب مال تو نیست",
                input_message_content=InputTextMessageContent("❌ این انتخاب مال تو نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        import sqlite3 as _sq
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT challenger_id, opponent_id, status FROM battle_states WHERE fight_id=?', (fight_id,))
        row = cursor.fetchone()
        conn.close()
        if not row or row[2] == 'completed':
            results.append(InlineQueryResultArticle(
                id="missing_effect_fight",
                title="این بازی فعال نیست",
                input_message_content=InputTextMessageContent("❌ این بازی فعال نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        ch_id, op_id, _status = row
        if user_id == ch_id:
            role = 'challenger'
        elif user_id == op_id:
            role = 'opponent'
        else:
            results.append(InlineQueryResultArticle(
                id="not_your_effect_fight",
                title="این انتخاب مال تو نیست",
                input_message_content=InputTextMessageContent("❌ این انتخاب مال تو نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        if context.bot_data.get(f"r3_{fight_id}_phase") != "effect_selection":
            results.append(InlineQueryResultArticle(
                id="effect_before_cards_done",
                title="فعلاً نوبت افکت نیست",
                input_message_content=InputTextMessageContent("⏳ اول هر دو کارت این راوند باید انتخاب شوند.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        expected_role = context.bot_data.get(f"r3_{fight_id}_effect_expected_role")
        if expected_role in ("challenger", "opponent") and role != expected_role:
            results.append(InlineQueryResultArticle(
                id="not_your_effect_turn",
                title="هنوز نوبت افکت تو نیست",
                input_message_content=InputTextMessageContent("⏳ هنوز نوبت تصمیم افکت این بازیکن نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        if not context.bot_data.get(f"r3_{fight_id}_{role}_effect_pending"):
            results.append(InlineQueryResultArticle(
                id="no_effect_pending",
                title="تصمیمی لازم نیست",
                input_message_content=InputTextMessageContent("✅ تصمیمی لازم نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        card_id = context.bot_data.get(f"r3_{fight_id}_{role}_card")
        card = (
            self.db.get_card_by_id_for_player(card_id, user_id)
            or self.db.get_card_by_id(card_id)
        )

        from systems.battle_system_3rounds import CARD_EFFECTS, get_card_effects
        effects = get_card_effects(card)
        effect_options = list(effects) + ["none"]
        player_name = self._battle_player_name(user_id, "Player")
        generic_message = f"✨ تصمیم افکت {player_name} ثبت شد."

        for effect_key in effect_options:
            if effect_key == "none":
                title = "بدون افکت"
                description = "این راوند افکت فعال نشود"
            else:
                info = CARD_EFFECTS[effect_key]
                title = f"{info['emoji']} {info['name_fa']}"
                description = "فعال کردن این افکت برای همین راوند"

            results.append(InlineQueryResultArticle(
                id=self._inline_effect_result_id(fight_id, user_id, effect_key),
                title=title,
                description=description,
                input_message_content=InputTextMessageContent(generic_message),
                reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅",
                    callback_data=self._inline_effect_confirm_callback_data(fight_id, user_id, effect_key),
                )
                ]]),
            ))

        await query.answer(results, cache_time=0, is_personal=True)

    async def _answer_pvp_deck_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Personal inline picker for deck selection inside the group."""
        query = update.inline_query
        raw_query = (query.query or "").strip()
        user_id = query.from_user.id
        query_parts = raw_query.split()
        results = []

        if len(query_parts) < 3:
            results.append(InlineQueryResultArticle(
                id="old_deck_picker",
                title="این دکمه قدیمی است",
                input_message_content=InputTextMessageContent("❌ این دکمه قدیمی است.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        fight_id = query_parts[1].strip()[:8]
        target_user_id = self._parse_inline_user_token(query_parts[2].strip())
        if target_user_id is None or user_id != target_user_id:
            results.append(InlineQueryResultArticle(
                id="locked_deck_picker",
                title="این انتخاب مال تو نیست",
                input_message_content=InputTextMessageContent("❌ این انتخاب مال تو نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        fight = self.db.get_fight_by_id(fight_id)
        if not fight or fight.status == FightStatus.COMPLETED or fight.status == FightStatus.CANCELLED:
            results.append(InlineQueryResultArticle(
                id="missing_deck_fight",
                title="این فایت فعال نیست",
                input_message_content=InputTextMessageContent("❌ این فایت فعال نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        if user_id not in (fight.challenger_id, fight.opponent_id):
            results.append(InlineQueryResultArticle(
                id="not_your_deck_fight",
                title="این فایت مال تو نیست",
                input_message_content=InputTextMessageContent("❌ این فایت مال تو نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        expected_user_id = context.bot_data.get(f"pvp_{fight_id}_deck_expected_user")
        if expected_user_id in (fight.challenger_id, fight.opponent_id) and user_id != expected_user_id:
            results.append(InlineQueryResultArticle(
                id="not_your_deck_turn",
                title="هنوز نوبت تو نیست",
                input_message_content=InputTextMessageContent("⏳ هنوز نوبت انتخاب دک این بازیکن نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        from systems.deck_system import DeckSystem
        deck_system = DeckSystem(self.db)
        valid_decks = deck_system.get_valid_decks(user_id)
        if not valid_decks:
            results.append(InlineQueryResultArticle(
                id="no_valid_decks",
                title="دک کامل نداری",
                description="اول در PV یک دک ۳ کارته بساز",
                input_message_content=InputTextMessageContent("⚠️ دک کامل نداری.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        rarity_emoji = {'normal': '🟢', 'epic': '🟣', 'legend': '🟡', 'rare': '🔵'}
        player_name = self._battle_player_name(user_id, "Player")
        generic_message = f"🗂️ دک {player_name} انتخاب شد."

        for deck in valid_decks:
            card_names = " · ".join(
                f"{rarity_emoji.get(c.rarity.value if hasattr(c.rarity, 'value') else c.rarity, '⚪')}{c.name[:10]}"
                for c in deck['cards']
            )
            deck_id = deck['deck_id']
            results.append(InlineQueryResultArticle(
                id=self._inline_deck_result_id(fight_id, user_id, deck_id),
                title=f"🃏 {deck['deck_name']}",
                description=card_names,
                input_message_content=InputTextMessageContent(generic_message),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "✅",
                        callback_data=self._inline_deck_result_id(fight_id, user_id, deck_id),
                    )
                ]]),
            ))

        await query.answer(results, cache_time=0, is_personal=True)

    async def r3_inline_card_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inline picker for round card selection inside the group chat."""
        query = update.inline_query
        raw_query = (query.query or "").strip()
        if raw_query.startswith("pvpdeck "):
            await self._answer_pvp_deck_inline_query(update, context)
            return
        if raw_query.startswith("r3effect "):
            await self._answer_r3_effect_inline_query(update, context)
            return
        if not raw_query:
            game_query_handler = getattr(self, "game_inline_query_handler", None)
            if callable(game_query_handler):
                await game_query_handler(update, context)
            return
        if not raw_query.startswith("r3pick "):
            return

        user_id = query.from_user.id
        query_parts = raw_query.split()
        results = []
        if len(query_parts) < 3:
            results.append(InlineQueryResultArticle(
                id="old_picker",
                title="این دکمه قدیمی است",
                input_message_content=InputTextMessageContent("❌ این دکمه قدیمی است. فایت جدید را از پیام جدید ادامه بده.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        fight_id = query_parts[1].strip()[:8]
        target_user_id = self._parse_inline_user_token(query_parts[2].strip())
        if target_user_id is None or user_id != target_user_id:
            results.append(InlineQueryResultArticle(
                id="locked_picker",
                title="این دست کارت مال تو نیست",
                input_message_content=InputTextMessageContent("❌ این دست کارت مال تو نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        import json as _json
        import sqlite3 as _sq
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT challenger_id, opponent_id,
                   challenger_remaining_cards, opponent_remaining_cards,
                   arena, current_round, status
            FROM battle_states WHERE fight_id=?
        ''', (fight_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            results.append(InlineQueryResultArticle(
                id="missing",
                title="بازی یافت نشد",
                input_message_content=InputTextMessageContent("❌ بازی یافت نشد.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        ch_id, op_id, ch_rem_raw, op_rem_raw, arena_id, round_num, status = row
        if status == 'completed':
            results.append(InlineQueryResultArticle(
                id="completed",
                title="این بازی تمام شده",
                input_message_content=InputTextMessageContent("❌ این بازی تمام شده.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        if user_id == ch_id:
            role = "challenger"
            remaining = _json.loads(ch_rem_raw or '[]')
        elif user_id == op_id:
            role = "opponent"
            remaining = _json.loads(op_rem_raw or '[]')
        else:
            results.append(InlineQueryResultArticle(
                id="not_yours",
                title="این انتخاب مال تو نیست",
                input_message_content=InputTextMessageContent("❌ این انتخاب مال تو نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        expected_role = context.bot_data.get(f"r3_{fight_id}_expected_role")
        if expected_role in ("challenger", "opponent") and role != expected_role:
            results.append(InlineQueryResultArticle(
                id="not_your_turn",
                title="هنوز نوبت تو نیست",
                input_message_content=InputTextMessageContent("⏳ هنوز نوبت این بازیکن نیست.")
            ))
            await query.answer(results, cache_time=0, is_personal=True)
            return

        player_name = self._battle_player_name(user_id, "Player")
        generic_message = f"🎴 انتخاب کارت {player_name} ثبت شد."
        final_deck_pick = (
            round_num == 3
            and len(remaining) == 1
            and self._fight_arena_mode(fight_id) == "deck"
        )
        hide_single_remaining_card = len(remaining) == 1 and not final_deck_pick

        for card_id in remaining:
            card = (
                self.db.get_card_by_id_for_player(card_id, user_id)
                or self.db.get_card_by_id(card_id)
            )
            if not card:
                continue

            result_id = self._inline_card_result_id(fight_id, user_id, card_id)
            description = self._round_card_description(card, arena_id)
            caption = f"🎴 {card.name}\nراوند {round_num} انتخاب شد."
            confirm_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅",
                    callback_data=self._inline_confirm_callback_data(fight_id, user_id, card_id),
                )
            ]])
            media_key = f"r3_{fight_id}_{user_id}_{card_id}_inline_media"
            # A visible final-round article is already a reveal even when no
            # cached sticker/photo is available; do not reveal it a second time.
            context.bot_data[media_key] = final_deck_pick
            if final_deck_pick:
                context.bot_data.pop(
                    f"r3_{fight_id}_{user_id}_{card_id}_explicit_confirm", None
                )

            # Keep the old hidden result for non-Deck flows and in-progress
            # battles started before the visible final Deck pick change.
            if hide_single_remaining_card:
                context.bot_data[
                    f"r3_{fight_id}_{user_id}_{card_id}_explicit_confirm"
                ] = True
                results.append(InlineQueryResultArticle(
                    id=result_id,
                    title=card.name,
                    description=description,
                    input_message_content=InputTextMessageContent(generic_message),
                    reply_markup=confirm_markup,
                ))
                continue

            sticker_file_id = await self._get_inline_card_sticker_file_id(context, user_id, card)
            if sticker_file_id:
                context.bot_data[media_key] = True
                results.append(InlineQueryResultCachedSticker(
                    id=result_id,
                    sticker_file_id=sticker_file_id,
                    reply_markup=confirm_markup,
                ))
                continue

            photo_file_id = await self._get_inline_card_photo_file_id(context, user_id, card)
            if photo_file_id:
                context.bot_data[media_key] = True
                results.append(InlineQueryResultCachedPhoto(
                    id=result_id,
                    photo_file_id=photo_file_id,
                    title=card.name,
                    description=description,
                    caption=caption,
                    reply_markup=confirm_markup,
                ))
            else:
                results.append(InlineQueryResultArticle(
                    id=result_id,
                    title=card.name,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        f"🎴 {player_name}: {card.name}\nراوند {round_num} انتخاب شد."
                        if final_deck_pick else generic_message
                    ),
                    reply_markup=confirm_markup,
                ))

        await query.answer(results, cache_time=0, is_personal=True)

    async def r3_chosen_inline_card_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Persist selected inline card and resolve the round when both players are ready."""
        chosen = update.chosen_inline_result
        parsed_deck = self._parse_inline_deck_result_id(chosen.result_id)
        if parsed_deck:
            fight_id, target_user_id, deck_id = parsed_deck
            user_id = chosen.from_user.id
            if user_id != target_user_id:
                logger.info(
                    "Ignored inline deck selection for wrong user: fight=%s target=%s actual=%s",
                    fight_id, target_user_id, user_id,
                )
                return
            ok, message, started = await self._record_pvp_deck_selection(
                context, fight_id, user_id, deck_id
            )
            if not ok:
                logger.info(f"Ignored inline deck selection: {message}")
                return
            inline_message_id = getattr(chosen, "inline_message_id", None)
            if inline_message_id:
                try:
                    await context.bot.edit_message_reply_markup(
                        inline_message_id=inline_message_id,
                        reply_markup=None,
                    )
                except Exception as e:
                    logger.debug(f"Could not remove inline deck confirm button: {e}")
            logger.info(
                "Recorded inline deck selection via chosen_inline_result: fight=%s user=%s deck=%s",
                fight_id, user_id, deck_id,
            )
            return

        parsed_effect = self._parse_inline_effect_result_id(chosen.result_id)
        if parsed_effect:
            fight_id, target_user_id, effect_key = parsed_effect
            user_id = chosen.from_user.id
            if user_id != target_user_id:
                logger.info(
                    "Ignored inline effect selection for wrong user: fight=%s target=%s actual=%s",
                    fight_id, target_user_id, user_id,
                )
                return
            ok, role, info = await self._record_round_effect_selection(
                context, fight_id, user_id, effect_key
            )
            if not ok:
                logger.info(f"Ignored inline effect selection: {info}")
                return
            inline_message_id = getattr(chosen, "inline_message_id", None)
            if inline_message_id:
                try:
                    await context.bot.edit_message_reply_markup(
                        inline_message_id=inline_message_id,
                        reply_markup=None,
                    )
                except Exception as e:
                    logger.debug(f"Could not remove inline effect confirm button: {e}")
            logger.info(
                "Recorded inline effect decision via chosen_inline_result: fight=%s user=%s effect=%s",
                fight_id, user_id, effect_key,
            )
            await self._advance_round_effect_turn_or_resolve(context, fight_id)
            return

        parsed = self._parse_inline_card_result_id(chosen.result_id)
        if not parsed:
            return
        fight_id, target_user_id, card_id = parsed
        user_id = chosen.from_user.id
        if target_user_id is not None and user_id != target_user_id:
            logger.info(
                "Ignored inline card selection for wrong user: fight=%s target=%s actual=%s",
                fight_id, target_user_id, user_id,
            )
            return
        if context.bot_data.get(
            f"r3_{fight_id}_{user_id}_{card_id}_explicit_confirm"
        ):
            logger.info(
                "Waiting for explicit final-card confirmation: fight=%s user=%s card=%s",
                fight_id,
                user_id,
                card_id,
            )
            return
        ok, card, info = await self._record_round_card_selection(
            context, fight_id, user_id, card_id
        )
        if not ok:
            logger.info(f"Ignored inline card selection: {info}")
            return
        if context.bot_data.get(f"r3_{fight_id}_{user_id}_{card_id}_inline_media"):
            context.bot_data[f"r3_{fight_id}_{info}_media_sent"] = True
        inline_message_id = getattr(chosen, "inline_message_id", None)
        if (
            inline_message_id
            and not context.bot_data.get(f"r3_{fight_id}_{user_id}_{card_id}_inline_media")
        ):
            context.bot_data[
                f"r3_{fight_id}_{info}_hidden_inline_message_id"
            ] = inline_message_id
        if inline_message_id:
            try:
                await context.bot.edit_message_reply_markup(
                    inline_message_id=inline_message_id,
                    reply_markup=None,
                )
            except Exception as e:
                logger.debug(f"Could not remove inline confirm button: {e}")
        logger.info(
            "Recorded inline card selection via chosen_inline_result: fight=%s user=%s card=%s",
            fight_id, user_id, card_id,
        )
        await self._after_round_card_selected(context, fight_id, user_id, info, card)

    async def r3_inline_effect_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fallback confirmation for hidden inline effect decisions."""
        query = update.callback_query
        await query.answer()
        parsed = self._parse_inline_effect_result_id(query.data)
        if not parsed:
            await query.answer("❌ انتخاب نامعتبر است.", show_alert=True)
            return

        fight_id, target_user_id, effect_key = parsed
        user_id = query.from_user.id
        if user_id != target_user_id:
            await query.answer("❌ این تصمیم مال تو نیست.", show_alert=True)
            return

        ok, role, info = await self._record_round_effect_selection(
            context, fight_id, user_id, effect_key
        )
        if not ok:
            await query.answer(f"❌ {info}", show_alert=True)
            return

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logger.debug(f"Could not remove inline effect confirm button: {e}")

        logger.info(
            "Recorded inline effect decision via confirm button: fight=%s user=%s effect=%s",
            fight_id, user_id, effect_key,
        )
        await self._advance_round_effect_turn_or_resolve(context, fight_id)

    async def pvp_inline_deck_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fallback confirmation for inline deck selection."""
        query = update.callback_query
        await query.answer()
        parsed = self._parse_inline_deck_result_id(query.data)
        if not parsed:
            await query.answer("❌ انتخاب نامعتبر است.", show_alert=True)
            return

        fight_id, target_user_id, deck_id = parsed
        user_id = query.from_user.id
        if user_id != target_user_id:
            await query.answer("❌ این دک مال تو نیست.", show_alert=True)
            return

        ok, message, started = await self._record_pvp_deck_selection(
            context, fight_id, user_id, deck_id
        )
        if not ok:
            await query.answer(f"❌ {message}", show_alert=True)
            return

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logger.debug(f"Could not remove inline deck confirm button: {e}")

        logger.info(
            "Recorded inline deck selection via confirm button: fight=%s user=%s deck=%s",
            fight_id, user_id, deck_id,
        )

    async def r3_inline_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fallback confirmation for inline card messages when chosen-inline feedback is not delivered."""
        query = update.callback_query
        await query.answer()
        parsed = self._parse_inline_confirm_callback_data(query.data)
        if not parsed:
            await query.answer("❌ انتخاب نامعتبر است.", show_alert=True)
            return

        fight_id, target_user_id, card_id = parsed
        user_id = query.from_user.id
        if user_id != target_user_id:
            await query.answer("❌ این کارت مال تو نیست.", show_alert=True)
            return

        ok, card, info = await self._record_round_card_selection(
            context, fight_id, user_id, card_id
        )
        if not ok:
            await query.answer(f"❌ {info}", show_alert=True)
            return
        context.bot_data.pop(
            f"r3_{fight_id}_{user_id}_{card_id}_explicit_confirm",
            None,
        )
        if context.bot_data.get(f"r3_{fight_id}_{user_id}_{card_id}_inline_media"):
            context.bot_data[f"r3_{fight_id}_{info}_media_sent"] = True

        inline_message_id = getattr(query, "inline_message_id", None)
        if (
            inline_message_id
            and not context.bot_data.get(f"r3_{fight_id}_{user_id}_{card_id}_inline_media")
        ):
            context.bot_data[
                f"r3_{fight_id}_{info}_hidden_inline_message_id"
            ] = inline_message_id

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logger.debug(f"Could not remove inline confirm button: {e}")

        logger.info(
            "Recorded inline card selection via confirm button: fight=%s user=%s card=%s",
            fight_id, user_id, card_id,
        )
        await self._after_round_card_selected(context, fight_id, user_id, info, card)

    async def r3_card_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بازیکن کارتی برای راوند انتخاب کرد.
        callback_data: r3_card_{fight_id}_{card_id}
        """
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        import json as _json
        import sqlite3 as _sq

        # parse — fight_id ۸ کاراکتر
        prefix = "r3_card_"
        rest = query.data[len(prefix):]
        fight_id = rest[:8]
        card_id  = rest[9:]

        ok, card, info = await self._record_round_card_selection(
            context, fight_id, user_id, card_id
        )
        if not ok:
            await query.answer(f"❌ {info}", show_alert=True)
            return

        role = info
        card_name = card.name if card else card_id

        await query.edit_message_text(
            f"✅ **{card_name}** انتخاب شد!\n\n⏳ منتظر حریف...",
            parse_mode='Markdown'
        )

        await self._after_round_card_selected(context, fight_id, user_id, role, card)

    async def _check_both_cards_selected(self, context, fight_id: str):
        """اگر هر دو بازیکن کارت این راوند را انتخاب کرده‌اند، resolve کن."""
        import json as _json
        import sqlite3 as _sq

        ch_card_id = context.bot_data.get(f"r3_{fight_id}_challenger_card")
        op_card_id = context.bot_data.get(f"r3_{fight_id}_opponent_card")

        if not ch_card_id or not op_card_id:
            return  # هنوز یکی انتخاب نکرده

        if (
            context.bot_data.get(f"r3_{fight_id}_challenger_effect_pending")
            or context.bot_data.get(f"r3_{fight_id}_opponent_effect_pending")
        ):
            return  # هنوز تصمیم افکت مشخص نشده

        if (
            f"r3_{fight_id}_challenger_effect" not in context.bot_data
            or f"r3_{fight_id}_opponent_effect" not in context.bot_data
        ):
            return  # هنوز نوبت افکت‌ها کامل نشده

        if context.bot_data.get(f"r3_{fight_id}_phase") != "effect_selection":
            return  # افکت فقط بعد از انتخاب هر دو کارت همان راوند resolve می‌شود

        context.bot_data[f"r3_{fight_id}_phase"] = "resolving"

        # پاک کردن state موقت
        context.bot_data.pop(f"r3_{fight_id}_challenger_card", None)
        context.bot_data.pop(f"r3_{fight_id}_opponent_card", None)
        context.bot_data.pop(f"r3_{fight_id}_expected_role", None)
        context.bot_data.pop(f"r3_{fight_id}_effect_expected_role", None)

        # دریافت battle_state کامل
        conn = _sq.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT challenger_id, opponent_id, challenger_card_id, opponent_card_id,
                   arena, current_round, challenger_rounds_won, opponent_rounds_won,
                   challenger_used_stats, opponent_used_stats,
                   challenger_current_stats, opponent_current_stats,
                   challenger_remaining_cards, opponent_remaining_cards
            FROM battle_states WHERE fight_id=?
        ''', (fight_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return

        (ch_id, op_id, _, _, arena_id, current_round,
         ch_rounds_won, op_rounds_won,
         ch_used_raw, op_used_raw,
         ch_stats_raw, op_stats_raw,
         ch_rem_raw, op_rem_raw) = row

        ch_used  = _json.loads(ch_used_raw or '[]')
        op_used  = _json.loads(op_used_raw or '[]')
        ch_stats = _json.loads(ch_stats_raw or '{}')
        op_stats = _json.loads(op_stats_raw or '{}')

        # اگر ch_stats خالی بود (deck-based) از کارت بخوان
        ch_card = (
            self.db.get_card_by_id_for_player(ch_card_id, ch_id)
            or self.db.get_card_by_id(ch_card_id)
        )
        op_card = (
            self.db.get_card_by_id_for_player(op_card_id, op_id)
            or self.db.get_card_by_id(op_card_id)
        )

        if not ch_stats and ch_card:
            ch_stats = {
                'power': ch_card.power, 'speed': ch_card.speed,
                'iq': ch_card.iq, 'popularity': ch_card.popularity
            }
        if not op_stats and op_card:
            op_stats = {
                'power': op_card.power, 'speed': op_card.speed,
                'iq': op_card.iq, 'popularity': op_card.popularity
            }

        # برای deck-based: stat = مجموع‌ترین stat کارت (dominant)
        from systems.battle_system_3rounds import get_dominant_attr
        ch_stat = get_dominant_attr(ch_card, arena_id) if ch_card else 'power'
        op_stat = get_dominant_attr(op_card, arena_id) if op_card else 'power'

        # آپدیت remaining_cards (حذف کارت بازی‌شده)
        ch_remaining = _json.loads(ch_rem_raw or '[]')
        op_remaining = _json.loads(op_rem_raw or '[]')
        if ch_card_id in ch_remaining:
            ch_remaining.remove(ch_card_id)
        if op_card_id in op_remaining:
            op_remaining.remove(op_card_id)

        self.db.update_battle_deck_state(fight_id, 'challenger', ch_remaining)
        self.db.update_battle_deck_state(fight_id, 'opponent',   op_remaining)

        # resolve راوند با stat های کارت انتخابی
        ch_stats_round = {
            'power': ch_card.power, 'speed': ch_card.speed,
            'iq': ch_card.iq, 'popularity': ch_card.popularity
        } if ch_card else ch_stats

        op_stats_round = {
            'power': op_card.power, 'speed': op_card.speed,
            'iq': op_card.iq, 'popularity': op_card.popularity
        } if op_card else op_stats

        await self._resolve_3round(
            context, fight_id,
            ch_stat, op_stat,
            ch_id, op_id,
            ch_card_id, op_card_id,
            arena_id, current_round,
            ch_rounds_won, op_rounds_won,
            ch_used, op_used,
            ch_stats_round, op_stats_round
        )
