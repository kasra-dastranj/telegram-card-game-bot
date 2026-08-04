from datetime import datetime, timedelta, timezone

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.game_mode_system import GameModeSystem


def _card(card_id: str, power: int, speed: int, iq: int, popularity: int) -> Card:
    return Card(
        card_id=card_id,
        name=card_id.title(),
        rarity=CardRarity.NORMAL,
        power=power,
        speed=speed,
        iq=iq,
        popularity=popularity,
        abilities=[],
    )


@pytest.fixture()
def mode_system(tmp_path):
    db = DatabaseManager(str(tmp_path / "modes.sqlite"))
    cards = [
        _card("alpha", 90, 30, 40, 50),
        _card("beta", 20, 80, 95, 40),
        _card("gamma", 55, 60, 65, 70),
        _card("delta", 45, 35, 25, 90),
        _card("omega", 75, 75, 75, 75),
    ]
    for card in cards:
        assert db.add_card(card)
    for user_id in (1, 2, 3):
        db.get_or_create_player(user_id, first_name=f"P{user_id}")
        for card in cards:
            assert db.add_card_to_player(user_id, card.card_id)
    return GameModeSystem(db)


def test_invite_is_one_time_and_cannot_be_self_accepted(mode_system):
    request = mode_system.create_invite(1, "quick", "normal")

    ok, reason, _ = mode_system.accept_invite(request["invite_token"], 1)
    assert not ok
    assert reason == "self_accept"

    ok, reason, accepted = mode_system.accept_invite(request["invite_token"], 2)
    assert ok
    assert reason == "accepted"
    assert accepted["opponent_id"] == 2

    ok, reason, _ = mode_system.accept_invite(request["invite_token"], 3)
    assert not ok
    assert reason == "accepted"


def test_expired_invite_is_rejected(mode_system):
    request = mode_system.create_invite(1, "quick", "normal")
    conn = mode_system._connect()
    conn.execute(
        "UPDATE game_requests SET expires_at=? WHERE request_id=?",
        ((datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)).isoformat(), request["request_id"]),
    )
    conn.commit()
    conn.close()

    ok, reason, _ = mode_system.accept_invite(request["invite_token"], 2)
    assert not ok
    assert reason == "expired"
    assert mode_system.get_request(request["request_id"])["status"] == "expired"


def test_random_queue_only_matches_same_variant(mode_system):
    status, normal = mode_system.matchmake_random(1, "quick", "normal")
    assert status == "waiting"

    status, random_request = mode_system.matchmake_random(2, "quick", "random")
    assert status == "waiting"
    assert random_request["request_id"] != normal["request_id"]

    status, matched = mode_system.matchmake_random(3, "quick", "normal")
    assert status == "matched"
    assert matched["request_id"] == normal["request_id"]
    assert matched["opponent_id"] == 3


def test_quick_choices_are_locked_and_report_is_persisted(mode_system, monkeypatch):
    request = mode_system.create_group_challenge(1, "quick", "normal", -100)
    ok, _, _ = mode_system.accept_request(request["request_id"], 2)
    assert ok
    state = mode_system.start_quick_match(request["request_id"])
    assert state["phase"] == "card_selection"

    mode_system.select_quick_card(request["request_id"], 1, "alpha")
    with pytest.raises(ValueError, match="choice_locked"):
        mode_system.select_quick_card(request["request_id"], 1, "beta")

    state, advanced = mode_system.select_quick_card(request["request_id"], 2, "beta")
    assert advanced
    assert state["phase"] == "ability_selection"

    mode_system.select_quick_ability(request["request_id"], 1, "skip")
    state, advanced = mode_system.select_quick_ability(request["request_id"], 2, "skip")
    assert advanced
    assert state["phase"] == "stat_selection"

    allowed_1 = mode_system.allowed_quick_stats(state, 1)
    allowed_2 = mode_system.allowed_quick_stats(state, 2)
    mode_system.select_quick_stat(request["request_id"], 1, allowed_1[0])
    _, report = mode_system.select_quick_stat(request["request_id"], 2, allowed_2[0])

    assert report is not None
    assert report["request_id"] == request["request_id"]
    assert mode_system.get_report(request["request_id"]) == report
    assert mode_system.get_request(request["request_id"])["status"] == "completed"


