#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TelBattle Mini App — Flask REST API
"""

import json
import hmac
import hashlib
import os
import random
import sqlite3
import logging
from datetime import datetime, timedelta
from urllib.parse import unquote, parse_qs
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from game_core import DatabaseManager, CardRarity
from ai_opponent import AsoAI, DAILY_SOLO_LIMIT
from battle_system_3rounds import BattleSystem3Rounds, ARENAS

logger = logging.getLogger(__name__)

# ==================== تنظیمات ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", "game_bot.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

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

app = Flask(__name__,
    static_folder=os.path.join(BASE_DIR, "miniapp"),
    static_url_path="/miniapp")
db = DatabaseManager(DB_PATH)
battle_system = BattleSystem3Rounds(db)

# ==================== احراز هویت ====================

def verify_telegram_init_data(init_data: str):
    """
    بررسی صحت initData تلگرام.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    برگشت: دیکشنری user یا None
    """
    try:
        parsed = parse_qs(unquote(init_data))
        data_check_string_parts = []
        hash_value = ""
        for key, values in sorted(parsed.items()):
            if key == "hash":
                hash_value = values[0]
            else:
                data_check_string_parts.append(f"{key}={values[0]}")
        data_check_string = "\n".join(data_check_string_parts)

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_hash, hash_value):
            return None

        user_str = parsed.get("user", ["{}"])[0]
        return json.loads(user_str)
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
            user = verify_telegram_init_data(init_data)
            if user:
                g.user_id = user["id"]
                db.get_or_create_player(
                    user_id=user["id"],
                    username=user.get("username", ""),
                    first_name=user.get("first_name", "")
                )
                return f(*args, **kwargs)
            # initData invalid — اگه debug mode، ادامه بده
            if not (app.debug or os.environ.get("FLASK_DEBUG", "0") == "1"):
                return jsonify({"error": "Invalid initData"}), 401

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
                        return f(*args, **kwargs)
                except Exception:
                    pass
            # fallback به X-Debug-User-Id
            debug_user = request.headers.get("X-Debug-User-Id", "1")
            g.user_id = int(debug_user)
            db.get_or_create_player(user_id=g.user_id)
            return f(*args, **kwargs)

        return jsonify({"error": "Unauthorized"}), 401
    return decorated


# ==================== Helper ====================

def card_to_dict(card) -> dict:
    """تبدیل Card object به دیکشنری برای JSON"""
    try:
        abilities = json.loads(card.abilities) if isinstance(card.abilities, str) else (card.abilities or [])
    except Exception:
        abilities = []
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
    }


@app.route("/api/v1/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ==================== Routes: Static ====================

@app.route("/")
@app.route("/miniapp")
def serve_miniapp():
    return send_from_directory("miniapp", "index.html")


# ==================== Routes: Profile ====================

@app.route("/api/v1/profile", methods=["GET"])
@require_auth
def get_profile():
    user_id = g.user_id
    player = db.get_or_create_player(user_id)
    prog = db.get_player_progression_full(user_id)
    stats = db.get_fight_stats(user_id)
    cards = db.get_player_cards(user_id)

    try:
        from phase2_systems import LevelSystem
        lvl_sys = LevelSystem()
        xp_for_next = lvl_sys.xp_for_next_level(prog.get("level", 1))
    except Exception:
        xp_for_next = 100

    best_card = None
    if cards:
        best = max(cards, key=lambda c: c.power + c.speed + c.iq + c.popularity)
        best_card = card_to_dict(best)

    return jsonify({
        "user_id": user_id,
        "first_name": player.first_name,
        "username": player.username or "",
        "hearts": player.hearts,
        "max_hearts": player.max_hearts,
        "coins": player.coins,
        "total_score": player.total_score,
        "level": prog.get("level", 1),
        "current_xp": prog.get("total_xp", 0) % (xp_for_next or 100),
        "xp_to_next_level": xp_for_next,
        "current_tier": prog.get("current_tier", "Bronze"),
        "tier_points": prog.get("tier_points", 0),
        "stats": stats,
        "best_card": best_card,
    })


# ==================== Routes: Cards ====================

@app.route("/api/v1/cards", methods=["GET"])
@require_auth
def get_cards():
    user_id = g.user_id
    rarity_filter = request.args.get("rarity", "all")
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))

    if rarity_filter != "all":
        try:
            rarity_enum = CardRarity(rarity_filter)
            cards, total = db.get_player_cards_by_rarity(user_id, rarity_enum, page, limit)
        except ValueError:
            cards, total = db.get_player_cards_by_rarity(user_id, None, page, limit)
    else:
        cards, total = db.get_player_cards_by_rarity(user_id, None, page, limit)

    result = []
    for card in cards:
        cd = db.is_card_in_cooldown(user_id, card.card_id) if hasattr(db, 'is_card_in_cooldown') else False
        d = card_to_dict(card)
        d["is_in_cooldown"] = bool(cd)
        result.append(d)

    return jsonify({"total": total, "page": page, "cards": result})


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
