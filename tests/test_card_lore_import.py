import copy
import json
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from tests.test_hidden_stat_profiles import game, connect, snapshot
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.card_lore_import import PACKAGE, PREFIX, REGISTRY, load_bundle, preview, apply
from systems.hidden_stat_profiles import encode, fingerprint


def install(db,tmp_path):
    bundle=load_bundle();plan=preview(db.db_path,bundle)
    return bundle,plan,apply(db.db_path,bundle,plan['plan_hash'],tmp_path/'before.db','synthetic-owner')


def test_source_mapping_and_all_314_approved_lines():
    bundle=load_bundle()
    assert len(bundle['characters'])==60
    lines=[line for c in bundle['characters'] for line in c['victory_lines']]
    assert len(lines)==314 and len({l['temporary_id'] for l in lines})==314
    assert sum(l['kind']=='verified_short_quote' for l in lines)==14
    assert sum(l['language']=='en' for l in lines)==13
    assert all(len(c['bio_lines'])==3 and c['bio_text']=='\n'.join(c['bio_lines']) for c in bundle['characters'])
    assert bundle['characters'][23]['source_character_id']=='char_024'
    assert bundle['characters'][55]['source_character_id']=='char_056'
    assert bundle['decisions']['activate_verified_short_quotes']


def test_preview_is_readonly_and_uses_receipt_ids(game):
    before=snapshot(game)
    plan=preview(game.db_path,load_bundle())
    assert plan['character_count']==60 and plan['bio_line_count']==180
    assert plan['incoming_lines']==plan['active_incoming_lines']==314 and plan['active_quotes']==14
    assert plan['changed_biographies']==plan['changed_dialog_pools']==60
    assert all(t['card_id'].startswith('live-') for t in plan['targets'])
    assert plan['plan_hash']==preview(game.db_path,load_bundle())['plan_hash']
    assert snapshot(game)==before


@pytest.mark.parametrize('journal',['DELETE','WAL'])
def test_apply_only_shared_text_and_provenance_and_complete_backup(game,tmp_path,journal):
    with closing(connect(game)) as conn:
        conn.execute('PRAGMA journal_mode='+journal)
    before=snapshot(game);bundle,plan,result=install(game,tmp_path)
    after=snapshot(game)
    assert result['status']=='applied'
    for table in before:
        if table not in ('cards','foundation_settings'):assert after[table]==before[table],table
    for old,new in zip(before['cards'],after['cards']):
        assert {k:v for k,v in old.items() if k not in ('biography','dialogs')}=={k:v for k,v in new.items() if k not in ('biography','dialogs')}
    old_settings={r['key']:r['value_json'] for r in before['foundation_settings']}
    new_settings={r['key']:r['value_json'] for r in after['foundation_settings']}
    assert all(new_settings[k]==v for k,v in old_settings.items())
    assert len(new_settings)-len(old_settings)==61
    for n,char in enumerate(bundle['characters'],1):
        cid='live-'+str(n).zfill(3)
        for rarity in ('normal','epic','legend'):
            card=game.get_card_by_id_for_rarity(cid,rarity)
            assert card.biography==char['bio_text']
            assert set(l['text'] for l in char['victory_lines'])<=set(card.dialogs)
            assert card.dialogs[0]=='Keep my slogan'
        registry=json.loads(new_settings[REGISTRY+cid])
        assert all(l['active'] for l in registry['lines'])
        assert [l['usage_permission'] for l in registry['lines']]==[l['usage_permission'] for l in char['victory_lines']]
        assert registry['review_note']==char['review_note']
    with closing(sqlite3.connect(str(tmp_path/'before.db'))) as conn:
        assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT biography FROM cards WHERE card_id=?',('live-001',)).fetchone()[0]==before['cards'][0]['biography']


def test_random_selection_includes_sixth_line_and_english(game,tmp_path,monkeypatch):
    bundle,_,_=install(game,tmp_path)
    from bot.utils import get_victory_dialog
    import bot.utils as utils
    card=game.get_card_by_id_for_rarity('live-001','legend')
    monkeypatch.setattr(utils.random,'choice',lambda pool:pool[-1])
    assert get_victory_dialog(card.name,card.dialogs)==bundle['characters'][0]['victory_lines'][5]['text']
    assert 'I drink and I know things.' in card.dialogs


