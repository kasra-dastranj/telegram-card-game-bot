from datetime import datetime

from core.models import Card, CardRarity
from systems.battle_system_3rounds import BEATS_MAP, beats, get_dominant_attr


def card(**stats):
    defaults = {
        "power": 10,
        "speed": 10,
        "iq": 10,
        "popularity": 10,
    }
    defaults.update(stats)
    return Card(
        card_id="c1",
        name="Test",
        rarity=CardRarity.NORMAL,
        abilities=[],
        created_at=datetime.now(),
        **defaults,
    )


def test_beats_map_cycle():
    assert BEATS_MAP == {
        "speed": "power",
        "power": "popularity",
        "popularity": "iq",
        "iq": "speed",
    }
    assert beats("speed", "power")
    assert beats("power", "popularity")
    assert beats("popularity", "iq")
    assert beats("iq", "speed")
    assert not beats("power", "speed")


def test_dominant_attr_uses_priority_for_ties():
    assert get_dominant_attr(card(power=50, speed=50, iq=20, popularity=20), "stage") == "power"
    assert get_dominant_attr(card(power=10, speed=40, iq=40, popularity=20), "power_arena") == "speed"


def test_dominant_attr_includes_arena_boost():
    boosted = card(power=20, speed=25, iq=10, popularity=10)

    assert get_dominant_attr(boosted, "power_arena") == "power"
