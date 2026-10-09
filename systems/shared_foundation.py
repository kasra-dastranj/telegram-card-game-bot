"""Phase 1 contracts. Future reward policy is deliberately not a live writer.

Contexts are trusted server records, never reconstructed from a callback payload.
Legacy writers retain their amounts and their existing idempotent ledgers.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


FLAGS = ("custom_cards_enabled", "quick_friendly_enabled",
         "easy_custom_cards_enabled", "progression_v2_enabled")
MODES = {"quick", "three_round", "deck", "easy", "practice", "risk", "legacy_pvp"}
ALIASES = {"mini_three_round": "three_round", "solo": "practice", "pvp": "legacy_pvp"}
DEFAULT_SETTINGS = {**{key: False for key in FLAGS},
                    "friendly_loss_hearts": 1, "competitive_loss_hearts": 1,
                    "easy_min_qualified_players": 5}


@dataclass(frozen=True)
class MatchContext:
    mode: str
    variant: str = "competitive"
    selection_variant: str = "normal"
    allow_custom_cards: bool = False
    policy_version: str = "legacy_v1"
    version: int = 1
    friendly_loss_hearts: int = 1
    competitive_loss_hearts: int = 1
    easy_min_qualified_players: int = 5

    def __post_init__(self):
        if self.mode not in MODES or self.variant not in {"competitive", "friendly"}:
            raise ValueError("invalid_match_context")
        if self.variant == "friendly" and self.mode != "quick":
            raise ValueError("friendly_requires_quick")
        if self.selection_variant not in {"normal", "random", "group"}:
            raise ValueError("invalid_selection_variant")
        if type(self.allow_custom_cards) is not bool or (self.allow_custom_cards and self.mode != "easy"):
            raise ValueError("invalid_custom_setting")
        if type(self.version) is not int or self.version != 1 or self.policy_version not in {"legacy_v1", "future_v2"}:
            raise ValueError("unsupported_policy_version")
        for value in (self.friendly_loss_hearts, self.competitive_loss_hearts):
            if type(value) is not int or value < 0:
                raise ValueError("invalid_heart_policy")
        if type(self.easy_min_qualified_players) is not int or self.easy_min_qualified_players < 5:
            raise ValueError("invalid_easy_threshold")

    def to_json(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value):
        return cls(**json.loads(value))


def ensure_foundation_schema(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}
    if not columns:
        raise ValueError("cards_table_required")
    if "origin" not in columns:
        conn.execute("ALTER TABLE cards ADD COLUMN origin TEXT NOT NULL DEFAULT 'official' "
                     "CHECK(origin IN ('official','custom'))")
    if conn.execute("SELECT 1 FROM cards WHERE origin IS NULL OR origin NOT IN ('official','custom')").fetchone():
        raise ValueError("invalid_existing_card_origin")
    conn.execute("CREATE TABLE IF NOT EXISTS foundation_settings "
                 "(key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
    conn.executemany("INSERT OR IGNORE INTO foundation_settings VALUES(?,?)",
                     ((key, json.dumps(value)) for key, value in DEFAULT_SETTINGS.items()))
    conn.execute("""CREATE TABLE IF NOT EXISTS match_contexts (
        match_key TEXT PRIMARY KEY, context_json TEXT NOT NULL,
        created_at TEXT NOT NULL)""")


def settings_in(conn):
    values = dict(DEFAULT_SETTINGS)
    values.update({row[0]: json.loads(row[1]) for row in conn.execute(
        "SELECT key,value_json FROM foundation_settings") if row[0] in values})
    if any(type(values[key]) is not bool for key in FLAGS):
        raise ValueError("invalid_feature_flag")
    # Reuse strict numeric validation, including excluding bool-as-int.
    MatchContext("quick", **{key: values[key] for key in DEFAULT_SETTINGS if key not in FLAGS})
    return values


def legacy_context(mode, selection_variant="normal", settings=None):
    values = settings or DEFAULT_SETTINGS
    return MatchContext(ALIASES.get(mode, mode), selection_variant=selection_variant,
                        **{key: values[key] for key in DEFAULT_SETTINGS if key not in FLAGS})


def bind_context(conn, match_key, context):
    """Create immutable identity in the creator's transaction; conflicting bind fails."""
    if not isinstance(match_key, str) or not match_key:
        raise ValueError("invalid_match_key")
    conn.execute("INSERT OR IGNORE INTO match_contexts VALUES(?,?,?)",
                 (match_key, context.to_json(), datetime.now(timezone.utc).isoformat()))
    stored = MatchContext.from_json(conn.execute(
        "SELECT context_json FROM match_contexts WHERE match_key=?", (match_key,)).fetchone()[0])
    if stored != context:
        raise ValueError("match_context_conflict")
    return stored


def bind_new_context(conn, match_key, mode, selection_variant="normal"):
    """Only creators opt into v2. Fallback contexts for old games stay legacy."""
    from dataclasses import replace
    from systems.progression_config import enabled_in, config_in
    context = legacy_context(mode, selection_variant, settings_in(conn))
    if enabled_in(conn):
        version, config = config_in(conn)
        context = replace(context, policy_version="future_v2", easy_min_qualified_players=config["easy"]["min_players"])
        conn.execute("INSERT INTO match_economy_snapshots VALUES(?,?)", (match_key, version))
    return bind_context(conn, match_key, context)


