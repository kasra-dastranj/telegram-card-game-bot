#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TelBattle Mini App — Flask REST API
"""

import json
import hmac
import hashlib
import os
import sys
import random
import sqlite3
import logging
from io import BytesIO
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, parse_qsl, quote
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory, send_file, g
from PIL import Image, ImageOps
from werkzeug.middleware.proxy_fix import ProxyFix
from game_core import DatabaseManager, CardRarity
from systems.ai_opponent import AsoAI, DAILY_SOLO_LIMIT
from systems.battle_system_3rounds import BattleSystem3Rounds, ARENAS
from systems.game_mode_system import GameModeSystem
from systems.player_hub_system import PlayerHubSystem
from systems.card_upgrade_system import CardUpgradeSystem
from systems.deck_system import DeckSystem
from systems.player_rewards_system import PlayerRewardsSystem
from systems.fusion_system import FusionSystem

logger = logging.getLogger(__name__)

# ==================== تنظیمات ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
MINIAPP_DIST_DIR = os.environ.get(
    "MINIAPP_DIST_DIR",
    os.path.join(PROJECT_ROOT, "frontend", "game", "dist"),
)
CARD_IMAGES_DIR = os.environ.get(
    "CARD_IMAGES_DIR",
    os.path.join(PROJECT_ROOT, "assets", "card_images"),
)
DB_PATH = os.environ.get("DATABASE_PATH", "game_bot.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = max(
    60,
    int(os.environ.get("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", "86400")),
)

# fallback به config.json اگه env نبود
if not BOT_TOKEN:
    try:
        with open("config.json") as f:
            _cfg = json.load(f)
            BOT_TOKEN = _cfg.get("bot_token", "")
    except Exception:
        pass
if not BOT_TOKEN:
    try:
        with open("game_config.json") as f:
            _cfg = json.load(f)
            BOT_TOKEN = _cfg.get("bot_settings", {}).get("token", "")
    except Exception:
        pass

app = Flask(__name__, static_folder=None)
# Production traffic reaches Flask through one trusted local Nginx proxy.
# Respect its forwarded host/scheme so generated invite links stay HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
db = DatabaseManager(DB_PATH)
battle_system = BattleSystem3Rounds(db)
quick_modes = GameModeSystem(db)

# ==================== احراز هویت ====================

def verify_telegram_init_data(init_data: str):
    """
    بررسی صحت initData تلگرام.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    برگشت: دیکشنری user یا None
    """
    try:
        if not init_data or not BOT_TOKEN:
            return None

        # Split the original query string before decoding individual values.
        # Telegram now includes photo_url for all Mini Apps; decoding the whole
        # string first turns an encoded '&' inside that URL into a fake field and
        # invalidates the otherwise-correct signature.
        pairs = parse_qsl(init_data, keep_blank_values=True)
        parsed = {}
        for key, value in pairs:
            # Duplicate signed fields are ambiguous and should never be trusted.
            if key in parsed:
                return None
            parsed[key] = value

        hash_value = parsed.pop("hash", "")
        if not hash_value:
            return None
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items())
        )

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_hash, hash_value):
            return None

        auth_date = int(parsed.get("auth_date", "0"))
        now = int(datetime.now(timezone.utc).timestamp())
        if auth_date <= 0 or auth_date > now + 60:
            return None
        if now - auth_date > TELEGRAM_INIT_DATA_MAX_AGE_SECONDS:
            return None

        user = json.loads(parsed.get("user", "{}"))
        if not isinstance(user, dict) or not user.get("id"):
            return None
        user["id"] = int(user["id"])
        return user
    except Exception as e:
        logger.warning(f"initData verification failed: {e}")
        return None


def require_auth(f):
    """دکوراتور: بررسی احراز هویت از Authorization header"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        # اگه initData داره، همیشه verify کن
        if auth_header.startswith("tma "):
            init_data = auth_header[4:]
            if not BOT_TOKEN:
                logger.error("BOT_TOKEN is missing; Mini App authentication is unavailable")
                return jsonify({
                    "error": "سرویس ورود موقتاً در دسترس نیست",
                    "error_code": "auth_not_configured",
                }), 503
            user = verify_telegram_init_data(init_data)
            if user:
                g.user_id = user["id"]
                player = db.get_or_create_player(
                    user_id=user["id"],
                    username=user.get("username", ""),
                    first_name=user.get("first_name", "")
                )
                _grant_starter_cards(user["id"])
                return f(*args, **kwargs)
            # initData invalid — اگه debug mode، ادامه بده
            if not (app.debug or os.environ.get("FLASK_DEBUG", "0") == "1"):
                logger.warning("Rejected invalid Telegram Mini App initData")
                return jsonify({
                    "error": "ورود تلگرام معتبر نیست؛ مینی‌اپ را از داخل ربات دوباره باز کن",
                    "error_code": "invalid_init_data",
                }), 401

        # Debug mode: بدون auth یا با initData ناموفق
        if app.debug or os.environ.get("FLASK_DEBUG", "0") == "1":
            # سعی کن از initData user_id بگیر
            if auth_header.startswith("tma "):
                try:
                    from urllib.parse import parse_qs, unquote
                    parsed = parse_qs(unquote(auth_header[4:]))
                    user_str = parsed.get("user", ["{}"])[0]
                    import json as _json
                    user_data = _json.loads(user_str)
                    if user_data.get("id"):
                        g.user_id = int(user_data["id"])
                        db.get_or_create_player(
                            user_id=g.user_id,
                            username=user_data.get("username", ""),
                            first_name=user_data.get("first_name", "")
                        )
                        _grant_starter_cards(g.user_id)
                        return f(*args, **kwargs)
                except Exception:
                    pass
            # fallback به X-Debug-User-Id
            debug_user = request.headers.get("X-Debug-User-Id", "1")
            g.user_id = int(debug_user)
            db.get_or_create_player(user_id=g.user_id)
            _grant_starter_cards(g.user_id)
            return f(*args, **kwargs)

        return jsonify({
            "error": "مینی‌اپ را از دکمه داخل ربات باز کن",
            "error_code": "auth_required",
        }), 401
    return decorated