def test_replace_known_placeholder_but_preserve_real_legacy_text(game,tmp_path):
    with closing(connect(game)) as conn,conn:
        conn.execute('UPDATE cards SET dialogs=? WHERE card_id=?',(encode(['من بردم','من بردم اما هنوز تموم نشده','  Existing line  ']),'live-001'))
    bundle,_,_=install(game,tmp_path)
    lines=game.get_card_by_id('live-001').dialogs
    assert 'من بردم' not in lines
    assert 'من بردم اما هنوز تموم نشده' in lines and '  Existing line  ' in lines
    assert len(lines)==8


def test_media_stats_new_cards_and_players_do_not_invalidate_text_plan(game,tmp_path):
    bundle=load_bundle();plan=preview(game.db_path,bundle)
    game.add_card(Card('new-extra','Extra',CardRarity.NORMAL,1,2,3,4,[]))
    game.get_or_create_player(99)
    with closing(connect(game)) as conn,conn:
        conn.execute("UPDATE cards SET image_path='new.webp',power=91 WHERE card_id='live-001'")
        conn.execute("UPDATE card_variant_media_cache SET file_id='fresh-sticker'")
    assert preview(game.db_path,bundle)['plan_hash']==plan['plan_hash']
    result=apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'media-before.db','owner')
    assert result['extra_official_cards']==[{'card_id':'new-extra','name':'Extra'}]
    assert game.get_card_by_id('live-001').image_path=='new.webp'
    assert game.get_card_by_id('live-001').power==91


@pytest.mark.parametrize('field',['biography','dialogs','registry'])
def test_stale_plan_never_overwrites_later_text(game,tmp_path,field):
    bundle=load_bundle();plan=preview(game.db_path,bundle)
    with closing(connect(game)) as conn,conn:
        if field=='registry':conn.execute('INSERT INTO foundation_settings VALUES(?,?)',(REGISTRY+'live-001','{}'))
        else:conn.execute('UPDATE cards SET '+field+'=? WHERE card_id=?',('later' if field=='biography' else '["later"]','live-001'))
    before=snapshot(game)
    with pytest.raises(ValueError,match='changed'):apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'stale.db','owner')
    assert snapshot(game)==before and not (tmp_path/'stale.db').exists()


def test_replay_preserves_later_panel_edits_and_refuses_changed_version(game,tmp_path):
    bundle,plan,_=install(game,tmp_path)
    with closing(connect(game)) as conn,conn:conn.execute("UPDATE cards SET biography='later bio' WHERE card_id='live-001'")
    before=snapshot(game)
    assert apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'before.db','owner')['status']=='already_applied'
    assert snapshot(game)==before
    changed={**bundle,'bundle_hash':'changed'}
    with pytest.raises(ValueError,match='different content'):preview(game.db_path,changed)


def test_rollback_restores_exact_original_text_and_metadata_only(game,tmp_path):
    with closing(connect(game)) as conn,conn:
        conn.execute('INSERT INTO foundation_settings VALUES(?,?)',(REGISTRY+'live-001','{"prior":"keep"}'))
        conn.execute("UPDATE cards SET biography=NULL,dialogs=NULL WHERE card_id='live-002'")
    before=snapshot(game);bundle,_,_=install(game,tmp_path)
    game.get_or_create_player(99)
    with closing(connect(game)) as conn,conn:
        conn.execute("UPDATE cards SET image_path='later.webp' WHERE card_id='live-001'")
        conn.execute('UPDATE players SET coins=999 WHERE user_id=99')
    plan=preview(game.db_path,bundle,rollback=True)
    assert plan['conflicts']==[]
    result=apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'undo-before.db','owner',rollback=True)
    assert result['status']=='rolled_back'
    with closing(connect(game)) as conn:
        for card in before['cards']:
            row=conn.execute('SELECT biography,dialogs FROM cards WHERE card_id=?',(card['card_id'],)).fetchone()
            assert tuple(row)==(card['biography'],card['dialogs'])
        assert conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',(REGISTRY+'live-001',)).fetchone()[0]=='{"prior":"keep"}'
        assert conn.execute('SELECT count(*) FROM foundation_settings WHERE key LIKE ?',(REGISTRY+'%',)).fetchone()[0]==1
    assert game.get_card_by_id('live-001').image_path=='later.webp'
    with closing(connect(game)) as conn:
        assert conn.execute('SELECT coins FROM players WHERE user_id=99').fetchone()[0]==999
    assert apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'undo-before.db','owner',rollback=True)['status']=='already_rolled_back'
    with pytest.raises(ValueError,match='rolled back'):preview(game.db_path,bundle)


