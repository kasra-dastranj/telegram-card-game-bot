"""Compatibility tests for the legacy arena presentation helpers."""

from systems.arena_system import ArenaSystem, ArenaType, get_card_type_emoji, get_card_type_name


def test_legacy_arena_helpers_remain_compatible_during_rollout():
    arena = ArenaSystem.select_random_arena()
    info = ArenaSystem.get_arena_info(arena)
    assert info["name"] and info["description"]
    value, boosted = ArenaSystem.calculate_boost("POWER_TYPE", ArenaType.POWER_ARENA, "power", 50)
    assert (value, boosted) == (51, True)
    value, boosted = ArenaSystem.calculate_boost("POWER_TYPE", ArenaType.POWER_ARENA, "speed", 50)
    assert (value, boosted) == (50, False)


def test_card_type_display_helpers():
    assert get_card_type_emoji("POWER_TYPE") == "💪"
    assert get_card_type_emoji("SPEED_TYPE") == "⚡"
    assert get_card_type_name("IQ_TYPE") == "هوش"
    assert get_card_type_name("POPULARITY_TYPE") == "محبوبیت"
