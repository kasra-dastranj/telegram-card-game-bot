"""Phase 1 regression, future policy contracts, and hostile card selection."""
import json
import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from migrations.migrate_card_trait_registry import copy_database
from migrations.migrate_shared_foundation import apply_migration
from systems.shared_foundation import (
    FLAGS, MatchContext, bind_context, context_in, economic_card_eligible,
    eligible_cards, future_settlement_policy, is_card_eligible, legacy_context,
    project_future_award, require_card_in, settings_in,
)
from systems.game_mode_system import GameModeSystem
from systems.match_rewards_system import MatchRewardsSystem


FUTURE_FLAGS = {key: True for key in FLAGS}


@pytest.mark.parametrize('mode,variant,allow_custom,custom_allowed', [
    ('quick', 'competitive', False, False),
    ('quick', 'friendly', False, True),
    ('three_round', 'competitive', False, False),
    ('deck', 'competitive', False, False),
    ('risk', 'competitive', False, False),
    ('practice', 'competitive', False, True),
    ('easy', 'competitive', False, False),
    ('easy', 'competitive', True, True),
    ('legacy_pvp', 'competitive', False, False),
])
@pytest.mark.parametrize('rarity', ['normal', 'epic', 'legend', 'rare'])
def test_origin_and_mode_contract_independent_of_rarity(mode, variant, allow_custom, custom_allowed, rarity):
    context = MatchContext(mode, variant, allow_custom_cards=allow_custom)
    assert is_card_eligible({'origin': 'official', 'rarity': rarity}, context, FUTURE_FLAGS)
    assert is_card_eligible({'origin': 'custom', 'rarity': rarity}, context, FUTURE_FLAGS) is custom_allowed
    assert not is_card_eligible({'origin': 'custom'}, context)  # Flags off, even on a future context.
    assert not economic_card_eligible({'origin': 'custom', 'rarity': rarity})


@pytest.mark.parametrize('origin', ['official', 'custom'])
@pytest.mark.parametrize('outcome,hearts', [('win', 0), ('tie', 0), ('loss', 1)])
def test_friendly_zero_rewards_and_ranked_progress_but_independent_heart(origin, outcome, hearts):
    context = MatchContext('quick', 'friendly', policy_version='future_v2')
    assert is_card_eligible({'origin': origin}, context, FUTURE_FLAGS)
    decision = future_settlement_policy(context, outcome)
    preview = project_future_award({'xp': 90, 'score': 20, 'coins': 5, 'tp_delta': 10}, decision)
    assert preview == dict(xp=0, score=0, coins=0, tp_delta=0, hearts_lost=hearts, ranked_progress=False)
    configurable = replace(context, friendly_loss_hearts=2)
    assert future_settlement_policy(configurable, 'loss').hearts_lost == 2


@pytest.mark.parametrize('mode', ['quick', 'three_round', 'deck'])
@pytest.mark.parametrize('outcome,hearts', [('win', 0), ('tie', 0), ('loss', 1)])
def test_competitive_policy_contract(mode, outcome, hearts):
    decision = future_settlement_policy(MatchContext(mode), outcome)
    assert decision.reward_eligible and decision.ranked_progress
    assert decision.hearts_lost == hearts


def test_easy_custom_does_not_change_rewards_and_requires_five_distinct_humans():
    official = MatchContext('easy')
    custom = replace(official, allow_custom_cards=True)
    for context in (official, custom):
        assert not future_settlement_policy(context, 'win', qualified_player_ids=[1, 2, 3, 4]).reward_eligible
        assert not future_settlement_policy(context, 'win', qualified_player_ids=[1, 2, 3, 4, 4]).reward_eligible
        decision = future_settlement_policy(context, 'win', qualified_player_ids=[1, 2, 3, 4, 5])
        assert decision.reward_eligible and decision.ranked_progress and decision.hearts_lost == 0
        amounts = {'xp': 8, 'score': 10, 'coins': 0, 'tp_delta': 0}
        assert project_future_award(amounts, decision) == {**amounts, 'hearts_lost': 0, 'ranked_progress': True}
    with pytest.raises(ValueError, match='unqualified'):
        future_settlement_policy(custom, 'win', qualified_player_ids=[1, 2, 3, 4, False])


def test_practice_and_invalid_match_contract_and_risk_remain_separate():
    for outcome in ('win', 'loss', 'tie'):
        practice = future_settlement_policy(MatchContext('practice'), outcome)
        assert not practice.reward_eligible and not practice.ranked_progress and practice.hearts_lost == 0
        invalid = future_settlement_policy(MatchContext('quick'), outcome, valid=False)
        assert not invalid.reward_eligible and invalid.hearts_lost == 0
    risk = future_settlement_policy(MatchContext('risk'), 'loss')
    assert risk.hearts_lost is None and risk.reward_policy == 'risk_independent'
    assert not risk.ranked_progress
    assert project_future_award({'xp': 1, 'score': 20, 'coins': 50}, risk)['score'] == 0


