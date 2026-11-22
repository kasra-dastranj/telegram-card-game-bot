"""Explicit, reversible text-only import. Never called during game startup."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from systems.hidden_stat_profiles import encode, fingerprint

PACKAGE = Path(__file__).resolve().parents[1] / 'content/card_lore_20261122'
ROSTER = PACKAGE.parent / 'card_catalog_20261121/telbattle_cards.json'
PREFIX = 'card-lore-import:'
REGISTRY = 'card-lore:'


def load_bundle(package=PACKAGE):
    package=Path(package)
    source=json.loads((package/'telbattle_lore.json').read_text(encoding='utf-8-sig'))
    manifest=json.loads((package/'identity_mapping.json').read_text(encoding='utf-8-sig'))
    roster=json.loads(ROSTER.read_text(encoding='utf-8-sig'))
    if source.get('schema_version')!='1.0.0' or source.get('data_kind')!='character_biographies_and_victory_lines':
        raise ValueError('Unsupported lore source schema')
    if manifest.get('source_hash')!=fingerprint(source) or manifest.get('roster_hash')!=fingerprint(roster):
        raise ValueError('Source or roster differs from the reviewed mapping')
    if not re.fullmatch(r'[a-z0-9-]{1,100}',manifest.get('bundle_id','')):
        raise ValueError('Invalid bundle version')
    chars=source.get('characters');mapping=manifest.get('mappings')
    if not isinstance(chars,list) or len(chars)!=60 or not isinstance(mapping,list) or len(mapping)!=60:
        raise ValueError('Expected 60 source characters and mappings')
    indexed={m['temporary_id']:m for m in mapping}
    expected={c['character_id'] for c in roster['characters']}
    if len(indexed)!=60 or {m['source_character_id'] for m in mapping}!=expected:
        raise ValueError('Missing, duplicate or unexpected canonical mapping')
    seen=set();lines=[];result=[]
    for char in chars:
        cid=char.get('temporary_id');match=indexed.get(cid)
        if not match or cid in seen or char.get('name_fa')!=match['name_fa']:
            raise ValueError('Character identity differs from reviewed mapping')
        seen.add(cid)
        bio=char.get('bio_lines')
        if not isinstance(bio,list) or len(bio)!=3 or any(not isinstance(s,str) or not s.strip() or '\n' in s or '\r' in s for s in bio) or char.get('bio_text')!='\n'.join(bio):
            raise ValueError('Expected exactly three independent biography lines')
        victory=char.get('victory_lines')
        if not isinstance(victory,list) or len(victory)<5:
            raise ValueError('Each character needs at least five victory lines; no fixed upper limit')
        texts=set()
        for line in victory:
            if not isinstance(line,dict) or not isinstance(line.get('temporary_id'),str) or not line['temporary_id']:
                raise ValueError('Invalid stable line identity')
            text=line.get('text')
            if not isinstance(text,str) or not text.strip() or '\n' in text or '\r' in text or text in texts:
                raise ValueError('Empty, multiline or duplicate victory text')
            texts.add(text)
            if line.get('kind') not in ('original_game_line','verified_short_quote') or line.get('language') not in ('fa','en'):
                raise ValueError('Invalid victory provenance or language')
            if not isinstance(line.get('usage_permission'),str) or not line['usage_permission']:
                raise ValueError('Missing source permission status')
            if line['kind']=='verified_short_quote' and urlsplit(line.get('reference_url') or '').scheme not in ('http','https'):
                raise ValueError('A quoted line needs its source URL')
        lines.extend(victory)
        result.append({**char,'source_character_id':match['source_character_id']})
    if len({line['temporary_id'] for line in lines})!=len(lines) or source.get('victory_line_count')!=len(lines) or source.get('character_count')!=60:
        raise ValueError('Source counts or line identities are inconsistent')
    decisions=manifest.get('owner_decisions',{})
    if decisions.get('davood_is_dozd_o_polis') is not True or type(decisions.get('activate_verified_short_quotes')) is not bool:
        raise ValueError('Reviewed content decisions are missing')
    return dict(bundle_id=manifest['bundle_id'],bundle_hash=fingerprint(manifest),
                roster_hash=manifest['roster_hash'],source_hash=manifest['source_hash'],
                characters=result,decisions=decisions)


def read_in(conn,key):
    row=conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',(key,)).fetchone()
    return row[0] if row else None


def receipt_in(conn,bundle):
    raw=read_in(conn,PREFIX+bundle['bundle_id'])
    if raw:
        receipt=json.loads(raw)
        if receipt['bundle_hash']!=bundle['bundle_hash']:
            raise ValueError('Bundle version already used with different content; review a new version')
        return receipt


def dialogs(raw):
    if not raw:return []
    try:value=json.loads(raw)
    except json.JSONDecodeError:value=[raw]
    if not isinstance(value,list) or any(not isinstance(line,str) for line in value):
        raise ValueError('Existing dialogs are not a text list; review rather than replace')
    return value


def plan_in(conn,bundle,rollback=False):
    prior=receipt_in(conn,bundle)
    if rollback:
        if not prior:raise ValueError('This bundle has not been applied')
        if prior['state']=='rolled_back':return {**prior,'status':'already_rolled_back'}
        targets=[];conflicts=[]
        for old in prior['targets']:
            row=conn.execute('SELECT biography,dialogs FROM cards WHERE card_id=?',(old['card_id'],)).fetchone()
            now=dict(row) if row else None
            registry=read_in(conn,REGISTRY+old['card_id'])
            if now!=old['after'] or registry!=old['registry_after']:conflicts.append(old['card_id'])
            targets.append(dict(old,current=now,current_registry=registry))
        token=fingerprint({'bundle':bundle['bundle_hash'],'rollback':targets})
        return {**prior,'status':'rollback_preview','plan_hash':token,'targets':targets,'conflicts':conflicts}
    if prior:
        if prior['state']=='rolled_back':raise ValueError('Bundle was rolled back; use a new reviewed version to reapply')
        return {**prior,'status':'already_applied'}
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_import_runs'").fetchone():
        raise ValueError('Applied card catalog receipt is missing')
    row=conn.execute('SELECT receipt_json FROM catalog_import_runs WHERE source_hash=?',(bundle['roster_hash'],)).fetchone()
    if not row:raise ValueError('Applied card catalog identity mapping is missing')
    matches=json.loads(row[0])['matches']
    targets=[];used=set();active=0;quotes=0;placeholder_count=0
    for char in bundle['characters']:
        cid=matches.get(char['source_character_id'])
        row=conn.execute('SELECT name,origin,biography,dialogs FROM cards WHERE card_id=?',(cid,)).fetchone()
        if not row or row['origin']!='official' or cid in used:raise ValueError('Missing or ambiguous official character: '+char['name_fa'])
        used.add(cid)
        old_registry=read_in(conn,REGISTRY+cid)
        existing=dialogs(row['dialogs'])
        kept=[text for text in existing if text.strip() and text.strip()!='من بردم']
        placeholder_count+=sum(text.strip()=='من بردم' for text in existing)
        pool=list(dict.fromkeys(kept));normalized={text.strip() for text in pool};registry_lines=[]
        for line in char['victory_lines']:
            enabled=line['kind']=='original_game_line' or bundle['decisions']['activate_verified_short_quotes']
            registry_lines.append({**line,'line_id':char['source_character_id']+':'+line['temporary_id'],'active':enabled})
            if enabled:
                active+=1;quotes+=line['kind']=='verified_short_quote'
                if line['text'].strip() not in normalized:
                    pool.append(line['text']);normalized.add(line['text'].strip())
        registry=encode(dict(bundle_id=bundle['bundle_id'],source_hash=bundle['source_hash'],
            source_character_id=char['source_character_id'],name_fa=char['name_fa'],
            bio_lines=char['bio_lines'],origin=char['origin'],review_note=char.get('review_note',''),
            lines=registry_lines,owner_decisions=bundle['decisions']))
        before={key:row[key] for key in ('biography','dialogs')}
        after=dict(biography=char['bio_text'],dialogs=encode(pool))
        targets.append(dict(card_id=cid,source_character_id=char['source_character_id'],
            temporary_id=char['temporary_id'],name_fa=char['name_fa'],current_name=row['name'],
            before=before,after=after,registry_before=old_registry,registry_after=registry,
            incoming_lines=len(char['victory_lines']),retained_existing_lines=len(set(kept))))
    token=fingerprint({'bundle':bundle['bundle_hash'],'before':[(t['card_id'],t['before'],t['registry_before']) for t in targets]})
    return dict(status='preview',state='preview',bundle_id=bundle['bundle_id'],bundle_hash=bundle['bundle_hash'],
        source_hash=bundle['source_hash'],plan_hash=token,character_count=len(targets),bio_line_count=3*len(targets),
        incoming_lines=sum(t['incoming_lines'] for t in targets),active_incoming_lines=active,active_quotes=quotes,
        removed_placeholders=placeholder_count,changed_biographies=sum(t['before']['biography']!=t['after']['biography'] for t in targets),
        changed_dialog_pools=sum(t['before']['dialogs']!=t['after']['dialogs'] for t in targets),targets=targets,
        extra_official_cards=[dict(r) for r in conn.execute("SELECT card_id,name FROM cards WHERE origin='official' ORDER BY card_id") if r['card_id'] not in used])


def preview(db_path,bundle,rollback=False):
    path=Path(db_path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
        conn.row_factory=sqlite3.Row;conn.execute('BEGIN')
        return plan_in(conn,bundle,rollback)


def backup_in(path,backup):
    protected={path,Path(str(path)+'-wal'),Path(str(path)+'-shm'),ROSTER.resolve(),
               *(p.resolve() for p in PACKAGE.iterdir() if p.is_file())}
    if backup in protected or backup.exists() or not backup.parent.is_dir():
        raise ValueError('Backup must be a new separate file in an existing directory')
    with backup.open('xb'):pass
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as reader:
        with closing(sqlite3.connect(str(backup))) as saved:
            reader.backup(saved)
            if saved.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')


def apply(db_path,bundle,plan_hash,backup_path,actor,rollback=False):
    if not isinstance(actor,str) or not actor.strip():raise ValueError('Owner actor is required')
    path=Path(db_path).resolve(strict=True);backup=Path(backup_path).resolve()
    with closing(sqlite3.connect(str(path),timeout=30)) as conn:
        conn.row_factory=sqlite3.Row
        try:
            conn.execute('BEGIN IMMEDIATE');plan=plan_in(conn,bundle,rollback)
            if plan['plan_hash']!=plan_hash:raise ValueError('Text changed since preview; generate a new plan')
            if plan['status'].startswith('already_'):
                conn.rollback();return plan
            if plan.get('conflicts'):raise ValueError('Text changed after import; rollback would overwrite later edits')
            backup_in(path,backup)
            for target in plan['targets']:
                content=target['before'] if rollback else target['after']
                conn.execute('UPDATE cards SET biography=?,dialogs=? WHERE card_id=?',
                             (content['biography'],content['dialogs'],target['card_id']))
                registry=target['registry_before'] if rollback else target['registry_after']
                if registry is None:conn.execute('DELETE FROM foundation_settings WHERE key=?',(REGISTRY+target['card_id'],))
                else:conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES(?,?)',(REGISTRY+target['card_id'],registry))
            receipt={**plan,'state':'rolled_back' if rollback else 'applied','status':'rolled_back' if rollback else 'applied',
                     'actor':actor,'backup':str(backup),'at':datetime.now(timezone.utc).isoformat()}
            conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES(?,?)',(PREFIX+bundle['bundle_id'],encode(receipt)))
            conn.commit();return receipt
        except Exception:
            conn.rollback();raise
