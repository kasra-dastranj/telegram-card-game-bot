"""Starter grants are complete, Normal-only, and repeat-safe."""

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.deck_system import DeckSystem
from systems.starter_cards_system import grant_starter_cards


def _card(card_id, name, rarity=CardRarity.NORMAL):
    return Card(card_id, name, rarity, 10, 10, 10, 10, [])


def test_missing_preferred_names_use_normal_fallbacks(tmp_path):
    db = DatabaseManager(str(tmp_path / "starter.db"))
    db.get_or_create_player(101)
    for card in (
        _card("wick", "John Wick"), _card("alpha", "Alpha"),
        _card("beta", "Beta"), _card("legend", "Legend", CardRarity.LEGEND),
    ):
        assert db.add_card(card)

    granted = grant_starter_cards(db, 101)
    assert granted == ["John Wick", "Alpha", "Beta"]
    assert len(db.get_player_cards(101)) == 3
    decks = DeckSystem(db).get_valid_decks(101)
    assert len(decks) == 1
    assert [card.name for card in decks[0]["cards"]] == granted
    assert grant_starter_cards(db, 101) == []
    assert len(db.get_player_cards(101)) == 3
    assert len(db.get_player_decks(101)) == 1


def test_insufficient_normal_pool_grants_nothing(tmp_path):
    db = DatabaseManager(str(tmp_path / "starter.db"))
    db.get_or_create_player(101)
    assert db.add_card(_card("wick", "John Wick"))
    assert db.add_card(_card("heisenberg", "Heisenberg"))
    assert grant_starter_cards(db, 101) == []
    assert db.get_player_cards(101) == []
    assert db.get_player_decks(101) == []
