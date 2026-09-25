#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent engines for Quick, Deck matchmaking, and Easy group games.

The Telegram handlers are intentionally kept out of this module.  Every choice is
written to SQLite first, which makes first-choice-wins rules and concurrent
accepts deterministic even when Telegram delivers callbacks at the same time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import closing
import os
import random
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from systems.arena_registry import ArenaRegistry

logger = logging.getLogger(__name__)

QUICK_INVITE_TTL_SECONDS = 5 * 60
QUICK_GROUP_TTL_SECONDS = 60
QUICK_CHOICE_TTL_SECONDS = 60
EASY_LOBBY_TTL_SECONDS = 3 * 60
EASY_CHOICE_TTL_SECONDS = 30

CORE_STATS = ("power", "speed", "iq", "popularity")

QUICK_CARD_TYPE_LABELS = {
    "power": "قدرتی",
    "speed": "سرعتی",
    "iq": "هوشی",
    "popularity": "محبوبیتی",
}

_QUICK_CARD_TYPE_ALIASES = {
    "POWER_TYPE": "power",
    "WARRIOR": "power",
    "SPEED_TYPE": "speed",
    "SPEEDSTER": "speed",
    "IQ_TYPE": "iq",
    "GENIUS": "iq",
    "POPULARITY_TYPE": "popularity",
    "CELEBRITY": "popularity",
}


def normalize_quick_card_type(card_type: Any) -> Optional[str]:
    """Return the Quick type key used by conditional arena effects."""
    raw = getattr(card_type, "value", card_type)
    return _QUICK_CARD_TYPE_ALIASES.get(str(raw or "").strip().upper())


QUICK_ARENAS: List[Dict[str, Any]] = [
    {
        "id": "city",
        "name": "شهر",
        "emoji": "🏙️",
        "effects": [
            {"card_type": "power", "stat": "power", "delta": 1},
            {"card_type": "iq", "stat": "iq", "delta": 1},
        ],
        "disabled_stats": [],
        "abilities_enabled": True,
        "passives_enabled": True,
    },
    {
        "id": "desert",
        "name": "بیابان",
        "emoji": "🏜️",
        "effects": [
            {"card_type": "power", "stat": "power", "delta": 2},
            {"card_type": "speed", "stat": "speed", "delta": -1},
        ],
        "disabled_stats": [],
        "abilities_enabled": True,
        "passives_enabled": True,
    },
    {
        "id": "ice",
        "name": "یخبندان",
        "emoji": "❄️",
        "effects": [
            {"card_type": "speed", "stat": "speed", "delta": -2},
            {"card_type": "iq", "stat": "iq", "delta": 1},
        ],
        "disabled_stats": [],
        "abilities_enabled": True,
        "passives_enabled": True,
    },
    {
        "id": "forest",
        "name": "جنگل",
        "emoji": "🌲",
        "effects": [
            {"card_type": "iq", "stat": "iq", "delta": 1},
            {"card_type": "popularity", "stat": "popularity", "delta": -1},
        ],
        "disabled_stats": [],
        "abilities_enabled": True,
        "passives_enabled": True,
    },
    {
        "id": "silent_temple",
        "name": "معبد خاموش",
        "emoji": "🏛️",
        "effects": [
            {"card_type": "iq", "stat": "iq", "delta": 2},
        ],
        "disabled_stats": ["speed"],
        "abilities_enabled": False,
        "passives_enabled": True,
    },
    {
        "id": "null_zone",
        "name": "منطقه خنثی",
        "emoji": "🌌",
        "effects": [],
        "disabled_stats": [],
        "abilities_enabled": True,
        "passives_enabled": False,
    },
]


ABILITY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "reroll_arena": {
        "title": "🔄 تغییر زمین",
        "description": "زمین یک‌بار به‌صورت تصادفی عوض می‌شود.",
        "effect": {"type": "reroll_arena"},
    },
    "reveal_opponent": {
        "title": "👁 مشاهده کارت حریف",
        "description": "کارت حریف قبل از انتخاب ویژگی نمایش داده می‌شود.",
        "effect": {"type": "reveal_opponent"},
    },
    "lock_power": {
        "title": "🔒 قفل قدرت",
        "description": "حریف نمی‌تواند قدرت را انتخاب کند.",
        "effect": {"type": "lock_stat", "stat": "power"},
    },
    "lock_speed": {
        "title": "🔒 قفل سرعت",
        "description": "حریف نمی‌تواند سرعت را انتخاب کند.",
        "effect": {"type": "lock_stat", "stat": "speed"},
    },
    "lock_iq": {
        "title": "🔒 قفل هوش",
        "description": "حریف نمی‌تواند هوش را انتخاب کند.",
        "effect": {"type": "lock_stat", "stat": "iq"},
    },
    "lock_popularity": {
        "title": "🔒 قفل محبوبیت",
        "description": "حریف نمی‌تواند محبوبیت را انتخاب کند.",
        "effect": {"type": "lock_stat", "stat": "popularity"},
    },
    "weaken_power": {
        "title": "📉 کاهش قدرت",
        "description": "۲ واحد از قدرت نهایی حریف کم می‌کند.",
        "effect": {"type": "weaken_stat", "stat": "power", "delta": -2},
    },
    "weaken_speed": {
        "title": "📉 کاهش سرعت",
        "description": "۲ واحد از سرعت نهایی حریف کم می‌کند.",
        "effect": {"type": "weaken_stat", "stat": "speed", "delta": -2},
    },
    "weaken_iq": {
        "title": "📉 کاهش هوش",
        "description": "۲ واحد از هوش نهایی حریف کم می‌کند.",
        "effect": {"type": "weaken_stat", "stat": "iq", "delta": -2},
    },
    "weaken_popularity": {
        "title": "📉 کاهش محبوبیت",
        "description": "۲ واحد از محبوبیت نهایی حریف کم می‌کند.",
        "effect": {"type": "weaken_stat", "stat": "popularity", "delta": -2},
    },
}