def _grant_starter_cards(user_id: int):
    """اگه player هیچ کارتی نداره، ۳ تا کارت starter بده"""
    try:
        existing = db.get_player_cards(user_id)
        if not existing:
            starter_names = ["Heisenberg", "John Wick", "Rehi"]
            all_cards = db.get_all_cards()
            granted = 0
            for card in all_cards:
                if card.name in starter_names:
                    db.add_card_to_player(user_id, card.card_id)
                    granted += 1
            # اگه starter cards پیدا نشد، اولین ۳ کارت رو بده
            if granted == 0 and all_cards:
                for card in all_cards[:3]:
                    db.add_card_to_player(user_id, card.card_id)
    except Exception as e:
        logger.warning(f"Failed to grant starter cards to {user_id}: {e}")


# ==================== Helper ====================

def card_to_dict(card) -> dict:
    """تبدیل Card object به دیکشنری برای JSON"""
    try:
        abilities = json.loads(card.abilities) if isinstance(card.abilities, str) else (card.abilities or [])
    except Exception:
        abilities = []
    image_path = getattr(card, "image_path", "") or ""
    image_name = os.path.basename(str(image_path).replace("\\", "/"))
    return {
        "card_id": card.card_id,
        "name": card.name,
        "rarity": card.rarity.value if hasattr(card.rarity, 'value') else card.rarity,
        "power": card.power,
        "speed": card.speed,
        "iq": card.iq,
        "popularity": card.popularity,
        "card_type": card.card_type,
        "abilities": abilities,
        "biography": card.biography or "",
        "image_url": f"/card-images/{quote(image_name)}?w=480" if image_name else "",
        "score": card.power + card.speed + card.iq + card.popularity,
    }


def _player_hub() -> PlayerHubSystem:
    # Construct on demand so tests and maintenance scripts can safely replace db.
    return PlayerHubSystem(db)


def _card_upgrades() -> CardUpgradeSystem:
    return CardUpgradeSystem(db)


def _decks() -> DeckSystem:
    return DeckSystem(db)


def _rewards() -> PlayerRewardsSystem:
    return PlayerRewardsSystem(db)


def _fusion() -> FusionSystem:
    return FusionSystem(db)


def _skin_payload(skin: dict) -> dict:
    result = dict(skin)
    image_name = os.path.basename(str(result.get("image_path", "")).replace("\\", "/"))
    result["image_url"] = f"/card-images/{quote(image_name)}?w=480" if image_name else ""
    return result


def _deck_payload(deck: dict) -> dict:
    synergy = GameModeSystem(db).calculate_deck_synergy([card.card_id for card in deck.get("cards", [])])
    return {
        "deck_id": deck["deck_id"],
        "deck_name": deck["deck_name"],
        "is_valid": bool(deck["is_valid"]),
        "total_points": deck["total_points"],
        "synergy": synergy,
        "cards": [card_to_dict(card) for card in deck.get("cards", [])],
    }


def _management_locked():
    if _card_upgrades().is_management_locked(g.user_id):
        return jsonify({"error": "تا پایان مسابقه امکان مدیریت مجموعه وجود ندارد", "error_code": "active_match"}), 409
    return None


@app.route("/api/v1/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ==================== Routes: Static ====================

@app.route("/")
@app.route("/miniapp")
def serve_miniapp():
    index_path = os.path.join(MINIAPP_DIST_DIR, "index.html")
    if not os.path.isfile(index_path):
        return jsonify({
            "error": "Mini App build not found",
            "hint": "Run npm install && npm run build in frontend/game",
        }), 503
    return send_from_directory(MINIAPP_DIST_DIR, "index.html")


@app.route("/miniapp-assets/<path:filename>")
def serve_miniapp_asset(filename):
    return send_from_directory(MINIAPP_DIST_DIR, filename)


@app.route("/card-images/<path:filename>")
def serve_card_image(filename):
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        return jsonify({"error": "Invalid image path"}), 404
    try:
        width = max(160, min(int(request.args.get("w", 480)), 960))
    except (TypeError, ValueError):
        width = 480
    try:
        encoded = _optimized_card_image(safe_name, width)
        return send_file(
            BytesIO(encoded),
            mimetype="image/webp",
            max_age=86400,
            download_name=f"{os.path.splitext(safe_name)[0]}.webp",
        )
    except (FileNotFoundError, OSError):
        return send_from_directory(CARD_IMAGES_DIR, safe_name)


@lru_cache(maxsize=192)
def _optimized_card_image(filename: str, width: int) -> bytes:
    source = os.path.join(CARD_IMAGES_DIR, filename)
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        if image.width > width:
            height = max(1, round(image.height * width / image.width))
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="WEBP", quality=82, method=5)
        return output.getvalue()


# ==================== Helpers: Quick Mode ====================

QUICK_VARIANTS = {"normal", "random"}
QUICK_ERROR_MESSAGES = {
    "not_found": "درخواست پیدا نشد.",
    "self_accept": "نمی‌توانی دعوت خودت را قبول کنی.",
    "expired": "زمان درخواست تمام شد؛ درخواست منقضی شد.",
    "accepted": "این دعوت قبلاً پذیرفته شده است.",
    "already_claimed": "بازیکن دیگری زودتر این دعوت را پذیرفت.",
    "choice_locked": "انتخاب قبلی ثبت شده و قابل تغییر نیست.",
    "card_not_owned": "این کارت در مجموعه تو نیست.",
    "invalid_phase_or_player": "این انتخاب در فاز فعلی معتبر نیست.",
    "abilities_disabled": "در این میدان Ability غیرفعال است.",
    "ability_not_owned": "این Ability را در موجودی نداری.",
    "unknown_ability": "Ability نامعتبر است.",
    "stat_not_allowed": "این ویژگی در میدان فعلی قابل انتخاب نیست.",
}


