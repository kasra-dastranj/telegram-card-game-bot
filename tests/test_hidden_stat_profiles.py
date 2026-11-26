import json
import sqlite3
from contextlib import closing

import pytest

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.easy_questions import CORE_STATS, HIDDEN_STATS, catalog_in, save_catalog_in
from systems.game_mode_system import GameModeSystem
from systems.hidden_stat_profiles import PREFIX, PROFILE_PATH, apply, encode, load_profile, preview
from web.web_api import WebAPI


def connect(db):
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot(db):
    with closing(connect(db)) as conn:
        return {name: [dict(r) for r in conn.execute('SELECT * FROM "'+name+'"')]
                for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}


@pytest.fixture
def game(tmp_path):
    db = DatabaseManager(str(tmp_path / 'hidden.db'))
    GameModeSystem(db)
    profile = load_profile()
    matches = {}
    with closing(connect(db)) as conn, conn:
        for n, char in enumerate(profile['characters'], 1):
            cid = 'live-' + str(n).zfill(3)
            matches[char['source_character_id']] = cid
            data = Card(cid, char['name_fa'], CardRarity.NORMAL, 3, 5, 7, 9,
                        [], dialogs=['Keep my slogan'], image_path='keep-'+cid+'.webp').to_dict()
            conn.execute('INSERT INTO cards(' + ','.join(data) + ') VALUES(' + ','.join('?' for _ in data) + ')', tuple(data.values()))
            conn.execute('INSERT INTO card_mode_metadata VALUES(?,?,?,?,?)',
                         (cid, '["Genius"]', '["Keep","Both"]', encode({**dict.fromkeys(HIDDEN_STATS, 50), 'custom_dimension': 77}), '{}'))
        db._ensure_card_variants(conn)
        conn.execute("INSERT INTO card_variant_media_cache SELECT variant_id,'sticker','keep-'||variant_id,'now' FROM card_variants")
        conn.execute('CREATE TABLE catalog_import_runs(source_hash TEXT PRIMARY KEY,policy_hash TEXT NOT NULL,receipt_json TEXT NOT NULL)')
        conn.execute('INSERT INTO catalog_import_runs VALUES(?,?,?)', (profile['roster_hash'], 'fixture', encode({'matches': matches})))
    db.get_or_create_player(1)
    with closing(connect(db)) as conn, conn:
        conn.execute('UPDATE players SET coins=1234,total_score=55,hearts=7 WHERE user_id=1')
        conn.execute("INSERT INTO player_ability_inventory VALUES(1,'reveal_opponent',6)")
    return db


def install(db, tmp_path, suffix=''):
    profile = load_profile()
    plan = preview(db.db_path, profile)
    return profile, plan, apply(db.db_path, profile, plan['plan_hash'], tmp_path / ('before'+suffix+'.db'), 'owner')


def test_authored_profile_has_480_complete_bounded_values_and_character_contrasts():
    profile = load_profile()
    chars = {c['source_character_id']: c['values'] for c in profile['characters']}
    assert len(chars) == 60 and sum(len(v) for v in chars.values()) == 480
    assert chars['char_018']['funny'] > chars['char_027']['funny'] + 50
    assert chars['char_059']['management'] > chars['char_005']['management'] + 50
    assert chars['char_037']['survival'] > chars['char_037']['management'] + 50
    assert chars['char_053']['leadership'] > chars['char_053']['management']
    assert chars['char_020']['funny'] > chars['char_020']['scary']


@pytest.mark.parametrize('selected_form', ['normal', 'epic', 'legend'])
def test_panel_save_from_one_form_is_shared_by_all_forms(game, selected_form):
    api = WebAPI(game)
    card = api._serialize_card(game.get_card_by_id_for_rarity('live-001', selected_form))
    fields = ('power', 'speed', 'iq', 'popularity', 'card_type', 'traits', 'abilities', 'card_effects',
              'image_path', 'photo_file_id', 'sticker_file_id', 'passive')
    forms = {v['rarity']: {key: v[key] for key in fields} for v in card['variants']}
    values = {key: 31+n for n, key in enumerate(HIDDEN_STATS)}
    response = api.app.test_client().put('/api/cards/live-001/family',
        json={'name': card['name'], 'hidden_stats': values, 'variants': forms})
    assert response.status_code == 200, response.get_json()
    reopened = GameModeSystem(DatabaseManager(game.db_path))
    for rarity in ('normal', 'epic', 'legend'):
        assert reopened.get_card_metadata('live-001', rarity)['hidden_stats'] == {
            **{key: card['hidden_stats'][key] for key in CORE_STATS}, **values,
        }
        assert reopened._hidden_stat_value(game.get_card_by_id_for_rarity('live-001', rarity), 'funny') == values['funny']
        assert {key: response.get_json()['card']['variants'][('normal','epic','legend').index(rarity)][key]
                for key in ('power','speed','iq','popularity')} == {key: forms[rarity][key] for key in ('power','speed','iq','popularity')}


