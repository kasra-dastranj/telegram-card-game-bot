"""Cross-mode admission, concurrent writers, and recovery from abandoned games."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.game_mode_system import GameModeSystem
from systems.match_activity import ActiveMatchError, BUSY_MESSAGE, active_in
from systems.mini_three_round_system import MiniThreeRoundSystem
from systems.arena_registry import ArenaRegistry
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.risk_mode_system import RiskModeSystem, RiskTable, RiskAction


@pytest.fixture
def games(tmp_path):
    db = DatabaseManager(str(tmp_path / 'admission.db'))
    for cid in ('alpha', 'beta', 'gamma'):
        db.add_card(Card(card_id=cid, name=cid, rarity=CardRarity.NORMAL,
                         power=60, speed=40, iq=50, popularity=30, abilities=[]))
    for uid in range(1, 7):
        db.get_or_create_player(uid, first_name=str(uid))
        for cid in ('alpha', 'beta', 'gamma'):
            db.add_card_to_player(uid, cid)
    modes = GameModeSystem(db)
    modes.mode_access.set_min_level('risk', 1)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('UPDATE players SET coins=10000')
    return db, modes


def accepted(modes, mode='quick', creator=1, opponent=2):
    request = modes.create_invite(creator, mode, 'normal')
    assert modes.accept_request(request['request_id'], opponent)[0]
    return request['request_id']


def block(games, mode):
    db, modes = games
    if mode == 'solo':
        return db.create_solo_fight(1, 'easy')
    if mode == 'risk':
        result = RiskModeSystem(db).create_risk_match(1, 2, list(RiskTable)[0])
        assert result['success']
        return result['match_id']
    if mode == 'easy':
        request = modes.create_easy_lobby(1, -100, 3)
        assert modes.join_easy_lobby(request['request_id'], 2)[0]
        assert modes.start_easy_match(request['request_id'])[0]
        return request['request_id']
    key = accepted(modes, mode)
    if mode == 'deck':
        return db.create_fight(1, 2, -100, mode='deck', request_id=key)
    if mode == 'mini_three_round':
        MiniThreeRoundSystem(db, modes, ArenaRegistry(db), BattleSystem3Rounds(db)).start(key)
    else:
        modes.start_quick_match(key)
    return key


@pytest.mark.parametrize('mode', ['quick', 'deck', 'mini_three_round', 'solo', 'easy', 'risk'])
def test_one_active_game_blocks_all_other_entry_paths_for_both_participants(games, mode):
    db, modes = games
    inbound = modes.create_invite(3, 'quick', 'normal')
    outbound = modes.create_invite(1, 'quick', 'normal')
    block(games, mode)
    before = db.get_or_create_player(1).coins
    attempts = [lambda: modes.create_invite(1, 'quick', 'normal'),
                lambda: modes.create_inline_private_challenge(1, 'deck', 'normal'),
                lambda: modes.create_group_challenge(1, 'deck', 'normal', -200),
                lambda: modes.matchmake_random(1, 'mini_three_round', 'normal'),
                lambda: db.create_fight(3, 1, -200),
                lambda: db.create_solo_fight(1, 'easy'),
                lambda: modes.create_easy_lobby(1, -200, 1)]
    for attempt in attempts:
        with pytest.raises(ActiveMatchError):
            attempt()
    for request, uid in ((inbound, 1), (outbound, 3)):
        ok, reason, _ = modes.accept_request(request['request_id'], uid)
        assert not ok and reason == BUSY_MESSAGE
        assert modes.get_request(request['request_id'])['status'] == 'waiting'
    assert RiskModeSystem(db).create_risk_match(1, 3, list(RiskTable)[0])['success'] is False
    assert db.get_or_create_player(1).coins == before
    # An unrelated player is never blocked by somebody else's game.
    assert modes.create_invite(4, 'quick', 'normal')['creator_id'] == 4


def test_two_simultaneous_invite_accepts_share_one_player_reservation(games):
    _, modes = games
    requests = [modes.create_invite(uid, 'quick', 'normal')['request_id'] for uid in (1, 2)]
    barrier = Barrier(2)
    def accept(key):
        barrier.wait(timeout=10)
        return modes.accept_request(key, 3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(accept, requests))
    assert sum(ok for ok, _, _ in outcomes) == 1
    assert [reason for ok, reason, _ in outcomes if not ok] == [BUSY_MESSAGE]


def test_solo_and_bot_fight_cannot_race_into_two_games(games):
    db, _ = games
    barrier = Barrier(2)
    def start(kind):
        barrier.wait(timeout=10)
        try:
            return db.create_solo_fight(1, 'easy') if kind == 'solo' else db.create_fight(1, 2, -100)
        except ActiveMatchError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(value is not None for value in pool.map(start, ['solo', 'bot'])) == 1


def test_deck_handoff_is_atomic_and_completed_deck_request_never_locks_players(games):
    db, modes = games
    request = accepted(modes, 'deck')
    key = db.create_fight(1, 2, -100, mode='deck', request_id=request)
    with pytest.raises(ActiveMatchError):
        modes.create_invite(1, 'quick', 'normal')
    assert db.create_fight(1, 2, -100, mode='deck', request_id=request) == key
    db.update_fight(key, status='completed')
    # Deck request remains accepted in the existing engine, but its fight is over.
    assert modes.get_request(request)['status'] == 'accepted'
    assert modes.create_invite(1, 'quick', 'normal')
    assert modes.create_invite(2, 'quick', 'normal')


@pytest.mark.parametrize('mode', ['deck', 'quick', 'mini_three_round'])
def test_orphan_accepted_request_has_a_bounded_handoff_even_without_state(games, mode):
    _, modes = games
    request = accepted(modes, mode)
    with closing(modes._connect()) as conn, conn:
        conn.execute("UPDATE game_requests SET accepted_at='2000-01-01',updated_at='2000-01-01' WHERE request_id=?", (request,))
    assert modes.create_invite(1, 'quick', 'normal')


@pytest.mark.parametrize('mode', ['quick', 'mini_three_round'])
def test_expired_active_request_does_not_lock_and_old_choice_cannot_resume(games, mode):
    db, modes = games
    request = accepted(modes, mode)
    engine = modes if mode == 'quick' else MiniThreeRoundSystem(db, modes, ArenaRegistry(db), BattleSystem3Rounds(db))
    state = engine.start_quick_match(request) if mode == 'quick' else engine.start(request)
    state['deadline'] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)).isoformat()
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, request, state)
    assert modes.create_invite(1, 'quick', 'normal')
    with pytest.raises(ValueError):
        if mode == 'quick':
            modes.select_quick_card(request, 1, 'alpha')
        else:
            engine.choose_card(request, 1, 'alpha')


@pytest.mark.parametrize('mode', ['solo', 'deck'])
def test_abandoned_legacy_or_practice_is_cancelled_before_next_game(games, mode):
    db, modes = games
    key = block(games, mode)
    with sqlite3.connect(db.db_path) as conn:
        table = 'solo_fights' if mode == 'solo' else 'active_fights'
        conn.execute(f"UPDATE {table} SET created_at='2000-01-01' WHERE fight_id=?", (key,))
        if mode == 'deck':
            conn.execute("UPDATE active_fights SET expires_at='2000-01-01' WHERE fight_id=?", (key,))
    assert modes.create_invite(1, 'quick', 'normal')
    row = db.get_solo_fight(key) if mode == 'solo' else db.get_fight_by_id(key)
    assert row['status'] == 'cancelled' if mode == 'solo' else row.status.value == 'cancelled'
    if mode == 'solo':
        from systems.card_upgrade_system import CardUpgradeSystem
        assert not CardUpgradeSystem(db).is_management_locked(1)


def test_stale_easy_timer_cannot_resurrect_an_abandoned_match(games):
    db, modes = games
    key = block(games, 'easy')
    state = modes.get_state(key)
    state['deadline'] = '2000-01-01'
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, key, state)
    assert modes.create_invite(1, 'quick', 'normal')
    assert modes.get_state(key)['phase'] == 'expired'
    with pytest.raises(ValueError):
        modes.resolve_easy_round(key)


def test_stale_risk_refunds_exact_contributions_with_unmatched_raise_only_once(games):
    db, modes = games
    risk = RiskModeSystem(db)
    table = list(RiskTable)[0]
    key = block(games, 'risk')
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE risk_matches SET bluff_phase='waiting' WHERE match_id=?", (key,))
    assert risk.make_action(key, 1, RiskAction.RAISE, 5)['success']
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE risk_matches SET created_at='2000-01-01' WHERE match_id=?", (key,))
    assert modes.create_invite(1, 'quick', 'normal')
    assert modes.create_invite(2, 'quick', 'normal')
    assert db.get_or_create_player(1).coins == db.get_or_create_player(2).coins == 10000
    assert risk.get_risk_match(key)['status'] == 'completed'
    assert risk.make_action(key, 1, RiskAction.CALL)['success'] is False


def test_completed_state_and_timezone_aware_deadlines_do_not_leave_busy_flags(games):
    db, modes = games
    key = block(games, 'quick')
    state = modes.get_state(key)
    state['deadline'] = (datetime.now(timezone(timedelta(hours=3, minutes=30))) + timedelta(seconds=40)).isoformat()
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, key, state)
    with pytest.raises(ActiveMatchError):
        modes.create_invite(1, 'quick', 'normal')
    state['phase'] = 'completed'
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, key, state)
    assert modes.create_invite(1, 'quick', 'normal')


@pytest.mark.parametrize('mode', ['quick', 'mini_three_round'])
def test_late_accepted_request_cannot_start_over_a_new_game(games, mode):
    db, modes = games
    old = accepted(modes, mode)
    with closing(modes._connect()) as conn, conn:
        conn.execute("UPDATE game_requests SET accepted_at='2000-01-01' WHERE request_id=?", (old,))
    db.create_solo_fight(1, 'easy')
    with pytest.raises(ActiveMatchError):
        if mode == 'quick':
            modes.start_quick_match(old)
        else:
            MiniThreeRoundSystem(db, modes, ArenaRegistry(db), BattleSystem3Rounds(db)).start(old)
    assert modes.get_state(old) is None


def test_late_easy_lobby_start_cannot_take_players_out_of_a_new_game(games):
    db, modes = games
    old = modes.create_easy_lobby(1, -100, 3)['request_id']
    assert modes.join_easy_lobby(old, 2)[0]
    with closing(modes._connect()) as conn, conn:
        conn.execute("UPDATE game_requests SET expires_at='2000-01-01' WHERE request_id=?", (old,))
    db.create_solo_fight(1, 'easy')
    ok, reason, state = modes.start_easy_match(old)
    assert not ok and reason == 'player_busy' and state['phase'] == 'expired'


def test_finished_battle_state_releases_even_if_old_fight_status_was_not_updated(games):
    db, modes = games
    key = db.create_fight(1, 2, -100)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("""INSERT INTO battle_states
            (fight_id,challenger_id,opponent_id,challenger_card_id,opponent_card_id,
             arena,challenger_current_stats,opponent_current_stats,status,created_at)
            VALUES (?,1,2,'alpha','beta','city','{}','{}','completed',?)""", (key, datetime.now().isoformat()))
    assert modes.create_invite(1, 'quick', 'normal')
    assert db.get_fight_by_id(key).status.value == 'completed'


def test_cancelled_easy_lobby_cannot_be_started_by_a_late_timer(games):
    _, modes = games
    key = modes.create_easy_lobby(1, -100, 1)['request_id']
    assert modes.join_easy_lobby(key, 2)[0]
    assert modes.cancel_request(key, 1)
    assert modes.start_easy_match(key)[0] is False
    assert modes.create_invite(1, 'quick', 'normal')


@pytest.mark.parametrize('phase', ['ability_selection', 'stat_selection'])
def test_expired_quick_cannot_consume_ability_or_advance_after_new_game(games, phase):
    db, modes = games
    key = accepted(modes)
    modes.start_quick_match(key)
    modes.select_quick_card(key, 1, 'alpha')
    modes.select_quick_card(key, 2, 'beta')
    modes.grant_ability(1, 'weaken_speed', 1)
    if phase == 'stat_selection':
        modes.select_quick_ability(key, 1, 'skip')
        modes.select_quick_ability(key, 2, 'skip')
    state = modes.get_state(key)
    state['deadline'] = '2000-01-01'
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, key, state)
    db.create_solo_fight(1, 'easy')
    with pytest.raises(ValueError, match='deadline_passed'):
        if phase == 'ability_selection':
            modes.select_quick_ability(key, 1, 'weaken_speed')
        else:
            modes.select_quick_stat(key, 1, modes.allowed_quick_stats(state, 1)[0])
    with closing(modes._connect()) as conn:
        assert conn.execute("SELECT quantity FROM player_ability_inventory WHERE user_id=1 AND ability_key='weaken_speed'").fetchone()[0] == 1
    assert modes.get_state(key)['phase'] == phase


def test_normal_quick_ability_timeout_still_auto_skips_without_releasing_reservation(games):
    _, modes = games
    key = accepted(modes)
    modes.start_quick_match(key)
    modes.select_quick_card(key, 1, 'alpha')
    modes.select_quick_card(key, 2, 'beta')
    state = modes.get_state(key)
    state['deadline'] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2)).isoformat()
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, key, state)
    with pytest.raises(ActiveMatchError):
        modes.create_invite(1, 'quick', 'normal')
    modes.select_quick_ability(key, 1, 'skip', auto_skip=True)
    state, advanced = modes.select_quick_ability(key, 2, 'skip', auto_skip=True)
    assert advanced and state['phase'] == 'stat_selection'
    assert state['ability_choices'] == {'1': 'skip', '2': 'skip'}


def test_expired_risk_entry_is_returned_before_minimum_balance_check(games):
    db, _ = games
    risk = RiskModeSystem(db)
    table = list(RiskTable)[0]
    from systems.risk_mode_system import MIN_BALANCE_MULTIPLIER
    balance = table.value * MIN_BALANCE_MULTIPLIER
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('UPDATE players SET coins=?', (balance,))
    result = risk.create_risk_match(1, 2, table)
    assert result['success']
    assert db.get_or_create_player(1).coins < balance
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE risk_matches SET created_at='2000-01-01' WHERE match_id=?", (result['match_id'],))
    assert risk.can_enter_risk(1, table) == (True, '')
    assert db.get_or_create_player(1).coins == db.get_or_create_player(2).coins == balance
    assert risk.create_risk_match(1, 2, table)['success']
