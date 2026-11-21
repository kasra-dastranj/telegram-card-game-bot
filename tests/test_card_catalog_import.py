import copy
import json
import sqlite3
from contextlib import closing

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.card_catalog_import import (PACKAGE, Replacement, apply, db_digest, load_catalog, preview)
from systems.card_inventory_system import CardInventorySystem
from systems.card_trait_registry import CardTraitRegistry
from systems.game_mode_system import GameModeSystem
from systems.progression_config import config_in, save_config_in, validate_config
from systems.progression_economy import ProgressionEconomy


def connect(db):
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot(db):
    with closing(connect(db)) as conn:
        return db_digest(conn)


def card(db, cid, name, rarity='normal'):
    assert db.add_card(Card(cid, name, CardRarity(rarity), 40, 50, 60, 70,
                            ['old ability'], ['drain'], ['شعار قدیمی'], image_path='assets/test/' + cid + '.png'))


@pytest.fixture
def game(tmp_path):
    db = DatabaseManager(str(tmp_path / 'game.db'))
    modes = GameModeSystem(db)
    card(db, 'heis', 'Heisenberg')
    card(db, 'turtle', 'Michelangelo')
    card(db, 'removed', 'Deadpool')
    card(db, 'rare', 'Rare Hulk', 'rare')
    card(db, 'custom', '__custom:custom', 'legend')
    modes.set_card_metadata('heis', ['mage'], 'Old Series', {'new_dimension': 99}, {})
    with closing(connect(db)) as conn, conn:
        conn.execute("INSERT INTO players(user_id,username,first_name,created_at,coins,total_score,hearts) VALUES(1,'first','First','now',1234,99,6)")
        for cid in ('heis', 'removed', 'rare', 'custom'):
            CardInventorySystem.grant_in(conn, 1, cid, 'rare' if cid == 'rare' else 'legend' if cid == 'custom' else 'normal', 2)
        conn.execute("UPDATE cards SET origin='custom' WHERE card_id='custom'")
        conn.execute("INSERT INTO player_card_missions VALUES(1,'heis',3,0,NULL,0,NULL)")
        conn.execute("INSERT INTO card_missions VALUES('heis','defeat_specific',7,'removed','now')")
        conn.execute("INSERT INTO player_decks VALUES('bad',1,'Bad','heis','removed','turtle',1,'now','now')")
        conn.execute("INSERT INTO player_decks VALUES('good',1,'Good','heis','turtle','heis',1,'now','now')")
        conn.execute("INSERT INTO fight_history(user_id,user_card_id,opponent_card_id,result,score_gained,hearts_lost,fought_at) VALUES(1,'removed','heis','win',1,0,'now')")
        conn.execute("INSERT INTO player_ability_inventory VALUES(1,'reveal_opponent',5)")
        conn.execute("INSERT INTO card_variant_media_cache VALUES((SELECT variant_id FROM card_variants WHERE card_id='heis' AND rarity='normal'),'sticker','existing-file-id','now')")
        conn.execute("INSERT INTO foundation_settings VALUES('deck_presentation:bad','{}')")
        conn.execute("INSERT INTO foundation_settings VALUES('custom-card-notice:1:custom',?)", (json.dumps({'state': 'pending', 'card_id': 'custom'}),))
        conn.execute("INSERT INTO foundation_settings VALUES('card-voices:heis',?)", (json.dumps({'revision': 1, 'media_ids': ['keep']}),))
        from systems.easter_eggs import ensure_in
        ensure_in(conn)
        conn.execute("INSERT INTO easter_rules VALUES('secret',1,?,0,'admin','now','now')", (json.dumps({'rewards': [{'kind': 'card', 'card_id': 'rare', 'rarity': 'rare', 'quantity': 1}], 'per_user_limit': 1}),))
        conn.execute("INSERT INTO easter_events VALUES('event','secret',1,-100,1,'{}','now',?)", (json.dumps({'done': True}),))
        _, config = config_in(conn)
        config['claim']['daily_pool'] = ['heis', 'removed']
        config['claim']['silver_pool'] = ['rare']
        config['claim']['weights'] = {'removed': 2}
        save_config_in(conn, config, 'fixture')
    return db


def install(db, tmp_path):
    catalog = load_catalog()
    plan = preview(db.db_path, catalog)
    result = apply(db.db_path, catalog, plan['plan_hash'], tmp_path / 'backup.db', 'test-owner')
    return catalog, plan, result