def test_preview_is_readonly_and_stable(game):
    before = snapshot(game)
    a, b = preview(game.db_path, load_profile()), preview(game.db_path, load_profile())
    assert a['plan_hash'] == b['plan_hash']
    assert a['character_count'] == 60 and a['value_count'] == 480 and a['changed_values'] > 400
    assert all(t['card_id'].startswith('live-') for t in a['targets'])
    assert snapshot(game) == before


@pytest.mark.parametrize('journal', ['delete', 'wal'])
def test_apply_changes_only_shared_hidden_values_and_receipt(game, tmp_path, journal):
    with closing(connect(game)) as conn:
        assert conn.execute('PRAGMA journal_mode='+journal).fetchone()[0] == journal
    before = snapshot(game)
    profile, plan, result = install(game, tmp_path)
    after = snapshot(game)
    assert result['applied']
    for table in before:
        if table not in ('card_mode_metadata', 'foundation_settings'):
            assert after[table] == before[table], table
    prior_settings = {r['key']: r['value_json'] for r in before['foundation_settings']}
    new_settings = {r['key']: r['value_json'] for r in after['foundation_settings']}
    assert {k: v for k, v in new_settings.items() if not k.startswith(PREFIX)} == prior_settings
    assert len(new_settings) == len(prior_settings)+1
    values = {t['card_id']: t['values'] for t in plan['targets']}
    for old, new in zip(before['card_mode_metadata'], after['card_mode_metadata']):
        assert {k:v for k,v in old.items() if k!='hidden_stats'} == {k:v for k,v in new.items() if k!='hidden_stats'}
        assert json.loads(new['hidden_stats']) == {**values[new['card_id']], 'custom_dimension': 77}
    modes = GameModeSystem(game)
    for rarity in ('normal','epic','legend'):
        assert modes.get_card_metadata('live-001', rarity)['hidden_stats']['management'] == values['live-001']['management']
    with sqlite3.connect(tmp_path / 'before.db') as saved:
        saved.row_factory = sqlite3.Row
        assert [dict(r) for r in saved.execute('SELECT * FROM card_mode_metadata')] == before['card_mode_metadata']


def test_parallel_media_edits_and_extra_dimensions_survive_apply(game, tmp_path):
    profile = load_profile()
    plan = preview(game.db_path, profile)
    game.add_card(Card('future-before-apply', 'Future before apply', CardRarity.NORMAL, 1, 2, 3, 4, []))
    with closing(connect(game)) as conn, conn:
        conn.execute("UPDATE cards SET image_path='fresh.webp',dialogs='[\"fresh slogan\"]' WHERE card_id='live-001'")
        conn.execute("UPDATE card_variant_media_cache SET file_id='fresh-sticker' WHERE variant_id IN (SELECT variant_id FROM card_variants WHERE card_id='live-001')")
        stats = json.loads(conn.execute("SELECT hidden_stats FROM card_mode_metadata WHERE card_id='live-001'").fetchone()[0])
        stats['luck'] = 91
        conn.execute("UPDATE card_mode_metadata SET hidden_stats=?,series='New collection' WHERE card_id='live-001'", (encode(stats),))
        catalog = catalog_in(conn)
        catalog['stats']['luck'] = 'شانس'
        save_catalog_in(conn, catalog, 'panel-owner')
    fresh = preview(game.db_path, profile)
    assert fresh['plan_hash'] == plan['plan_hash'] and fresh['unscored_dimensions'] == ['luck']
    assert fresh['unrated_characters'] == [{'card_id': 'future-before-apply', 'name': 'Future before apply'}]
    apply(game.db_path, profile, plan['plan_hash'], tmp_path / 'media-before.db', 'owner')
    with closing(connect(game)) as conn:
        assert conn.execute("SELECT image_path FROM cards WHERE card_id='live-001'").fetchone()[0] == 'fresh.webp'
        assert conn.execute("SELECT series FROM card_mode_metadata WHERE card_id='live-001'").fetchone()[0] == 'New collection'
        assert json.loads(conn.execute("SELECT hidden_stats FROM card_mode_metadata WHERE card_id='live-001'").fetchone()[0])['luck'] == 91
        assert conn.execute("SELECT COUNT(*) FROM card_variant_media_cache WHERE file_id='fresh-sticker'").fetchone()[0] == 3
    assert game.get_card_by_id('future-before-apply')


def test_hidden_edit_after_preview_rejects_stale_plan(game, tmp_path):
    profile = load_profile()
    plan = preview(game.db_path, profile)
    with closing(connect(game)) as conn, conn:
        stats = json.loads(conn.execute("SELECT hidden_stats FROM card_mode_metadata WHERE card_id='live-001'").fetchone()[0])
        stats['funny'] = 51
        conn.execute("UPDATE card_mode_metadata SET hidden_stats=? WHERE card_id='live-001'", (encode(stats),))
    before = snapshot(game)
    with pytest.raises(ValueError, match='changed since preview'):
        apply(game.db_path, profile, plan['plan_hash'], tmp_path / 'stale.db', 'owner')
    assert snapshot(game) == before and not (tmp_path / 'stale.db').exists()


