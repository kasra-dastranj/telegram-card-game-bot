"""Versioned, database-backed arena registry.

The registry deliberately keeps all executable arena rules in a small, validated
schema.  It is the boundary between the admin panel and gameplay engines: the
panel never gives a game engine arbitrary JSON or source code, and a match only
uses an immutable snapshot created at match start.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

CORE_STATS: Tuple[str, ...] = ("power", "speed", "iq", "popularity")
MODE_KEYS: Tuple[str, ...] = ("quick", "three_round", "deck")
PLATFORMS: Tuple[str, ...] = ("telegram", "miniapp")
ARENA_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,23}$")
SCHEMA_VERSION = 1
MAX_NAME_FA = 80
MAX_NAME_EN = 100
MAX_DESCRIPTION_FA = 800
MAX_EMOJI = 16
MAX_TAGS = 12
MAX_TAG_LENGTH = 32


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def normalise_utc(value: Any) -> Optional[str]:
    """Return an aware ISO timestamp in UTC or raise ValueError."""
    if value in (None, ""):
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _legacy_seed() -> Dict[str, Dict[str, Any]]:
    """Exact production-compatible definitions, kept until the two-release cleanup.

    They intentionally mirror the existing Quick and three-round constants.  The
    migration is idempotent and never overwrites a published version.
    """
    quick = {
        "city": ("شهر", "City", "🏙️", [{"card_type": "power", "stat": "power", "delta": 1}, {"card_type": "iq", "stat": "iq", "delta": 1}], [], True, True),
        "desert": ("بیابان", "Desert", "🏜️", [{"card_type": "power", "stat": "power", "delta": 2}, {"card_type": "speed", "stat": "speed", "delta": -1}], [], True, True),
        "ice": ("یخبندان", "Ice", "❄️", [{"card_type": "speed", "stat": "speed", "delta": -2}, {"card_type": "iq", "stat": "iq", "delta": 1}], [], True, True),
        "forest": ("جنگل", "Forest", "🌲", [{"card_type": "iq", "stat": "iq", "delta": 1}, {"card_type": "popularity", "stat": "popularity", "delta": -1}], [], True, True),
        "silent_temple": ("معبد خاموش", "Silent Temple", "🏛️", [{"card_type": "iq", "stat": "iq", "delta": 2}], ["speed"], False, True),
        "null_zone": ("منطقه خنثی", "Null Zone", "🌌", [], [], True, False),
    }
    three = {
        "power_arena": ("عرصه قدرت", "Power Arena", "⚡", "power", 8, [["god", "monster"], ["hero", "warrior"], ["villain"]]),
        "speed_track": ("پیست سرعت", "Speed Track", "🏃", "speed", 8, [["assassin"], ["hero", "warrior"], ["funny"]]),
        "thinking_room": ("اتاق فکر", "Thinking Room", "🧠", "iq", 8, [["detective", "mage"], ["leader", "assassin"], ["hero"]]),
        "stage": ("صحنه", "Stage", "⭐", "popularity", 8, [["hero", "funny"], ["leader", "villain"], ["monster"]]),
    }
    payload: Dict[str, Dict[str, Any]] = {}
    for arena_id, (name_fa, name_en, emoji, effects, disabled, abilities, passives) in quick.items():
        payload[arena_id] = {
            "name_fa": name_fa, "name_en": name_en, "description_fa": "", "emoji": emoji,
            "profiles": {"quick": {"enabled": True, "selection_weight": 100, "rules": {
                "effects": [{"type": "stat_modifier", "condition": {"card_type": item["card_type"]}, "target_stat": item["stat"], "delta": item["delta"], "priority": index}
                            for index, item in enumerate(effects)],
                "disabled_stats": disabled, "abilities_enabled": abilities, "passives_enabled": passives,
            }}},
        }
    for arena_id, (name_fa, name_en, emoji, stat, amount, traits) in three.items():
        item = payload.setdefault(arena_id, {"name_fa": name_fa, "name_en": name_en, "description_fa": "", "emoji": emoji, "profiles": {}})
        rules = {"boost_stat": stat, "boost_amount": amount, "requires_card_type_match": True, "compare_stat": stat, "trait_ranks": traits}
        item["profiles"]["three_round"] = {"enabled": True, "selection_weight": 100, "rules": rules}
        item["profiles"]["deck"] = {"enabled": True, "selection_weight": 100, "rules": {"compare_stat": stat, "trait_ranks": traits, "stat_tiebreak_enabled": True}}
    return payload


def ensure_arena_registry_schema(conn: sqlite3.Connection) -> None:
    """Create additive registry tables and additive snapshot columns."""
    cursor = conn.cursor()
    cursor.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS arenas (
            arena_id TEXT PRIMARY KEY,
            lifecycle_status TEXT NOT NULL DEFAULT 'draft_only' CHECK(lifecycle_status IN ('draft_only','published','archived')),
            current_published_version INTEGER,
            created_at TEXT NOT NULL,
            created_by TEXT,
            updated_at TEXT NOT NULL,
            updated_by TEXT
        );
        CREATE TABLE IF NOT EXISTS arena_versions (
            arena_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            version_status TEXT NOT NULL CHECK(version_status IN ('draft','published','superseded')),
            draft_revision INTEGER NOT NULL DEFAULT 1,
            name_fa TEXT NOT NULL,
            name_en TEXT,
            description_fa TEXT NOT NULL DEFAULT '',
            emoji TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            rule_schema_version INTEGER NOT NULL DEFAULT 1,
            content_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            created_by TEXT,
            published_at TEXT,
            published_by TEXT,
            PRIMARY KEY(arena_id, version),
            FOREIGN KEY(arena_id) REFERENCES arenas(arena_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_one_draft
            ON arena_versions(arena_id) WHERE version_status='draft';
        CREATE TABLE IF NOT EXISTS arena_mode_profiles (
            arena_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            mode_key TEXT NOT NULL CHECK(mode_key IN ('quick','three_round','deck')),
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            selection_weight INTEGER NOT NULL DEFAULT 100,
            active_from TEXT,
            active_until TEXT,
            rules_json TEXT NOT NULL DEFAULT '{}',
            rules_hash TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(arena_id, version, mode_key),
            FOREIGN KEY(arena_id, version) REFERENCES arena_versions(arena_id, version)
        );
        CREATE TABLE IF NOT EXISTS arena_platform_settings (
            arena_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('telegram','miniapp')),
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            presentation_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(arena_id, version, platform),
            FOREIGN KEY(arena_id, version) REFERENCES arena_versions(arena_id, version)
        );
        CREATE TABLE IF NOT EXISTS arena_media (
            media_id TEXT PRIMARY KEY,
            arena_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('telegram','miniapp')),
            media_kind TEXT NOT NULL CHECK(media_kind IN ('background','photo','sticker','thumbnail')),
            storage_path TEXT,
            telegram_file_id TEXT,
            mime_type TEXT NOT NULL DEFAULT '',
            width INTEGER,
            height INTEGER,
            byte_size INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL DEFAULT '',
            readiness_status TEXT NOT NULL DEFAULT 'pending' CHECK(readiness_status IN ('pending','ready','failed','retired')),
            created_at TEXT NOT NULL,
            created_by TEXT,
            FOREIGN KEY(arena_id, version) REFERENCES arena_versions(arena_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_arena_media_lookup ON arena_media(arena_id, version, platform, media_kind, readiness_status);
        CREATE TABLE IF NOT EXISTS arena_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arena_id TEXT NOT NULL,
            version INTEGER,
            action TEXT NOT NULL,
            actor_id TEXT,
            request_id TEXT,
            before_json TEXT,
            after_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS arena_registry_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    for table, column, definition in (
        ("active_fights", "arena_version", "INTEGER"), ("active_fights", "arena_snapshot", "TEXT"),
        ("battle_states", "arena_version", "INTEGER"), ("battle_states", "arena_snapshot", "TEXT"),
        ("battle_states", "arena_history", "TEXT DEFAULT '[]'"),
        ("solo_fights", "arena_version", "INTEGER"), ("solo_fights", "arena_snapshot", "TEXT"),
    ):
        exists = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            continue
        columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    cursor.execute("INSERT OR IGNORE INTO arena_registry_meta(meta_key, meta_value, updated_at) VALUES ('registry_version','0',?)", (utc_now(),))


class ArenaValidationError(ValueError):
    def __init__(self, issues: Sequence[Mapping[str, str]]):
        super().__init__("arena_validation_failed")
        self.issues = [dict(issue) for issue in issues]


class ArenaRegistry:
    def __init__(self, db_or_path: Any):
        self.db_path = str(getattr(db_or_path, "db_path", db_or_path))
        self.seed_report = self.seed_legacy_arenas()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(json_dumps(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _issue(path: str, code: str, message_fa: str, severity: str = "error") -> Dict[str, str]:
        return {"severity": severity, "path": path, "code": code, "message_fa": message_fa}

    def validate_payload(self, arena_id: str, payload: Mapping[str, Any], publishing: bool = False) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        if not isinstance(payload, Mapping):
            return [self._issue("payload", "payload_invalid", "ساختار اطلاعات زمین نامعتبر است.")]
        if not ARENA_ID_RE.fullmatch(str(arena_id or "")):
            issues.append(self._issue("arena_id", "arena_id_invalid", "شناسه زمین باید ۳ تا ۲۴ نویسه، انگلیسی و snake_case باشد."))
        name_fa = str(payload.get("name_fa") or "").strip()
        name_en = str(payload.get("name_en") or "").strip()
        description = str(payload.get("description_fa") or "").strip()
        emoji = str(payload.get("emoji") or "").strip()
        if not name_fa:
            issues.append(self._issue("name_fa", "name_required", "نام فارسی زمین الزامی است."))
        elif len(name_fa) > MAX_NAME_FA:
            issues.append(self._issue("name_fa", "name_too_long", "نام فارسی حداکثر ۸۰ نویسه است."))
        if len(name_en) > MAX_NAME_EN:
            issues.append(self._issue("name_en", "name_too_long", "نام انگلیسی حداکثر ۱۰۰ نویسه است."))
        if len(description) > MAX_DESCRIPTION_FA:
            issues.append(self._issue("description_fa", "description_too_long", "توضیح زمین حداکثر ۸۰۰ نویسه است."))
        if len(emoji) > MAX_EMOJI:
            issues.append(self._issue("emoji", "emoji_too_long", "نماد زمین بیش از حد طولانی است."))
        if publishing and not description:
            issues.append(self._issue("description_fa", "description_required", "توضیح فارسی برای انتشار الزامی است."))
        tags = payload.get("tags", [])
        if not isinstance(tags, list) or len(tags) > MAX_TAGS or any(not str(tag).strip() or len(str(tag).strip()) > MAX_TAG_LENGTH for tag in tags):
            issues.append(self._issue("tags", "tags_invalid", "حداکثر ۱۲ برچسب کوتاه و معتبر مجاز است."))
        profiles = payload.get("profiles") or {}
        if not isinstance(profiles, Mapping):
            return issues + [self._issue("profiles", "profiles_invalid", "پروفایل‌ها نامعتبرند.")]
        enabled_modes = 0
        for mode, profile in profiles.items():
            if mode not in MODE_KEYS or not isinstance(profile, Mapping):
                issues.append(self._issue(f"profiles.{mode}", "invalid_mode_profile", "پروفایل مود نامعتبر است."))
                continue
            enabled = bool(profile.get("enabled"))
            enabled_modes += int(enabled)
            try:
                weight = int(profile.get("selection_weight", 100))
            except (ValueError, TypeError):
                weight = 0
            if enabled and not 1 <= weight <= 1000:
                issues.append(self._issue(f"profiles.{mode}.selection_weight", "invalid_weight", "وزن انتخاب باید بین ۱ تا ۱۰۰۰ باشد."))
            start = end = None
            for field in ("active_from", "active_until"):
                raw = profile.get(field)
                try:
                    parsed = normalise_utc(raw)
                    if field == "active_from": start = parsed
                    else: end = parsed
                except (TypeError, ValueError):
                    issues.append(self._issue(f"profiles.{mode}.{field}", "invalid_datetime", "زمان باید ISO-8601 و دارای منطقه زمانی باشد."))
            if start and end and end <= start:
                issues.append(self._issue(f"profiles.{mode}.active_until", "invalid_time_window", "پایان بازه باید پس از شروع باشد."))
            rules = profile.get("rules") or {}
            if not isinstance(rules, Mapping):
                issues.append(self._issue(f"profiles.{mode}.rules", "rules_invalid", "ساختار قواعد مود نامعتبر است."))
                continue
            if mode == "quick":
                disabled = rules.get("disabled_stats", [])
                if not isinstance(disabled, list) or any(stat not in CORE_STATS for stat in disabled):
                    issues.append(self._issue(f"profiles.{mode}.disabled_stats", "invalid_stat", "ویژگی غیرفعال نامعتبر است."))
                elif len(set(disabled)) >= len(CORE_STATS):
                    issues.append(self._issue(f"profiles.{mode}.disabled_stats", "all_stats_disabled", "حداقل یک ویژگی باید قابل انتخاب بماند."))
                effects = rules.get("effects", [])
                if not isinstance(effects, list):
                    issues.append(self._issue(f"profiles.{mode}.effects", "effects_invalid", "Effectها باید لیست باشند."))
                elif len(effects) > 12:
                    issues.append(self._issue(f"profiles.{mode}.effects", "effects_limit", "تعداد Effectها بیش از حد مجاز است."))
                else:
                    seen = set()
                    for index, effect in enumerate(effects):
                        path = f"profiles.quick.effects[{index}]"
                        if not isinstance(effect, Mapping):
                            issues.append(self._issue(path, "invalid_quick_effect", "Effect زمین Quick باید یک شیء باشد."))
                            continue
                        condition = effect.get("condition") or {}
                        if not isinstance(condition, Mapping):
                            issues.append(self._issue(f"{path}.condition", "invalid_condition", "شرط Effect نامعتبر است."))
                            continue
                        card_type = condition.get("card_type", effect.get("card_type"))
                        target = effect.get("target_stat", effect.get("stat"))
                        try: delta = int(effect.get("delta", 0))
                        except (TypeError, ValueError): delta = 999
                        if effect.get("type", "stat_modifier") != "stat_modifier" or card_type not in CORE_STATS or target not in CORE_STATS or not -10 <= delta <= 10:
                            issues.append(self._issue(path, "invalid_quick_effect", "Effect زمین Quick نامعتبر است."))
                        key = (card_type, target, delta)
                        if key in seen:
                            issues.append(self._issue(path, "duplicate_effect", "Effect تکراری است.", "warning"))
                        seen.add(key)
            elif mode == "three_round":
                stat = rules.get("boost_stat")
                compare = rules.get("compare_stat", stat)
                try: amount = int(rules.get("boost_amount", 0))
                except (TypeError, ValueError): amount = -1
                if stat not in CORE_STATS or compare not in CORE_STATS or not 0 <= amount <= 30:
                    issues.append(self._issue(f"profiles.{mode}.rules", "invalid_three_round_rules", "قواعد سه‌راندی نامعتبر است."))
                issues.extend(self._validate_trait_ranks(rules.get("trait_ranks", []), f"profiles.{mode}.trait_ranks"))
            elif mode == "deck":
                if rules.get("compare_stat") not in CORE_STATS:
                    issues.append(self._issue(f"profiles.{mode}.compare_stat", "invalid_stat", "ویژگی مقایسه Deck نامعتبر است."))
                issues.extend(self._validate_trait_ranks(rules.get("trait_ranks", []), f"profiles.{mode}.trait_ranks"))
        if publishing and enabled_modes == 0:
            issues.append(self._issue("profiles", "no_mode_enabled", "برای انتشار باید حداقل یک مود فعال باشد."))
        platform = payload.get("platform") or {}
        if not isinstance(platform, Mapping):
            issues.append(self._issue("platform", "platform_invalid", "تنظیمات پلتفرم باید یک شیء باشد."))
            return issues
        for key, config in platform.items():
            if key not in PLATFORMS or not isinstance(config, Mapping):
                issues.append(self._issue(f"platform.{key}", "platform_invalid", "تنظیمات پلتفرم نامعتبر است."))
        if publishing and not any(isinstance(platform.get(key), Mapping) and bool(platform[key].get("enabled")) for key in PLATFORMS):
            issues.append(self._issue("platform", "no_platform_enabled", "حداقل یک پلتفرم باید فعال باشد."))
        if publishing and isinstance(platform.get("telegram"), Mapping) and platform["telegram"].get("enabled") and not emoji:
            issues.append(self._issue("emoji", "telegram_emoji_required", "برای انتشار در تلگرام، نماد زمین الزامی است."))
        return issues

    def _validate_trait_ranks(self, ranks: Any, path: str) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        if not isinstance(ranks, list) or len(ranks) > 5:
            return [self._issue(path, "invalid_trait_ranks", "رتبه‌بندی Trait نامعتبر است.")]
        seen = set()
        for tier in ranks:
            if not isinstance(tier, list):
                issues.append(self._issue(path, "invalid_trait_ranks", "رتبه‌بندی Trait نامعتبر است.")); continue
            for trait in tier:
                normalized = str(trait).strip().casefold()
                if not normalized or normalized in seen:
                    issues.append(self._issue(path, "duplicate_trait", "هر Trait فقط یک‌بار می‌تواند رتبه داشته باشد."))
                seen.add(normalized)
        return issues

    def seed_legacy_arenas(self) -> Dict[str, int]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_arena_registry_schema(conn)
        conn.commit()
        created = skipped = different = 0
        try:
            conn.execute("BEGIN IMMEDIATE")
            for arena_id, payload in _legacy_seed().items():
                existing = conn.execute("SELECT current_published_version FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
                if existing:
                    if existing["current_published_version"]:
                        skipped += 1
                    else:
                        different += 1
                    continue
                now = utc_now()
                conn.execute("INSERT OR IGNORE INTO arenas(arena_id,lifecycle_status,current_published_version,created_at,created_by,updated_at,updated_by) VALUES (?, 'draft_only', NULL, ?, 'seed', ?, 'seed')", (arena_id, now, now))
                self._insert_version(conn, arena_id, 1, payload, "published", "seed", now)
                legacy_path = f"/miniapp-assets/arena-backgrounds/{arena_id}.webp"
                conn.execute("""INSERT OR IGNORE INTO arena_media(
                    media_id,arena_id,version,platform,media_kind,storage_path,mime_type,
                    byte_size,sha256,readiness_status,created_at,created_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    f"seed-{arena_id}-v1-bg", arena_id, 1, "miniapp", "background", legacy_path,
                    "image/webp", 0, self._hash(legacy_path), "ready", now, "seed",
                ))
                conn.execute("UPDATE arenas SET lifecycle_status='published', current_published_version=1, updated_at=?, updated_by='seed' WHERE arena_id=?", (now, arena_id))
                self._refresh_content_hash(conn, arena_id, 1)
                self._audit(conn, arena_id, 1, "seed", "seed", None, None, payload)
                created += 1
            if created:
                self._bump_version(conn)
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            conn.close()
        return {"created": created, "skipped": skipped, "different": different}

    def _insert_version(self, conn: sqlite3.Connection, arena_id: str, version: int, payload: Mapping[str, Any], status: str, actor_id: Any, now: Optional[str] = None) -> None:
        now = now or utc_now()
        profiles = payload.get("profiles") or {}
        platform = payload.get("platform") or {"telegram": {"enabled": True}, "miniapp": {"enabled": True}}
        immutable = {"name_fa": str(payload.get("name_fa") or "").strip(), "name_en": str(payload.get("name_en") or "").strip(), "description_fa": str(payload.get("description_fa") or "").strip(), "emoji": str(payload.get("emoji") or "").strip(), "tags": list(payload.get("tags") or []), "profiles": profiles, "platform": platform}
        content_hash = self._hash(immutable)
        conn.execute("""INSERT INTO arena_versions(arena_id,version,version_status,draft_revision,name_fa,name_en,description_fa,emoji,tags_json,rule_schema_version,content_hash,created_at,created_by,published_at,published_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (arena_id, version, status, 1, immutable["name_fa"], immutable["name_en"], immutable["description_fa"], immutable["emoji"], json_dumps(immutable["tags"]), SCHEMA_VERSION, content_hash, now, str(actor_id), now if status == "published" else None, str(actor_id) if status == "published" else None))
        for mode, profile in profiles.items():
            if mode not in MODE_KEYS: continue
            rules = self._normalise_rules(mode, profile.get("rules") or {})
            conn.execute("INSERT INTO arena_mode_profiles(arena_id,version,mode_key,enabled,selection_weight,active_from,active_until,rules_json,rules_hash) VALUES (?,?,?,?,?,?,?,?,?)", (arena_id, version, mode, int(bool(profile.get("enabled"))), int(profile.get("selection_weight", 100)), normalise_utc(profile.get("active_from")), normalise_utc(profile.get("active_until")), json_dumps(rules), self._hash(rules)))
        for target in PLATFORMS:
            config = platform.get(target) or {}
            conn.execute("INSERT INTO arena_platform_settings(arena_id,version,platform,enabled,presentation_json) VALUES (?,?,?,?,?)", (arena_id, version, target, int(bool(config.get("enabled"))), json_dumps({k:v for k,v in config.items() if k != "enabled"})))

    def _normalise_rules(self, mode: str, rules: Mapping[str, Any]) -> Dict[str, Any]:
        if mode == "quick":
            effects = []
            for index, effect in enumerate(rules.get("effects") or []):
                condition = effect.get("condition") or {"card_type": effect.get("card_type")}
                effects.append({"type": "stat_modifier", "condition": {"card_type": condition.get("card_type")}, "target_stat": effect.get("target_stat", effect.get("stat")), "delta": int(effect.get("delta", 0)), "priority": int(effect.get("priority", index))})
            return {"effects": sorted(effects, key=lambda value: value["priority"]), "disabled_stats": list(dict.fromkeys(rules.get("disabled_stats") or [])), "abilities_enabled": bool(rules.get("abilities_enabled", True)), "passives_enabled": bool(rules.get("passives_enabled", True))}
        if mode == "three_round":
            return {"boost_stat": rules.get("boost_stat"), "boost_amount": int(rules.get("boost_amount", 0)), "requires_card_type_match": bool(rules.get("requires_card_type_match", True)), "compare_stat": rules.get("compare_stat", rules.get("boost_stat")), "trait_ranks": [[str(trait).strip().casefold() for trait in tier] for tier in rules.get("trait_ranks", [])]}
        return {"compare_stat": rules.get("compare_stat"), "trait_ranks": [[str(trait).strip().casefold() for trait in tier] for tier in rules.get("trait_ranks", [])], "stat_tiebreak_enabled": bool(rules.get("stat_tiebreak_enabled", True))}

    def _content_material(self, conn: sqlite3.Connection, arena_id: str, version: int) -> Dict[str, Any]:
        data = self._read_version(conn, arena_id, version) or {}
        media = [dict(row) for row in conn.execute(
            """SELECT platform,media_kind,storage_path,telegram_file_id,mime_type,width,height,
                      byte_size,sha256,readiness_status
                 FROM arena_media WHERE arena_id=? AND version=?
                 ORDER BY platform,media_kind,media_id""",
            (arena_id, version),
        )]
        return {
            key: data.get(key)
            for key in ("name_fa", "name_en", "description_fa", "emoji", "tags", "profiles", "platform")
        } | {"media": media}

    def _refresh_content_hash(self, conn: sqlite3.Connection, arena_id: str, version: int) -> str:
        digest = self._hash(self._content_material(conn, arena_id, version))
        conn.execute(
            "UPDATE arena_versions SET content_hash=? WHERE arena_id=? AND version=?",
            (digest, arena_id, version),
        )
        return digest

    def _read_version(self, conn: sqlite3.Connection, arena_id: str, version: int) -> Optional[Dict[str, Any]]:
        row = conn.execute("SELECT * FROM arena_versions WHERE arena_id=? AND version=?", (arena_id, version)).fetchone()
        if not row: return None
        profiles = {}
        for profile in conn.execute("SELECT * FROM arena_mode_profiles WHERE arena_id=? AND version=?", (arena_id, version)):
            profiles[profile["mode_key"]] = {"enabled": bool(profile["enabled"]), "selection_weight": profile["selection_weight"], "active_from": profile["active_from"], "active_until": profile["active_until"], "rules": json_loads(profile["rules_json"], {})}
        platform = {}
        for item in conn.execute("SELECT * FROM arena_platform_settings WHERE arena_id=? AND version=?", (arena_id, version)):
            platform[item["platform"]] = {"enabled": bool(item["enabled"]), **json_loads(item["presentation_json"], {})}
        result = dict(row)
        result.update({"tags": json_loads(row["tags_json"], []), "profiles": profiles, "platform": platform})
        return result

    def get_version(self, arena_id: str, version: int) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try: return self._read_version(conn, arena_id, int(version))
        finally: conn.close()

    def get_published(self, arena_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT current_published_version FROM arenas WHERE arena_id=? AND lifecycle_status!='archived'", (arena_id,)).fetchone()
            return self._read_version(conn, arena_id, row[0]) if row and row[0] else None
        finally: conn.close()

    def get_current_version(self, arena_id: str) -> Optional[Dict[str, Any]]:
        """Return the current immutable version for admin/history, even if archived."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT current_published_version FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
            return self._read_version(conn, arena_id, row[0]) if row and row[0] else None
        finally:
            conn.close()

    def runtime(self, arena_id: str, mode: str, platform: str = "telegram", version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        data = self.get_version(arena_id, version) if version else self.get_published(arena_id)
        if not data or mode not in MODE_KEYS or platform not in PLATFORMS:
            return None
        if data.get("version_status") not in ("published", "superseded"):
            return None
        return self._runtime_from_data(data, mode, platform, require_enabled=True)

    def preview(self, arena_id: str, mode: str, platform: str = "telegram", version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Render an admin-only preview. Drafts never pass through gameplay runtime."""
        conn = self._connect()
        try:
            if version is None:
                row = conn.execute(
                    """SELECT version FROM arena_versions WHERE arena_id=?
                       ORDER BY CASE version_status WHEN 'draft' THEN 0 WHEN 'published' THEN 1 ELSE 2 END,
                                version DESC LIMIT 1""",
                    (arena_id,),
                ).fetchone()
                version = int(row[0]) if row else None
            data = self._read_version(conn, arena_id, int(version)) if version is not None else None
        finally:
            conn.close()
        if not data or mode not in MODE_KEYS or platform not in PLATFORMS:
            return None
        return self._runtime_from_data(data, mode, platform, require_enabled=False)

    def _runtime_from_data(self, data: Mapping[str, Any], mode: str, platform: str, require_enabled: bool) -> Optional[Dict[str, Any]]:
        profile = data["profiles"].get(mode)
        platform_config = data.get("platform", {}).get(platform)
        if not profile or not isinstance(platform_config, Mapping):
            return None
        if require_enabled and (not profile.get("enabled") or not platform_config.get("enabled")):
            return None
        media = self._background_for(data["arena_id"], data["version"], platform)
        rules = profile["rules"]
        result = {"id": data["arena_id"], "arena_id": data["arena_id"], "version": data["version"], "name": data["name_fa"], "name_fa": data["name_fa"], "name_en": data["name_en"], "description_fa": data["description_fa"], "emoji": data["emoji"], "mode": mode, "selection_weight": profile["selection_weight"], "rules": rules, "platform": data["platform"], "background_url": media.get("storage_path") if media else None}
        if mode == "quick":
            result.update({"effects": [{"card_type": effect["condition"]["card_type"], "stat": effect["target_stat"], "delta": effect["delta"]} for effect in rules["effects"]], "disabled_stats": rules["disabled_stats"], "abilities_enabled": rules["abilities_enabled"], "passives_enabled": rules["passives_enabled"]})
        else:
            result.update(rules)
        return result

    def _background_for(self, arena_id: str, version: int, platform: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM arena_media WHERE arena_id=? AND version=? AND platform=? AND media_kind='background' AND readiness_status='ready' ORDER BY created_at DESC, media_id DESC LIMIT 1", (arena_id, version, platform)).fetchone()
            return dict(row) if row else None
        finally: conn.close()

    def list_active(self, mode: str, platform: str, at_utc: Optional[str] = None) -> List[Dict[str, Any]]:
        if mode not in MODE_KEYS or platform not in PLATFORMS: return []
        try:
            now = normalise_utc(at_utc) if at_utc else utc_now()
        except (TypeError, ValueError):
            return []
        conn = self._connect()
        try:
            rows = conn.execute("""SELECT a.arena_id, a.current_published_version FROM arenas a
                JOIN arena_mode_profiles p ON p.arena_id=a.arena_id AND p.version=a.current_published_version AND p.mode_key=?
                JOIN arena_platform_settings s ON s.arena_id=a.arena_id AND s.version=a.current_published_version AND s.platform=?
                WHERE a.lifecycle_status='published' AND p.enabled=1 AND s.enabled=1
                  AND (p.active_from IS NULL OR p.active_from<=?) AND (p.active_until IS NULL OR p.active_until>?)""", (mode, platform, now, now)).fetchall()
            active = []
            for row in rows:
                runtime = self.runtime(row["arena_id"], mode, platform, row["current_published_version"])
                if not runtime: continue
                if platform == "miniapp" and not runtime.get("background_url"): continue
                active.append(runtime)
            return active
        finally: conn.close()

    def select_for_match(self, mode: str, platform: str = "telegram", exclude_ids: Optional[Iterable[str]] = None, rng: Optional[random.Random] = None) -> Optional[Dict[str, Any]]:
        pool = self.list_active(mode, platform)
        excluded = {str(value) for value in (exclude_ids or [])}
        candidates = [item for item in pool if item["arena_id"] not in excluded] or pool
        if not candidates:
            logger.error("arena_registry_empty_pool mode=%s platform=%s", mode, platform)
            return None
        chooser = rng or random
        total = sum(max(1, int(item.get("selection_weight", 1))) for item in candidates)
        pick = chooser.uniform(0, total)
        cursor = 0.0
        for item in candidates:
            cursor += max(1, int(item.get("selection_weight", 1)))
            if pick <= cursor: return item
        return candidates[-1]

    def snapshot_for_match(self, arena_id: str, mode: str, platform: str = "telegram", version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        runtime = self.runtime(arena_id, mode, platform, version)
        if not runtime: return None
        return {key: runtime.get(key) for key in ("arena_id", "version", "name_fa", "name_en", "description_fa", "emoji", "mode", "rules", "background_url", "effects", "disabled_stats", "abilities_enabled", "passives_enabled", "boost_stat", "boost_amount", "requires_card_type_match", "compare_stat", "trait_ranks", "stat_tiebreak_enabled") if key in runtime}

    def create_draft(self, arena_id: str, payload: Mapping[str, Any], actor_id: Any, request_id: Optional[str] = None) -> Dict[str, Any]:
        issues = [issue for issue in self.validate_payload(arena_id, payload) if issue["severity"] == "error"]
        if issues: raise ArenaValidationError(issues)
        conn = self._connect(); now = utc_now()
        try:
            conn.execute("BEGIN IMMEDIATE")
            exists = conn.execute("SELECT * FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
            if exists: raise ValueError("arena_id_locked")
            conn.execute("INSERT INTO arenas(arena_id,lifecycle_status,current_published_version,created_at,created_by,updated_at,updated_by) VALUES (?, 'draft_only', NULL, ?, ?, ?, ?)", (arena_id, now, str(actor_id), now, str(actor_id)))
            self._insert_version(conn, arena_id, 1, payload, "draft", actor_id, now)
            self._audit(conn, arena_id, 1, "create", actor_id, request_id, None, payload)
            conn.commit(); return self._read_version(conn, arena_id, 1) or {}
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

    def update_draft(self, arena_id: str, payload: Mapping[str, Any], actor_id: Any, expected_revision: int, request_id: Optional[str] = None) -> Dict[str, Any]:
        conn = self._connect(); now = utc_now()
        try:
            conn.execute("BEGIN IMMEDIATE")
            draft = conn.execute("SELECT * FROM arena_versions WHERE arena_id=? AND version_status='draft'", (arena_id,)).fetchone()
            if not draft: raise ValueError("draft_not_found")
            if int(draft["draft_revision"]) != int(expected_revision): raise ValueError("draft_conflict")
            issues = [issue for issue in self.validate_payload(arena_id, payload) if issue["severity"] == "error"]
            if issues: raise ArenaValidationError(issues)
            previous = self._read_version(conn, arena_id, draft["version"])
            conn.execute("DELETE FROM arena_mode_profiles WHERE arena_id=? AND version=?", (arena_id, draft["version"]))
            conn.execute("DELETE FROM arena_platform_settings WHERE arena_id=? AND version=?", (arena_id, draft["version"]))
            scratch = dict(payload); scratch.setdefault("tags", payload.get("tags") or [])
            self._insert_version_replacing(conn, arena_id, draft["version"], scratch, actor_id, now, int(expected_revision) + 1)
            self._audit(conn, arena_id, draft["version"], "update_draft", actor_id, request_id, previous, payload)
            conn.execute("UPDATE arenas SET updated_at=?,updated_by=? WHERE arena_id=?", (now, str(actor_id), arena_id))
            conn.commit(); return self._read_version(conn, arena_id, draft["version"]) or {}
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

    def _insert_version_replacing(self, conn: sqlite3.Connection, arena_id: str, version: int, payload: Mapping[str, Any], actor_id: Any, now: str, revision: int) -> None:
        immutable = {"name_fa": str(payload.get("name_fa") or "").strip(), "name_en": str(payload.get("name_en") or "").strip(), "description_fa": str(payload.get("description_fa") or "").strip(), "emoji": str(payload.get("emoji") or "").strip(), "tags": list(payload.get("tags") or []), "profiles": payload.get("profiles") or {}, "platform": payload.get("platform") or {}}
        conn.execute("UPDATE arena_versions SET draft_revision=?,name_fa=?,name_en=?,description_fa=?,emoji=?,tags_json=?,content_hash=?,created_at=?,created_by=? WHERE arena_id=? AND version=?", (revision, immutable["name_fa"], immutable["name_en"], immutable["description_fa"], immutable["emoji"], json_dumps(immutable["tags"]), self._hash(immutable), now, str(actor_id), arena_id, version))
        for mode, profile in immutable["profiles"].items():
            if mode not in MODE_KEYS: continue
            rules = self._normalise_rules(mode, profile.get("rules") or {})
            conn.execute("INSERT INTO arena_mode_profiles(arena_id,version,mode_key,enabled,selection_weight,active_from,active_until,rules_json,rules_hash) VALUES (?,?,?,?,?,?,?,?,?)", (arena_id, version, mode, int(bool(profile.get("enabled"))), int(profile.get("selection_weight",100)), normalise_utc(profile.get("active_from")), normalise_utc(profile.get("active_until")), json_dumps(rules), self._hash(rules)))
        for platform in PLATFORMS:
            config = (immutable["platform"].get(platform) or {})
            conn.execute("INSERT INTO arena_platform_settings(arena_id,version,platform,enabled,presentation_json) VALUES (?,?,?,?,?)", (arena_id, version, platform, int(bool(config.get("enabled"))), json_dumps({key:value for key,value in config.items() if key != "enabled"})))

    def publish(self, arena_id: str, actor_id: Any, expected_draft_revision: int, request_id: Optional[str] = None) -> Dict[str, Any]:
        conn = self._connect(); now = utc_now()
        try:
            conn.execute("BEGIN IMMEDIATE")
            draft = conn.execute("SELECT * FROM arena_versions WHERE arena_id=? AND version_status='draft'", (arena_id,)).fetchone()
            if not draft: raise ValueError("draft_not_found")
            if int(draft["draft_revision"]) != int(expected_draft_revision): raise ValueError("draft_conflict")
            payload = self._read_version(conn, arena_id, draft["version"])
            issues = self.validate_payload(arena_id, payload or {}, publishing=True)
            if (payload or {}).get("platform", {}).get("miniapp", {}).get("enabled") and not self._background_ready(conn, arena_id, draft["version"]):
                issues.append(self._issue("platform.miniapp", "miniapp_media_not_ready", "پس‌زمینه آماده Mini App لازم است."))
            errors = [issue for issue in issues if issue["severity"] == "error"]
            if errors: raise ArenaValidationError(errors)
            current = conn.execute("SELECT current_published_version FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
            if current and current[0]: conn.execute("UPDATE arena_versions SET version_status='superseded' WHERE arena_id=? AND version=?", (arena_id, current[0]))
            self._refresh_content_hash(conn, arena_id, int(draft["version"]))
            conn.execute("UPDATE arena_versions SET version_status='published',published_at=?,published_by=? WHERE arena_id=? AND version=?", (now, str(actor_id), arena_id, draft["version"]))
            conn.execute("UPDATE arenas SET lifecycle_status='published',current_published_version=?,updated_at=?,updated_by=? WHERE arena_id=?", (draft["version"], now, str(actor_id), arena_id))
            self._audit(conn, arena_id, draft["version"], "publish", actor_id, request_id, current[0] if current else None, payload)
            self._bump_version(conn); conn.commit()
            return self._read_version(conn, arena_id, draft["version"]) or {}
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

    def _background_ready(self, conn: sqlite3.Connection, arena_id: str, version: int) -> bool:
        return bool(conn.execute("SELECT 1 FROM arena_media WHERE arena_id=? AND version=? AND platform='miniapp' AND media_kind='background' AND readiness_status='ready' LIMIT 1", (arena_id, version)).fetchone())

    def validate_draft_for_publish(self, arena_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT version FROM arena_versions WHERE arena_id=? AND version_status='draft'",
                (arena_id,),
            ).fetchone()
            if not row:
                raise ValueError("draft_not_found")
            draft = self._read_version(conn, arena_id, int(row[0])) or {}
            issues = self.validate_payload(arena_id, draft, publishing=True)
            if draft.get("platform", {}).get("miniapp", {}).get("enabled") and not self._background_ready(conn, arena_id, int(row[0])):
                issues.append(self._issue("platform.miniapp", "miniapp_media_not_ready", "پس‌زمینه آماده Mini App لازم است."))
            current_row = conn.execute("SELECT current_published_version FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
            published = self._read_version(conn, arena_id, current_row[0]) if current_row and current_row[0] else None
            return {
                "version": int(row[0]),
                "valid": not any(item["severity"] == "error" for item in issues),
                "issues": issues,
                "diff": self._payload_diff(published, draft),
            }
        finally:
            conn.close()

    @staticmethod
    def _payload_diff(before: Optional[Mapping[str, Any]], after: Mapping[str, Any]) -> List[Dict[str, Any]]:
        tracked = ("name_fa", "name_en", "description_fa", "emoji", "tags", "profiles", "platform")
        changes: List[Dict[str, Any]] = []

        def walk(path: str, left: Any, right: Any) -> None:
            if isinstance(left, Mapping) and isinstance(right, Mapping):
                for key in sorted(set(left) | set(right)):
                    walk(f"{path}.{key}" if path else str(key), left.get(key), right.get(key))
            elif left != right:
                changes.append({"path": path, "before": left, "after": right})

        if before is None:
            return [{"path": "version", "before": None, "after": "new_arena"}]
        for key in tracked:
            walk(key, before.get(key), after.get(key))
        return changes[:200]

    def create_next_draft(self, arena_id: str, actor_id: Any, from_version: Optional[int] = None, request_id: Optional[str] = None) -> Dict[str, Any]:
        conn = self._connect(); now = utc_now()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM arena_versions WHERE arena_id=? AND version_status='draft'", (arena_id,)).fetchone(): raise ValueError("draft_conflict")
            arena = conn.execute("SELECT current_published_version FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
            source_version = from_version or (arena[0] if arena else None)
            source = self._read_version(conn, arena_id, source_version) if source_version else None
            if not source: raise ValueError("arena_not_found")
            next_version = int(conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM arena_versions WHERE arena_id=?", (arena_id,)).fetchone()[0])
            payload = {key: source.get(key) for key in ("name_fa","name_en","description_fa","emoji","tags","profiles","platform")}
            self._insert_version(conn, arena_id, next_version, payload, "draft", actor_id, now)
            self._audit(conn, arena_id, next_version, "clone_as_draft", actor_id, request_id, source_version, payload)
            conn.commit(); return self._read_version(conn, arena_id, next_version) or {}
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

    def archive(self, arena_id: str, actor_id: Any, request_id: Optional[str] = None) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT current_published_version,lifecycle_status FROM arenas WHERE arena_id=?", (arena_id,)).fetchone()
            if not row: raise ValueError("arena_not_found")
            if row["lifecycle_status"] == "archived": raise ValueError("arena_already_archived")
            conn.execute("UPDATE arenas SET lifecycle_status='archived',updated_at=?,updated_by=? WHERE arena_id=?", (utc_now(), str(actor_id), arena_id))
            self._audit(conn, arena_id, row["current_published_version"], "archive", actor_id, request_id, None, None); self._bump_version(conn); conn.commit()
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

    def list_arenas(self, include_archived: bool = True) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            query = "SELECT * FROM arenas"
            params: Tuple[Any, ...] = ()
            if not include_archived:
                query += " WHERE lifecycle_status!='archived'"
            rows = conn.execute(query + " ORDER BY arena_id", params).fetchall(); result=[]
            for row in rows:
                item = dict(row); item["published"] = self._read_version(conn, row["arena_id"], row["current_published_version"]) if row["current_published_version"] else None
                draft = conn.execute("SELECT version,draft_revision,updated_at FROM (SELECT version,draft_revision,created_at AS updated_at FROM arena_versions WHERE arena_id=? AND version_status='draft')", (row["arena_id"],)).fetchone()
                item["draft"] = dict(draft) if draft else None
                published = item.get("published") or {}
                item["enabled_modes"] = sorted(mode for mode, cfg in published.get("profiles", {}).items() if cfg.get("enabled"))
                item["enabled_platforms"] = sorted(target for target, cfg in published.get("platform", {}).items() if cfg.get("enabled"))
                item["media_ready"] = bool(row["current_published_version"] and self._background_ready(conn, row["arena_id"], row["current_published_version"]))
                item["warnings"] = []
                if item.get("draft"):
                    item["warnings"].append("has_unpublished_draft")
                if "miniapp" in item["enabled_platforms"] and not item["media_ready"]:
                    item["warnings"].append("miniapp_media_missing")
                result.append(item)
            return result
        finally: conn.close()

    def list_versions(self, arena_id: str) -> List[Dict[str, Any]]:
        conn = self._connect()
        try: return [dict(row) for row in conn.execute("SELECT arena_id,version,version_status,draft_revision,name_fa,content_hash,created_at,created_by,published_at,published_by FROM arena_versions WHERE arena_id=? ORDER BY version DESC", (arena_id,))]
        finally: conn.close()

    def list_dependencies(self, arena_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            def table_exists(name: str) -> bool:
                return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())
            active = conn.execute("SELECT COUNT(*) FROM active_fights WHERE arena_type=? AND status NOT IN ('completed','cancelled','expired')", (arena_id,)).fetchone()[0] if table_exists("active_fights") else 0
            battle = conn.execute("SELECT COUNT(*) FROM battle_states WHERE arena=? AND status!='completed'", (arena_id,)).fetchone()[0] if table_exists("battle_states") else 0
            solo = conn.execute("SELECT COUNT(*) FROM solo_fights WHERE arena=? AND status='in_progress'", (arena_id,)).fetchone()[0] if table_exists("solo_fights") else 0
            passive = 0
            if table_exists("card_mode_metadata"):
                for row in conn.execute("SELECT passive FROM card_mode_metadata WHERE passive IS NOT NULL AND passive!=''"):
                    value = json_loads(row[0], {})
                    if isinstance(value, Mapping) and str(value.get("arena") or value.get("arena_id") or "") == arena_id:
                        passive += 1
            return {"active_fights": active, "battle_states": battle, "solo_fights": solo, "card_passives": passive, "total": active + battle + solo + passive}
        finally: conn.close()

    def add_media(self, arena_id: str, version: int, platform: str, media_kind: str, storage_path: Optional[str], mime_type: str, byte_size: int, sha256: str, width: Optional[int], height: Optional[int], actor_id: Any, readiness_status: str = "ready", telegram_file_id: Optional[str] = None) -> Dict[str, Any]:
        if platform not in PLATFORMS or media_kind not in ("background", "photo", "sticker", "thumbnail") or readiness_status not in ("pending", "ready", "failed", "retired"):
            raise ValueError("invalid_media")
        conn = self._connect(); now=utc_now(); media_id=uuid.uuid4().hex
        try:
            conn.execute("BEGIN IMMEDIATE")
            target = self._read_version(conn, arena_id, version)
            if not target: raise ValueError("arena_not_found")
            if target.get("version_status") != "draft": raise ValueError("published_media_immutable")
            if readiness_status == "ready":
                conn.execute(
                    """UPDATE arena_media SET readiness_status='retired'
                       WHERE arena_id=? AND version=? AND platform=? AND media_kind=?
                         AND readiness_status='ready'""",
                    (arena_id, version, platform, media_kind),
                )
            conn.execute("INSERT INTO arena_media(media_id,arena_id,version,platform,media_kind,storage_path,telegram_file_id,mime_type,width,height,byte_size,sha256,readiness_status,created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (media_id,arena_id,version,platform,media_kind,storage_path,telegram_file_id,mime_type,width,height,int(byte_size),sha256,readiness_status,now,str(actor_id)))
            self._refresh_content_hash(conn, arena_id, version)
            self._audit(conn, arena_id, version, "upload_media", actor_id, None, None, {"media_id":media_id,"platform":platform,"media_kind":media_kind}); conn.commit()
            return {"media_id":media_id,"storage_path":storage_path,"readiness_status":readiness_status}
        except Exception:
            conn.rollback(); raise
        finally: conn.close()

    def arena_exists_for_mode(self, arena_id: str, mode: str, include_draft: bool = True) -> bool:
        if mode not in MODE_KEYS:
            return False
        conn = self._connect()
        try:
            statuses = ("published", "draft") if include_draft else ("published",)
            placeholders = ",".join("?" for _ in statuses)
            return bool(conn.execute(
                f"""SELECT 1 FROM arena_versions v JOIN arenas a ON a.arena_id=v.arena_id
                    JOIN arena_mode_profiles p ON p.arena_id=v.arena_id AND p.version=v.version
                    WHERE v.arena_id=? AND p.mode_key=? AND p.enabled=1
                      AND v.version_status IN ({placeholders}) AND a.lifecycle_status!='archived' LIMIT 1""",
                (arena_id, mode, *statuses),
            ).fetchone())
        finally:
            conn.close()

    def list_audit(self, arena_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM arena_audit_log WHERE arena_id=? ORDER BY id DESC LIMIT ?",
                (arena_id, max(1, min(int(limit), 500))),
            )]
        finally:
            conn.close()

    def manifest(self, mode: str) -> Dict[str, Any]:
        return {"registry_version": self.registry_version(), "mode": mode, "arenas": [{key:item.get(key) for key in ("arena_id","version","name_fa","emoji","background_url")} for item in self.list_active(mode, "miniapp")]}

    def registry_version(self) -> int:
        conn=self._connect()
        try: return int(conn.execute("SELECT meta_value FROM arena_registry_meta WHERE meta_key='registry_version'").fetchone()[0])
        finally: conn.close()

    def _bump_version(self, conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE arena_registry_meta SET meta_value=CAST(meta_value AS INTEGER)+1,updated_at=? WHERE meta_key='registry_version'", (utc_now(),))

    @staticmethod
    def _audit(conn: sqlite3.Connection, arena_id: str, version: Optional[int], action: str, actor_id: Any, request_id: Optional[str], before: Any, after: Any) -> None:
        conn.execute("INSERT INTO arena_audit_log(arena_id,version,action,actor_id,request_id,before_json,after_json,created_at) VALUES (?,?,?,?,?,?,?,?)", (arena_id,version,action,str(actor_id) if actor_id is not None else None,request_id,json_dumps(before) if before is not None else None,json_dumps(after) if after is not None else None,utc_now()))
