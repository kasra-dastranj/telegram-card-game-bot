"""Current battle-depth rules: arena boosts, abilities, and dominance map."""

from types import SimpleNamespace

from game_core import Card, CardRarity
from systems.battle_system_3rounds import (
    ABILITIES,
    ARENAS,
    BattleSystem3Rounds,
    beats,
    get_card_ability,
)


def card(card_id="power", rarity=CardRarity.EPIC, card_type="POWER_TYPE"):
    return Card(card_id=card_id, name=card_id, rarity=rarity, power=85, speed=40,
                iq=70, popularity=50, abilities=[], card_type=card_type)


def test_arena_boost_requires_stat_and_matching_type_by_default():
    battle = BattleSystem3Rounds(SimpleNamespace(db_path=":memory:"))
    assert all(arena["boost_amount"] == 8 for arena in ARENAS.values())
    assert battle.calculate_boost(card(), "power_arena", "power") == 8
    assert battle.calculate_boost(card(), "power_arena", "speed") == 0
    assert battle.calculate_boost(card(card_type="SPEED_TYPE"), "power_arena", "power") == 0


def test_card_ability_mapping_and_application():
    battle = BattleSystem3Rounds(SimpleNamespace(db_path=":memory:"))
    epic = card(rarity=CardRarity.EPIC)
    assert get_card_ability(epic) == "boost_15"
    assert "boost_15" in ABILITIES
    challenger, opponent, text = battle.apply_ability(
        "boost_15", "challenger", 70, 65, 60, 55, 5, 5
    )
    assert (challenger, opponent) == (85, 65)
    assert text


def test_dominance_map_is_cyclic_and_not_a_removed_type_counter():
    assert beats("speed", "power")
    assert beats("power", "popularity")
    assert beats("popularity", "iq")
    assert beats("iq", "speed")
    assert not beats("power", "speed")
