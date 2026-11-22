"""Explicit owner-run patch of shared Easy attributes; never a startup seed."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from systems.easy_questions import CORE_STATS, HIDDEN_STATS, catalog_in

PACKAGE = Path(__file__).resolve().parents[1] / 'content/card_catalog_20261121'
PROFILE_PATH = PACKAGE / 'easy_hidden_stats_v1.json'
PREFIX = 'hidden-stat-profile:'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def load_profile(path=PROFILE_PATH):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Invalid shared hidden-stat profile')
    if (data.get('schema_version') != 1 or data.get('shared_across_forms') is not True
            or data.get('stat_keys') != list(HIDDEN_STATS)
            or not isinstance(data.get('profile_id'), str)
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', data.get('profile_id', ''))):
        raise ValueError('Invalid shared hidden-stat profile')
    roster = json.loads((PACKAGE / 'telbattle_cards.json').read_text(encoding='utf-8'))
    expected = {c['character_id']: c['name'] for c in roster['characters']}
    chars = data.get('characters')
    if not isinstance(chars, list) or len(chars) != 60:
        raise ValueError('Expected 60 reviewed character profiles')
    seen = set()
    for char in chars:
        if not isinstance(char, dict):
            raise ValueError('Invalid character profile')
        cid, values = char.get('source_character_id'), char.get('values')
        if cid not in expected or cid in seen:
            raise ValueError('Unknown or duplicate profile identity')
        seen.add(cid)
        if char.get('name_fa') != expected[cid]:
            raise ValueError('Profile label differs from its source identity')
        if not isinstance(values, dict) or set(values) != set(HIDDEN_STATS) or any(type(v) is not int or not 1 <= v <= 100 for v in values.values()):
            raise ValueError('Each profile needs the eight integer values 1..100')
        if not all(isinstance(char.get(k), str) and char[k].strip() for k in ('name_fa', 'portrayal_fa', 'rationale_fa')):
            raise ValueError('Every rating needs its portrayal and rationale')
        if not char.get('source_ids') or any(key not in data.get('sources', {}) for key in char['source_ids']):
            raise ValueError('Every rating needs a declared basis')
    return {**data, 'profile_hash': fingerprint(data), 'roster_hash': fingerprint(roster)}


def _prior(conn, profile):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',
                       (PREFIX + profile['profile_id'],)).fetchone()
    if row:
        receipt = json.loads(row[0])
        if receipt['profile_hash'] != profile['profile_hash']:
            raise ValueError('Profile version already applied with different content; use a new reviewed version')
        return {**receipt, 'replayed': True, 'applied': False}
    return None


def _plan(conn, profile):
    prior = _prior(conn, profile)
    if prior:
        return prior
    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'catalog_import_runs' not in present:
        raise ValueError('Apply the reviewed 60-character roster before hidden attributes')
    row = conn.execute('SELECT receipt_json FROM catalog_import_runs WHERE source_hash=?',
                       (profile['roster_hash'],)).fetchone()
    if not row:
        raise ValueError('Reviewed roster identity mapping is missing')
    matches = json.loads(row[0])['matches']
    registered = catalog_in(conn)['stats']
    if not HIDDEN_STATS.keys() <= registered.keys():
        raise ValueError('A rated dimension was removed or renamed; review the live Easy catalog')
    targets, before = [], []
    used = set()
    for char in profile['characters']:
        cid = matches.get(char['source_character_id'])
        row = conn.execute('SELECT c.name,c.origin,m.hidden_stats FROM cards c '
                           'JOIN card_mode_metadata m USING(card_id) WHERE c.card_id=?', (cid,)).fetchone()
        if not row or row['origin'] != 'official' or cid in used:
            raise ValueError('Character missing or ambiguous: ' + char['name_fa'])
        used.add(cid)
        current = json.loads(row['hidden_stats'])
        if not isinstance(current, dict):
            raise ValueError('Invalid current hidden attributes')
        fields = {key: {'old': current.get(key), 'new': value} for key, value in char['values'].items()
                  if current.get(key) != value}
        targets.append({'source_character_id': char['source_character_id'], 'card_id': cid, 'current_name': row['name'],
                        'name_fa': char['name_fa'], 'values': char['values'], 'changes': fields,
                        'portrayal_fa': char['portrayal_fa'], 'rationale_fa': char['rationale_fa']})
        # Media, other metadata and extra user-authored dimensions intentionally
        # do not invalidate a preview; their current values are kept at apply.
        before.append((cid, {key: current.get(key) for key in HIDDEN_STATS}))
    active = conn.execute("SELECT COUNT(*) FROM game_requests WHERE mode='easy' AND status='active'").fetchone()[0]
    unrated = [dict(r) for r in conn.execute("SELECT card_id,name FROM cards WHERE origin='official' ORDER BY name")
               if r['card_id'] not in used]
    token = fingerprint({'profile': profile['profile_hash'], 'before': before})
    return {'profile_id': profile['profile_id'], 'profile_hash': profile['profile_hash'], 'plan_hash': token,
            'replayed': False, 'applied': False, 'shared_across_forms': True, 'character_count': len(targets),
            'value_count': sum(len(t['values']) for t in targets), 'changed_characters': sum(bool(t['changes']) for t in targets),
            'changed_values': sum(len(t['changes']) for t in targets), 'targets': targets,
            'unscored_dimensions': sorted(set(registered) - set(CORE_STATS) - set(HIDDEN_STATS)),
            'unrated_characters': unrated,
            'active_easy_matches': active}


def preview(db_path, profile):
    path = Path(db_path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN')
        return _plan(conn, profile)


def apply(db_path, profile, plan_hash, backup_path, actor):
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('Owner actor is required')
    path, backup = Path(db_path).resolve(strict=True), Path(backup_path).resolve()
    with closing(sqlite3.connect(str(path), timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN IMMEDIATE')
            plan = _plan(conn, profile)
            if plan['plan_hash'] != plan_hash:
                raise ValueError('Hidden attributes changed since preview; generate a new plan')
            if plan['replayed']:
                conn.rollback()
                return plan
            if plan['active_easy_matches']:
                raise ValueError('Finish active Easy matches before applying ratings')
            if backup.exists() or backup in {path, Path(str(path) + '-wal'), Path(str(path) + '-shm')} or not backup.parent.is_dir():
                raise ValueError('Backup must be a new separate file in an existing directory')
            with backup.open('xb'):
                pass
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as reader:
                with closing(sqlite3.connect(str(backup))) as saved:
                    reader.backup(saved)
                    if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('Backup integrity check failed')
            for target in plan['targets']:
                if not target['changes']:
                    continue
                current = json.loads(conn.execute('SELECT hidden_stats FROM card_mode_metadata WHERE card_id=?',
                                                  (target['card_id'],)).fetchone()[0])
                current.update(target['values'])
                conn.execute('UPDATE card_mode_metadata SET hidden_stats=? WHERE card_id=?',
                             (encode(current), target['card_id']))
            receipt = {**plan, 'applied': True, 'actor': actor, 'applied_at': datetime.now(timezone.utc).isoformat(),
                       'backup': str(backup)}
            conn.execute('INSERT INTO foundation_settings(key,value_json) VALUES(?,?)',
                         (PREFIX + profile['profile_id'], encode(receipt)))
            conn.commit()
            return receipt
        except Exception:
            conn.rollback()
            raise