@pytest.mark.parametrize('kwargs', [
    {'mode': 'unknown'}, {'mode': 'deck', 'variant': 'friendly'},
    {'mode': 'quick', 'variant': 'normal'}, {'mode': 'quick', 'allow_custom_cards': True},
    {'mode': 'easy', 'allow_custom_cards': 'true'}, {'mode': 'quick', 'friendly_loss_hearts': True},
    {'mode': 'easy', 'easy_min_qualified_players': 4}, {'mode': 'quick', 'policy_version': 'client_policy'},
])
def test_untrusted_or_ambiguous_context_rejected(kwargs):
    with pytest.raises(ValueError):
        MatchContext(**kwargs)


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(str(tmp_path / 'foundation.sqlite'))
    for cid in ('official-a', 'official-b', 'official-c', 'future-custom'):
        assert manager.add_card(Card(cid, cid, CardRarity.NORMAL, 20, 30, 40, 50, []))
    for uid in (101, 202):
        manager.get_or_create_player(uid)
        for cid in ('official-a', 'official-b', 'official-c', 'future-custom'):
            assert manager.add_card_to_player(uid, cid)
    # Fixture only, NOT a production custom-card creation/assignment API.
    with closing(sqlite3.connect(manager.db_path)) as conn, conn:
        conn.execute("UPDATE cards SET origin='custom' WHERE card_id='future-custom'")
    return manager


def test_flags_default_off_and_card_projection_preserves_origin(db):
    with closing(sqlite3.connect(db.db_path)) as conn:
        assert all(settings_in(conn)[key] is False for key in FLAGS)
    assert db.get_card_by_id('future-custom').origin == 'custom'
    assert db.get_card_by_name('future-custom').origin == 'custom'
    # Phase 3 projections require a live grant; raw definition still preserves origin.
    assert db.get_card_by_id_for_player('future-custom', 101) is None
    for cards in (db.get_all_cards(), db.get_player_cards(101),db.get_player_cards_by_rarity(101)[0]):
        assert all(card.card_id != 'future-custom' for card in cards)
    card = db.get_card_by_id('future-custom')
    card.origin = 'official'  # Ordinary editing cannot promote the definition's origin.
    assert db.update_card(card)
    assert db.get_card_by_id('future-custom').origin == 'custom'
    assert not db.add_card(Card('blocked-new', 'new', CardRarity.EPIC, 1, 1, 1, 1, [], origin='custom'))
    legacy = card.to_dict(); legacy.pop('origin')
    assert Card.from_dict(legacy).origin == 'official'
    with pytest.raises(ValueError):
        Card('bad', 'bad', CardRarity.NORMAL, 1, 1, 1, 1, [], origin='client-origin')


def test_match_context_immutable_after_restart_and_variant_not_inferred_from_group(db):
    modes = GameModeSystem(db)
    request = modes.create_group_challenge(101, 'quick', 'random', -1001)
    key = request['request_id']
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        context = context_in(conn, key, 'quick')
        assert context.variant == 'competitive' and context.selection_variant == 'random'
        with pytest.raises(ValueError, match='conflict'):
            bind_context(conn, key, replace(context, variant='friendly'))
        conn.execute("UPDATE foundation_settings SET value_json='2' WHERE key='friendly_loss_hearts'")
    restarted = DatabaseManager(db.db_path)
    with closing(sqlite3.connect(restarted.db_path)) as conn:
        assert context_in(conn, key, 'quick') == context


def test_manual_and_random_quick_reject_custom_even_when_callback_state_is_tampered(db):
    modes = GameModeSystem(db)
    request = modes.create_invite(101, 'quick', 'normal')
    modes.accept_invite(request['invite_token'], 202)
    modes.start_quick_match(request['request_id'])
    with pytest.raises(ValueError, match='ineligible|not_owned'):
        modes.select_quick_card(request['request_id'], 101, 'future-custom')
    assert not modes.get_state(request['request_id'])['cards']
    request = modes.create_invite(101, 'quick', 'random')
    modes.accept_invite(request['invite_token'], 202)
    state = modes.start_quick_match(request['request_id'])
    assert 'future-custom' not in state['cards'].values()
    with closing(sqlite3.connect(db.db_path)) as conn:
        for mode in ('quick', 'three_round', 'deck', 'risk'):
            with pytest.raises(ValueError):
                require_card_in(conn, 'future-custom', MatchContext(mode), 101)
            assert all(card.card_id != 'future-custom' for card in eligible_cards(db, db.get_all_cards(), mode))