EASY_QUESTIONS: List[Dict[str, Any]] = [
    {"id": "smart", "text": "باهوش‌ترین شخصیت کیست؟", "attribute": "iq"},
    {"id": "strong", "text": "قوی‌ترین شخصیت کیست؟", "attribute": "power"},
    {"id": "fast", "text": "سریع‌ترین شخصیت کیست؟", "attribute": "speed"},
    {"id": "popular", "text": "محبوب‌ترین شخصیت کیست؟", "attribute": "popularity"},
    {"id": "funny", "text": "بامزه‌ترین شخصیت کیست؟", "attribute": "funny"},
    {"id": "scary", "text": "ترسناک‌ترین شخصیت کیست؟", "attribute": "scary"},
    {"id": "charismatic", "text": "کاریزماتیک‌ترین شخصیت کیست؟", "attribute": "charisma"},
    {"id": "cute", "text": "کیوت‌ترین شخصیت کیست؟", "attribute": "cute"},
    {"id": "evil", "text": "شرورترین شخصیت کیست؟", "attribute": "evil"},
    {"id": "leader", "text": "بهترین رهبر کیست؟", "attribute": "leadership"},
]


def _now() -> datetime:
    # Keep storage compatible with the project's existing naive ISO timestamps,
    # while avoiding datetime.utcnow() deprecation on Python 3.12+.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def bidi_isolate(value: Any) -> str:
    """Keep dynamic Persian/Latin labels stable inside Telegram RTL text."""
    return f"\u2068{str(value or '').strip()}\u2069"