def test_rollback_refuses_later_panel_text_edits(game,tmp_path):
    bundle,_,_=install(game,tmp_path)
    with closing(connect(game)) as conn,conn:conn.execute("UPDATE cards SET dialogs='[\"later\"]' WHERE card_id='live-001'")
    plan=preview(game.db_path,bundle,rollback=True)
    assert plan['conflicts']==['live-001']
    before=snapshot(game)
    with pytest.raises(ValueError,match='overwrite'):apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'no-undo.db','owner',rollback=True)
    assert snapshot(game)==before and not (tmp_path/'no-undo.db').exists()


def test_mid_import_error_rolls_back_every_row_and_registry(game,tmp_path):
    bundle=load_bundle();plan=preview(game.db_path,bundle)
    with closing(connect(game)) as conn,conn:
        conn.execute("CREATE TRIGGER deny_lore BEFORE UPDATE OF biography ON cards WHEN OLD.card_id='live-060' BEGIN SELECT RAISE(ABORT,'test'); END")
    before=snapshot(game)
    with pytest.raises(sqlite3.IntegrityError):apply(game.db_path,bundle,plan['plan_hash'],tmp_path/'failed-before.db','owner')
    assert snapshot(game)==before
    with closing(sqlite3.connect(str(tmp_path/'failed-before.db'))) as conn:assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'


def test_missing_identity_is_not_guessed_or_created(game):
    with closing(connect(game)) as conn,conn:conn.execute("DELETE FROM cards WHERE card_id='live-024'")
    before=snapshot(game)
    with pytest.raises(ValueError,match='Missing or ambiguous'):preview(game.db_path,load_bundle())
    assert snapshot(game)==before


def test_source_accepts_more_than_six_lines_without_a_runtime_cap(tmp_path):
    data=json.loads((PACKAGE/'telbattle_lore.json').read_text(encoding='utf-8'))
    manifest=json.loads((PACKAGE/'identity_mapping.json').read_text(encoding='utf-8'))
    extra=copy.deepcopy(data['characters'][0]['victory_lines'][-1]);extra.update(temporary_id='tb_victory_01_07',text='A seventh original line')
    data['characters'][0]['victory_lines'].append(extra);data['victory_line_count']+=1
    manifest.update(bundle_id='character-lore-test-v2',source_hash=fingerprint(data))
    (tmp_path/'telbattle_lore.json').write_text(json.dumps(data),encoding='utf-8')
    (tmp_path/'identity_mapping.json').write_text(json.dumps(manifest),encoding='utf-8')
    assert len(load_bundle(tmp_path)['characters'][0]['victory_lines'])==7


def test_cli_preview_apply_rollback_and_report_guards(game,tmp_path):
    report=tmp_path/'report.json';backup=tmp_path/'cli-before.db'
    base=[sys.executable,'migrations/import_card_lore.py','--db',game.db_path,'--report',str(report)]
    def run(*args):
        result=subprocess.run([*base,*args],capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    plan=run();assert plan['status']=='preview'
    result=run('--apply-plan',plan['plan_hash'],'--backup',str(backup),'--actor','owner')
    assert result['status']=='applied'
    assert run()['status']=='already_applied'
    undo=run('--rollback');assert undo['status']=='rollback_preview'
    assert run('--rollback','--apply-plan',undo['plan_hash'],'--backup',str(tmp_path/'cli-undo.db'),'--actor','owner')['status']=='rolled_back'
    before=snapshot(game)
    rejected=subprocess.run([sys.executable,'migrations/import_card_lore.py','--db',game.db_path,'--report',game.db_path],capture_output=True)
    assert rejected.returncode!=0 and snapshot(game)==before