def _quick_error(reason: str, status: int = 400):
    return jsonify({"error": QUICK_ERROR_MESSAGES.get(reason, reason), "reason": reason}), status


def _expire_waiting_request(game_request: dict) -> dict:
    if game_request.get("status") != "waiting":
        return game_request
    try:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        expired = datetime.fromisoformat(game_request["expires_at"]) <= now_utc
    except (KeyError, TypeError, ValueError):
        expired = False
    if expired:
        quick_modes.expire_request(game_request["request_id"])
        return quick_modes.get_request(game_request["request_id"]) or game_request
    return game_request


def _quick_request_for_user(request_id: str, user_id: int):
    game_request = quick_modes.get_request(request_id)
    if not game_request:
        return None
    game_request = _expire_waiting_request(game_request)
    participants = {game_request.get("creator_id"), game_request.get("opponent_id")}
    return game_request if user_id in participants else None


def _settle_quick_deadline(request_id: str, state: dict) -> dict:
    if state.get("phase") == "completed" or not state.get("deadline"):
        return state
    try:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        deadline_passed = datetime.fromisoformat(state["deadline"]) <= now_utc
    except (TypeError, ValueError):
        deadline_passed = False
    if not deadline_passed:
        return state
    phase = state.get("phase")
    if phase == "ability_selection":
        for player_id in state.get("players", []):
            latest = quick_modes.get_state(request_id) or state
            if latest.get("phase") != "ability_selection":
                break
            if str(player_id) not in latest.get("ability_choices", {}):
                try:
                    quick_modes.select_quick_ability(request_id, player_id, "skip")
                except ValueError:
                    pass
        return quick_modes.get_state(request_id) or state
    choice_key = "cards" if phase == "card_selection" else "stat_choices"
    missing = [
        player_id for player_id in state.get("players", [])
        if str(player_id) not in state.get(choice_key, {})
    ]
    if missing:
        try:
            quick_modes.forfeit_quick(request_id, missing, reason=f"{phase}_timeout")
        except ValueError:
            pass
    return quick_modes.get_state(request_id) or state


def _quick_snapshot(game_request: dict, user_id: int) -> dict:
    """Return a player-scoped state without leaking the opponent's hidden choices."""
    request_id = game_request["request_id"]
    state = quick_modes.get_state(request_id)
    if game_request["status"] in ("accepted", "active") and state is None:
        state = quick_modes.start_quick_match(request_id)
    if state:
        state = _settle_quick_deadline(request_id, state)
        game_request = quick_modes.get_request(request_id) or game_request

    response = {
        "request_id": request_id,
        "user_id": user_id,
        "status": game_request["status"],
        "source": game_request["source"],
        "variant": game_request["variant"],
        "expires_at": game_request["expires_at"],
        "opponent_id": (
            game_request.get("opponent_id")
            if game_request.get("creator_id") == user_id
            else game_request.get("creator_id")
        ),
    }
    if game_request["status"] == "expired":
        response["message"] = "زمان درخواست تمام شد؛ درخواست منقضی شد."
    if not state:
        return response

    user_key = str(user_id)
    opponent_id = next((pid for pid in state.get("players", []) if pid != user_id), None)
    opponent_key = str(opponent_id) if opponent_id is not None else ""
    arena = quick_modes._arena(state["arena"]) if state.get("arena") else None
    own_card_id = state.get("cards", {}).get(user_key)
    own_card = db.get_card_by_id(own_card_id) if own_card_id else None
    reveal_opponent = (
        state.get("phase") == "completed"
        or (
            state.get("phase") == "stat_selection"
            and state.get("ability_choices", {}).get(user_key) == "reveal_opponent"
        )
    )
    opponent_card_id = state.get("cards", {}).get(opponent_key) if reveal_opponent else None
    opponent_card = db.get_card_by_id(opponent_card_id) if opponent_card_id else None
    response.update({
        "phase": state.get("phase"),
        "deadline": state.get("deadline"),
        "arena": arena,
        "my_card": card_to_dict(own_card) if own_card else None,
        "my_card_locked": own_card_id is not None,
        "opponent_card_selected": opponent_key in state.get("cards", {}),
        "opponent_card": card_to_dict(opponent_card) if opponent_card else None,
        "my_ability": state.get("ability_choices", {}).get(user_key),
        "my_ability_locked": user_key in state.get("ability_choices", {}),
        "opponent_ability_selected": opponent_key in state.get("ability_choices", {}),
        "my_stat": state.get("stat_choices", {}).get(user_key),
        "my_stat_locked": user_key in state.get("stat_choices", {}),
        "opponent_stat_selected": opponent_key in state.get("stat_choices", {}),
        "allowed_stats": quick_modes.allowed_quick_stats(state, user_id)
            if state.get("phase") == "stat_selection" else [],
        "abilities": quick_modes.list_player_abilities(user_id)
            if state.get("phase") == "ability_selection" and arena and arena.get("abilities_enabled", True)
            else [],
        "report": state.get("report") if state.get("phase") == "completed" else None,
    })
    return response


# ==================== Routes: Profile ====================

@app.route("/api/v1/profile", methods=["GET"])
@require_auth
def get_profile():
    return _player_hub_overview_response()


def _player_hub_overview_response():
    overview = _player_hub().get_overview(g.user_id)
    best_card_id = overview.pop("best_card_id", None)
    best_card = db.get_card_by_id_for_player(best_card_id, g.user_id) if best_card_id else None
    overview["best_card"] = card_to_dict(best_card) if best_card else None
    return jsonify(overview)