def test_easy_first_choice_is_final_and_ties_share_points(mode_system):
    request = mode_system.create_easy_lobby(1, -100, rounds=1)
    ok, _, _ = mode_system.join_easy_lobby(request["request_id"], 2)
    assert ok
    ok, _, state = mode_system.start_easy_match(request["request_id"])
    assert ok

    # Make the option lists deterministic for this focused state-machine test.
    conn = mode_system._connect()
    state["options"] = {"1": ["alpha"], "2": ["alpha"]}
    conn.execute(
        "UPDATE game_match_states SET state_json=? WHERE request_id=?",
        (__import__("json").dumps(state), request["request_id"]),
    )
    conn.commit()
    conn.close()

    ok, reason, _ = mode_system.select_easy_card(request["request_id"], 1, "alpha")
    assert ok and reason == "selected"
    ok, reason, _ = mode_system.select_easy_card(request["request_id"], 1, "beta")
    assert not ok and reason == "choice_locked"
    ok, reason, _ = mode_system.select_easy_card(request["request_id"], 2, "alpha")
    assert ok and reason == "all_selected"

    result = mode_system.resolve_easy_round(request["request_id"])
    assert result["completed"]
    assert result["report"]["scores"] == {"1": 3, "2": 3}


def test_deck_round_prefers_trait_tier_then_uses_arena_stat(mode_system):
    mode_system.set_card_metadata("alpha", traits=["God"])
    mode_system.set_card_metadata("beta", traits=["Hero"])
    battle = BattleSystem3Rounds(mode_system.db)

    trait_result = battle.resolve_deck_cards(
        mode_system.db.get_card_by_id("alpha"),
        mode_system.db.get_card_by_id("beta"),
        "power_arena",
    )
    assert trait_result["winner"] == "challenger"
    assert trait_result["reason"] == "trait"
    assert trait_result["challenger_trait_rank"] == 1

    stat_result = battle.resolve_deck_cards(
        mode_system.db.get_card_by_id("gamma"),
        mode_system.db.get_card_by_id("delta"),
        "power_arena",
    )
    assert stat_result["winner"] == "challenger"
    assert stat_result["reason"] == "stat"
    assert stat_result["challenger_value"] == 55


def test_deck_synergy_uses_series_and_common_trait(mode_system):
    for card_id in ("alpha", "beta", "gamma"):
        mode_system.set_card_metadata(card_id, traits=["Hero"], series="Telverse")

    synergy = mode_system.calculate_deck_synergy(["alpha", "beta", "gamma"])
    assert synergy["score"] == 7
    assert len(synergy["reasons"]) == 2


def test_easy_composite_questions_only_offer_eligible_cards(mode_system):
    mode_system.set_card_metadata("alpha", traits=["Hero"], series="Telverse")
    mode_system.set_card_metadata("beta", traits=["Villain"], series="Other")
    pool = mode_system._easy_question_pool([1, 2])
    assert any(question.get("trait") == "Hero" for question in pool)
    assert any(question.get("series") == "Telverse" for question in pool)

    request = mode_system.create_easy_lobby(1, -100, rounds=1)
    mode_system.join_easy_lobby(request["request_id"], 2)
    _, _, state = mode_system.start_easy_match(request["request_id"])
    state["question"] = {
        "id": "trait:hero:iq",
        "text": "Hero IQ",
        "attribute": "iq",
        "trait": "Hero",
    }
    state["options"] = {}
    conn = mode_system._connect()
    conn.execute(
        "UPDATE game_match_states SET state_json=? WHERE request_id=?",
        (__import__("json").dumps(state), request["request_id"]),
    )
    conn.commit()
    conn.close()

    assert [card.card_id for card in mode_system.get_easy_options(request["request_id"], 1)] == ["alpha"]