def test_source_and_csv_validate_without_rebalancing():
    catalog = load_catalog()
    assert len(catalog['characters']) == 60
    assert sum(len(c['cards']) for c in catalog['characters']) == 180
    assert catalog['characters'][49]['translated_traits'][1] == 'animal'
    assert len({t for c in catalog['characters'] for t in c['translated_traits']}) == 28


def test_preview_is_readonly_and_reports_fields(game):
    before = snapshot(game)
    a = preview(game.db_path, load_catalog())
    b = preview(game.db_path, load_catalog())
    assert snapshot(game) == before
    assert a['plan_hash'] == b['plan_hash']
    assert (a['created'], a['updated'], len(a['removed'])) == (58, 2, 3)
    assert a['matches']['char_013'] == 'heis'
    assert a['matches']['char_006'] == 'turtle'
    change = next(v for v in a['changes'] if v['table'] == 'cards' and v['key'] == {'card_id': 'heis'})
    assert change['fields']['power']['new'] == load_catalog()['characters'][12]['cards'][0]['stats']['power']


@pytest.mark.parametrize('journal_mode', ['delete', 'wal'])
def test_apply_preserves_media_inventory_progression_and_history(game, tmp_path, journal_mode):
    with closing(connect(game)) as conn:
        assert conn.execute('PRAGMA journal_mode=' + journal_mode).fetchone()[0] == journal_mode
        player = tuple(conn.execute('SELECT * FROM players').fetchone())
        history = tuple(conn.execute('SELECT * FROM fight_history').fetchone())
        progress = tuple(conn.execute('SELECT * FROM player_card_missions').fetchone())
        old_arenas = [tuple(v) for v in conn.execute('SELECT * FROM arena_versions')]
    catalog, plan, result = install(game, tmp_path)
    assert result['applied']
    with closing(connect(game)) as conn:
        assert conn.execute('SELECT count(*) FROM cards').fetchone()[0] == 60
        assert conn.execute('SELECT count(*) FROM card_variants').fetchone()[0] == 180
        assert tuple(conn.execute('SELECT * FROM players').fetchone()) == player
        assert tuple(conn.execute('SELECT * FROM fight_history').fetchone()) == history
        assert tuple(conn.execute('SELECT * FROM player_card_missions').fetchone()) == progress
        assert conn.execute('SELECT card_id,quantity FROM player_card_stacks').fetchall()[0][:] == ('heis', 2)
        assert [r[0] for r in conn.execute('SELECT deck_id FROM player_decks')] == ['good']
        assert conn.execute('SELECT quantity FROM player_ability_inventory').fetchone()[0] == 5
        assert conn.execute('SELECT file_id FROM card_variant_media_cache').fetchone()[0] == 'existing-file-id'
        assert conn.execute("SELECT dialogs,image_path,abilities,card_effects FROM cards WHERE card_id='heis'").fetchone()[:] == (
            json.dumps(['شعار قدیمی'], ensure_ascii=False, separators=(',', ':')), 'assets/test/heis.png', '[]', '[]')
        assert json.loads(conn.execute("SELECT hidden_stats FROM card_mode_metadata WHERE card_id='heis'").fetchone()[0])['new_dimension'] == 50
        assert conn.execute("SELECT value_json FROM foundation_settings WHERE key='card-voices:heis'").fetchone()
        assert json.loads(conn.execute("SELECT value_json FROM foundation_settings WHERE key='custom-card-notice:1:custom'").fetchone()[0])['state'] == 'cancelled'
        assert not conn.execute("SELECT 1 FROM foundation_settings WHERE key='deck_presentation:bad'").fetchone()
        assert conn.execute('SELECT count(*) FROM retired_card_catalog').fetchone()[0] == 3
        assert not list(conn.execute('PRAGMA foreign_key_check'))
        for old in old_arenas:
            assert tuple(conn.execute('SELECT * FROM arena_versions WHERE arena_id=? AND version=?', old[:2]).fetchone()) == old
        for char in catalog['characters']:
            cid = plan['matches'][char['character_id']]
            for n, form in enumerate(char['cards'], 1):
                stored = conn.execute('SELECT * FROM card_variants WHERE card_id=? AND rarity=?', (cid, form['rarity'].lower())).fetchone()
                assert {k: stored[k] for k in form['stats']} == form['stats']
                assert json.loads(stored['traits']) == char['translated_traits'][:n]
                assert stored['passive'] == '{}'
        config = config_in(conn)[1]
        assert set(config['upgrade']) == {'epic', 'legend'}
        assert validate_config(config) == config
        assert ProgressionEconomy.recipe(conn, config, 'no-tier-needed', 'legend')[1] == config['upgrade']['legend']
        conn.execute("UPDATE economy_character_rules SET legend_recipe_tier='B' WHERE card_id='heis'")
        assert ProgressionEconomy.recipe(conn, config, 'heis', 'legend')[1] == config['upgrade']['legend']
        assert all(cid not in ('removed', 'rare') for cid in config['claim']['daily_pool'] + config['claim']['silver_pool'])
        reward = json.loads(conn.execute('SELECT payload_json FROM easter_rules').fetchone()[0])['rewards'][0]
        assert reward['card_id'] not in ('rare', 'custom') and reward['rarity'] == 'normal'
        assert conn.execute('SELECT count(*) FROM easter_events').fetchone()[0] == 1
    with closing(sqlite3.connect(tmp_path / 'backup.db')) as backup:
        assert backup.execute('SELECT count(*) FROM cards').fetchone()[0] == 5