def test_bot_database_card_assignment_boundary_and_solo_guard(db):
    fight = db.create_fight(101, 202, -1001)
    assert not db.update_fight(fight, challenger_card_id='future-custom')
    assert db.update_fight(fight, challenger_card_id='official-a')
    solo = db.create_solo_fight(101, 'easy')
    assert not db.update_solo_fight(solo, player_card_id='future-custom')
    assert db.update_solo_fight(solo, player_card_id='official-a')
    from systems.deck_system import DeckSystem
    ok, _ = DeckSystem(db)._validate(101, ['official-a', 'official-b', 'future-custom'], 'deck')
    assert not ok


def test_settlement_uses_persisted_context_retry_is_idempotent_and_future_history_writer_blocked(db):
    GameModeSystem(db)
    item = {101: dict(result='loss', xp=2, score=0, hearts_lost=1, card_id='official-a')}
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        before = conn.execute('SELECT hearts FROM players WHERE user_id=101').fetchone()[0]
        MatchRewardsSystem.award(conn, 'old-running', 'quick', item)
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        first = MatchRewardsSystem.award(conn, 'old-running', 'quick', item)
        second = MatchRewardsSystem.award(conn, 'old-running', 'quick', item)
        assert first == second == {'101': {'xp': 2, 'score': 0}}
        assert conn.execute('SELECT hearts FROM players WHERE user_id=101').fetchone()[0] == before - 1
        assert conn.execute("SELECT COUNT(*) FROM match_reward_events WHERE request_id='old-running'").fetchone()[0] == 1
        bind_context(conn, 'preview-friendly', MatchContext('quick', 'friendly', policy_version='future_v2'))
        history_before = conn.execute('SELECT COUNT(*) FROM fight_history').fetchone()[0]
        with pytest.raises(ValueError, match='not_live'):
            MatchRewardsSystem.award(conn, 'preview-friendly', 'quick', item)
        assert conn.execute('SELECT COUNT(*) FROM fight_history').fetchone()[0] == history_before
        with pytest.raises(ValueError, match='mode_conflict'):
            MatchRewardsSystem.award(conn, 'old-running', 'solo', item)


def test_economic_entry_points_exclude_custom_without_spending(db):
    from systems.card_inventory_system import CardInventorySystem
    from systems.card_upgrade_system import CardUpgradeSystem
    from systems.fusion_system import FusionSystem
    from systems.claim_system import ClaimSystem
    from systems.player_rewards_system import PlayerRewardsSystem
    assert not CardUpgradeSystem(db).preview(101, 'future-custom')['ok']
    assert not FusionSystem(db).preview_identical(101, 'future-custom', 'epic')['ok']
    assert PlayerRewardsSystem(db).claim_status(101)['pool_count'] == 3
    assert all(card.origin == 'official' for card in ClaimSystem(db).get_claimable_pool(101))
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        before = CardInventorySystem.counts_in(conn, 101, 'future-custom')
        assert not CardInventorySystem.consume_in(conn, 101, 'future-custom', 'normal')
        with pytest.raises(ValueError, match='not_implemented'):
            CardInventorySystem.grant_in(conn, 202, 'future-custom', 'epic')
        assert CardInventorySystem.counts_in(conn, 101, 'future-custom') == before


def test_migration_preview_backup_repeated_apply_and_legacy_records_preserved(tmp_path):
    source = tmp_path / 'legacy.sqlite'
    with closing(sqlite3.connect(str(source))) as conn, conn:
        conn.execute('CREATE TABLE cards(card_id TEXT PRIMARY KEY, rarity TEXT, power INTEGER)')
        conn.executemany('INSERT INTO cards VALUES(?,?,?)', [('a', 'normal', 70), ('b', 'rare', 90)])
        conn.execute('CREATE TABLE player_cards(user_id INTEGER, card_id TEXT)')
        conn.executemany('INSERT INTO player_cards VALUES(?,?)', [(1, 'a'), (2, 'a'), (2, 'b')])
        conn.execute('CREATE TABLE active_matches(key TEXT, state TEXT)')
        conn.execute("INSERT INTO active_matches VALUES('running','unchanged')")
    preview = copy_database(source, tmp_path / 'preview.sqlite')
    assert apply_migration(preview) == apply_migration(preview) == 2
    with closing(sqlite3.connect(str(source))) as conn:
        assert 'origin' not in {row[1] for row in conn.execute('PRAGMA table_info(cards)')}
    backup = copy_database(source, tmp_path / 'backup.sqlite')
    with pytest.raises(FileExistsError):
        copy_database(source, backup)
    assert apply_migration(source) == 2
    with closing(sqlite3.connect(str(source))) as conn:
        assert conn.execute('SELECT * FROM cards ORDER BY card_id').fetchall() == [('a', 'normal', 70, 'official'), ('b', 'rare', 90, 'official')]
        assert conn.execute('SELECT * FROM player_cards').fetchall() == [(1, 'a'), (2, 'a'), (2, 'b')]
        assert conn.execute('SELECT * FROM active_matches').fetchall() == [('running', 'unchanged')]
        assert all(settings_in(conn)[key] is False for key in FLAGS)
        assert conn.execute('PRAGMA quick_check').fetchall() == [('ok',)]