def test_replay_preserves_later_panel_changes_and_new_characters(game, tmp_path):
    profile, plan, _ = install(game, tmp_path)
    with closing(connect(game)) as conn, conn:
        conn.execute("UPDATE card_mode_metadata SET hidden_stats='{}' WHERE card_id='live-001'")
    game.add_card(Card('future', 'Future', CardRarity.NORMAL, 1, 2, 3, 4, []))
    before = snapshot(game)
    assert preview(game.db_path, profile)['replayed']
    assert apply(game.db_path, profile, plan['plan_hash'], tmp_path / 'before.db', 'owner')['replayed']
    assert snapshot(game) == before and game.get_card_by_id('future')


def test_error_near_end_rolls_back_every_character(game, tmp_path):
    with closing(connect(game)) as conn, conn:
        conn.execute("CREATE TRIGGER stop_patch BEFORE UPDATE OF hidden_stats ON card_mode_metadata WHEN OLD.card_id='live-060' BEGIN SELECT RAISE(ABORT,'test failure'); END")
    profile = load_profile()
    plan = preview(game.db_path, profile)
    before = snapshot(game)
    with pytest.raises(sqlite3.IntegrityError, match='test failure'):
        apply(game.db_path, profile, plan['plan_hash'], tmp_path / 'rollback.db', 'owner')
    assert snapshot(game) == before
    with sqlite3.connect(tmp_path / 'rollback.db') as conn:
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'


def test_active_easy_blocks_apply_until_match_finishes(game, tmp_path):
    with closing(connect(game)) as conn, conn:
        conn.execute("INSERT INTO game_requests(request_id,creator_id,mode,variant,source,status,rounds,created_at,expires_at,updated_at) VALUES('active',1,'easy','normal','group','active',3,'now','tomorrow','now')")
    profile = load_profile()
    plan = preview(game.db_path, profile)
    assert plan['active_easy_matches'] == 1
    before = snapshot(game)
    with pytest.raises(ValueError, match='Finish active Easy'):
        apply(game.db_path, profile, plan['plan_hash'], tmp_path / 'quiet.db', 'owner')
    assert snapshot(game) == before and not (tmp_path / 'quiet.db').exists()
    with closing(connect(game)) as conn, conn:
        conn.execute("UPDATE game_requests SET status='completed'")
    assert apply(game.db_path, profile, plan['plan_hash'], tmp_path / 'quiet.db', 'owner')['applied']


@pytest.mark.parametrize('kind', ['range','bool','missing','duplicate','wrong-name'])
def test_invalid_profile_fails_validation(tmp_path, kind):
    data = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
    if kind=='range': data['characters'][0]['values']['funny']=101
    if kind=='bool': data['characters'][0]['values']['funny']=True
    if kind=='missing': data['characters'][0]['values'].pop('funny')
    if kind=='duplicate': data['characters'][1]['source_character_id']=data['characters'][0]['source_character_id']
    if kind=='wrong-name': data['characters'][0]['name_fa']='Wrong character'
    file = tmp_path / 'invalid.json'
    file.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError): load_profile(file)


def test_cli_preview_apply_and_same_command_replay_are_explicit(game, tmp_path, monkeypatch, capsys):
    import sys
    from migrations.apply_hidden_stat_profiles import main
    report = tmp_path / 'preview.json'
    base = ['hidden', '--db', game.db_path, '--report', str(report)]
    monkeypatch.setattr(sys, 'argv', base)
    main()
    assert json.loads(capsys.readouterr().out)['status'] == 'preview'
    plan = json.loads(report.read_text(encoding='utf-8'))
    command = [*base, '--apply-plan', plan['plan_hash'], '--backup', str(tmp_path/'cli-before.db'), '--actor', 'owner']
    monkeypatch.setattr(sys, 'argv', command)
    main()
    assert json.loads(capsys.readouterr().out)['status'] == 'applied'
    before = snapshot(game)
    main()
    assert json.loads(capsys.readouterr().out)['status'] == 'already_applied'
    assert snapshot(game) == before


@pytest.mark.parametrize('target', ['db', 'profile', 'backup', 'missing-parent'])
def test_cli_report_never_clobbers_inputs_or_backup(game, tmp_path, monkeypatch, target):
    import sys
    from migrations.apply_hidden_stat_profiles import main
    backup = tmp_path/'before.db'
    paths = {'db': game.db_path, 'profile': PROFILE_PATH, 'backup': backup,
             'missing-parent': tmp_path/'missing'/'report.json'}
    original = PROFILE_PATH.read_bytes()
    before = snapshot(game)
    monkeypatch.setattr(sys, 'argv', ['hidden', '--db', game.db_path, '--report', str(paths[target]),
                                    '--apply-plan', 'wrong', '--backup', str(backup), '--actor', 'owner'])
    with pytest.raises(SystemExit): main()
    assert snapshot(game) == before and PROFILE_PATH.read_bytes() == original and not backup.exists()


def test_changed_content_cannot_reuse_applied_profile_version(game, tmp_path):
    install(game, tmp_path)
    data = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
    data['characters'][0]['values']['funny'] += 1
    path = tmp_path/'changed.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    before = snapshot(game)
    with pytest.raises(ValueError, match='different content'):
        preview(game.db_path, load_profile(path))
    assert snapshot(game) == before