@app.route("/api/v1/player-hub/overview", methods=["GET"])
@require_auth
def get_player_hub_overview():
    return _player_hub_overview_response()


# ==================== Routes: Cards ====================

@app.route("/api/v1/cards", methods=["GET"])
@require_auth
def get_cards():
    user_id = g.user_id
    rarity_filter = request.args.get("rarity", "all")
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        return jsonify({"error": "پارامتر صفحه نامعتبر است", "error_code": "invalid_pagination"}), 400
    cards, total, page, limit = _player_hub().get_cards(
        user_id,
        page=page,
        limit=limit,
        rarity=rarity_filter,
        sort=request.args.get("sort", "rarity"),
        query=request.args.get("query", ""),
    )

    result = []
    for card in cards:
        cd = db.is_card_in_cooldown(user_id, card.card_id) if hasattr(db, 'is_card_in_cooldown') else False
        d = card_to_dict(card)
        d["is_in_cooldown"] = bool(cd)
        result.append(d)

    return jsonify({
        "total": total,
        "page": page,
        "limit": limit,
        "page_count": max(1, (total + limit - 1) // limit),
        "cards": result,
    })


@app.route("/api/v1/cards/<card_id>", methods=["GET"])
@require_auth
def get_card_detail(card_id):
    card = _player_hub().get_owned_card(g.user_id, card_id)
    if not card:
        return jsonify({"error": "کارت در کلکسیون شما نیست", "error_code": "card_not_owned"}), 404
    result = card_to_dict(card)
    cooldown = db.is_card_in_cooldown(g.user_id, card.card_id) if hasattr(db, "is_card_in_cooldown") else False
    result["is_in_cooldown"] = bool(cooldown)
    result["upgrade"] = _card_upgrades().preview(g.user_id, card_id)
    return jsonify(result)


@app.route("/api/v1/cards/<card_id>/upgrade/preview", methods=["POST"])
@require_auth
def preview_card_upgrade(card_id):
    result = _card_upgrades().preview(g.user_id, card_id)
    return jsonify(result), 200 if result.get("ok") else 409


@app.route("/api/v1/cards/<card_id>/upgrade", methods=["POST"])
@require_auth
def upgrade_card(card_id):
    data = request.get_json(silent=True) or {}
    result = _card_upgrades().upgrade(g.user_id, card_id, str(data.get("upgrade_key", "")))
    if not result.get("ok"):
        status = 404 if result.get("error_code") == "card_not_owned" else 409
        return jsonify(result), status
    card = db.get_card_by_id_for_player(card_id, g.user_id)
    return jsonify({
        "ok": True,
        "message": "کارت با موفقیت ارتقا پیدا کرد",
        "profile": _player_hub().get_overview(g.user_id),
        "data": {"upgrade": result, "card": card_to_dict(card)},
    })


# ==================== Routes: Deck management ====================

@app.route("/api/v1/decks", methods=["GET"])
@require_auth
def get_decks():
    return jsonify({"decks": [_deck_payload(deck) for deck in _decks().get_player_decks(g.user_id)]})


@app.route("/api/v1/decks", methods=["POST"])
@require_auth
def create_deck():
    locked = _management_locked()
    if locked:
        return locked
    data = request.get_json(silent=True) or {}
    card_ids = data.get("card_ids") if isinstance(data.get("card_ids"), list) else []
    ok, value = _decks().create_deck(g.user_id, [str(item) for item in card_ids], str(data.get("name", "")).strip() or None)
    if not ok:
        return jsonify({"error": value, "error_code": "invalid_deck"}), 400
    deck = next(item for item in _decks().get_player_decks(g.user_id) if item["deck_id"] == value)
    return jsonify({"ok": True, "message": "دک ساخته شد", "data": _deck_payload(deck)}), 201


@app.route("/api/v1/decks/<deck_id>", methods=["PUT"])
@require_auth
def update_deck(deck_id):
    locked = _management_locked()
    if locked:
        return locked
    data = request.get_json(silent=True) or {}
    card_ids = data.get("card_ids")
    normalized = [str(item) for item in card_ids] if isinstance(card_ids, list) else None
    name = str(data["name"]).strip() if "name" in data else None
    ok, error = _decks().update_deck(g.user_id, deck_id, normalized, name)
    if not ok:
        status = 404 if error == "دک یافت نشد." else 403 if error == "این دک متعلق به شما نیست." else 400
        return jsonify({"error": error, "error_code": "invalid_deck"}), status
    deck = next(item for item in _decks().get_player_decks(g.user_id) if item["deck_id"] == deck_id)
    return jsonify({"ok": True, "message": "دک بروزرسانی شد", "data": _deck_payload(deck)})


@app.route("/api/v1/decks/<deck_id>", methods=["DELETE"])
@require_auth
def delete_deck(deck_id):
    locked = _management_locked()
    if locked:
        return locked
    ok, error = _decks().delete_deck(g.user_id, deck_id)
    if not ok:
        status = 404 if error == "دک یافت نشد." else 403
        return jsonify({"error": error, "error_code": "deck_not_accessible"}), status
    return jsonify({"ok": True, "message": "دک حذف شد", "data": {"deck_id": deck_id}})


# ==================== Routes: Rewards and skins ====================

@app.route("/api/v1/claim", methods=["GET"])
@require_auth
def get_claim_status():
    return jsonify(_rewards().claim_status(g.user_id))


@app.route("/api/v1/claim", methods=["POST"])
@require_auth
def claim_daily_card():
    locked = _management_locked()
    if locked:
        return locked
    result = _rewards().claim_daily(g.user_id)
    if not result.get("ok"):
        return jsonify(result), 409
    card = db.get_card_by_id_for_player(result["card_id"], g.user_id) or db.get_card_by_id(result["card_id"])
    return jsonify({"ok": True, "message": "کارت روزانه دریافت شد", "data": {"card": card_to_dict(card)}, "profile": _player_hub().get_overview(g.user_id)})


@app.route("/api/v1/missions", methods=["GET"])
@require_auth
def get_missions():
    return jsonify({"missions": _rewards().missions(g.user_id)})


@app.route("/api/v1/missions/<mission_id>/claim", methods=["POST"])
@require_auth
def claim_mission_reward(mission_id):
    locked = _management_locked()
    if locked:
        return locked
    result = _rewards().claim_mission(g.user_id, mission_id)
    if not result.get("ok"):
        return jsonify(result), 409
    card = db.get_card_by_id_for_player(result["card_id"], g.user_id)
    return jsonify({"ok": True, "message": "پاداش مأموریت دریافت شد", "data": {"mission": result, "card": card_to_dict(card)}, "profile": _player_hub().get_overview(g.user_id)})


@app.route("/api/v1/cards/<card_id>/skins", methods=["GET"])
@require_auth
def get_card_skins(card_id):
    result = _rewards().skins(g.user_id, card_id)
    if not result.get("ok"):
        return jsonify(result), 404
    result["skins"] = [_skin_payload(skin) for skin in result["skins"]]
    return jsonify(result)


@app.route("/api/v1/cards/<card_id>/skins/<skin_id>/purchase", methods=["POST"])
@require_auth
def purchase_card_skin(card_id, skin_id):
    locked = _management_locked()
    if locked:
        return locked
    result = _rewards().purchase_skin(g.user_id, card_id, skin_id)
    if not result.get("ok"):
        return jsonify(result), 409
    return jsonify({"ok": True, "message": "پوسته خریداری شد", "data": result, "profile": _player_hub().get_overview(g.user_id)})


@app.route("/api/v1/cards/<card_id>/skins/activate", methods=["POST"])
@require_auth
def activate_card_skin(card_id):
    locked = _management_locked()
    if locked:
        return locked
    data = request.get_json(silent=True) or {}
    skin_id = str(data.get("skin_id")) if data.get("skin_id") else None
    result = _rewards().activate_skin(g.user_id, card_id, skin_id)
    if not result.get("ok"):
        return jsonify(result), 409
    return jsonify({"ok": True, "message": "ظاهر کارت بروزرسانی شد", "data": result})


# ==================== Routes: Fusion ====================

@app.route("/api/v1/fusions/preview", methods=["POST"])
@require_auth
def preview_fusion():
    data = request.get_json(silent=True) or {}
    card_ids = [str(item) for item in data.get("card_ids", [])] if isinstance(data.get("card_ids"), list) else []
    result = _fusion().preview(g.user_id, card_ids, str(data.get("retained_card_id", "")), str(data.get("target_rarity", "")))
    if not result.get("ok"):
        return jsonify(result), 400
    result["cards"] = [card_to_dict(card) for card in result["cards"]]
    return jsonify(result)


@app.route("/api/v1/fusions", methods=["POST"])
@require_auth
def execute_fusion():
    locked = _management_locked()
    if locked:
        return locked
    data = request.get_json(silent=True) or {}
    card_ids = [str(item) for item in data.get("card_ids", [])] if isinstance(data.get("card_ids"), list) else []
    retained = str(data.get("retained_card_id", ""))
    target = str(data.get("target_rarity", ""))
    result = _fusion().fuse_to_epic(g.user_id, card_ids, retained) if target == "epic" else _fusion().fuse_to_legend(g.user_id, card_ids, retained) if target == "legend" else None
    if result is None:
        return jsonify({"error": "هدف Fusion نامعتبر است", "error_code": "invalid_target"}), 400
    if not result.success:
        return jsonify({"error": result.error, "error_code": "fusion_failed"}), 409
    return jsonify({
        "ok": True, "message": "Fusion با موفقیت انجام شد",
        "profile": _player_hub().get_overview(g.user_id),
        "data": {
            "card": card_to_dict(result.upgraded_card),
            "consumed_cards": [card_to_dict(card) for card in result.consumed_cards if card.card_id != retained],
            "xp_gained": result.xp_gained,
            "level_up": result.new_level > result.old_level,
        },
    })


# ==================== Routes: Quick PvP ====================

@app.route("/api/v1/quick/matchmaking", methods=["POST"])
@require_auth
def quick_matchmaking():
    data = request.get_json(silent=True) or {}
    variant = data.get("variant", "normal")
    if variant not in QUICK_VARIANTS:
        return jsonify({"error": "نوع Quick نامعتبر است", "reason": "invalid_variant"}), 400
    status, game_request = quick_modes.matchmake_random(g.user_id, "quick", variant)
    snapshot = _quick_snapshot(game_request, g.user_id)
    snapshot["matchmaking_status"] = status
    return jsonify(snapshot), 200 if status == "matched" else 201


@app.route("/api/v1/quick/invites", methods=["POST"])
@require_auth
def quick_create_invite():
    data = request.get_json(silent=True) or {}
    variant = data.get("variant", "normal")
    if variant not in QUICK_VARIANTS:
        return jsonify({"error": "نوع Quick نامعتبر است", "reason": "invalid_variant"}), 400
    game_request = quick_modes.create_invite(g.user_id, "quick", variant)
    snapshot = _quick_snapshot(game_request, g.user_id)
    snapshot.update({
        "invite_token": game_request["invite_token"],
        "invite_url": f"{request.host_url.rstrip('/')}?invite={game_request['invite_token']}",
    })
    return jsonify(snapshot), 201


@app.route("/api/v1/quick/invites/<token>/accept", methods=["POST"])
@require_auth
def quick_accept_invite(token: str):
    ok, reason, game_request = quick_modes.accept_invite(token, g.user_id)
    if not ok:
        return _quick_error(reason, 404 if reason == "not_found" else 409)
    return jsonify(_quick_snapshot(game_request, g.user_id))


@app.route("/api/v1/quick/requests/<request_id>", methods=["GET"])
@require_auth
def quick_request_status(request_id: str):
    game_request = _quick_request_for_user(request_id, g.user_id)
    if not game_request:
        return _quick_error("not_found", 404)
    return jsonify(_quick_snapshot(game_request, g.user_id))


@app.route("/api/v1/quick/requests/<request_id>/cancel", methods=["POST"])
@require_auth
def quick_cancel_request(request_id: str):
    game_request = _quick_request_for_user(request_id, g.user_id)
    if not game_request:
        return _quick_error("not_found", 404)
    if not quick_modes.cancel_request(request_id, g.user_id):
        return jsonify({"error": "این درخواست دیگر قابل لغو نیست", "reason": game_request["status"]}), 409
    return jsonify(_quick_snapshot(quick_modes.get_request(request_id), g.user_id))


def _quick_active_request(request_id: str):
    game_request = _quick_request_for_user(request_id, g.user_id)
    if not game_request:
        return None, _quick_error("not_found", 404)
    if game_request["status"] not in ("accepted", "active", "completed"):
        return None, (
            jsonify({"error": "مسابقه هنوز شروع نشده", "reason": game_request["status"]}),
            409,
        )
    return game_request, None


@app.route("/api/v1/quick/matches/<request_id>", methods=["GET"])
@require_auth
def quick_match_state(request_id: str):
    game_request, error = _quick_active_request(request_id)
    if error:
        return error
    return jsonify(_quick_snapshot(game_request, g.user_id))


@app.route("/api/v1/quick/matches/<request_id>/card", methods=["POST"])
@require_auth
def quick_choose_card(request_id: str):
    game_request, error = _quick_active_request(request_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if not data.get("card_id"):
        return jsonify({"error": "card_id الزامی است", "reason": "missing_card_id"}), 400
    _quick_snapshot(game_request, g.user_id)
    try:
        quick_modes.select_quick_card(request_id, g.user_id, str(data["card_id"]))
    except ValueError as exc:
        return _quick_error(str(exc), 409 if str(exc) == "choice_locked" else 400)
    return jsonify(_quick_snapshot(quick_modes.get_request(request_id), g.user_id))


@app.route("/api/v1/quick/matches/<request_id>/ability", methods=["POST"])
@require_auth
def quick_choose_ability(request_id: str):
    game_request, error = _quick_active_request(request_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    ability_key = str(data.get("ability_key", ""))
    if not ability_key:
        return jsonify({"error": "ability_key الزامی است", "reason": "missing_ability_key"}), 400
    try:
        quick_modes.select_quick_ability(request_id, g.user_id, ability_key)
    except ValueError as exc:
        return _quick_error(str(exc), 409 if str(exc) == "choice_locked" else 400)
    return jsonify(_quick_snapshot(quick_modes.get_request(request_id), g.user_id))


@app.route("/api/v1/quick/matches/<request_id>/stat", methods=["POST"])
@require_auth
def quick_choose_stat(request_id: str):
    game_request, error = _quick_active_request(request_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    stat = str(data.get("stat", ""))
    if not stat:
        return jsonify({"error": "stat الزامی است", "reason": "missing_stat"}), 400
    try:
        quick_modes.select_quick_stat(request_id, g.user_id, stat)
    except ValueError as exc:
        return _quick_error(str(exc), 409 if str(exc) == "choice_locked" else 400)
    return jsonify(_quick_snapshot(quick_modes.get_request(request_id), g.user_id))


# ==================== Routes: Solo Fight ====================

@app.route("/api/v1/solo/daily-limit", methods=["GET"])
@require_auth
def get_daily_limit():
    user_id = g.user_id
    used = db.get_daily_solo_count(user_id)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    return jsonify({
        "used": used,
        "limit": DAILY_SOLO_LIMIT,
        "remaining": max(0, DAILY_SOLO_LIMIT - used),
        "resets_at": tomorrow,
    })


@app.route("/api/v1/solo/start", methods=["POST"])
@require_auth
def solo_start():
    """شروع یک Solo fight جدید"""
    user_id = g.user_id
    data = request.get_json() or {}
    player_card_id = data.get("player_card_id")
    difficulty = data.get("difficulty", "medium")

    if difficulty not in ("easy", "medium", "hard"):
        return jsonify({"error": "سختی نامعتبر است"}), 400

    used = db.get_daily_solo_count(user_id)
    if used >= DAILY_SOLO_LIMIT:
        return jsonify({"error": f"امروز {DAILY_SOLO_LIMIT} بار بازی کردی. فردا دوباره بیا."}), 429

    player = db.get_or_create_player(user_id)
    if player.hearts <= 0:
        return jsonify({"error": "قلب نداری! از شاپ بخر."}), 400

    if not player_card_id:
        return jsonify({"error": "کارت انتخاب‌شده معتبر نیست"}), 400

    player_card = db.get_card_by_id(player_card_id)
    if not player_card:
        return jsonify({"error": "کارت انتخاب‌شده معتبر نیست"}), 400

    player_cards = db.get_player_cards(user_id)
    player_card_ids = [c.card_id for c in player_cards]
    if player_card_id not in player_card_ids:
        return jsonify({"error": "این کارت مال تو نیست"}), 403

    aso = AsoAI(difficulty)
    ai_card = aso.select_card(db)
    if not ai_card:
        return jsonify({"error": "کارت AI پیدا نشد"}), 500

    # انتخاب arena — قوی‌تر انتخاب می‌کنه
    arena_id, selector = battle_system.select_arena(player_card, ai_card)
    if arena_id is None:
        arena_id = random.choice(list(ARENAS.keys()))

    arena_info = ARENAS[arena_id]

    fight_id = db.create_solo_fight(user_id, difficulty)
    db.update_solo_fight(
        fight_id,
        player_card_id=player_card_id,
        ai_card_id=ai_card.card_id,
        arena=arena_id,
        status="in_progress",
        player_current_stats=json.dumps({
            "power": player_card.power,
            "speed": player_card.speed,
            "iq": player_card.iq,
            "popularity": player_card.popularity,
        }),
        ai_current_stats=json.dumps({
            "power": ai_card.power,
            "speed": ai_card.speed,
            "iq": ai_card.iq,
            "popularity": ai_card.popularity,
        }),
    )

    return jsonify({
        "fight_id": fight_id,
        "player_card": card_to_dict(player_card),
        "ai_card": card_to_dict(ai_card),
        "ai_name": aso.mode["name"],
        "aso_dialog": aso.get_greeting(),
        "arena": {
            "arena_id": arena_id,
            "name_fa": arena_info["name_fa"],
            "boost_stat": arena_info["boost_stat"],
            "emoji": arena_info["emoji"],
        },
        "current_round": 1,
        "available_stats": ["power", "speed", "iq", "popularity"],
    })


@app.route("/api/v1/solo/round", methods=["POST"])
@require_auth
def solo_round():
    """بازی یک راوند"""
    user_id = g.user_id
    data = request.get_json() or {}
    fight_id = data.get("fight_id")
    player_stat = data.get("player_stat")

    if not fight_id or not player_stat:
        return jsonify({"error": "fight_id و player_stat الزامی است"}), 400

    fight = db.get_solo_fight(fight_id)
    if not fight or fight["player_id"] != user_id:
        return jsonify({"error": "Fight پیدا نشد"}), 404

    if fight["status"] != "in_progress":
        return jsonify({"error": "این fight تموم شده"}), 400

    player_used = json.loads(fight["player_used_stats"] or "[]")
    ai_used = json.loads(fight["ai_used_stats"] or "[]")
    available_stats = [s for s in ["power", "speed", "iq", "popularity"] if s not in player_used]

    if player_stat not in available_stats:
        return jsonify({"error": "این stat قبلاً استفاده شده"}), 400

    player_card = db.get_card_by_id(fight["player_card_id"])
    ai_card = db.get_card_by_id(fight["ai_card_id"])

    aso = AsoAI(fight["difficulty"])
    ai_available = [s for s in ["power", "speed", "iq", "popularity"] if s not in ai_used]
    ai_stat = aso.select_stat(ai_available, ai_card, player_card, fight["current_round"])

    player_current = json.loads(fight["player_current_stats"])
    ai_current = json.loads(fight["ai_current_stats"])

    player_base = player_current[player_stat]
    ai_base = ai_current[ai_stat]

    # محاسبه boost از arena
    arena_id = fight["arena"]
    player_boost = battle_system.calculate_boost(player_card, arena_id, player_stat)
    ai_boost = battle_system.calculate_boost(ai_card, arena_id, ai_stat)

    player_total = player_base + player_boost
    ai_total = ai_base + ai_boost

    # تعیین برنده راوند
    if player_total > ai_total:
        round_winner = "player"
        win_margin = player_total - ai_total
        reduction = 2 if win_margin >= 5 else 1
        ai_current[ai_stat] = max(0, ai_current[ai_stat] - reduction)
    elif ai_total > player_total:
        round_winner = "ai"
        win_margin = ai_total - player_total
        reduction = 2 if win_margin >= 5 else 1
        player_current[player_stat] = max(0, player_current[player_stat] - reduction)
    else:
        round_winner = "tie"

    player_rounds_won = fight["player_rounds_won"] + (1 if round_winner == "player" else 0)
    ai_rounds_won = fight["ai_rounds_won"] + (1 if round_winner == "ai" else 0)
    current_round = fight["current_round"] + 1

    player_used.append(player_stat)
    ai_used.append(ai_stat)

    rounds_history = json.loads(fight["rounds_history"] or "[]")
    rounds_history.append({
        "round": fight["current_round"],
        "player_stat": player_stat,
        "player_total": player_total,
        "ai_stat": ai_stat,
        "ai_total": ai_total,
        "winner": round_winner,
    })

    # بازی تموم میشه وقتی یکی ۲ راوند برنده بشه یا ۳ راوند بگذره
    game_over = player_rounds_won >= 2 or ai_rounds_won >= 2 or current_round > 3

    aso_dialog = aso.get_round_dialog(round_winner == "ai")

    update_data = {
        "player_rounds_won": player_rounds_won,
        "ai_rounds_won": ai_rounds_won,
        "current_round": current_round,
        "player_used_stats": json.dumps(player_used),
        "ai_used_stats": json.dumps(ai_used),
        "player_current_stats": json.dumps(player_current),
        "ai_current_stats": json.dumps(ai_current),
        "rounds_history": json.dumps(rounds_history),
    }
    if game_over:
        update_data["status"] = "completed"
        update_data["completed_at"] = datetime.now().isoformat()

    db.update_solo_fight(fight_id, **update_data)

    remaining_stats = [s for s in ["power", "speed", "iq", "popularity"] if s not in player_used]

    response = {
        "round_number": fight["current_round"],
        "player_stat": player_stat,
        "player_value": player_base,
        "player_boost": player_boost,
        "player_total": player_total,
        "ai_stat": ai_stat,
        "ai_value": ai_base,
        "ai_boost": ai_boost,
        "ai_total": ai_total,
        "round_winner": round_winner,
        "player_rounds_won": player_rounds_won,
        "ai_rounds_won": ai_rounds_won,
        "game_over": game_over,
        "next_round": current_round,
        "used_stats": {"player": player_used, "ai": ai_used},
        "available_stats": remaining_stats,
        "aso_dialog": aso_dialog,
    }

    if game_over:
        # در تساوی، بررسی می‌کنیم کی بیشتر راوند برده
        if player_rounds_won > ai_rounds_won:
            winner = "player"
        elif ai_rounds_won > player_rounds_won:
            winner = "ai"
        else:
            winner = "tie"
        rewards = _finalize_solo_fight(user_id, fight_id, winner, aso, player_card, ai_card)
        response["final_result"] = {
            "winner": winner,
            "aso_dialog": aso.get_result_dialog(winner == "ai"),
            "rewards": rewards,
            "rounds_detail": rounds_history,
        }

    return jsonify(response)


def _finalize_solo_fight(user_id, fight_id, winner, aso: AsoAI, player_card, ai_card) -> dict:
    """محاسبه و اعمال جوایز/جریمه‌های solo fight"""
    player = db.get_or_create_player(user_id)

    if winner == "player":
        rewards = aso.calculate_rewards()
        player.total_score += rewards["score"]
        db.save_player(player)
        old_level, new_level = db.add_xp(user_id, rewards["xp"])
        old_tier, new_tier = db.add_tier_points(user_id, rewards["tier_points"])
        db.increment_daily_solo_count(user_id)
        _record_solo_history(user_id, player_card, ai_card, "win", rewards["score"], 0, rewards["xp"])
        return {
            "score_gained": rewards["score"],
            "xp_gained": rewards["xp"],
            "tier_points_change": rewards["tier_points"],
            "hearts_lost": 0,
            "level_up": new_level > old_level,
            "new_level": new_level if new_level > old_level else None,
            "tier_change": new_tier if new_tier != old_tier else None,
        }
    elif winner == "ai":
        penalty = aso.calculate_defeat_penalty()
        player.hearts = max(0, player.hearts - penalty["hearts_lost"])
        db.save_player(player)
        old_level, new_level = db.add_xp(user_id, penalty["xp"])
        db.increment_daily_solo_count(user_id)
        _record_solo_history(user_id, player_card, ai_card, "loss", 0, penalty["hearts_lost"], penalty["xp"])
        return {
            "score_gained": 0,
            "xp_gained": penalty["xp"],
            "tier_points_change": -5,
            "hearts_lost": penalty["hearts_lost"],
            "hearts_remaining": player.hearts,
            "level_up": False,
            "new_level": None,
            "tier_change": None,
        }
    else:  # tie
        db.increment_daily_solo_count(user_id)
        _record_solo_history(user_id, player_card, ai_card, "tie", 0, 0, 2)
        db.add_xp(user_id, 2)
        return {
            "score_gained": 0,
            "xp_gained": 2,
            "tier_points_change": 0,
            "hearts_lost": 0,
            "level_up": False,
            "new_level": None,
            "tier_change": None,
        }


def _record_solo_history(user_id, player_card, ai_card, result, score, hearts_lost, xp):
    """ذخیره در fight_history"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO fight_history
        (user_id, user_card_id, opponent_card_id, result, score_gained,
         hearts_lost, fought_at, fight_type, xp_gained)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'solo', ?)
    ''', (user_id, player_card.card_id, ai_card.card_id, result,
          score, hearts_lost, datetime.now().isoformat(), xp))
    conn.commit()
    conn.close()


@app.route("/api/v1/solo/result/<fight_id>", methods=["GET"])
@require_auth
def solo_result(fight_id):
    """دریافت نتیجه نهایی یک fight تموم‌شده"""
    user_id = g.user_id
    fight = db.get_solo_fight(fight_id)
    if not fight or fight["player_id"] != user_id:
        return jsonify({"error": "Fight پیدا نشد"}), 404

    player = db.get_or_create_player(user_id)
    return jsonify({
        "fight_id": fight_id,
        "status": fight["status"],
        "player_rounds_won": fight["player_rounds_won"],
        "ai_rounds_won": fight["ai_rounds_won"],
        "rounds_detail": json.loads(fight["rounds_history"] or "[]"),
        "player_after": {
            "hearts": player.hearts,
            "total_score": player.total_score,
        }
    })


# ==================== Routes: Leaderboard ====================

@app.route("/api/v1/leaderboard", methods=["GET"])
@require_auth
def get_leaderboard():
    period = request.args.get("period", "weekly")
    limit = min(int(request.args.get("limit", 50)), 100)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT user_id, username, first_name, total_score
        FROM players
        ORDER BY total_score DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()

    user_id = g.user_id
    my_rank = None
    my_score = None
    cursor.execute(
        'SELECT COUNT(*)+1 FROM players WHERE total_score > (SELECT total_score FROM players WHERE user_id = ?)',
        (user_id,)
    )
    rank_row = cursor.fetchone()
    if rank_row:
        my_rank = rank_row[0]
    cursor.execute('SELECT total_score FROM players WHERE user_id = ?', (user_id,))
    score_row = cursor.fetchone()
    if score_row:
        my_score = score_row[0]

    conn.close()

    entries = []
    for i, row in enumerate(rows):
        entries.append({
            "rank": i + 1,
            "user_id": row["user_id"],
            "username": row["username"] or "",
            "first_name": row["first_name"] or "",
            "score": row["total_score"],
        })

    return jsonify({
        "period": period,
        "my_rank": my_rank,
        "my_score": my_score,
        "entries": entries,
    })


# ==================== اجرا ====================

def run_miniapp_server(host="0.0.0.0", port=5001, debug=False):
    debug_mode = debug or os.environ.get("FLASK_DEBUG", "0") == "1"
    # use_reloader=False چون در thread اجرا میشه
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False)


if __name__ == "__main__":
    run_miniapp_server(debug=True)
