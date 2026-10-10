import json
import sqlite3
from datetime import datetime, timezone

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from migrations.activate_progression_v2 import apply_activation
from systems.card_inventory_system import CardInventorySystem
from systems.progression_config import config_in
from systems.progression_leaderboard import ProgressionLeaderboard
from systems.progression_missions import ProgressionMissions
from systems.progression_rollout import activate_in, protected_digest
from systems.reward_ledger import apply_in, capacities_in

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


@pytest.fixture
def legacy_game(tmp_path):
    db = DatabaseManager(str(tmp_path / 'legacy.db'))
    db.get_or_create_player(1)
    db.get_or_create_player(2)
    db.add_card(Card(card_id='wick', name='Wick', rarity=CardRarity.NORMAL,
                     power=5, speed=5, iq=5, popularity=5, abilities=[]))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE card_variants SET power=7,speed=7,iq=7,popularity=7 WHERE card_id='wick'")
        conn.execute('DELETE FROM progression_capacities WHERE user_id=2')
        conn.execute('UPDATE players SET coins=321,hearts=2,max_hearts=24,total_score=7 WHERE user_id=1')
        conn.execute('UPDATE player_progression SET total_xp=95,level=1 WHERE user_id=1')
        capacities_in(conn, 1, config_in(conn)[1])
        CardInventorySystem.grant_in(conn, 1, 'wick', 'normal', 3)
    return db


def activate(db):
    return apply_activation(db.db_path, 'test-owner', now=NOW)


def test_activation_preserves_all_business_data_and_fills_missing_legacy_capacity(legacy_game):
    with sqlite3.connect(legacy_game.db_path) as conn:
        before = protected_digest(conn)
    result = activate(legacy_game)
    assert result['enabled'] and result['protected_data_unchanged'] and result['legacy_accounts'] == 2
    assert result['recipes_added'] == 1 and result['missions_added'] == 4
    with sqlite3.connect(legacy_game.db_path) as conn:
        assert protected_digest(conn) == before == result['protected_digest']
        assert conn.execute('SELECT DISTINCT legacy FROM progression_capacities').fetchall() == [(1,)]
        assert conn.execute('SELECT * FROM economy_character_rules').fetchall() == [('wick', 'B')]
        assert conn.execute('SELECT value_json FROM foundation_settings WHERE key="custom_cards_enabled"').fetchone() == ('false',)
        assert all(json.loads(row[0])['start'] == NOW.isoformat() for row in conn.execute('SELECT definition_json FROM economy_missions'))


def test_retry_does_not_freeze_new_accounts_or_reenable_deliberately_disabled_flag(legacy_game):
    first = activate(legacy_game)
    legacy_game.get_or_create_player(3)
    with sqlite3.connect(legacy_game.db_path) as conn:
        assert conn.execute('SELECT legacy,base_hearts,base_slots FROM progression_capacities WHERE user_id=3').fetchone() == (0, 8, 3)
        conn.execute("UPDATE foundation_settings SET value_json='false' WHERE key='progression_v2_enabled'")
        before = list(conn.iterdump())
    replay = activate(legacy_game)
    assert replay['replayed'] and not replay['enabled'] and replay['activated_at'] == first['activated_at']
    with sqlite3.connect(legacy_game.db_path) as conn:
        assert list(conn.iterdump()) == before


def test_existing_deliberate_recipe_is_preserved(legacy_game):
    with sqlite3.connect(legacy_game.db_path) as conn:
        conn.execute("INSERT INTO economy_character_rules VALUES('wick','A')")
        version = config_in(conn)[0]
    assert activate(legacy_game)['recipes_added'] == 0
    with sqlite3.connect(legacy_game.db_path) as conn:
        assert conn.execute('SELECT legend_recipe_tier FROM economy_character_rules').fetchone() == ('A',)
        assert config_in(conn)[0] == version


