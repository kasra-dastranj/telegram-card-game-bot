"""Gameplay regressions exercised against disposable databases only."""

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from threading import Barrier

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.economy_system import EconomySystem
from systems.arena_registry import ArenaRegistry
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.risk_mode_system import RiskModeSystem, RiskTable, RiskAction
import web.miniapp_api as miniapp


@pytest.fixture
def game_db(tmp_path):
    db = DatabaseManager(str(tmp_path / "integrity.db"))
    for uid in (101, 202):
        player = db.get_or_create_player(uid)
        player.coins = 1000
        db.update_player(player)
        db.get_or_create_progression(uid)
        db.update_progression(uid, level=7)
    for index in range(5):
        card = Card(f"card{index}", f"Card {index}", CardRarity.NORMAL, 10, 10, 10, 10, [])
        db.add_card(card)
        db.add_card_to_player(101, card.card_id)
    return db


@pytest.mark.parametrize("amount", [-50, 0])
def test_spending_invalid_amount_never_creates_money(game_db, amount):
    assert not game_db.spend_coins(101, amount)[0]
    assert game_db.get_or_create_player(101).coins == 1000


@pytest.mark.parametrize("via_economy", [False, True])
def test_concurrent_spending_cannot_overdraw(game_db, via_economy):
    spender = EconomySystem(game_db) if via_economy else game_db
    gate = Barrier(8)

    def spend(_):
        gate.wait(timeout=10)
        return spender.spend_coins(101, 1000)[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(spend, range(8)))
    assert sum(results) == 1
    assert game_db.get_or_create_player(101).coins == 0


