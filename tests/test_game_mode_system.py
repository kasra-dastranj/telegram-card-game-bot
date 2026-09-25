from datetime import datetime, timedelta, timezone

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.game_mode_system import GameModeSystem, bidi_isolate


def _card(
    card_id: str,
    power: int,
    speed: int,
    iq: int,
    popularity: int,
    card_type: str = "POWER_TYPE",
) -> Card:
    return Card(
        card_id=card_id,
        name=card_id.title(),
        rarity=CardRarity.NORMAL,
        power=power,
        speed=speed,
        iq=iq,
        popularity=popularity,
        abilities=[],
        card_type=card_type,
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


def test_cancel_fight_if_expired_only_touches_requested_fight(tmp_path):
    db = DatabaseManager(str(tmp_path / "scoped-expiry.sqlite"))
    expired_id = db.create_fight(1, 2, -1001)
    active_id = db.create_fight(3, 4, -1002)
    db.update_fight(
        expired_id,
        expires_at=(datetime.now() - timedelta(seconds=1)).isoformat(),
    )
    db.update_fight(
        active_id,
        expires_at=(datetime.now() + timedelta(minutes=5)).isoformat(),
    )

    assert db.cancel_fight_if_expired(expired_id)
    assert db.get_fight_by_id(expired_id).status.value == "cancelled"
    assert db.get_fight_by_id(active_id).status.value != "cancelled"


def test_inline_private_challenge_persists_editable_message_reference(mode_system):
    request = mode_system.create_inline_private_challenge(1, "deck", "random")
    mode_system.update_inline_message_reference(request["request_id"], "inline-message-42")

    stored = mode_system.get_request(request["request_id"])
    assert stored["source"] == "inline_private"
    assert stored["origin_chat_id"] == 1
    assert stored["origin_inline_message_id"] == "inline-message-42"


def test_inline_private_challenge_rejects_invalid_mode(mode_system):
    with pytest.raises(ValueError, match="invalid_inline_game"):
        mode_system.create_inline_private_challenge(1, "easy", "normal")


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


def test_quick_stat_preview_matches_resolution_math(mode_system):
    mode_system.set_card_metadata(
        "alpha",
        passive={
            "name": "Desert strength",
            "condition": {"arena": "desert"},
            "effect": {"stat": "power", "delta": 3},
        },
    )
    state = {
        "players": [1, 2],
        "cards": {"1": "alpha", "2": "beta"},
        "arena": "desert",
        "ability_choices": {"1": "skip", "2": "weaken_power"},
    }

    preview = mode_system.quick_stat_preview(state, 1)

    assert preview["card_name"] == "Alpha"
    assert preview["base_values"] == {"power": 90, "speed": 30, "iq": 40, "popularity": 50}
    assert preview["final_values"] == {"power": 93, "speed": 30, "iq": 40, "popularity": 50}
    assert preview["arena_effects"] == [
        {"card_type": "power", "stat": "power", "delta": 2}
    ]
    assert preview["passive"] == {"name": "Desert strength", "stat": "power", "delta": 3}
    assert preview["opponent_ability_effect"] == {
        "ability": "weaken_power",
        "stat": "power",
        "delta": -2,
    }


@pytest.mark.parametrize(
    "first_stat,second_stat,first_parts,second_parts,winner",
    [
        ("power", "iq", [90, 40], [95, 20], 1),
        ("power", "power", [90, 90], [20, 20], 1),
    ],
)
def test_quick_adds_both_selected_stats_for_each_card(
    mode_system, monkeypatch, first_stat, second_stat, first_parts, second_parts, winner
):
    monkeypatch.setattr(mode_system, "_random_arena", lambda exclude=None: mode_system._arena("null_zone"))
    request = mode_system.create_group_challenge(1, "quick", "normal", -100)
    assert mode_system.accept_request(request["request_id"], 2)[0]
    mode_system.start_quick_match(request["request_id"])
    mode_system.select_quick_card(request["request_id"], 1, "alpha")
    mode_system.select_quick_card(request["request_id"], 2, "beta")
    mode_system.select_quick_ability(request["request_id"], 1, "skip")
    mode_system.select_quick_ability(request["request_id"], 2, "skip")
    mode_system.select_quick_stat(request["request_id"], 1, first_stat)
    _, report = mode_system.select_quick_stat(request["request_id"], 2, second_stat)

    assert report["winner_id"] == winner
    assert report["breakdown"]["1"]["scored_stats"] == [first_stat, second_stat]
    assert report["breakdown"]["2"]["scored_stats"] == [second_stat, first_stat]
    assert report["breakdown"]["1"]["base_components"] == first_parts
    assert report["breakdown"]["2"]["base_components"] == second_parts
    assert report["breakdown"]["1"]["final_value"] == sum(first_parts)
    assert report["breakdown"]["2"]["final_value"] == sum(second_parts)


def test_quick_effects_apply_to_both_stats_before_sum(mode_system, monkeypatch):
    mode_system.set_card_metadata(
        "alpha",
        passive={"name": "Desert strength", "condition": {"arena": "desert"},
                 "effect": {"stat": "power", "delta": 3}},
    )
    monkeypatch.setattr(mode_system, "_random_arena", lambda exclude=None: mode_system._arena("desert"))
    request = mode_system.create_group_challenge(1, "quick", "normal", -100)
    assert mode_system.accept_request(request["request_id"], 2)[0]
    mode_system.start_quick_match(request["request_id"])
    mode_system.select_quick_card(request["request_id"], 1, "alpha")
    mode_system.select_quick_card(request["request_id"], 2, "beta")
    mode_system.grant_ability(2, "weaken_power")
    mode_system.select_quick_ability(request["request_id"], 1, "skip")
    mode_system.select_quick_ability(request["request_id"], 2, "weaken_power")
    mode_system.select_quick_stat(request["request_id"], 1, "power")
    _, report = mode_system.select_quick_stat(request["request_id"], 2, "iq")

    first = report["breakdown"]["1"]
    second = report["breakdown"]["2"]
    assert first["base_components"] == [90, 40]
    assert first["final_components"] == [93, 40]  # +2 arena, +3 passive, -2 ability
    assert first["final_value"] == 133
    assert second["final_components"] == [95, 22]  # Beta's power also gets desert +2.
    assert second["final_value"] == 117


def test_quick_match_started_before_rule_change_keeps_original_scoring(mode_system, monkeypatch):
    import json
    from contextlib import closing

    monkeypatch.setattr(mode_system, "_random_arena", lambda exclude=None: mode_system._arena("null_zone"))
    request = mode_system.create_group_challenge(1, "quick", "normal", -100)
    assert mode_system.accept_request(request["request_id"], 2)[0]
    state = mode_system.start_quick_match(request["request_id"])
    state.pop("scoring_rule")
    with closing(mode_system._connect()) as conn:
        with conn:
            conn.execute("UPDATE game_match_states SET state_json=? WHERE request_id=?",
                         (json.dumps(state), request["request_id"]))
    mode_system.select_quick_card(request["request_id"], 1, "alpha")
    mode_system.select_quick_card(request["request_id"], 2, "beta")
    mode_system.select_quick_ability(request["request_id"], 1, "skip")
    mode_system.select_quick_ability(request["request_id"], 2, "skip")
    mode_system.select_quick_stat(request["request_id"], 1, "power")
    _, report = mode_system.select_quick_stat(request["request_id"], 2, "iq")

    assert report["winner_id"] == 2  # Original rule compares 90 against 95.
    assert report["breakdown"]["1"]["final_value"] == 90
    assert "scored_stats" not in report["breakdown"]["1"]


def test_quick_arena_effects_only_apply_to_the_target_card_type(mode_system):
    speed_card = _card("speedy", 60, 80, 50, 40, card_type="SPEED_TYPE")
    assert mode_system.db.add_card(speed_card)
    assert mode_system.db.add_card_to_player(1, speed_card.card_id)
    state = {
        "players": [1, 2],
        "cards": {"1": "speedy", "2": "alpha"},
        "arena": "desert",
        "ability_choices": {"1": "skip", "2": "skip"},
    }

    speed_preview = mode_system.quick_stat_preview(state, 1)
    power_preview = mode_system.quick_stat_preview(state, 2)

    assert speed_preview["final_values"] == {
        "power": 60,
        "speed": 79,
        "iq": 50,
        "popularity": 40,
    }
    assert speed_preview["arena_effects"] == [
        {"card_type": "speed", "stat": "speed", "delta": -1}
    ]
    assert power_preview["final_values"] == {
        "power": 92,
        "speed": 30,
        "iq": 40,
        "popularity": 50,
    }


def test_quick_arena_effect_can_change_a_different_stat_for_target_type(mode_system, monkeypatch):
    monkeypatch.setattr(
        mode_system,
        "_arena",
        lambda _arena_id: {
            "id": "cross-stat-test",
            "effects": [
                {"card_type": "power", "stat": "popularity", "delta": 1}
            ],
            "passives_enabled": True,
        },
    )
    state = {
        "players": [1, 2],
        "cards": {"1": "alpha", "2": "beta"},
        "arena": "cross-stat-test",
        "ability_choices": {"1": "skip", "2": "skip"},
    }

    preview = mode_system.quick_stat_preview(state, 1)

    assert preview["final_values"]["power"] == 90
    assert preview["final_values"]["popularity"] == 51
    assert preview["arena_effects"] == [
        {"card_type": "power", "stat": "popularity", "delta": 1}
    ]


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
    trait_question = next(question for question in pool if question.get("trait") == "Hero")
    assert "با ویژگی" in trait_question["text"]
    assert "Trait" not in trait_question["text"]
    assert "«" not in trait_question["text"]
    assert bidi_isolate("Hero") in trait_question["text"]
    series_question = next(question for question in pool if question.get("series") == "Telverse")
    assert "«" not in series_question["text"]
    assert bidi_isolate("Telverse") in series_question["text"]

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