def test_restart_and_replay_preserve_future_panel_cards(game, tmp_path):
    catalog, plan, _ = install(game, tmp_path)
    reopened = DatabaseManager(game.db_path)
    modes = GameModeSystem(reopened)
    assert len(CardTraitRegistry(reopened).list_traits()) == 28
    card(reopened, 'future', 'Future Card')
    modes.set_card_metadata('future', ['Future Trait'], collections=['Future Collection'])
    before = snapshot(reopened)
    assert preview(reopened.db_path, catalog)['replayed']
    assert apply(reopened.db_path, catalog, plan['plan_hash'], tmp_path / 'unused.db', 'test')['replayed']
    assert snapshot(reopened) == before
    assert reopened.get_card_by_id('future')
    assert not (tmp_path / 'unused.db').exists()


def test_stale_plan_and_apply_failure_do_not_mutate_game(game, tmp_path, monkeypatch):
    catalog = load_catalog()
    plan = preview(game.db_path, catalog)
    with closing(connect(game)) as conn, conn:
        conn.execute('UPDATE players SET coins=coins+1')
    before = snapshot(game)
    with pytest.raises(ValueError, match='stale'):
        apply(game.db_path, catalog, plan['plan_hash'], tmp_path / 'stale.db', 'owner')
    assert snapshot(game) == before
    assert not (tmp_path / 'stale.db').exists()
    plan = preview(game.db_path, catalog)
    original = Replacement.cleanup
    calls = []
    def fail_on_real_apply(self):
        original(self)
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError('simulated apply failure')
    monkeypatch.setattr(Replacement, 'cleanup', fail_on_real_apply)
    with pytest.raises(RuntimeError, match='simulated'):
        apply(game.db_path, catalog, plan['plan_hash'], tmp_path / 'rollback.db', 'owner')
    assert snapshot(game) == before


def test_active_game_and_ambiguous_identity_refuse_import(game):
    modes = GameModeSystem(game)
    # A second spelling of the same character is an explicit conflict.
    card(game, 'duplicate', 'هایزنبرگ')
    with pytest.raises(ValueError, match='Ambiguous'):
        preview(game.db_path, load_catalog())
    with closing(connect(game)) as conn, conn:
        conn.execute("DELETE FROM card_variants WHERE card_id='duplicate'")
        conn.execute("DELETE FROM cards WHERE card_id='duplicate'")
        conn.execute("INSERT INTO game_requests(request_id,creator_id,mode,variant,source,status,rounds,created_at,expires_at,updated_at) VALUES('active',1,'quick','normal','telegram','waiting',1,'now','tomorrow','now')")
    with pytest.raises(ValueError, match='Active games'):
        preview(game.db_path, load_catalog())


def test_multiple_collections_engine_and_easy_membership(game):
    from systems.easy_questions import evaluate_card
    modes = GameModeSystem(game)
    names = ['Set ' + str(i) for i in range(7)]
    for cid in ('heis', 'turtle', 'removed'):
        modes.set_card_metadata(cid, [], collections=names)
    result = modes.calculate_deck_synergy(['heis', 'turtle', 'removed'])
    assert sum('سه کارت از' in text for text in result['reasons']) == 7
    assert result['score'] >= 28
    assert modes.get_card_metadata('heis')['collections'] == names
    assert evaluate_card(modes, game.get_card_by_id('heis'), {'series': 'Set 6', 'formula': 'iq'})['eligible']
    assert not evaluate_card(modes, game.get_card_by_id('heis'), {'series': 'Missing', 'formula': 'iq'})['eligible']