@pytest.mark.parametrize('failure', ['catalog', 'existing_mission', 'policy', 'recipe', 'flag', 'nonlegacy', 'different_plan'])
def test_failed_cutover_rolls_back_everything(legacy_game, failure):
    import systems.progression_rollout as rollout
    with sqlite3.connect(legacy_game.db_path) as conn:
        if failure == 'catalog':
            conn.execute("DELETE FROM card_variants WHERE rarity='legend'")
        elif failure == 'existing_mission':
            conn.execute("INSERT INTO economy_missions VALUES('tester-first-quick','{}',1,'tester','now')")
        elif failure in ('policy', 'recipe'):
            version, config = config_in(conn)
            if failure == 'policy':
                config['migration']['legacy_user_policy'] = None
            else:
                config['upgrade']['legend_B']['copies'] = 2
            conn.execute('UPDATE economy_config_versions SET config_json=? WHERE version=?', (json.dumps(config), version))
        elif failure == 'flag':
            conn.execute("DELETE FROM foundation_settings WHERE key='progression_v2_enabled'")
        elif failure == 'nonlegacy':
            conn.execute('UPDATE progression_capacities SET legacy=0 WHERE user_id=1')
        else:
            activate_in(conn, 'test-owner', now=NOW)
            conn.execute("UPDATE economy_state SET value=? WHERE key=?", (json.dumps({'plan_hash': 'conflict'}), rollout.ROLLOUT_KEY))
        before = list(conn.iterdump())
    with pytest.raises(ValueError):
        activate(legacy_game)
    with sqlite3.connect(legacy_game.db_path) as conn:
        assert list(conn.iterdump()) == before


def test_no_retroactive_mission_reward_and_new_level_prizes_only_for_new_account(legacy_game):
    with sqlite3.connect(legacy_game.db_path) as conn:
        version, _ = config_in(conn)
        apply_in(conn, 'old-claim', 1, 'claim', 'daily_claim', version, now=datetime(2026, 10, 9, tzinfo=timezone.utc))
    activate(legacy_game)
    legacy_game.get_or_create_player(3)
    with sqlite3.connect(legacy_game.db_path) as conn:
        version, config = config_in(conn)
        mission = json.loads(conn.execute("SELECT definition_json FROM economy_missions WHERE mission_id='tester-daily-claim'").fetchone()[0])
        assert ProgressionMissions.progress_in(conn, 1, mission, config, NOW)['current_progress'] == 0
        old = apply_in(conn, 'old-user-new-win', 1, 'match', 'match', version, xp=10)
        new = apply_in(conn, 'new-user-level', 3, 'match', 'match', version, xp=100)
        assert old['level_coins'] == 0 and new['level_coins'] == 50
        assert conn.execute('SELECT coins,max_hearts FROM players WHERE user_id=1').fetchone() == (321, 24)
        assert conn.execute('SELECT level_slots FROM progression_capacities WHERE user_id=3').fetchone() == (1,)


@pytest.mark.parametrize('period,closed,current', [
    ('weekly', NOW, datetime(2026, 10, 12, 12, tzinfo=timezone.utc)),
    ('monthly', NOW, datetime(2026, 11, 1, 12, tzinfo=timezone.utc)),
])
def test_leaderboard_cutover_skips_closed_period_but_pays_first_overlapping_period(legacy_game, period, closed, current):
    with sqlite3.connect(legacy_game.db_path) as conn:
        for at in ('2026-09-05T12:00:00+00:00', '2026-10-03T12:00:00+00:00', '2026-10-10T13:00:00+00:00'):
            conn.execute("INSERT INTO fight_history(user_id,user_card_id,result,score_gained,fought_at) VALUES(1,'wick','win',1,?)", (at,))
    activate(legacy_game)
    service = ProgressionLeaderboard(legacy_game)
    with sqlite3.connect(legacy_game.db_path) as conn:
        before = list(conn.iterdump())
    assert service.settle(period, closed) == []
    with sqlite3.connect(legacy_game.db_path) as conn:
        assert list(conn.iterdump()) == before
    assert service.settle(period, current)
    assert service.settle(period, current) == []
