"""Starter grants are complete, Normal-only, and repeat-safe."""

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.deck_system import DeckSystem
from systems.starter_cards_system import grant_starter_cards
from systems.starter_cards_system import grant_starter_pack, starter_status
from systems.card_inventory_system import CardInventorySystem
import sqlite3


def _card(card_id, name, rarity=CardRarity.NORMAL):
    return Card(card_id, name, rarity, 10, 10, 10, 10, [])


def test_random_normal_pack_is_complete_and_repeat_safe(tmp_path):
    db = DatabaseManager(str(tmp_path / "starter.db"))
    db.get_or_create_player(101)
    for index in range(20):
        assert db.add_card(_card('card-' + str(index), 'Character ' + str(index)))
    assert db.add_card(_card('rare', 'Rare', CardRarity.RARE))
    granted = grant_starter_cards(db, 101)
    assert len(granted) == len(set(granted)) == 10
    assert 'Rare' not in granted
    assert len(db.get_player_cards(101)) == 10
    decks = DeckSystem(db).get_valid_decks(101)
    assert len(decks) == 1
    assert [card.name for card in decks[0]["cards"]] == granted[:3]
    assert grant_starter_cards(db, 101) == []
    assert len(db.get_player_cards(101)) == 10
    assert len(db.get_player_decks(101)) == 1


def test_insufficient_normal_pool_grants_nothing(tmp_path):
    db = DatabaseManager(str(tmp_path / "starter.db"))
    db.get_or_create_player(101)
    assert db.add_card(_card("wick", "John Wick"))
    assert db.add_card(_card("heisenberg", "Heisenberg"))
    assert grant_starter_cards(db, 101) == []
    assert db.get_player_cards(101) == []
    assert db.get_player_decks(101) == []


def test_nine_owned_characters_receive_ten_additional_new_normals(tmp_path):
    db = DatabaseManager(str(tmp_path / 'returning.db'))
    db.get_or_create_player(101)
    for i in range(30):db.add_card(_card(str(i), 'Hero ' + str(i)))
    with sqlite3.connect(db.db_path) as conn:
        for i in range(9):
            CardInventorySystem.grant_in(conn, 101, str(i), 'normal', 5)
            CardInventorySystem.grant_in(conn, 101, str(i), 'epic', 1)
    result = grant_starter_pack(db, 101)
    assert result['ok'] and len(result['card_ids']) == len(set(result['card_ids'])) == 10
    assert not set(result['card_ids']) & {str(i) for i in range(9)}
    assert len(db.get_player_cards(101)) == 19
    for i in range(9):assert CardInventorySystem(db).counts(101, str(i)) == {'normal': 5, 'epic': 1}


def test_returning_users_wait_for_start_instead_of_automatic_miniapp_bonus(tmp_path):
    db = DatabaseManager(str(tmp_path / 'miniapp.db'))
    db.get_or_create_player(101)
    for i in range(20):db.add_card(_card(str(i), 'Hero ' + str(i)))
    db.add_card_to_player(101, '0')
    assert grant_starter_cards(db, 101, allow_existing=False) == []
    assert len(db.get_player_cards(101)) == 1
    assert starter_status(db, 101).get('pending')
    assert len(grant_starter_cards(db, 101)) == 10


def test_random_draw_is_used_and_is_frozen_for_retries(tmp_path, monkeypatch):
    db = DatabaseManager(str(tmp_path / 'random.db'))
    db.get_or_create_player(101)
    for i in range(30):db.add_card(_card(str(i), 'Hero ' + str(i)))
    calls = []
    def draw(pool, size):
        calls.append((len(pool), size))
        return list(pool)[-size:]
    monkeypatch.setattr('systems.starter_cards_system.random.sample', draw)
    result = grant_starter_pack(db, 101)
    again = grant_starter_pack(db, 101)
    assert calls == [(30, 10)]
    assert again['replayed'] and result['card_ids'] == again['card_ids']
