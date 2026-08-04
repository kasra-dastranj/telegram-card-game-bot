from datetime import datetime

from core.models import Card, CardRarity
from systems.deck_system import DeckSystem


def make_card(card_id, rarity=CardRarity.NORMAL):
    return Card(
        card_id=card_id,
        name=card_id,
        rarity=rarity,
        power=10,
        speed=20,
        iq=30,
        popularity=40,
        abilities=[],
        created_at=datetime.now(),
    )


class FakeDeckDb:
    def __init__(self):
        self.cards_by_player = {
            1: [make_card("a"), make_card("b"), make_card("c")],
            2: [make_card("x"), make_card("y"), make_card("z")],
        }
        self.decks = {
            "deck1": {
                "deck_id": "deck1",
                "player_id": 1,
                "deck_name": "main",
                "card_id_1": "a",
                "card_id_2": "b",
                "card_id_3": "c",
                "is_valid": 1,
            }
        }
        self.updated = []

    def count_player_decks(self, player_id):
        return sum(1 for d in self.decks.values() if d["player_id"] == player_id)

    def get_player_cards(self, player_id):
        return self.cards_by_player.get(player_id, [])

    def get_player_decks(self, player_id):
        return [d for d in self.decks.values() if d["player_id"] == player_id]

    def get_deck_by_id(self, deck_id):
        return self.decks.get(deck_id)

    def get_card_by_id_for_player(self, card_id, player_id):
        for card in self.get_player_cards(player_id):
            if card.card_id == card_id:
                return card
        return None

    def get_card_by_id(self, card_id):
        for cards in self.cards_by_player.values():
            for card in cards:
                if card.card_id == card_id:
                    return card
        return None

    def update_deck(self, deck_id, **kwargs):
        self.updated.append((deck_id, kwargs))
        self.decks[deck_id].update({k: v for k, v in kwargs.items() if v is not None})
        return True


def test_deck_cards_rejects_non_owner():
    system = DeckSystem(FakeDeckDb())

    assert system.get_deck_cards("deck1", player_id=2) == []


def test_validate_deck_integrity_rejects_non_owner_without_invalidating():
    db = FakeDeckDb()
    system = DeckSystem(db)

    assert system.validate_deck_integrity(player_id=2, deck_id="deck1") is False
    assert db.updated == []


def test_validate_deck_integrity_invalidates_missing_owned_card():
    db = FakeDeckDb()
    db.cards_by_player[1] = [make_card("a"), make_card("b")]
    system = DeckSystem(db)

    assert system.validate_deck_integrity(player_id=1, deck_id="deck1") is False
    assert db.updated == [("deck1", {"is_valid": 0})]