def context_in(conn, match_key, legacy_mode):
    prior = conn.execute("SELECT context_json FROM match_contexts WHERE match_key=?",
                         (match_key,)).fetchone()
    if prior:
        return MatchContext.from_json(prior[0])
    # Use server records for old running requests. Never infer Friendly from source.
    selection = "normal"
    if not match_key.startswith(("fight:", "solo:", "risk:")) and conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='game_requests'").fetchone():
        row = conn.execute("SELECT mode,variant FROM game_requests WHERE request_id=?", (match_key,)).fetchone()
        if row:
            legacy_mode, selection = row[0], row[1]
    if match_key.startswith("fight:") and conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='battle_states'").fetchone():
        row = conn.execute("SELECT 1 FROM battle_states WHERE fight_id=?", (match_key[6:],)).fetchone()
        if row:
            legacy_mode = "three_round"
        row = conn.execute("SELECT challenger_deck_id,opponent_deck_id FROM active_fights WHERE fight_id=?",
                           (match_key[6:],)).fetchone()
        if row and any(row):
            legacy_mode = "deck"
    # No bulk rewrite of running matches; bind on first use in the caller's transaction.
    return bind_context(conn, match_key, legacy_context(legacy_mode, selection, settings_in(conn)))


def require_settlement_mode(context, ledger_mode):
    canonical = ALIASES.get(ledger_mode, ledger_mode)
    allowed = {"legacy_pvp", "three_round", "deck"} if ledger_mode == "pvp" else {canonical}
    if context.mode not in allowed:
        raise ValueError("settlement_mode_conflict")


def card_origin(card):
    if card is None:
        return None
    return card.get("origin", "official") if isinstance(card, dict) else getattr(card, "origin", "official")


def is_card_eligible(card, context, flags=None):
    if not isinstance(context, MatchContext):
        return False
    flags = flags or DEFAULT_SETTINGS
    if context.variant == "friendly" and flags.get("quick_friendly_enabled") is not True:
        return False
    origin = card_origin(card)
    if origin == "official":
        return True
    if origin != "custom" or flags.get("custom_cards_enabled") is not True:
        return False
    if context.mode == "quick":
        return context.variant == "friendly"
    if context.mode == "practice":
        return True
    return (context.mode == "easy" and context.allow_custom_cards
            and flags.get("easy_custom_cards_enabled") is True)


def economic_card_eligible(card):
    """Claim, duplicate/upgrade, sell, wheel, trade and collection rewards."""
    return card_origin(card) == "official"


def economic_card_in(conn, card_id):
    row = conn.execute("SELECT origin FROM cards WHERE card_id=?", (card_id,)).fetchone()
    return bool(row and economic_card_eligible({"origin": row[0]}))


def validate_match_card(db, match_key, mode, card_id, user_id=None):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        require_card_in(conn, card_id, context_in(conn, match_key, mode), user_id)


def require_card_in(conn, card_id, context, user_id=None):
    # Read the definition afresh: caches/rarity overrides cannot hide its origin.
    row = conn.execute("SELECT origin FROM cards WHERE card_id=?", (card_id,)).fetchone()
    if not row or not is_card_eligible({"origin": row[0]}, context, settings_in(conn)):
        raise ValueError("card_ineligible")
    if user_id is not None and not conn.execute(
            "SELECT 1 FROM player_cards WHERE user_id=? AND card_id=?", (user_id, card_id)).fetchone():
        raise ValueError("card_not_owned")


def eligible_cards(db, cards, mode, match_key=None):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        context = (context_in(conn, match_key, mode) if match_key
                   else legacy_context(mode, settings=settings_in(conn)))
        flags = settings_in(conn)
        origins = dict(conn.execute("SELECT card_id,origin FROM cards"))
        return [card for card in cards if card.card_id in origins
                and is_card_eligible({"origin": origins[card.card_id]}, context, flags)]


@dataclass(frozen=True)
class SettlementDecision:
    reward_eligible: bool
    ranked_progress: bool
    hearts_lost: int | None  # Risk is undecided, NOT zero.
    reward_policy: str


def future_settlement_policy(context, outcome, *, valid=True, qualified_player_ids=()):
    """Pure Phase 2/3 contract; callers supply server-validated real human IDs.

    No economic amounts, level curve, top-three ranking or DB writes here.
    The legacy writer intentionally does not call this in Phase 1.
    """
    if outcome not in {"win", "loss", "tie", "draw"} or type(valid) is not bool:
        raise ValueError("invalid_match_result")
    if not valid:
        return SettlementDecision(False, False, 0, "invalid")
    if context.mode == "quick" and context.variant == "friendly":
        return SettlementDecision(False, False, context.friendly_loss_hearts if outcome == "loss" else 0,
                                  "none")
    if context.mode == "practice":
        return SettlementDecision(False, False, 0, "none")
    if context.mode == "easy":
        if any(type(uid) is not int or uid <= 0 for uid in qualified_player_ids):
            raise ValueError("unqualified_player_ids")
        qualified = len(set(qualified_player_ids)) >= context.easy_min_qualified_players
        return SettlementDecision(qualified, qualified, 0, "easy" if qualified else "none")
    if context.mode == "risk":
        return SettlementDecision(True, False, None, "risk_independent")
    return SettlementDecision(True, True, context.competitive_loss_hearts if outcome == "loss" else 0,
                              "competitive")


def project_future_award(item, decision):
    """Preview only: separate reward and ranked effects from heart loss.

    Phase 2 must connect ranked_progress to ALL history/mission/achievement writers.
    Never pass this preview into an unaware legacy history writer for Friendly.
    """
    result = dict(item)
    if not decision.reward_eligible:
        result.update(xp=0, score=0, coins=0, tp_delta=0)
    if not decision.ranked_progress:
        result["score"] = 0
    if decision.hearts_lost is not None:
        result["hearts_lost"] = decision.hearts_lost
    result["ranked_progress"] = decision.ranked_progress
    return result