def test_concurrent_mining_only_pays_once(game_db):
    economy = EconomySystem(game_db)
    gate = Barrier(8)

    def claim(_):
        gate.wait(timeout=10)
        return economy.claim_daily_mining(101)[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert sum(results) == 1
    assert economy.get_coins(101) == 1001


@pytest.fixture
def solo_client(game_db, monkeypatch):
    monkeypatch.setattr(miniapp, "db", game_db)
    monkeypatch.setattr(miniapp, "DB_PATH", game_db.db_path)
    monkeypatch.setattr(miniapp, "arena_registry", ArenaRegistry(game_db))
    monkeypatch.setattr(miniapp, "battle_system", BattleSystem3Rounds(game_db))
    monkeypatch.setitem(miniapp.app.config, "TESTING", True)
    monkeypatch.setitem(miniapp.app.config, "DEBUG", True)
    return miniapp.app.test_client()


HEADERS = {"X-Debug-User-Id": "101"}


def start_solo(client):
    response = client.post("/api/v1/solo/start", json={"player_card_id": "card0", "difficulty": "easy"}, headers=HEADERS)
    assert response.status_code == 200
    return response.get_json()


def prepare_final_round(db, fight_id, *, losing=False):
    db.update_solo_fight(
        fight_id, current_round=2, player_rounds_won=0 if losing else 1,
        ai_rounds_won=1 if losing else 0, player_used_stats='["power"]',
        ai_used_stats='["power"]',
        player_current_stats=json.dumps(dict.fromkeys(("power", "speed", "iq", "popularity"), 1 if losing else 100)),
        ai_current_stats=json.dumps(dict.fromkeys(("power", "speed", "iq", "popularity"), 100 if losing else 1)),
    )


def test_solo_uses_owned_upgraded_card(solo_client, game_db):
    game_db.set_player_card_rarity_override(101, "card0", "epic")
    owned = game_db.get_card_by_id_for_player("card0", 101)
    payload = start_solo(solo_client)
    assert payload["player_card"]["rarity"] == "epic"
    fight = game_db.get_solo_fight(payload["fight_id"])
    assert json.loads(fight["player_current_stats"])["power"] == owned.power


def test_solo_defeat_applies_advertised_tier_penalty(solo_client, game_db):
    game_db.update_progression(101, tier_points=50)
    fight = start_solo(solo_client)
    prepare_final_round(game_db, fight["fight_id"], losing=True)
    response = solo_client.post("/api/v1/solo/round", json={"fight_id": fight["fight_id"], "player_stat": "speed"}, headers=HEADERS)
    assert response.status_code == 200
    rewards = response.get_json()["final_result"]["rewards"]
    assert game_db.get_or_create_progression(101)["tier_points"] == 50 + rewards["tier_points_change"]


def test_solo_failed_reward_rolls_back_round(solo_client, game_db):
    fight_id = start_solo(solo_client)["fight_id"]
    prepare_final_round(game_db, fight_id)
    before = game_db.get_or_create_player(101).total_score
    with sqlite3.connect(game_db.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_history BEFORE INSERT ON fight_history BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        solo_client.post("/api/v1/solo/round", json={"fight_id": fight_id, "player_stat": "speed"}, headers=HEADERS)
    assert game_db.get_solo_fight(fight_id)["status"] == "in_progress"
    assert game_db.get_solo_fight(fight_id)["current_round"] == 2
    assert game_db.get_or_create_player(101).total_score == before
    assert game_db.get_daily_solo_count(101) == 0


def test_risk_tie_advances_and_clears_selection(game_db):
    risk = RiskModeSystem(game_db)
    match_id = risk.create_risk_match(101, 202, RiskTable.TABLE_50)["match_id"]
    match = risk.get_risk_match(match_id)
    for uid, role in ((101, "challenger"), (202, "opponent")):
        risk.select_card(match_id, uid, match[f"{role}_cards"][0])
    assert risk.resolve_round(match_id)["winner"] == "tie"
    after = risk.get_risk_match(match_id)
    assert after["current_round"] == 2
    assert after["challenger_selected_card"] is None
    assert not risk.resolve_round(match_id)["success"]


def test_risk_outsider_cannot_fold_and_fold_cannot_pay_twice(game_db):
    risk = RiskModeSystem(game_db)
    match_id = risk.create_risk_match(101, 202, RiskTable.TABLE_50)["match_id"]
    assert not risk.make_action(match_id, 303, RiskAction.FOLD)["success"]
    assert risk.make_action(match_id, 101, RiskAction.FOLD)["success"]
    assert not risk.make_action(match_id, 101, RiskAction.FOLD)["success"]
    assert game_db.get_or_create_player(202).coins == 1050


def test_concurrent_score_conversion_cannot_overdraw(game_db):
    with sqlite3.connect(game_db.db_path) as conn:
        conn.execute("UPDATE players SET total_score=100 WHERE user_id=101")
    economy = EconomySystem(game_db)
    gate = Barrier(8)

    def convert(_):
        gate.wait(timeout=10)
        return economy.convert_score_to_coins(101, 100)[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(convert, range(8)))
    assert sum(results) == 1
    player = game_db.get_or_create_player(101)
    assert (player.total_score, player.coins) == (0, 1001)


def test_last_heart_upgrade_is_only_charged_once(game_db):
    with sqlite3.connect(game_db.db_path) as conn:
        conn.execute("UPDATE players SET max_hearts=14 WHERE user_id=101")
    economy = EconomySystem(game_db)
    gate = Barrier(4)

    def buy(_):
        gate.wait(timeout=10)
        return economy.buy_heart_increase(101)[0]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(buy, range(4)))
    assert sum(results) == 1
    player = game_db.get_or_create_player(101)
    assert (player.max_hearts, player.coins) == (15, 800)


def test_concurrent_solo_finish_awards_once(solo_client, game_db):
    fight_id = start_solo(solo_client)["fight_id"]
    prepare_final_round(game_db, fight_id)
    gate = Barrier(4)

    def finish(_):
        with miniapp.app.test_client() as client:
            gate.wait(timeout=10)
            return client.post("/api/v1/solo/round", json={"fight_id": fight_id, "player_stat": "speed"}, headers=HEADERS).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(finish, range(4)))
    assert statuses.count(200) == 1
    assert statuses.count(400) == 3
    assert game_db.get_daily_solo_count(101) == 1
    assert game_db.get_or_create_player(101).total_score == 3
    with sqlite3.connect(game_db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fight_history WHERE user_id=101").fetchone()[0] == 1


def test_started_solo_fights_cannot_bypass_daily_limit(solo_client, game_db):
    first = start_solo(solo_client)["fight_id"]
    second = start_solo(solo_client)["fight_id"]
    for fight_id in (first, second):
        prepare_final_round(game_db, fight_id)
    for _ in range(miniapp.DAILY_SOLO_LIMIT - 1):
        game_db.increment_daily_solo_count(101)
    results = [solo_client.post("/api/v1/solo/round", json={"fight_id": fid, "player_stat": "speed"}, headers=HEADERS) for fid in (first, second)]
    assert [r.status_code for r in results] == [200, 429]
    assert game_db.get_daily_solo_count(101) == miniapp.DAILY_SOLO_LIMIT


def test_risk_failed_creation_refunds_both_players(game_db):
    with sqlite3.connect(game_db.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_risk BEFORE INSERT ON risk_matches BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    result = RiskModeSystem(game_db).create_risk_match(101, 202, RiskTable.TABLE_50)
    assert not result["success"]
    assert game_db.get_or_create_player(101).coins == 1000
    assert game_db.get_or_create_player(202).coins == 1000


@pytest.mark.parametrize("legacy_id", [False, True])
def test_risk_bot_buttons_complete_three_ties_and_refund_raises(game_db, legacy_id):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from bot.handlers.risk import RiskHandlersMixin

    handler = RiskHandlersMixin()
    handler.db = game_db
    handler.risk = RiskModeSystem(game_db)
    match_id = handler.risk.create_risk_match(101, 202, RiskTable.TABLE_50, -100)["match_id"]
    if legacy_id:
        old_id = match_id
        match_id = "risk_101_202_1234567890"
        with sqlite3.connect(game_db.db_path) as conn:
            conn.execute("UPDATE risk_matches SET match_id=? WHERE match_id=?", (match_id, old_id))
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    async def press(uid, data, method):
        query = SimpleNamespace(from_user=SimpleNamespace(id=uid), data=data,
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        await method(SimpleNamespace(callback_query=query), context)

    async def play():
        for round_number in (1, 2, 3):
            match = handler.risk.get_risk_match(match_id)
            for uid, role in ((101, "challenger"), (202, "opponent")):
                card_id = match[f"{role}_cards"][0]
                await press(uid, f"risk_card_{match_id}_{card_id}", handler.risk_card_select_handler)
            assert handler.risk.get_risk_match(match_id)["bluff_phase"] == "waiting"
            await press(101, f"risk_bluff_{match_id}_raise_50", handler.risk_bluff_handler)
            assert handler.risk.get_risk_match(match_id)["bluff_phase"] == "raise_pending"
            await press(202, f"risk_bluff_{match_id}_call", handler.risk_bluff_handler)
            assert handler.risk.get_risk_match(match_id)["current_round"] == round_number + 1

    asyncio.run(play())
    assert handler.risk.get_risk_match(match_id)["status"] == "completed"
    assert game_db.get_or_create_player(101).coins == 1000
    assert game_db.get_or_create_player(202).coins == 1000
    assert not handler.risk.resolve_round(match_id)["success"]
    assert not handler.risk.make_action(match_id, 101, RiskAction.FOLD)["success"]


def test_risk_concurrent_fold_pays_pot_once(game_db):
    risk = RiskModeSystem(game_db)
    match_id = risk.create_risk_match(101, 202, RiskTable.TABLE_50)["match_id"]
    gate = Barrier(4)

    def fold(_):
        gate.wait(timeout=10)
        return risk.make_action(match_id, 101, RiskAction.FOLD)["success"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fold, range(4)))
    assert sum(results) == 1
    assert game_db.get_or_create_player(202).coins == 1050


@pytest.fixture
def quick_game(game_db):
    from systems.game_mode_system import GameModeSystem
    game_db.add_card_to_player(202, "card1")
    modes = GameModeSystem(game_db)
    invite = modes.create_invite(101, "quick", "normal")
    assert modes.accept_invite(invite["invite_token"], 202)[0]
    return modes, invite["request_id"]


def test_quick_start_does_not_overwrite_persisted_choice(quick_game, monkeypatch):
    modes, request_id = quick_game
    modes.start_quick_match(request_id)
    modes.select_quick_card(request_id, 101, "card0")
    # Model a second starter whose earlier read saw no state yet.
    with monkeypatch.context() as patch:
        patch.setattr(modes, "get_state", lambda _: None)
        resumed = modes.start_quick_match(request_id)
    assert resumed["cards"] == {"101": "card0"}
    assert modes.get_state(request_id)["cards"] == {"101": "card0"}


def test_stale_quick_timeout_cannot_end_next_phase(quick_game):
    modes, request_id = quick_game
    modes.start_quick_match(request_id)
    modes.select_quick_card(request_id, 101, "card0")
    modes.select_quick_card(request_id, 202, "card1")
    with pytest.raises(ValueError):
        modes.forfeit_quick(request_id, [202], reason="card_selection_timeout")
    assert modes.get_state(request_id)["phase"] == "ability_selection"
    assert modes.get_report(request_id) is None


def test_risk_normal_victory_pays_once(game_db):
    strong = Card("strong", "Strong", CardRarity.NORMAL, 100, 100, 100, 100, [])
    weak = Card("weak", "Weak", CardRarity.NORMAL, 1, 1, 1, 1, [])
    game_db.add_card(strong)
    game_db.add_card(weak)
    risk = RiskModeSystem(game_db)
    match_id = risk.create_risk_match(101, 202, RiskTable.TABLE_50)["match_id"]
    with sqlite3.connect(game_db.db_path) as conn:
        conn.execute("UPDATE risk_matches SET challenger_cards='strong',opponent_cards='weak' WHERE match_id=?", (match_id,))
    for _ in range(2):
        assert risk.select_card(match_id, 101, "strong")["success"]
        assert risk.select_card(match_id, 202, "weak")["success"]
        result = risk.resolve_round(match_id)
    assert result["game_over"] and result["winner_id"] == 101
    assert game_db.get_or_create_player(101).coins == 1050
    assert game_db.get_or_create_player(202).coins == 950
    assert game_db.get_or_create_progression(101)["total_xp"] == 25
    assert game_db.get_or_create_progression(202)["total_xp"] == 5
    assert not risk.resolve_round(match_id)["success"]


def test_solo_pending_match_cannot_play_without_hearts(solo_client, game_db):
    fight_id = start_solo(solo_client)["fight_id"]
    with sqlite3.connect(game_db.db_path) as conn:
        conn.execute("UPDATE players SET hearts=0 WHERE user_id=101")
    response = solo_client.post("/api/v1/solo/round", json={"fight_id": fight_id, "player_stat": "speed"}, headers=HEADERS)
    assert response.status_code == 400
    assert game_db.get_solo_fight(fight_id)["current_round"] == 1
