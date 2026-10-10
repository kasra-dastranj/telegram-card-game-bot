import json
import sqlite3

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from scripts.provision_economy_testers import KIT, provision, unrelated_snapshot
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import ABILITY_DEFINITIONS, GameModeSystem
from systems.progression_config import config_in
from systems.reward_ledger import apply_in, capacities_in, items_in


@pytest.fixture
def db(tmp_path):
    game = DatabaseManager(str(tmp_path/'tester.db'))
    for user, name in ((1, 'TesterOne'), (2, 'TesterTwo'), (3, 'Ordinary')):
        game.get_or_create_player(user, name)
    for card_id in ('one', 'two', 'three'):
        game.add_card(Card(card_id=card_id, name=card_id, rarity=CardRarity.NORMAL,
                           power=5, speed=5, iq=5, popularity=5, abilities=[]))
    GameModeSystem(game)
    with sqlite3.connect(game.db_path) as conn:
        config = config_in(conn)[1]
        for user in (1, 2, 3):
            capacities_in(conn, user, config)
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
        conn.execute('UPDATE player_progression SET total_xp=95,level=1 WHERE user_id=1')
        conn.execute('UPDATE players SET coins=40000,hearts=2 WHERE user_id=2')
        CardInventorySystem.grant_in(conn, 2, 'one', 'legend', 3)
        CardInventorySystem.grant_in(conn, 2, 'one', 'normal', 20)
    return game


def run(db, accounts=None, batch='batch-1'):
    return provision(db.db_path, accounts or {'testerone': 1, 'TesterTwo': 2}, 'test-owner', batch)


def dump(db):
    with sqlite3.connect(db.db_path) as conn:
        return list(conn.iterdump())


def test_kit_preserves_progress_forms_and_unrelated_accounts_with_future_level_prizes(db):
    with sqlite3.connect(db.db_path) as conn:
        unrelated = unrelated_snapshot(conn, [1, 2])
        progression = conn.execute('SELECT * FROM player_progression ORDER BY user_id').fetchall()
        active = conn.execute('SELECT * FROM player_cards WHERE user_id=2').fetchall()
    result = run(db)
    assert result['unrelated_data_unchanged'] and result['existing_foreign_key_violations'] == 0
    with sqlite3.connect(db.db_path) as conn:
        assert unrelated_snapshot(conn, [1, 2]) == unrelated
        assert conn.execute('SELECT * FROM player_progression ORDER BY user_id').fetchall() == progression
        assert conn.execute("SELECT * FROM player_cards WHERE user_id=2 AND card_id='one'").fetchall() == active
        assert conn.execute('SELECT coins FROM players ORDER BY user_id').fetchall() == [(20000,), (40000,), (0,)]
        assert conn.execute('SELECT legacy FROM progression_capacities ORDER BY user_id').fetchall() == [(0,), (0,), (1,)]
        for user in (1, 2):
            for card in ('one', 'two', 'three'):
                assert all(CardInventorySystem.counts_in(conn, user, card)[form] >= count for form, count in KIT['forms'].items())
            assert dict(conn.execute('SELECT ability_key,quantity FROM player_ability_inventory WHERE user_id=?', (user,))) == {key:20 for key in ABILITY_DEFINITIONS}
            assert all(items_in(conn, user, item) >= count for item, count in KIT['items'].items())
        assert CardInventorySystem.counts_in(conn, 2, 'one')['normal'] == 20
        assert CardInventorySystem.counts_in(conn, 2, 'one')['legend'] == 3
        reward = apply_in(conn, 'future-win', 1, 'match', 'match', config_in(conn)[0], xp=10)
        assert reward['level_coins'] == 50
        assert capacities_in(conn, 1, config_in(conn)[1])['level_slots'] == 1


def test_same_batch_does_not_refill_spent_supplies_or_rewrite_receipts(db):
    run(db)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('UPDATE players SET coins=1000 WHERE user_id=1')
        conn.execute('UPDATE player_ability_inventory SET quantity=0 WHERE user_id=1')
        items_in(conn, 1, 'upgrade_card', -20)
    before = dump(db)
    assert run(db)['replayed']
    assert dump(db) == before


def test_batch_identity_conflict_rolls_back(db):
    run(db)
    before = dump(db)
    with pytest.raises(ValueError, match='idempotency_conflict'):
        run(db, {'testerone':1, 'Ordinary':3})
    assert dump(db) == before


@pytest.mark.parametrize('reason', ['identity', 'active', 'capacity', 'disabled'])
def test_invalid_precondition_does_not_grant_partial_kit(db, reason, monkeypatch):
    accounts = {'testerone':1, 'WrongName':2} if reason == 'identity' else None
    if reason == 'active':
        monkeypatch.setattr('scripts.provision_economy_testers.CardUpgradeSystem._active_match', lambda conn, user:user==2)
    with sqlite3.connect(db.db_path) as conn:
        if reason == 'capacity':
            conn.execute('UPDATE players SET max_hearts=24 WHERE user_id=2')
        if reason == 'disabled':
            conn.execute("UPDATE foundation_settings SET value_json='false' WHERE key='progression_v2_enabled'")
    before = dump(db)
    with pytest.raises(ValueError):
        run(db, accounts)
    assert dump(db) == before


def test_mid_inventory_failure_rolls_back_wallet_and_conversion(db, monkeypatch):
    original = CardInventorySystem.grant_in
    calls = []
    def fail(conn, user, card, form, amount):
        calls.append(card)
        if len(calls) == 2:
            raise RuntimeError('injected inventory failure')
        return original(conn, user, card, form, amount)
    monkeypatch.setattr(CardInventorySystem, 'grant_in', staticmethod(fail))
    before = dump(db)
    with pytest.raises(RuntimeError, match='injected inventory failure'):
        run(db)
    assert len(calls) == 2 and dump(db) == before
