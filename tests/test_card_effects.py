from datetime import datetime

from core.models import Card, CardRarity
from systems.battle_system_3rounds import (
    apply_drain_to_stats,
    apply_reflect_reduction,
    get_dominant_attr_from_stats,
    has_card_effect,
    select_arena_shift_role,
)


def card(card_id, effects=None):
    return Card(
        card_id=card_id,
        name=card_id,
        rarity=CardRarity.NORMAL,
        power=50,
        speed=40,
        iq=30,
        popularity=20,
        abilities=[],
        card_effects=effects or [],
        created_at=datetime.now(),
    )


def test_drain_reduces_opponent_dominant_attr():
    source = card("drainer", ["drain"])
    target_stats = {"power": 20, "speed": 70, "iq": 40, "popularity": 10}

    drained, attr = apply_drain_to_stats(source, target_stats, "speed")

    assert attr == "speed"
    assert drained["speed"] == 60
    assert target_stats["speed"] == 70


def test_drain_can_change_final_dominant_attr():
    source = card("drainer", ["drain"])
    target_stats = {"power": 65, "speed": 70, "iq": 40, "popularity": 10}
    initial_dom = get_dominant_attr_from_stats(target_stats, "stage")

    drained, _ = apply_drain_to_stats(source, target_stats, initial_dom)
    final_dom = get_dominant_attr_from_stats(drained, "stage")

    assert initial_dom == "speed"
    assert final_dom == "power"


def test_reflect_moves_loser_reduction_to_winner():
    challenger = card("winner")
    opponent = card("reflector", ["reflect"])

    ch_reduction, op_reduction, reflected_by = apply_reflect_reduction(
        "challenger", challenger, opponent, "power", "speed", 0, 5
    )

    assert reflected_by == "opponent"
    assert ch_reduction == 5
    assert op_reduction == 0


def test_reflect_does_not_trigger_on_tie():
    challenger = card("reflector", ["reflect"])
    opponent = card("other")

    ch_reduction, op_reduction, reflected_by = apply_reflect_reduction(
        None, challenger, opponent, "power", "speed", 3, 3
    )

    assert reflected_by is None
    assert ch_reduction == 3
    assert op_reduction == 3


def test_arena_shift_role_selection():
    assert select_arena_shift_role(card("a", ["arena_shift"]), card("b"), "opponent") == "challenger"
    assert select_arena_shift_role(card("a"), card("b", ["arena_shift"]), "challenger") == "opponent"
    assert select_arena_shift_role(card("a", ["arena_shift"]), card("b", ["arena_shift"]), "opponent") == "opponent"
    assert select_arena_shift_role(card("a", ["arena_shift"]), card("b", ["arena_shift"]), None) == "challenger"


def test_card_effects_are_distinct_from_abilities():
    c = card("hybrid", ["reflect"])

    assert c.abilities == []
    assert has_card_effect(c, "reflect")