def test_failed_migration_rolls_back_additions(tmp_path):
    source = tmp_path / 'invalid.sqlite'
    with closing(sqlite3.connect(str(source))) as conn, conn:
        conn.execute('CREATE TABLE cards(card_id TEXT PRIMARY KEY, origin TEXT)')
        conn.execute("INSERT INTO cards VALUES('bad', 'unexpected')")
    with pytest.raises(ValueError):
        apply_migration(source)
    with closing(sqlite3.connect(str(source))) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='foundation_settings'").fetchone()


def test_easy_cached_options_cannot_smuggle_custom_and_old_two_player_flow_still_works(db):
    modes = GameModeSystem(db)
    request = modes.create_easy_lobby(101, -1001, 1)
    key = request['request_id']
    assert modes.join_easy_lobby(key, 202)[0]
    assert modes.start_easy_match(key)[0]  # Preserve current live minimum, not future five.
    with closing(modes._connect()) as conn, conn:
        state = modes.get_state(key)
        state['options']['101'] = ['future-custom', 'official-a']
        state['question'] = {'id': 'test', 'attribute': 'power', 'text': 'power'}
        modes._save_state(conn, key, state)
    assert not modes.select_easy_card(key, 101, 'future-custom')[0]
    assert modes.select_easy_card(key, 101, 'official-a')[0]


def test_risk_random_pool_and_direct_selection_reject_custom(db):
    from systems.risk_mode_system import RiskModeSystem, RiskTable
    for uid in (101, 202):
        db.add_coins(uid, 1000)
        db.update_progression(uid, level=30)
    system = RiskModeSystem(db)
    created = system.create_risk_match(101, 202, RiskTable.TABLE_50)
    assert created['success'], created
    assert 'future-custom' not in created['challenger_cards'] + created['opponent_cards']
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute("UPDATE risk_matches SET challenger_cards='future-custom' WHERE match_id=?", (created['match_id'],))
    assert not system.select_card(created['match_id'], 101, 'future-custom')['success']


def test_bot_round_callback_rejects_smuggled_custom_without_locking_choice(db):
    import asyncio
    from types import SimpleNamespace
    from bot.handlers.battle import BattleHandlersMixin
    handler = BattleHandlersMixin()
    handler.db = db
    fight_id = db.create_fight(101, 202, -1001)
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('''INSERT INTO battle_states
            (fight_id,challenger_id,opponent_id,challenger_card_id,opponent_card_id,
             arena,challenger_current_stats,opponent_current_stats,created_at,
             challenger_remaining_cards,opponent_remaining_cards)
            VALUES(?,101,202,'official-a','official-b','desert','{}','{}',CURRENT_TIMESTAMP,?,?)''',
            (fight_id, json.dumps(['future-custom', 'official-a']), json.dumps(['official-b'])))
    context = SimpleNamespace(bot_data={})
    ok, _, _ = asyncio.run(handler._record_round_card_selection(context, fight_id, 101, 'future-custom'))
    assert not ok and context.bot_data == {}
    ok, card, _ = asyncio.run(handler._record_round_card_selection(context, fight_id, 101, 'official-a'))
    assert ok and card.card_id == 'official-a'


def test_running_legacy_request_recovers_server_variant_after_restart(db):
    modes = GameModeSystem(db)
    request = modes.create_invite(101, 'quick', 'random')
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('DELETE FROM match_contexts WHERE match_key=?', (request['request_id'],))
    restarted = GameModeSystem(DatabaseManager(db.db_path))
    assert restarted.accept_invite(request['invite_token'], 202)[0]
    restarted.start_quick_match(request['request_id'])
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        restored = context_in(conn, request['request_id'], 'quick')
        assert restored.mode == 'quick' and restored.variant == 'competitive'
        assert restored.selection_variant == 'random'