class GameModeSystem:
    """Owns persistent matchmaking and the deterministic mode state machines."""

    def __init__(self, db):
        self.db = db
        self.db_path = db.db_path
        # Keep a flag for fast rollback during the gradual rollout.  New installs
        # use the registry by default; setting ARENA_REGISTRY_READS=0 restores
        # only the legacy read path without deleting data.
        self.arena_registry_enabled = os.getenv("ARENA_REGISTRY_READS", "1").strip().lower() not in {"0", "false", "off"}
        self.arena_registry_fallback = os.getenv("ARENA_REGISTRY_FALLBACK_SEED", "1").strip().lower() not in {"0", "false", "off"}
        self.arena_registry_shadow = os.getenv("ARENA_REGISTRY_SHADOW_COMPARE", "0").strip().lower() not in {"0", "false", "off"}
        self.arena_registry = ArenaRegistry(db)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS game_requests (
                request_id TEXT PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                opponent_id INTEGER,
                mode TEXT NOT NULL,
                variant TEXT NOT NULL,
                source TEXT NOT NULL,
                origin_chat_id INTEGER,
                origin_message_id INTEGER,
                origin_inline_message_id TEXT,
                status TEXT NOT NULL DEFAULT 'waiting',
                invite_token TEXT UNIQUE,
                rounds INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                accepted_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_game_requests_queue
                ON game_requests(mode, variant, source, status, expires_at);
            CREATE INDEX IF NOT EXISTS idx_game_requests_creator
                ON game_requests(creator_id, status);
            CREATE INDEX IF NOT EXISTS idx_game_requests_opponent
                ON game_requests(opponent_id, status);

            CREATE TABLE IF NOT EXISTS game_match_states (
                request_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (request_id) REFERENCES game_requests(request_id)
            );

            CREATE TABLE IF NOT EXISTS card_mode_metadata (
                card_id TEXT PRIMARY KEY,
                traits TEXT NOT NULL DEFAULT '[]',
                series TEXT,
                hidden_stats TEXT NOT NULL DEFAULT '{}',
                passive TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS ability_definitions (
                ability_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                effect_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_ability_inventory (
                user_id INTEGER NOT NULL,
                ability_key TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, ability_key),
                FOREIGN KEY (ability_key) REFERENCES ability_definitions(ability_key)
            );

            CREATE TABLE IF NOT EXISTS game_match_reports (
                request_id TEXT PRIMARY KEY,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        request_columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(game_requests)").fetchall()
        }
        if "origin_inline_message_id" not in request_columns:
            cursor.execute(
                "ALTER TABLE game_requests ADD COLUMN origin_inline_message_id TEXT"
            )
        for key, definition in ABILITY_DEFINITIONS.items():
            cursor.execute(
                """
                INSERT OR IGNORE INTO ability_definitions
                    (ability_key, title, description, effect_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    key,
                    definition["title"],
                    definition["description"],
                    json.dumps(definition["effect"], ensure_ascii=False),
                ),
            )
        conn.commit()
        conn.close()

    @staticmethod
    def _request_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        return dict(row) if row else None

    def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM game_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        conn.close()
        return self._request_dict(row)

    def get_request_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM game_requests WHERE invite_token = ?", (token,)
        ).fetchone()
        conn.close()
        return self._request_dict(row)

    def _insert_request(
        self,
        conn: sqlite3.Connection,
        creator_id: int,
        mode: str,
        variant: str,
        source: str,
        ttl_seconds: int,
        origin_chat_id: Optional[int] = None,
        invite_token: Optional[str] = None,
        rounds: int = 1,
    ) -> Dict[str, Any]:
        now = _now()
        request_id = uuid.uuid4().hex[:12]
        conn.execute(
            """
            INSERT INTO game_requests (
                request_id, creator_id, mode, variant, source,
                origin_chat_id, status, invite_token, rounds,
                created_at, expires_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                creator_id,
                mode,
                variant,
                source,
                origin_chat_id,
                invite_token,
                rounds,
                _iso(now),
                _iso(now + timedelta(seconds=ttl_seconds)),
                _iso(now),
            ),
        )
        row = conn.execute(
            "SELECT * FROM game_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        return dict(row)

    def create_invite(
        self,
        creator_id: int,
        mode: str,
        variant: str,
        origin_chat_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        conn = self._connect()
        token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]
        request = self._insert_request(
            conn,
            creator_id,
            mode,
            variant,
            "invite_link",
            QUICK_INVITE_TTL_SECONDS,
            origin_chat_id=origin_chat_id,
            invite_token=token,
        )
        conn.commit()
        conn.close()
        return request

    def create_group_challenge(
        self, creator_id: int, mode: str, variant: str, chat_id: int
    ) -> Dict[str, Any]:
        conn = self._connect()
        request = self._insert_request(
            conn,
            creator_id,
            mode,
            variant,
            "group_challenge",
            QUICK_GROUP_TTL_SECONDS,
            origin_chat_id=chat_id,
        )
        conn.commit()
        conn.close()
        return request

    def create_inline_private_challenge(
        self, creator_id: int, mode: str, variant: str
    ) -> Dict[str, Any]:
        """Create a challenge inserted through inline mode into a peer chat."""
        if mode not in ("quick", "deck") or variant not in ("normal", "random"):
            raise ValueError("invalid_inline_game")
        conn = self._connect()
        request = self._insert_request(
            conn,
            creator_id,
            mode,
            variant,
            "inline_private",
            QUICK_GROUP_TTL_SECONDS,
            # Telegram does not expose the peer-chat id to inline bots. Keep a
            # valid service chat for private fallbacks; shared UI uses the
            # inline_message_id recorded after insertion.
            origin_chat_id=creator_id,
        )
        conn.commit()
        conn.close()
        return request

    def matchmake_random(
        self, creator_id: int, mode: str, variant: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Atomically join a compatible queue entry or create a new one."""
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        now = _iso(_now())
        conn.execute(
            """
            UPDATE game_requests SET status='expired', updated_at=?
            WHERE status='waiting' AND expires_at <= ?
            """,
            (now, now),
        )
        existing = conn.execute(
            """
            SELECT * FROM game_requests
            WHERE creator_id=? AND mode=? AND variant=? AND source='random_queue'
              AND status='waiting' AND expires_at > ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (creator_id, mode, variant, now),
        ).fetchone()
        if existing:
            conn.commit()
            conn.close()
            return "waiting", dict(existing)
        row = conn.execute(
            """
            SELECT * FROM game_requests
            WHERE mode=? AND variant=? AND source='random_queue'
              AND status='waiting' AND creator_id != ? AND expires_at > ?
            ORDER BY RANDOM() LIMIT 1
            """,
            (mode, variant, creator_id, now),
        ).fetchone()
        if row:
            request_id = row["request_id"]
            updated = conn.execute(
                """
                UPDATE game_requests
                SET opponent_id=?, status='accepted', accepted_at=?, updated_at=?
                WHERE request_id=? AND status='waiting' AND expires_at > ?
                """,
                (creator_id, now, now, request_id, now),
            )
            if updated.rowcount == 1:
                matched = conn.execute(
                    "SELECT * FROM game_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                conn.commit()
                conn.close()
                return "matched", dict(matched)

        request = self._insert_request(
            conn,
            creator_id,
            mode,
            variant,
            "random_queue",
            QUICK_INVITE_TTL_SECONDS,
        )
        conn.commit()
        conn.close()
        return "waiting", request

    def accept_request(self, request_id: str, opponent_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        now = _iso(_now())
        row = conn.execute(
            "SELECT * FROM game_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return False, "not_found", None
        if row["creator_id"] == opponent_id:
            conn.rollback()
            conn.close()
            return False, "self_accept", dict(row)
        if row["status"] != "waiting":
            conn.rollback()
            conn.close()
            return False, row["status"], dict(row)
        if row["expires_at"] <= now:
            conn.execute(
                "UPDATE game_requests SET status='expired', updated_at=? WHERE request_id=?",
                (now, request_id),
            )
            conn.commit()
            conn.close()
            return False, "expired", dict(row)
        updated = conn.execute(
            """
            UPDATE game_requests
            SET opponent_id=?, status='accepted', accepted_at=?, updated_at=?
            WHERE request_id=? AND status='waiting' AND expires_at > ?
            """,
            (opponent_id, now, now, request_id, now),
        )
        if updated.rowcount != 1:
            conn.rollback()
            conn.close()
            return False, "already_claimed", None
        accepted = conn.execute(
            "SELECT * FROM game_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        conn.commit()
        conn.close()
        return True, "accepted", dict(accepted)

    def accept_invite(self, token: str, opponent_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        request = self.get_request_by_token(token)
        if not request:
            return False, "not_found", None
        return self.accept_request(request["request_id"], opponent_id)

    def update_message_reference(self, request_id: str, chat_id: int, message_id: int) -> None:
        conn = self._connect()
        conn.execute(
            """
            UPDATE game_requests SET origin_chat_id=?, origin_message_id=?, updated_at=?
            WHERE request_id=?
            """,
            (chat_id, message_id, _iso(_now()), request_id),
        )
        conn.commit()
        conn.close()

    def update_inline_message_reference(self, request_id: str, inline_message_id: str) -> None:
        conn = self._connect()
        conn.execute(
            """
            UPDATE game_requests
               SET origin_inline_message_id=?, updated_at=?
             WHERE request_id=?
            """,
            (inline_message_id, _iso(_now()), request_id),
        )
        conn.commit()
        conn.close()

    def expire_request(self, request_id: str) -> bool:
        conn = self._connect()
        result = conn.execute(
            """
            UPDATE game_requests SET status='expired', updated_at=?
            WHERE request_id=? AND status='waiting'
            """,
            (_iso(_now()), request_id),
        )
        conn.commit()
        conn.close()
        return result.rowcount == 1

    def cancel_request(self, request_id: str, user_id: int) -> bool:
        conn = self._connect()
        result = conn.execute(
            """
            UPDATE game_requests SET status='cancelled', updated_at=?
            WHERE request_id=? AND creator_id=? AND status='waiting'
            """,
            (_iso(_now()), request_id, user_id),
        )
        conn.commit()
        conn.close()
        return result.rowcount == 1

    def get_state(self, request_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        conn.close()
        return _loads(row[0], {}) if row else None

    def _save_state(self, conn: sqlite3.Connection, request_id: str, state: Dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO game_match_states(request_id, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (request_id, json.dumps(state, ensure_ascii=False), _iso(_now())),
        )

    def _arena(self, arena_id: str) -> Dict[str, Any]:
        if self.arena_registry_enabled:
            runtime = self.arena_registry.runtime(str(arena_id or ""), "quick", "telegram")
            if runtime:
                self._shadow_compare_quick(runtime)
                return runtime
            if not self.arena_registry_fallback:
                raise ValueError("arena_not_available")
        logger.warning("arena_registry_static_fallback arena=%s mode=quick", arena_id)
        return next((a for a in QUICK_ARENAS if a["id"] == arena_id), QUICK_ARENAS[0])

    def _random_arena(self, exclude: Optional[str] = None) -> Dict[str, Any]:
        if self.arena_registry_enabled:
            runtime = self.arena_registry.select_for_match("quick", "telegram", [exclude] if exclude else None)
            if runtime:
                logger.info("arena_selected arena=%s mode=quick platform=telegram reroll=%s", runtime["arena_id"], bool(exclude))
                self._shadow_compare_quick(runtime)
                return runtime
            if not self.arena_registry_fallback:
                raise ValueError("arena_pool_empty")
        logger.warning("arena_registry_static_fallback mode=quick exclude=%s", exclude)
        choices = [a for a in QUICK_ARENAS if a["id"] != exclude] or QUICK_ARENAS
        return random.choice(choices)

    def _shadow_compare_quick(self, runtime: Mapping[str, Any]) -> None:
        if not self.arena_registry_shadow:
            return
        legacy = next((item for item in QUICK_ARENAS if item["id"] == runtime.get("arena_id")), None)
        if not legacy:
            return
        fields = ("effects", "disabled_stats", "abilities_enabled", "passives_enabled")
        mismatches = [field for field in fields if legacy.get(field) != runtime.get(field)]
        if mismatches:
            logger.warning("arena_registry_shadow_mismatch arena=%s fields=%s", runtime.get("arena_id"), ",".join(mismatches))

    def arena_for_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Return the immutable Quick arena snapshot when a match has one."""
        snapshot = state.get("arena_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("mode") == "quick" and snapshot.get("arena_id", snapshot.get("id")) == state.get("arena"):
            return snapshot
        return self._arena(state.get("arena") or state.get("arena_id") or "")

    @staticmethod
    def _store_arena_snapshot(state: Dict[str, Any], arena: Dict[str, Any], replaced: bool = False) -> None:
        snapshot = {key: arena.get(key) for key in (
            "id", "arena_id", "version", "name", "name_fa", "name_en", "description_fa", "emoji", "mode",
            "rules", "effects", "disabled_stats", "abilities_enabled", "passives_enabled", "background_url",
        ) if key in arena}
        snapshot.setdefault("id", arena.get("arena_id"))
        snapshot.setdefault("arena_id", snapshot.get("id"))
        snapshot.setdefault("mode", "quick")
        if replaced and state.get("arena_snapshot"):
            state.setdefault("arena_history", []).append(state["arena_snapshot"])
        state["arena"] = snapshot["arena_id"]
        state["arena_id"] = snapshot["arena_id"]
        state["arena_version"] = snapshot.get("version")
        state["arena_snapshot"] = snapshot

    def start_quick_match(self, request_id: str) -> Dict[str, Any]:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                request = self.get_request(request_id)
                if not request or request["status"] not in ("accepted", "active"):
                    raise ValueError("request_not_accepted")
                players = [request["creator_id"], request["opponent_id"]]
                if not all(players):
                    raise ValueError("missing_opponent")
                row = conn.execute("SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)).fetchone()
                state = _loads(row[0], {}) if row else None
                if state:
                    return state

                state = {
                    "mode": "quick",
                    "scoring_rule": "sum_selected_stats_v1",
                    "variant": request["variant"],
                    "players": players,
                    "phase": "card_selection",
                    "cards": {},
                    "ability_choices": {},
                    "stat_choices": {},
                    "locked_stats": {str(uid): [] for uid in players},
                    "arena": None,
                    "initial_arena": None,
                    "deadline": _iso(_now() + timedelta(seconds=QUICK_CHOICE_TTL_SECONDS)),
                }
                if request["variant"] == "random":
                    for user_id in players:
                        cards = self.db.get_player_cards(user_id)
                        if not cards:
                            raise ValueError(f"player_has_no_cards:{user_id}")
                        state["cards"][str(user_id)] = random.choice(cards).card_id
                    self._advance_quick_after_cards(state)

                self._save_state(conn, request_id, state)
                conn.execute(
                    "UPDATE game_requests SET status='active', updated_at=? WHERE request_id=?",
                    (_iso(_now()), request_id),
                )
                return state

    def _advance_quick_after_cards(self, state: Dict[str, Any]) -> None:
        arena = self._random_arena()
        self._store_arena_snapshot(state, arena)
        state["initial_arena"] = arena["id"]
        state["initial_arena_snapshot"] = dict(state["arena_snapshot"])
        state["phase"] = "ability_selection"
        state["deadline"] = _iso(_now() + timedelta(seconds=30))

    def select_quick_card(self, request_id: str, user_id: int, card_id: str) -> Tuple[Dict[str, Any], bool]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            raise ValueError("state_not_found")
        state = _loads(row[0], {})
        if state.get("phase") != "card_selection" or user_id not in state.get("players", []):
            conn.rollback()
            conn.close()
            raise ValueError("invalid_phase_or_player")
        key = str(user_id)
        if key in state["cards"]:
            conn.rollback()
            conn.close()
            raise ValueError("choice_locked")
        owned = {card.card_id for card in self.db.get_player_cards(user_id)}
        if card_id not in owned:
            conn.rollback()
            conn.close()
            raise ValueError("card_not_owned")
        state["cards"][key] = card_id
        advanced = len(state["cards"]) == len(state["players"])
        if advanced:
            self._advance_quick_after_cards(state)
        self._save_state(conn, request_id, state)
        conn.commit()
        conn.close()
        return state, advanced

    def list_player_abilities(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT i.ability_key, i.quantity, d.title, d.description, d.effect_json
            FROM player_ability_inventory i
            JOIN ability_definitions d ON d.ability_key=i.ability_key
            WHERE i.user_id=? AND i.quantity > 0
            ORDER BY d.title
            """,
            (user_id,),
        ).fetchall()
        conn.close()
        return [
            {
                **dict(row),
                "effect": _loads(row["effect_json"], {}),
            }
            for row in rows
        ]

    def grant_ability(self, user_id: int, ability_key: str, quantity: int = 1) -> bool:
        if ability_key not in ABILITY_DEFINITIONS or quantity <= 0:
            return False
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO player_ability_inventory(user_id, ability_key, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, ability_key) DO UPDATE SET quantity=quantity+excluded.quantity
            """,
            (user_id, ability_key, quantity),
        )
        conn.commit()
        conn.close()
        return True

    def select_quick_ability(self, request_id: str, user_id: int, ability_key: str) -> Tuple[Dict[str, Any], bool]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            raise ValueError("state_not_found")
        state = _loads(row[0], {})
        if state.get("phase") != "ability_selection" or user_id not in state.get("players", []):
            conn.rollback()
            conn.close()
            raise ValueError("invalid_phase_or_player")
        user_key = str(user_id)
        if user_key in state["ability_choices"]:
            conn.rollback()
            conn.close()
            raise ValueError("choice_locked")
        arena = self.arena_for_state(state)
        if ability_key != "skip":
            if not arena.get("abilities_enabled", True):
                conn.rollback()
                conn.close()
                raise ValueError("abilities_disabled")
            if ability_key not in ABILITY_DEFINITIONS:
                conn.rollback()
                conn.close()
                raise ValueError("unknown_ability")
            consumed = conn.execute(
                """
                UPDATE player_ability_inventory SET quantity=quantity-1
                WHERE user_id=? AND ability_key=? AND quantity > 0
                """,
                (user_id, ability_key),
            )
            if consumed.rowcount != 1:
                conn.rollback()
                conn.close()
                raise ValueError("ability_not_owned")
        state["ability_choices"][user_key] = ability_key
        advanced = len(state["ability_choices"]) == len(state["players"])
        if advanced:
            if "reroll_arena" in state["ability_choices"].values():
                self._store_arena_snapshot(state, self._random_arena(exclude=state["arena"]), replaced=True)
            for actor_id in state["players"]:
                selected = state["ability_choices"].get(str(actor_id), "skip")
                effect = ABILITY_DEFINITIONS.get(selected, {}).get("effect", {})
                if effect.get("type") == "lock_stat":
                    target = next(pid for pid in state["players"] if pid != actor_id)
                    state["locked_stats"][str(target)].append(effect["stat"])
            state["phase"] = "stat_selection"
            state["deadline"] = _iso(_now() + timedelta(seconds=QUICK_CHOICE_TTL_SECONDS))
        self._save_state(conn, request_id, state)
        conn.commit()
        conn.close()
        return state, advanced

    def allowed_quick_stats(self, state: Dict[str, Any], user_id: int) -> List[str]:
        arena = self.arena_for_state(state)
        blocked = set(arena.get("disabled_stats", []))
        blocked.update(state.get("locked_stats", {}).get(str(user_id), []))
        return [stat for stat in CORE_STATS if stat not in blocked]

    def quick_stat_preview(self, state: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Return the exact Quick values a player will use during resolution."""
        players = state.get("players", [])
        if user_id not in players or len(players) != 2:
            raise ValueError("invalid_quick_player")

        opponent_id = next(player_id for player_id in players if player_id != user_id)
        card_id = state.get("cards", {}).get(str(user_id))
        opponent_card_id = state.get("cards", {}).get(str(opponent_id))
        if not card_id or not opponent_card_id:
            raise ValueError("quick_card_not_selected")

        card = self.db.get_card_by_id_for_player(card_id, user_id) or self.db.get_card_by_id(card_id)
        opponent_card = (
            self.db.get_card_by_id_for_player(opponent_card_id, opponent_id)
            or self.db.get_card_by_id(opponent_card_id)
        )
        if card is None or opponent_card is None:
            raise ValueError("card_not_found")

        arena = self.arena_for_state(state)
        base_values = {stat: int(getattr(card, stat)) for stat in CORE_STATS}
        final_values = dict(base_values)
        card_type = normalize_quick_card_type(getattr(card, "card_type", None))
        applied_arena_effects = []
        for effect in arena.get("effects", []):
            if effect.get("card_type") != card_type:
                continue
            stat = effect.get("stat")
            if stat not in CORE_STATS:
                continue
            delta = int(effect.get("delta", 0))
            final_values[stat] += delta
            applied_arena_effects.append({
                "card_type": card_type,
                "stat": stat,
                "delta": delta,
            })

        passive = self._apply_passive(card, opponent_card, arena, final_values)
        opponent_ability = state.get("ability_choices", {}).get(str(opponent_id), "skip")
        ability_effect = ABILITY_DEFINITIONS.get(opponent_ability, {}).get("effect", {})
        applied_ability = None
        if ability_effect.get("type") == "weaken_stat":
            target_stat = ability_effect["stat"]
            delta = int(ability_effect.get("delta", -2))
            final_values[target_stat] += delta
            applied_ability = {"ability": opponent_ability, "stat": target_stat, "delta": delta}

        return {
            "card_id": card.card_id,
            "card_name": card.name,
            "card_type": card_type,
            "base_values": base_values,
            "final_values": final_values,
            "arena_effects": applied_arena_effects,
            "passive": passive,
            "opponent_ability_effect": applied_ability,
        }

    def select_quick_stat(self, request_id: str, user_id: int, stat: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            raise ValueError("state_not_found")
        state = _loads(row[0], {})
        if state.get("phase") != "stat_selection" or user_id not in state.get("players", []):
            conn.rollback()
            conn.close()
            raise ValueError("invalid_phase_or_player")
        key = str(user_id)
        if key in state["stat_choices"]:
            conn.rollback()
            conn.close()
            raise ValueError("choice_locked")
        if stat not in self.allowed_quick_stats(state, user_id):
            conn.rollback()
            conn.close()
            raise ValueError("stat_not_allowed")
        state["stat_choices"][key] = stat
        completed = len(state["stat_choices"]) == len(state["players"])
        self._save_state(conn, request_id, state)
        conn.commit()
        conn.close()
        if not completed:
            return state, None
        return self.get_state(request_id), self.resolve_quick(request_id)

    def set_card_metadata(
        self,
        card_id: str,
        traits: Optional[Iterable[str]] = None,
        series: Optional[str] = None,
        hidden_stats: Optional[Dict[str, int]] = None,
        passive: Optional[Dict[str, Any]] = None,
    ) -> None:
        passive_value = passive or {}
        condition = passive_value.get("condition") or {} if isinstance(passive_value, dict) else {}
        arena_id = condition.get("arena") if isinstance(condition, dict) else None
        if arena_id and not self.arena_registry.arena_exists_for_mode(str(arena_id), "quick", include_draft=True):
            raise ValueError("passive_arena_not_found")
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO card_mode_metadata(card_id, traits, series, hidden_stats, passive)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                traits=excluded.traits,
                series=excluded.series,
                hidden_stats=excluded.hidden_stats,
                passive=excluded.passive
            """,
            (
                card_id,
                json.dumps(list(traits or []), ensure_ascii=False),
                series,
                json.dumps(hidden_stats or {}, ensure_ascii=False),
                json.dumps(passive_value, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

    def get_card_metadata(self, card_id: str, rarity: Optional[str] = None) -> Dict[str, Any]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM card_mode_metadata WHERE card_id=?", (card_id,)
        ).fetchone()
        conn.close()
        if not row:
            metadata = {"card_id": card_id, "traits": [], "series": None, "hidden_stats": {}, "passive": {}}
        else:
            metadata = {
            "card_id": card_id,
            "traits": _loads(row["traits"], []),
            "series": row["series"],
            "hidden_stats": _loads(row["hidden_stats"], {}),
            "passive": _loads(row["passive"], {}),
            }
        # Passive is form-specific; story-oriented mode metadata remains shared.
        if rarity and hasattr(self.db, "get_card_variant"):
            variant = self.db.get_card_variant(card_id, rarity)
            if variant and variant.get("passive"):
                metadata["passive"] = variant["passive"]
        return metadata

    def calculate_deck_synergy(self, card_ids: Iterable[str]) -> Dict[str, Any]:
        """Calculate the initial, data-driven deck-construction bonuses.

        The product document leaves the complete bonus catalog for a later
        balancing pass.  These rules implement its concrete examples without
        coupling them to card rarity.
        """
        cards = [self.db.get_card_by_id(card_id) for card_id in card_ids]
        cards = [card for card in cards if card]
        metadata = [self.get_card_metadata(card.card_id) for card in cards]
        score = 0
        reasons: List[str] = []

        series_counts: Dict[str, int] = {}
        for item in metadata:
            series = (item.get("series") or "").strip()
            if series:
                series_counts[series] = series_counts.get(series, 0) + 1
        for series, count in series_counts.items():
            if count >= 3:
                score += 4
                reasons.append(f"سه کارت از {series}: +4")
            elif count == 2:
                score += 2
                reasons.append(f"دو کارت از {series}: +2")

        if len(cards) == 3:
            dominant = []
            for card in cards:
                values = {stat: int(getattr(card, stat)) for stat in CORE_STATS}
                dominant.append(max(CORE_STATS, key=lambda stat: values[stat]))
            if len(set(dominant)) == 1:
                score += 3
                reasons.append(f"سه کارت {dominant[0]} محور: +3")

            common_traits = None
            for item in metadata:
                traits = {trait.casefold(): trait for trait in item.get("traits", [])}
                common_traits = traits if common_traits is None else {
                    key: common_traits[key] for key in common_traits.keys() & traits.keys()
                }
            if common_traits:
                trait = next(iter(common_traits.values()))
                score += 3
                reasons.append(f"سه کارت با ویژگی {bidi_isolate(trait)}: +3")

        return {"score": score, "reasons": reasons}

    def _apply_passive(
        self,
        card,
        opponent_card,
        arena: Dict[str, Any],
        values: Dict[str, int],
    ) -> Optional[Dict[str, Any]]:
        if not arena.get("passives_enabled", True):
            return None
        rarity = getattr(getattr(card, "rarity", None), "value", getattr(card, "rarity", None))
        metadata = self.get_card_metadata(card.card_id, rarity)
        passive = metadata.get("passive") or {}
        condition = passive.get("condition") or {}
        effect = passive.get("effect") or {}
        if not condition or effect.get("stat") not in CORE_STATS:
            return None
        matches = True
        if condition.get("arena") and condition["arena"] != arena["id"]:
            matches = False
        if condition.get("opponent_name") and condition["opponent_name"].casefold() != opponent_card.name.casefold():
            matches = False
        if condition.get("opponent_trait"):
            opponent_traits = self.get_card_metadata(opponent_card.card_id).get("traits", [])
            if condition["opponent_trait"].casefold() not in {t.casefold() for t in opponent_traits}:
                matches = False
        if not matches:
            return None
        stat = effect["stat"]
        delta = int(effect.get("delta", 0))
        values[stat] += delta
        return {"name": passive.get("name", "Passive"), "stat": stat, "delta": delta}

    def resolve_quick(self, request_id: str) -> Dict[str, Any]:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)).fetchone()
                state = _loads(row[0], {}) if row else None
                if state and state.get("phase") == "completed":
                    return state["report"]
                if not state or state.get("phase") != "stat_selection":
                    raise ValueError("quick_not_ready")
                if len(state.get("stat_choices", {})) != len(state.get("players", [])):
                    raise ValueError("quick_not_ready")
                players = state["players"]
                arena = self.arena_for_state(state)
                previews = {user_id: self.quick_stat_preview(state, user_id) for user_id in players}
                breakdown: Dict[str, Any] = {}
                for user_id in players:
                    preview = previews[user_id]
                    selected_stat = state["stat_choices"][str(user_id)]
                    opponent_id = next(player_id for player_id in players if player_id != user_id)
                    opponent_stat = state["stat_choices"][str(opponent_id)]
                    # Matches started before this rule was deployed finish under their original rule.
                    scored_stats = (
                        [selected_stat, opponent_stat]
                        if state.get("scoring_rule") == "sum_selected_stats_v1"
                        else [selected_stat]
                    )
                    base_components = [preview["base_values"][stat] for stat in scored_stats]
                    final_components = [preview["final_values"][stat] for stat in scored_stats]
                    item = {
                        "card_id": preview["card_id"],
                        "card_name": preview["card_name"],
                        "card_type": preview["card_type"],
                        "selected_stat": selected_stat,
                        "base_value": sum(base_components),
                        "final_value": sum(final_components),
                        "all_final_values": preview["final_values"],
                        "arena_effects": preview["arena_effects"],
                        "passive": preview["passive"],
                        "opponent_ability_effect": preview["opponent_ability_effect"],
                        "ability_used": state["ability_choices"].get(str(user_id), "skip"),
                    }
                    if state.get("scoring_rule") == "sum_selected_stats_v1":
                        item.update({"opponent_selected_stat": opponent_stat,
                                     "scored_stats": scored_stats, "base_components": base_components,
                                     "final_components": final_components})
                    breakdown[str(user_id)] = item
                first, second = players
                first_value = breakdown[str(first)]["final_value"]
                second_value = breakdown[str(second)]["final_value"]
                winner_id = first if first_value > second_value else second if second_value > first_value else None
                report = {
                    "request_id": request_id,
                    "mode": "quick",
                    "players": players,
                    "winner_id": winner_id,
                    "is_tie": winner_id is None,
                    "initial_arena": state["initial_arena"],
                    "initial_arena_data": state.get("initial_arena_snapshot"),
                    "arena": state["arena"],
                    "arena_data": arena,
                    "breakdown": breakdown,
                    "completed_at": _iso(_now()),
                }
                state["phase"] = "completed"
                state["report"] = report
                self._save_state(conn, request_id, state)
                conn.execute(
                    "UPDATE game_requests SET status='completed', updated_at=? WHERE request_id=?",
                    (_iso(_now()), request_id),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO game_match_reports(request_id, report_json, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (request_id, json.dumps(report, ensure_ascii=False), _iso(_now())),
                )
                return report

    def forfeit_quick(
        self, request_id: str, loser_ids: Iterable[int], reason: str = "timeout"
    ) -> Dict[str, Any]:
        """Finish an unfinished Quick match when a required choice times out."""
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)).fetchone()
                state = _loads(row[0], {}) if row else None
                if not state or state.get("phase") == "completed":
                    raise ValueError("quick_not_active")
                if reason in ("card_selection_timeout", "stat_selection_timeout"):
                    expected_phase = reason.removesuffix("_timeout")
                    if state.get("phase") != expected_phase or datetime.fromisoformat(state["deadline"]) > _now():
                        raise ValueError("quick_timeout_stale")
                    choice_key = "cards" if expected_phase == "card_selection" else "stat_choices"
                    loser_ids = [uid for uid in state["players"] if str(uid) not in state.get(choice_key, {})]
                    if not loser_ids:
                        raise ValueError("quick_timeout_stale")
                losers = {int(user_id) for user_id in loser_ids}
                players = [int(user_id) for user_id in state.get("players", [])]
                eligible_winners = [user_id for user_id in players if user_id not in losers]
                winner_id = eligible_winners[0] if len(eligible_winners) == 1 else None
                report = {
                    "request_id": request_id,
                    "mode": "quick",
                    "players": players,
                    "winner_id": winner_id,
                    "is_tie": winner_id is None,
                    "forfeit": True,
                    "loser_ids": sorted(losers),
                    "reason": reason,
                    "initial_arena": state.get("initial_arena"),
                    "arena": state.get("arena"),
                    "breakdown": {},
                    "completed_at": _iso(_now()),
                }
                state["phase"] = "completed"
                state["report"] = report
                self._save_state(conn, request_id, state)
                conn.execute(
                    "UPDATE game_requests SET status='completed', updated_at=? WHERE request_id=?",
                    (_iso(_now()), request_id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO game_match_reports VALUES (?, ?, ?)",
                    (request_id, json.dumps(report, ensure_ascii=False), _iso(_now())),
                )
                return report

    def get_report(self, request_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT report_json FROM game_match_reports WHERE request_id=?", (request_id,)
        ).fetchone()
        conn.close()
        return _loads(row[0], {}) if row else None

    # -------------------- Easy mode --------------------

    def create_easy_lobby(self, creator_id: int, chat_id: int, rounds: int) -> Dict[str, Any]:
        if rounds not in (1, 3, 5, 10):
            raise ValueError("invalid_round_count")
        conn = self._connect()
        request = self._insert_request(
            conn,
            creator_id,
            "easy",
            "group",
            "easy_lobby",
            EASY_LOBBY_TTL_SECONDS,
            origin_chat_id=chat_id,
            rounds=rounds,
        )
        state = {
            "mode": "easy",
            "phase": "lobby",
            "players": [creator_id],
            "rounds": rounds,
            "current_round": 0,
            "scores": {str(creator_id): 0},
            "question": None,
            "choices": {},
            "options": {},
            "round_history": [],
        }
        self._save_state(conn, request["request_id"], state)
        conn.commit()
        conn.close()
        return request

    def join_easy_lobby(self, request_id: str, user_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        request = conn.execute(
            "SELECT * FROM game_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        state_row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not request or not state_row:
            conn.rollback()
            conn.close()
            return False, "not_found", {}
        state = _loads(state_row[0], {})
        if request["status"] != "waiting" or request["expires_at"] <= _iso(_now()) or state.get("phase") != "lobby":
            conn.rollback()
            conn.close()
            return False, "expired", state
        if user_id in state["players"]:
            conn.rollback()
            conn.close()
            return True, "already_ready", state
        state["players"].append(user_id)
        state["scores"][str(user_id)] = 0
        self._save_state(conn, request_id, state)
        conn.commit()
        conn.close()
        return True, "joined", state

    def start_easy_match(self, request_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        request = conn.execute(
            "SELECT * FROM game_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        state_row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not request or not state_row:
            conn.rollback()
            conn.close()
            return False, "not_found", {}
        state = _loads(state_row[0], {})
        if state.get("phase") != "lobby":
            conn.rollback()
            conn.close()
            return False, "already_started", state
        if len(state["players"]) < 2:
            conn.execute(
                "UPDATE game_requests SET status='expired', updated_at=? WHERE request_id=?",
                (_iso(_now()), request_id),
            )
            conn.commit()
            conn.close()
            return False, "not_enough_players", state
        state["current_round"] = 1
        state["phase"] = "selection"
        state["question"] = self._choose_easy_question(state["players"])
        state["deadline"] = _iso(_now() + timedelta(seconds=EASY_CHOICE_TTL_SECONDS))
        self._save_state(conn, request_id, state)
        conn.execute(
            "UPDATE game_requests SET status='active', updated_at=? WHERE request_id=?",
            (_iso(_now()), request_id),
        )
        conn.commit()
        conn.close()
        return True, "started", state

    def _easy_question_pool(self, players: Iterable[int]) -> List[Dict[str, Any]]:
        """Build safe simple/composite questions for the current collections."""
        per_player_traits = []
        per_player_series = []
        display_traits: Dict[str, str] = {}
        display_series: Dict[str, str] = {}
        for user_id in players:
            traits = set()
            series_values = set()
            for card in self.db.get_player_cards(user_id):
                metadata = self.get_card_metadata(card.card_id)
                for trait in metadata.get("traits", []):
                    key = str(trait).strip().casefold()
                    if key:
                        traits.add(key)
                        display_traits.setdefault(key, str(trait).strip())
                series = str(metadata.get("series") or "").strip()
                if series:
                    key = series.casefold()
                    series_values.add(key)
                    display_series.setdefault(key, series)
            per_player_traits.append(traits)
            per_player_series.append(series_values)

        common_traits = set.intersection(*per_player_traits) if per_player_traits else set()
        common_series = set.intersection(*per_player_series) if per_player_series else set()
        composite = []
        for key in sorted(common_traits):
            label = display_traits[key]
            composite.append(
                {
                    "id": f"trait:{key}:iq",
                    "text": f"باهوش‌ترین شخصیت با ویژگی {bidi_isolate(label)} کیست؟",
                    "attribute": "iq",
                    "trait": label,
                }
            )
        for key in sorted(common_series):
            label = display_series[key]
            composite.append(
                {
                    "id": f"series:{key}:popularity",
                    "text": f"محبوب‌ترین شخصیت از مجموعه {bidi_isolate(label)} کیست؟",
                    "attribute": "popularity",
                    "series": label,
                }
            )
        return [*EASY_QUESTIONS, *composite]

    def _choose_easy_question(
        self, players: Iterable[int], previous_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pool = self._easy_question_pool(players)
        choices = [question for question in pool if question["id"] != previous_id]
        return random.choice(choices or pool)

    def _hidden_stat_value(self, card, attribute: str) -> int:
        metadata = self.get_card_metadata(card.card_id)
        authored = metadata.get("hidden_stats", {})
        if attribute in authored:
            return max(1, min(100, int(authored[attribute])))
        if attribute in CORE_STATS:
            return int(getattr(card, attribute))
        digest = hashlib.sha256(f"{card.card_id}:{attribute}".encode("utf-8")).digest()
        return 25 + (int.from_bytes(digest[:2], "big") % 76)

    def get_easy_options(self, request_id: str, user_id: int) -> List[Any]:
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return []
        state = _loads(row[0], {})
        if state.get("phase") != "selection" or user_id not in state.get("players", []):
            conn.rollback()
            conn.close()
            return []
        key = str(user_id)
        cards = self.db.get_player_cards(user_id)
        if key in state["options"]:
            wanted = set(state["options"][key])
            conn.rollback()
            conn.close()
            return [card for card in cards if card.card_id in wanted]
        question = state["question"]
        trait = question.get("trait")
        series = question.get("series")
        if trait or series:
            eligible = []
            for card in cards:
                metadata = self.get_card_metadata(card.card_id)
                trait_ok = not trait or trait.casefold() in {t.casefold() for t in metadata.get("traits", [])}
                series_ok = not series or (metadata.get("series") or "").casefold() == series.casefold()
                if trait_ok and series_ok:
                    eligible.append(card)
            cards = eligible
        else:
            cards = random.sample(cards, min(5, len(cards))) if cards else []
        state["options"][key] = [card.card_id for card in cards]
        self._save_state(conn, request_id, state)
        conn.commit()
        conn.close()
        return cards

    def select_easy_card(self, request_id: str, user_id: int, card_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        # Build/persist the personal option list before taking the state lock.
        options = {card.card_id for card in self.get_easy_options(request_id, user_id)}
        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state_json FROM game_match_states WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return False, "not_found", {}
        state = _loads(row[0], {})
        key = str(user_id)
        if state.get("phase") != "selection" or user_id not in state.get("players", []):
            conn.rollback()
            conn.close()
            return False, "invalid_phase", state
        if key in state["choices"]:
            conn.rollback()
            conn.close()
            return False, "choice_locked", state
        if card_id not in options:
            conn.rollback()
            conn.close()
            return False, "card_not_allowed", state
        state["choices"][key] = card_id
        all_selected = len(state["choices"]) == len(state["players"])
        self._save_state(conn, request_id, state)
        conn.commit()
        conn.close()
        return True, "all_selected" if all_selected else "selected", state

    def resolve_easy_round(self, request_id: str) -> Dict[str, Any]:
        state = self.get_state(request_id)
        if not state or state.get("phase") != "selection":
            raise ValueError("easy_round_not_ready")
        attribute = state["question"]["attribute"]
        entries = []
        for user_id in state["players"]:
            card_id = state["choices"].get(str(user_id))
            if not card_id:
                continue
            card = self.db.get_card_by_id(card_id)
            if card:
                entries.append(
                    {
                        "user_id": user_id,
                        "card_id": card_id,
                        "card_name": card.name,
                        "hidden_value": self._hidden_stat_value(card, attribute),
                    }
                )
        entries.sort(key=lambda item: item["hidden_value"], reverse=True)
        distinct_values = []
        for item in entries:
            if item["hidden_value"] not in distinct_values:
                distinct_values.append(item["hidden_value"])
        awards = (3, 2, 1)
        for item in entries:
            rank_index = distinct_values.index(item["hidden_value"])
            item["points"] = awards[rank_index] if rank_index < len(awards) else 0
            state["scores"][str(item["user_id"])] += item["points"]
        round_result = {
            "round": state["current_round"],
            "question": state["question"],
            "entries": entries,
        }
        state["round_history"].append(round_result)
        completed = state["current_round"] >= state["rounds"]
        if completed:
            state["phase"] = "completed"
            top_score = max(state["scores"].values()) if state["scores"] else 0
            winners = [int(uid) for uid, score in state["scores"].items() if score == top_score]
            report = {
                "request_id": request_id,
                "mode": "easy",
                "scores": state["scores"],
                "winner_ids": winners,
                "round_history": state["round_history"],
                "completed_at": _iso(_now()),
            }
            state["report"] = report
        else:
            state["current_round"] += 1
            previous_id = state["question"]["id"]
            state["question"] = self._choose_easy_question(state["players"], previous_id)
            state["choices"] = {}
            state["options"] = {}
            state["deadline"] = _iso(_now() + timedelta(seconds=EASY_CHOICE_TTL_SECONDS))
            report = None

        conn = self._connect()
        conn.execute("BEGIN IMMEDIATE")
        self._save_state(conn, request_id, state)
        if completed:
            conn.execute(
                "UPDATE game_requests SET status='completed', updated_at=? WHERE request_id=?",
                (_iso(_now()), request_id),
            )
            conn.execute(
                "INSERT OR REPLACE INTO game_match_reports VALUES (?, ?, ?)",
                (request_id, json.dumps(report, ensure_ascii=False), _iso(_now())),
            )
        conn.commit()
        conn.close()
        return {"round": round_result, "state": state, "completed": completed, "report": report}
