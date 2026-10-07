"""Two-player Mini App three-round flow and its player-scoped state."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from core.models import Card, CardRarity
from game_core import DatabaseManager
from systems.arena_registry import ArenaRegistry
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.game_mode_system import GameModeSystem
from systems.mini_three_round_system import MiniThreeRoundSystem
from systems.mode_access_system import ModeAccessSystem
import web.miniapp_api as miniapp


def headers(user_id):
    return {"X-Debug-User-Id": str(user_id)}


def ready_solo(client, monkeypatch):
    monkeypatch.setattr(miniapp.AsoAI, 'select_card', lambda self, db: db.get_card_by_id('three-b'))
    monkeypatch.setattr(miniapp.AsoAI, 'select_stat', lambda self, available, *args: available[0])
    response = post(client, '/api/v1/solo/start', 101,
                    {'player_card_id': 'three-a', 'difficulty': 'easy'})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['ai_card'] is None
    return response.get_json()['fight_id']


def solo_ability(client, fight_id, key, round_number=1, user_id=101):
    return post(client, '/api/v1/solo/ability', user_id,
                {'fight_id': fight_id, 'ability_key': key, 'round': round_number})


def solo_round(client, fight_id, stat='power'):
    result = post(client, '/api/v1/solo/round', 101, {'fight_id': fight_id, 'player_stat': stat})
    assert result.status_code == 200, result.get_json()
    return result.get_json()


def test_solo_reveal_uses_shared_stock_once_and_survives_new_api_client(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reveal_opponent', 2)
    modes.grant_ability(101, 'weaken_speed')
    fight_id = ready_solo(client, monkeypatch)
    used = solo_ability(client, fight_id, 'reveal_opponent')
    assert used.status_code == 200, used.get_json()
    assert used.get_json()['ai_card']['card_id'] == 'three-b'
    assert used.get_json()['my_ability']['round'] == 1
    assert used.get_json()['abilities'] == []
    assert quantity(modes, 101, 'reveal_opponent') == 1
    result = solo_round(client, fight_id)
    assert result['fight']['current_round'] == 2
    assert result['fight']['my_ability_used'] is True
    assert solo_ability(client, fight_id, 'weaken_speed', 2).get_json()['reason'] == 'ability_already_used'
    assert quantity(modes, 101, 'weaken_speed') == 1
    restored = miniapp.app.test_client().get(f'/api/v1/solo/fights/{fight_id}', headers=headers(101)).get_json()
    assert restored['ai_card']['card_id'] == 'three-b'
    assert restored['my_ability_used'] is True
    pvp = ready_three(client, modes)
    assert use_ability(client, pvp, 101, 'reveal_opponent').status_code == 200
    assert quantity(modes, 101, 'reveal_opponent') == 0


@pytest.mark.parametrize('stat', ['power', 'speed', 'iq', 'popularity'])
def test_solo_weaken_exact_stat_floors_at_zero_and_keeps_natural_locks(client_and_modes, monkeypatch, stat):
    client, modes = client_and_modes
    modes.grant_ability(101, f'weaken_{stat}')
    fight_id = ready_solo(client, monkeypatch)
    assert solo_round(client, fight_id)['fight']['current_round'] == 2
    before = modes.db.get_solo_fight(fight_id)
    current = json.loads(before['ai_current_stats'])
    current[stat] = 1
    modes.db.update_solo_fight(fight_id, ai_current_stats=json.dumps(current))
    result = solo_ability(client, fight_id, f'weaken_{stat}', 2)
    assert result.status_code == 200, result.get_json()
    after = modes.db.get_solo_fight(fight_id)
    current[stat] = 0
    assert json.loads(after['ai_current_stats']) == current
    assert after['player_used_stats'] == before['player_used_stats']
    assert after['ai_used_stats'] == before['ai_used_stats']
    assert result.get_json()['available_stats'] == ['speed', 'iq', 'popularity']
    assert result.get_json()['ai_card'] is None
    assert quantity(modes, 101, f'weaken_{stat}') == 0
    if stat == 'speed':
        round_result = solo_round(client, fight_id, 'speed')
        assert round_result['ai_value'] == 0


@pytest.mark.parametrize('round_number', [2, 3])
def test_solo_reroll_in_later_round_preserves_history_and_recomputes_boost(client_and_modes, monkeypatch, round_number):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reroll_arena')
    fight_id = ready_solo(client, monkeypatch)
    solo_round(client, fight_id)
    if round_number == 3:
        solo_round(client, fight_id, 'speed')
    before = modes.db.get_solo_fight(fight_id)
    replacement = {'arena_id': 'qa-speed', 'name_fa': 'New arena', 'boost_stat': 'speed',
                   'boost_amount': 4, 'version': 1, 'abilities_enabled': True,
                   'requires_card_type_match': False}
    monkeypatch.setattr(miniapp, 'select_arena', lambda *args, **kwargs: replacement.copy())
    result = solo_ability(client, fight_id, 'reroll_arena', round_number)
    assert result.status_code == 200, result.get_json()
    payload = result.get_json()
    assert payload['arena']['arena_id'] == 'qa-speed'
    assert payload['my_boosts']['speed'] == 4
    assert '_three_round_ability' not in payload['arena']
    assert payload['my_ability']['round'] == round_number
    after = modes.db.get_solo_fight(fight_id)
    assert after['rounds_history'] == before['rounds_history']
    assert after['arena_version'] == 1
    assert quantity(modes, 101, 'reroll_arena') == 0
    stat = 'speed' if round_number == 2 else 'iq'
    finished = solo_round(client, fight_id, stat)
    assert finished['player_boost'] == (4 if stat == 'speed' else 0)
    history = json.loads(modes.db.get_solo_fight(fight_id)['rounds_history'])
    assert history[-1]['arena']['arena_id'] == 'qa-speed'
    assert history[0]['arena']['arena_id'] == before['arena']


@pytest.mark.parametrize('stat', ['power', 'speed', 'iq', 'popularity'])
def test_solo_lock_abilities_cannot_be_listed_or_consumed(client_and_modes, monkeypatch, stat):
    client, modes = client_and_modes
    key = f'lock_{stat}'
    modes.grant_ability(101, key)
    fight_id = ready_solo(client, monkeypatch)
    view = client.get(f'/api/v1/solo/fights/{fight_id}', headers=headers(101)).get_json()
    assert not view['abilities']
    result = solo_ability(client, fight_id, key)
    assert result.status_code == 400
    assert result.get_json()['reason'] == 'ability_not_supported'
    assert quantity(modes, 101, key) == 1


def test_solo_ability_rejects_outsider_stale_round_unknown_unowned_and_completed(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reveal_opponent', 2)
    fight_id = ready_solo(client, monkeypatch)
    assert solo_ability(client, fight_id, 'reveal_opponent', user_id=202).status_code == 404
    assert client.get(f'/api/v1/solo/fights/{fight_id}', headers=headers(202)).status_code == 404
    for key, round_number, reason in [('unknown', 1, 'unknown_ability'),
        ('weaken_speed', 1, 'ability_not_owned'), ('reveal_opponent', True, 'invalid_round'),
        ('reveal_opponent', 2, 'round_changed')]:
        assert solo_ability(client, fight_id, key, round_number).get_json()['reason'] == reason
    solo_round(client, fight_id)
    assert solo_ability(client, fight_id, 'reveal_opponent', 1).get_json()['reason'] == 'round_changed'
    assert quantity(modes, 101, 'reveal_opponent') == 2
    modes.db.update_solo_fight(fight_id, status='completed')
    assert solo_ability(client, fight_id, 'reveal_opponent', 2).get_json()['reason'] == 'match_not_ready'
    assert quantity(modes, 101, 'reveal_opponent') == 2


def test_solo_disabled_arena_and_no_alternative_never_consume_stock(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reroll_arena')
    fight_id = ready_solo(client, monkeypatch)
    fight = modes.db.get_solo_fight(fight_id)
    arena = json.loads(fight['arena_snapshot'])
    arena['abilities_enabled'] = False
    modes.db.update_solo_fight(fight_id, arena_snapshot=json.dumps(arena))
    assert solo_ability(client, fight_id, 'reroll_arena').get_json()['reason'] == 'abilities_disabled'
    arena['abilities_enabled'] = True
    modes.db.update_solo_fight(fight_id, arena_snapshot=json.dumps(arena))
    monkeypatch.setattr(miniapp.arena_registry, 'select_for_match', lambda *args, **kwargs:
                        {'arena_id': fight['arena'], 'version': 1})
    assert solo_ability(client, fight_id, 'reroll_arena').get_json()['reason'] == 'no_alternative_arena'
    assert quantity(modes, 101, 'reroll_arena') == 1


def test_solo_ability_duplicate_requests_and_failed_persistence_are_atomic(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'weaken_speed', 2)
    fight_id = ready_solo(client, monkeypatch)
    before = modes.db.get_solo_fight(fight_id)
    with closing(modes._connect()) as conn, conn:
        conn.execute("CREATE TRIGGER fail_solo BEFORE UPDATE ON solo_fights BEGIN SELECT RAISE(ABORT, 'failed'); END")
    with pytest.raises(sqlite3.IntegrityError):
        solo_ability(client, fight_id, 'weaken_speed')
    assert modes.db.get_solo_fight(fight_id) == before
    assert quantity(modes, 101, 'weaken_speed') == 2
    with closing(modes._connect()) as conn, conn:
        conn.execute('DROP TRIGGER fail_solo')
    def use(_):
        return solo_ability(miniapp.app.test_client(), fight_id, 'weaken_speed').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(use, range(2))) == [200, 409]
    assert quantity(modes, 101, 'weaken_speed') == 1
    assert json.loads(modes.db.get_solo_fight(fight_id)['ai_current_stats'])['speed'] == 68


@pytest.fixture()
def client_and_modes(tmp_path, monkeypatch):
    database = DatabaseManager(str(tmp_path / "three.db"))
    modes = GameModeSystem(database)
    arena_registry = ArenaRegistry(database)
    engine = MiniThreeRoundSystem(database, modes, arena_registry, BattleSystem3Rounds(database))
    monkeypatch.setattr(miniapp, "db", database)
    monkeypatch.setattr(miniapp, "quick_modes", modes)
    monkeypatch.setattr(miniapp, "mini_three_round", engine)
    monkeypatch.setattr(miniapp, "arena_registry", arena_registry)
    monkeypatch.setattr(miniapp, "battle_system", engine.battle_system)
    miniapp.app.config.update(TESTING=True, DEBUG=True)
    for user_id, card_id, power in ((101, "three-a", 80), (202, "three-b", 80)):
        card = Card(card_id=card_id, name=f"Hero {user_id}", rarity=CardRarity.NORMAL,
                    power=power, speed=70, iq=60, popularity=50, abilities=[],
                    card_type="POWER_TYPE")
        assert database.add_card(card)
        database.get_or_create_player(user_id)
        assert database.add_card_to_player(user_id, card_id)
    return miniapp.app.test_client(), modes


def post(client, path, user_id, payload=None):
    return client.post(path, json=payload or {}, headers=headers(user_id))


def test_trial_level_gate_returns_clear_error_for_three_round(client_and_modes):
    client, modes = client_and_modes
    ModeAccessSystem(modes.db).set_min_level("mini_three_round", 2)
    response = post(client, "/api/v1/three-round/matchmaking", 101)
    assert response.status_code == 403
    assert response.get_json()["reason"] == "mode_locked"
    assert "Level 2" in response.get_json()["error"]
    modes.db.update_progression(101, level=2)
    assert post(client, "/api/v1/three-round/matchmaking", 101).status_code == 201


def test_random_match_is_separate_from_quick_and_hides_cards(client_and_modes):
    client, _ = client_and_modes
    quick = post(client, "/api/v1/quick/matchmaking", 101, {"variant": "normal"}).get_json()
    first = post(client, "/api/v1/three-round/matchmaking", 101)
    assert first.status_code == 201
    assert first.get_json()["request_id"] != quick["request_id"]
    assert client.get(f"/api/v1/three-round/requests/{quick['request_id']}", headers=headers(101)).status_code == 404
    second = post(client, "/api/v1/three-round/matchmaking", 202)
    assert second.status_code == 200
    match = second.get_json()
    assert match["phase"] == "card_selection"
    assert match["opponent_card"] is None
    request_id = match["request_id"]
    assert client.get(f"/api/v1/quick/requests/{request_id}", headers=headers(101)).status_code == 404
    assert client.get(f"/api/v1/three-round/requests/{request_id}", headers=headers(303)).status_code == 404
    assert post(client, f"/api/v1/three-round/matches/{request_id}/card", 101, {"card_id": "three-b"}).status_code == 409
    selected = post(client, f"/api/v1/three-round/matches/{request_id}/card", 101, {"card_id": "three-a"})
    assert selected.status_code == 200
    assert selected.get_json()["opponent_card"] is None
    assert post(client, f"/api/v1/three-round/matches/{request_id}/card", 202, {"card_id": "three-b"}).status_code == 200
    selected = client.get(f"/api/v1/three-round/requests/{request_id}", headers=headers(101)).get_json()
    assert selected["opponent_card"] is None  # Must spend reveal_opponent to see it.
    assert selected["arena"]["arena_id"] == match["arena"]["arena_id"]


def test_invite_three_tie_and_unique_stats(client_and_modes):
    client, _ = client_and_modes
    invite = post(client, "/api/v1/three-round/invites", 101).get_json()
    assert "?three_invite=" in invite["invite_url"]
    token = invite["invite_token"]
    assert post(client, f"/api/v1/quick/invites/{token}/accept", 202).status_code == 404
    accepted = post(client, f"/api/v1/three-round/invites/{token}/accept", 202)
    assert accepted.status_code == 200
    request_id = invite["request_id"]
    for user_id, card_id in ((101, "three-a"), (202, "three-b")):
        assert post(client, f"/api/v1/three-round/matches/{request_id}/card", user_id, {"card_id": card_id}).status_code == 200
    for round_index, stat in enumerate(("power", "speed", "iq"), start=1):
        first = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 101, {"stat": stat})
        assert first.status_code == 200
        assert first.get_json()["last_round"] is None if round_index == 1 else first.get_json()["last_round"]["round"] == round_index - 1
        if round_index == 2:
            assert post(client, f"/api/v1/three-round/matches/{request_id}/stat", 101, {"stat": "power"}).status_code == 409
        second = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 202, {"stat": stat})
        assert second.status_code == 200
        assert second.get_json()["last_round"]["winner_id"] is None
    final = second.get_json()
    assert final["status"] == "completed"
    assert final["report"]["is_tie"] is True
    assert len(final["report"]["rounds"]) == 3
    assert final["report"]["rewards"] == {"101": {"xp": 3, "score": 0}, "202": {"xp": 3, "score": 0}}
    assert client_and_modes[1].db.get_or_create_progression(101)["total_xp"] == 3


def test_two_round_wins_finish_early_and_preserve_calculation(client_and_modes):
    client, _ = client_and_modes
    first = post(client, "/api/v1/three-round/matchmaking", 101).get_json()
    post(client, "/api/v1/three-round/matchmaking", 202)
    request_id = first["request_id"]
    for user_id, card_id in ((101, "three-a"), (202, "three-b")):
        post(client, f"/api/v1/three-round/matches/{request_id}/card", user_id, {"card_id": card_id})
    for mine, rival in (("power", "popularity"), ("speed", "iq")):
        hidden = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 101, {"stat": mine}).get_json()
        assert hidden["opponent_stat_selected"] is False
        final = post(client, f"/api/v1/three-round/matches/{request_id}/stat", 202, {"stat": rival}).get_json()
        last = final["last_round"]
        assert last["winner_id"] == 101
        assert last["values"]["101"]["total"] == last["values"]["101"]["base"] + last["values"]["101"]["boost"]
    assert final["status"] == "completed"
    assert final["report"]["winner_id"] == 101
    assert len(final["report"]["rounds"]) == 2
    assert final["report"]["rewards"] == {"101": {"xp": 10, "score": 10}, "202": {"xp": 3, "score": 0}}
    assert client_and_modes[1].db.get_or_create_player(101).total_score == 10


def test_deadline_forfeits_to_player_who_chose(client_and_modes):
    client, modes = client_and_modes
    first = post(client, "/api/v1/three-round/matchmaking", 101).get_json()
    post(client, "/api/v1/three-round/matchmaking", 202)
    request_id = first["request_id"]
    post(client, f"/api/v1/three-round/matches/{request_id}/card", 101, {"card_id": "three-a"})
    state = modes.get_state(request_id)
    state["deadline"] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)).isoformat()
    with modes._connect() as conn:
        modes._save_state(conn, request_id, state)
    final = client.get(f"/api/v1/three-round/requests/{request_id}", headers=headers(101)).get_json()
    assert final["status"] == "completed"
    assert final["report"]["winner_id"] == 101
    assert final["report"]["forfeit"] is True


def ready_three(client, modes):
    match = post(client, '/api/v1/three-round/matchmaking', 101).get_json()
    post(client, '/api/v1/three-round/matchmaking', 202)
    request_id = match['request_id']
    for user_id, card_id in ((101, 'three-a'), (202, 'three-b')):
        response = post(client, f'/api/v1/three-round/matches/{request_id}/card', user_id, {'card_id': card_id})
        assert response.status_code == 200
    return request_id


def use_ability(client, request_id, user_id, ability, round_number=1):
    return post(client, f'/api/v1/three-round/matches/{request_id}/ability', user_id,
                {'ability_key': ability, 'round': round_number})


def next_tied_round(client, request_id, stat='power'):
    for user_id in (101, 202):
        response = post(client, f'/api/v1/three-round/matches/{request_id}/stat', user_id, {'stat': stat})
        assert response.status_code == 200, response.get_json()
    return response.get_json()


def quantity(modes, user_id, ability):
    with closing(modes._connect()) as conn:
        row = conn.execute('SELECT quantity FROM player_ability_inventory WHERE user_id=? AND ability_key=?',
                           (user_id, ability)).fetchone()
        return row[0] if row else 0


def store_three(modes, request_id, state):
    with closing(modes._connect()) as conn, conn:
        modes._save_state(conn, request_id, state)


def test_three_reveal_is_private_once_per_match_and_survives_restart(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reveal_opponent', 2)
    modes.grant_ability(101, 'weaken_speed')
    request_id = ready_three(client, modes)
    used = use_ability(client, request_id, 101, 'reveal_opponent')
    assert used.status_code == 200, used.get_json()
    assert used.get_json()['opponent_card']['card_id'] == 'three-b'
    assert used.get_json()['my_stat_locked'] is False
    assert used.get_json()['my_ability_used'] is True
    assert used.get_json()['my_ability']['round'] == 1
    assert used.get_json()['abilities'] == []
    assert quantity(modes, 101, 'reveal_opponent') == 1
    other = client.get(f'/api/v1/three-round/requests/{request_id}', headers=headers(202)).get_json()
    assert other['opponent_card'] is None
    assert other['my_ability_used'] is False
    assert other['opponent_ability_used'] is True
    assert use_ability(client, request_id, 101, 'reveal_opponent').get_json()['reason'] == 'ability_already_used'
    assert next_tied_round(client, request_id)['round'] == 2
    assert use_ability(client, request_id, 101, 'weaken_speed', 2).get_json()['reason'] == 'ability_already_used'
    assert quantity(modes, 101, 'weaken_speed') == 1
    engine = miniapp.mini_three_round
    monkeypatch.setattr(miniapp, 'mini_three_round', MiniThreeRoundSystem(
        modes.db, modes, engine.arena_registry, engine.battle_system))
    restored = client.get(f'/api/v1/three-round/requests/{request_id}', headers=headers(101)).get_json()
    assert restored['my_ability_used'] is True
    assert restored['opponent_card']['card_id'] == 'three-b'
    modes.grant_ability(202, 'reveal_opponent')
    assert use_ability(client, request_id, 202, 'reveal_opponent', 2).status_code == 200


def test_three_inventory_is_the_same_inventory_consumed_by_quick(client_and_modes):
    client, modes = client_and_modes
    modes.grant_ability(101, 'weaken_speed', 2)
    request_id = ready_three(client, modes)
    assert use_ability(client, request_id, 101, 'weaken_speed').status_code == 200
    assert quantity(modes, 101, 'weaken_speed') == 1
    quick = post(client, '/api/v1/quick/matchmaking', 101, {'variant': 'normal'}).get_json()
    post(client, '/api/v1/quick/matchmaking', 202, {'variant': 'normal'})
    quick_id = quick['request_id']
    for user_id, card_id in ((101, 'three-a'), (202, 'three-b')):
        post(client, f'/api/v1/quick/matches/{quick_id}/card', user_id, {'card_id': card_id})
    state = modes.get_state(quick_id)
    modes._store_arena_snapshot(state, modes._arena('city'))
    store_three(modes, quick_id, state)
    modes.select_quick_ability(quick_id, 101, 'weaken_speed')
    assert quantity(modes, 101, 'weaken_speed') == 0
    assert not [item for item in modes.list_player_abilities(101) if item['ability_key'] == 'weaken_speed']


@pytest.mark.parametrize('ability,stat', [('weaken_power', 'power'), ('weaken_speed', 'speed'),
                                        ('weaken_iq', 'iq'), ('weaken_popularity', 'popularity')])
def test_three_weaken_targets_exact_stat_and_does_not_add_a_lock(client_and_modes, ability, stat):
    client, modes = client_and_modes
    modes.grant_ability(101, ability)
    request_id = ready_three(client, modes)
    before = modes.get_state(request_id)
    used = use_ability(client, request_id, 101, ability)
    assert used.status_code == 200, used.get_json()
    after = modes.get_state(request_id)
    for name in ('power', 'speed', 'iq', 'popularity'):
        assert after['current_stats']['202'][name] == before['current_stats']['202'][name] - (2 if name == stat else 0)
    assert after['used_stats'] == before['used_stats'] == {'101': [], '202': []}
    assert after['current_stats']['101'] == before['current_stats']['101']
    assert after['deadline'] == before['deadline']
    post(client, f'/api/v1/three-round/matches/{request_id}/stat', 101, {'stat': stat})
    resolved = post(client, f'/api/v1/three-round/matches/{request_id}/stat', 202, {'stat': stat}).get_json()
    assert resolved['last_round']['values']['202']['base'] == before['current_stats']['202'][stat] - 2
    assert resolved['last_round']['abilities']['101']['ability_key'] == ability


def test_three_can_save_weaken_until_second_round_and_floor_is_zero(client_and_modes):
    client, modes = client_and_modes
    modes.grant_ability(101, 'weaken_speed')
    request_id = ready_three(client, modes)
    assert next_tied_round(client, request_id)['round'] == 2
    state = modes.get_state(request_id)
    state['current_stats']['202']['speed'] = 1
    store_three(modes, request_id, state)
    used = use_ability(client, request_id, 101, 'weaken_speed', 2)
    assert used.status_code == 200
    assert modes.get_state(request_id)['current_stats']['202']['speed'] == 0
    assert used.get_json()['my_ability']['round'] == 2


@pytest.mark.parametrize('round_number', [2, 3])
def test_three_reroll_in_later_round_changes_snapshot_and_keeps_old_rounds(client_and_modes, monkeypatch, round_number):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reroll_arena')
    request_id = ready_three(client, modes)
    next_tied_round(client, request_id)
    if round_number == 3:
        next_tied_round(client, request_id, 'speed')
    previous = modes.get_state(request_id)
    replacement = dict(previous['arena'], arena_id='test-new', name_fa='زمین تازه',
                       boost_stat='iq', boost_amount=3, requires_card_type_match=False)
    def select_new(exclude_id=None, allow_fallback=True):
        assert exclude_id == previous['arena']['arena_id']
        return replacement
    monkeypatch.setattr(miniapp.mini_three_round, '_arena', select_new)
    used = use_ability(client, request_id, 101, 'reroll_arena', round_number)
    assert used.status_code == 200, used.get_json()
    assert used.get_json()['arena']['arena_id'] == 'test-new'
    assert used.get_json()['my_boosts']['iq'] == 3
    assert modes.get_state(request_id)['history'] == previous['history']
    assert modes.get_state(request_id)['deadline'] == previous['deadline']
    result = next_tied_round(client, request_id, 'iq')
    assert result['last_round']['arena']['arena_id'] == 'test-new'
    assert result['last_round']['values']['101']['boost'] == 3
    assert quantity(modes, 101, 'reroll_arena') == 0


@pytest.mark.parametrize('ability', ['lock_power', 'lock_speed', 'lock_iq', 'lock_popularity'])
def test_three_never_lists_or_consumes_lock_abilities(client_and_modes, ability):
    client, modes = client_and_modes
    modes.grant_ability(101, ability)
    request_id = ready_three(client, modes)
    snapshot = client.get(f'/api/v1/three-round/requests/{request_id}', headers=headers(101)).get_json()
    assert not any(item['ability_key'] == ability for item in snapshot['abilities'])
    response = use_ability(client, request_id, 101, ability)
    assert response.status_code == 400
    assert response.get_json()['reason'] == 'ability_not_supported'
    assert quantity(modes, 101, ability) == 1
    assert modes.get_state(request_id)['ability_uses'] == {}


def test_three_rejects_unowned_unknown_stale_and_locked_actions_without_consuming(client_and_modes):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reveal_opponent')
    request_id = ready_three(client, modes)
    for ability, reason in [('weaken_power', 'ability_not_owned'), ('boost_15', 'unknown_ability')]:
        assert use_ability(client, request_id, 101, ability).get_json()['reason'] == reason
    assert use_ability(client, request_id, 303, 'reveal_opponent').status_code == 404
    assert use_ability(client, request_id, 101, 'reveal_opponent', True).status_code == 400
    next_tied_round(client, request_id)
    assert use_ability(client, request_id, 101, 'reveal_opponent', 1).get_json()['reason'] == 'round_changed'
    post(client, f'/api/v1/three-round/matches/{request_id}/stat', 101, {'stat': 'speed'})
    assert use_ability(client, request_id, 101, 'reveal_opponent', 2).get_json()['reason'] == 'choice_locked'
    assert quantity(modes, 101, 'reveal_opponent') == 1
    assert modes.get_state(request_id)['ability_uses'] == {}


def test_three_disabled_arena_and_timeout_do_not_consume(client_and_modes):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reveal_opponent')
    request_id = ready_three(client, modes)
    state = modes.get_state(request_id)
    state['arena']['abilities_enabled'] = False
    store_three(modes, request_id, state)
    assert use_ability(client, request_id, 101, 'reveal_opponent').get_json()['reason'] == 'abilities_disabled'
    assert quantity(modes, 101, 'reveal_opponent') == 1
    state['deadline'] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)).isoformat()
    store_three(modes, request_id, state)
    assert use_ability(client, request_id, 101, 'reveal_opponent').status_code == 409
    assert quantity(modes, 101, 'reveal_opponent') == 1


def test_three_no_alternate_published_arena_does_not_consume_or_use_legacy(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reroll_arena')
    request_id = ready_three(client, modes)
    state = modes.get_state(request_id)
    state['arena']['version'] = 1
    store_three(modes, request_id, state)
    registry = miniapp.mini_three_round.arena_registry
    monkeypatch.setattr(registry, 'select_for_match', lambda *args, **kwargs: dict(state['arena']))
    assert use_ability(client, request_id, 101, 'reroll_arena').get_json()['reason'] == 'no_alternative_arena'
    monkeypatch.setattr(registry, 'select_for_match', lambda *args, **kwargs: None)
    assert use_ability(client, request_id, 101, 'reroll_arena').get_json()['reason'] == 'no_alternative_arena'
    assert quantity(modes, 101, 'reroll_arena') == 1
    assert modes.get_state(request_id)['arena'] == state['arena']


def test_three_concurrent_double_click_consumes_only_one_inventory_item(client_and_modes):
    client, modes = client_and_modes
    modes.grant_ability(101, 'reveal_opponent', 2)
    request_id = ready_three(client, modes)
    def click():
        with miniapp.app.test_client() as independent:
            return use_ability(independent, request_id, 101, 'reveal_opponent').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: click(), range(2))) == [200, 409]
    assert quantity(modes, 101, 'reveal_opponent') == 1
    assert len(modes.get_state(request_id)['ability_uses']) == 1


def test_three_older_active_json_and_stock_rollback_on_save_failure(client_and_modes, monkeypatch):
    client, modes = client_and_modes
    modes.grant_ability(101, 'weaken_power')
    request_id = ready_three(client, modes)
    state = modes.get_state(request_id)
    state.pop('ability_uses')
    store_three(modes, request_id, state)
    assert client.get(f'/api/v1/three-round/requests/{request_id}', headers=headers(101)).get_json()['my_ability_used'] is False
    original = modes._save_state
    def broken(*args):
        raise sqlite3.OperationalError('synthetic disk failure')
    monkeypatch.setattr(modes, '_save_state', broken)
    with pytest.raises(sqlite3.OperationalError):
        miniapp.mini_three_round.choose_ability(request_id, 101, 'weaken_power', 1)
    assert quantity(modes, 101, 'weaken_power') == 1
    assert modes.get_state(request_id) == state
    monkeypatch.setattr(modes, '_save_state', original)
    assert use_ability(client, request_id, 101, 'weaken_power').status_code == 200