def test_panel_roundtrip_and_future_creation(game, tmp_path):
    from web.web_api import WebAPI
    install(game, tmp_path)
    api = WebAPI(game)
    client = api.app.test_client()
    existing = api._serialize_card(game.get_card_by_id('heis'))
    forms = {v['rarity']: {k: v[k] for k in ('power', 'speed', 'iq', 'popularity', 'traits', 'abilities', 'card_effects', 'image_path', 'card_type', 'passive')} for v in existing['variants']}
    payload = {'name': 'Future Panel Card', 'collections': ['New Collection', 'Second Collection'], 'variants': forms}
    response = client.post('/api/cards/family', json=payload)
    assert response.status_code == 201, response.get_json()
    created = response.get_json()['card']
    assert created['collections'] == payload['collections']
    assert client.get('/api/card-editor/options').get_json()['collections'][-1] is not None
    assert 'Second Collection' in client.get('/api/card-editor/options').get_json()['series']
    with closing(connect(game)) as conn:
        assert conn.execute('SELECT legend_recipe_tier FROM economy_character_rules WHERE card_id=?', (created['id'],)).fetchone()[0] == 'A'


def test_historical_101_identity_preview(tmp_path):
    from systems.card_catalog_import import ROOT
    db = DatabaseManager(str(tmp_path / 'historical.db'))
    GameModeSystem(db)
    manifest = json.loads((ROOT / 'content/trial_card_missions_v1.json').read_text(encoding='utf-8'))
    for n, entry in enumerate(manifest['missions']):
        card(db, 'old-' + str(n), entry['card_name'])
    result = preview(db.db_path, load_catalog())
    assert (result['created'], result['updated'], len(result['removed'])) == (12, 48, 53)


def test_mission_history_survives_replacement_without_rewriting_ledger(game, tmp_path):
    from datetime import datetime, timedelta, timezone
    from systems.progression_missions import save_mission_in, ProgressionMissions
    from systems.reward_ledger import record_in
    mission = dict(mission_id='keep-progress', title='Old mission', description='Old mission',
                   start=None, end=None, status='active', type='character_games', target=5,
                   filters={'card_id': 'removed', 'trait': 'mage'}, eligibility={},
                   xp_reward=1, coin_reward=1, repeat_policy='once')
    with closing(connect(game)) as conn, conn:
        save_mission_in(conn, mission, 'owner')
        version, config = config_in(conn)
        record_in(conn, 'old-match', 1, 'match', 'match',
                  {'card_id': 'removed', 'traits': ['mage'], 'qualified': True, 'mode': 'quick'},
                  {}, version, now=datetime.now(timezone.utc)-timedelta(days=1))
        old = tuple(conn.execute("SELECT * FROM reward_ledger WHERE operation_id='old-match'").fetchone())
        assert ProgressionMissions.progress_in(conn, 1, mission, config)['current_progress'] == 1
    install(game, tmp_path)
    with closing(connect(game)) as conn, conn:
        mission = json.loads(conn.execute("SELECT definition_json FROM economy_missions WHERE mission_id='keep-progress'").fetchone()[0])
        version, config = config_in(conn)
        assert ProgressionMissions.progress_in(conn, 1, mission, config)['current_progress'] == 1
        record_in(conn, 'new-match', 1, 'match', 'match',
                  {'card_id': mission['filters']['card_id'], 'traits': [mission['filters']['trait']], 'qualified': True, 'mode': 'quick'},
                  {}, version)
        assert ProgressionMissions.progress_in(conn, 1, mission, config)['current_progress'] == 2
        assert tuple(conn.execute("SELECT * FROM reward_ledger WHERE operation_id='old-match'").fetchone()) == old


@pytest.mark.parametrize('mutation', ['stat', 'type', 'total', 'trait', 'duplicate'])
def test_bad_source_is_rejected(tmp_path, mutation):
    source = json.loads((PACKAGE / 'telbattle_cards.json').read_text(encoding='utf-8'))
    first = source['characters'][0]
    if mutation == 'stat': first['cards'][0]['stats']['power'] = 99
    if mutation == 'type': first['cards'][0]['card_type_fa'] = 'قدرتی'
    if mutation == 'total': first['cards'][0]['total'] += 1
    if mutation == 'trait': first['traits'][0] = 'Unreviewed Trait'
    if mutation == 'duplicate': source['characters'][1]['character_id'] = first['character_id']
    file = tmp_path / 'bad.json'
    file.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError):
        load_catalog(file, None)
