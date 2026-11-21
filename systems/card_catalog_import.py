"""One reviewed catalog replacement; never called during bot startup.

Planning mutates only an in-memory SQLite copy. Apply requires its exact digest,
an exclusive maintenance window and an SQLite backup made under the write lock.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from systems.card_collections import collection_names, stored_collections, remember_collections
from systems.easy_questions import catalog_in as easy_catalog_in, CORE_STATS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'content/card_catalog_20261121'
STATS = ('power', 'speed', 'iq', 'popularity')
RARITIES = ('normal', 'epic', 'legend')
TYPES = {'قدرتی': 'POWER_TYPE', 'سرعتی': 'SPEED_TYPE', 'هوشی': 'IQ_TYPE', 'محبوبیتی': 'POPULARITY_TYPE'}
OLD_TRAITS = {'hero': 'Hero', 'funny': 'Funny', 'leader': 'Leader', 'villain': 'Villain',
              'monster': 'animal', 'god': 'Superhuman', 'warrior': 'Martial Artist',
              'assassin': 'Stealthy', 'detective': 'Genius', 'mage': 'Strategist'}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(conn, table):
    return [r[1] for r in conn.execute('PRAGMA table_info(' + quote(table) + ')')]


def rows(conn, table):
    return [dict(r) for r in conn.execute('SELECT * FROM ' + quote(table))]


def db_digest(conn):
    material = []
    for table in sorted(tables(conn)):
        material.append((table, sorted((encoded(r) for r in rows(conn, table)))))
    return digest(material)


def identity(value):
    return re.sub(r'[^\w]', '', value.translate(str.maketrans({'ي': 'ی', 'ك': 'ک'})).casefold())


def load_catalog(source=PACKAGE / 'telbattle_cards.json', flat=PACKAGE / 'telbattle_cards_flat.csv'):
    data = json.loads(Path(source).read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != '2.0':
        raise ValueError('Expected reviewed catalog schema 2.0')
    translations = json.loads((PACKAGE / 'trait_translations.json').read_text(encoding='utf-8'))
    aliases = json.loads((PACKAGE / 'identity_aliases.json').read_text(encoding='utf-8'))
    chars, ids, card_ids = copy.deepcopy(data.get('characters')), set(), set()
    if not isinstance(chars, list) or len(chars) != 60:
        raise ValueError('Expected 60 characters')
    for char in chars:
        cid = char['character_id']
        if cid in ids or cid not in aliases or not isinstance(char['name'], str) or not char['name'].strip():
            raise ValueError('Invalid or duplicate character identity: ' + cid)
        ids.add(cid)
        if len(char['traits']) != 3 or len(set(char['traits'])) != 3:
            raise ValueError('Expected three ordered traits: ' + cid)
        try:
            char['translated_traits'] = [translations[t] for t in char['traits']]
            char['card_type'] = TYPES[char['fixed_card_type_fa']]
        except KeyError as exc:
            raise ValueError('Unreviewed trait or type: ' + str(exc)) from exc
        char['collections'] = collection_names(char['collections'])
        if not char['collections'] or len(char['cards']) != 3:
            raise ValueError('Missing collections or forms: ' + cid)
        if [c['rarity'].lower() for c in char['cards']] != list(RARITIES):
            raise ValueError('Expected ordered Normal/Epic/Legend: ' + cid)
        previous = 0
        for card in char['cards']:
            if card['card_id'] in card_ids or card['character_id'] != cid:
                raise ValueError('Duplicate or misplaced form')
            card_ids.add(card['card_id'])
            stats = card['stats']
            if set(stats) != set(STATS) or any(type(v) is not int or not 1 <= v <= 10 for v in stats.values()):
                raise ValueError('Stats must be integers 1..10: ' + card['card_id'])
            if sum(stats.values()) != card['total'] or not 15 <= card['total'] <= 33 or card['total'] <= previous:
                raise ValueError('Invalid total/order: ' + card['card_id'])
            previous = card['total']
            if (card['card_type_fa'] != char['fixed_card_type_fa'] or card['traits'] != char['traits']
                    or card['collections'] != char['collections'] or card['victory_lines']):
                raise ValueError('Conflicting form metadata or unreviewed slogans: ' + card['card_id'])
            # future_card_type_override_fa is deliberately never consumed.
        char.update(aliases[cid])
    if len({t for c in chars for t in c['translated_traits']}) != 28 or len({v for c in chars for v in c['collections']}) != 47:
        raise ValueError('Expected 28 normalized traits and 47 collections')
    if flat is not None:
        with Path(flat).open(encoding='utf-8-sig', newline='') as handle:
            entries = list(csv.DictReader(handle))
        by_id = {r['card_id']: r for r in entries}
        if len(entries) != 180 or len(by_id) != 180 or set(by_id) != card_ids:
            raise ValueError('CSV identities differ from JSON')
        for char in chars:
            for card in char['cards']:
                row = by_id[card['card_id']]
                if (any(int(row[s]) != card['stats'][s] for s in STATS)
                        or int(row['total']) != card['total'] or row['character_id'] != char['character_id']
                        or row['character_name'] != char['name'] or row['rarity'] != card['rarity']
                        or row['card_type_fa'] != card['card_type_fa']
                        or [row['trait_'+str(n)] for n in (1, 2, 3)] != char['traits']
                        or json.loads(row['collections_json']) != char['collections']):
                    raise ValueError('CSV differs from JSON: ' + card['card_id'])
    return {'characters': chars, 'source_hash': digest(data), 'policy_hash': digest([aliases, translations, hashlib.sha256(Path(__file__).read_bytes()).hexdigest()]),
            'warnings': ['Aniimal and Animal normalize to animal', 'Existing internal names are retained to preserve media and slogans',
                         'Future type overrides are ignored']}


def require_quiet(conn):
    present = tables(conn)
    for table, final in [('game_requests', ('completed', 'cancelled', 'expired', 'rejected')),
                         ('active_fights', ('completed', 'cancelled', 'expired', 'rejected')),
                         ('solo_fights', ('completed', 'cancelled', 'expired')),
                         ('risk_matches', ('completed', 'cancelled', 'expired'))]:
        if table in present and conn.execute('SELECT 1 FROM ' + quote(table) + ' WHERE status NOT IN (' +
                                              ','.join('?' for _ in final) + ') LIMIT 1', final).fetchone():
            raise ValueError('Active games must finish before import: ' + table)
    if 'foundation_settings' in present:
        for key, value in conn.execute('SELECT key,value_json FROM foundation_settings'):
            if key.startswith(('group-attacks:open:', 'group-attacks:reserve:', 'group-attacks:player:', 'group-attacks:notice:')):
                raise ValueError('Open attack/reservation must settle before import: ' + key)
    if 'easter_events' in present:
        for row in conn.execute('SELECT delivery_json FROM easter_events'):
            if not json.loads(row[0] or '{}').get('done'):
                raise ValueError('Pending Easter egg delivery must finish before import')


class Replacement:
    def __init__(self, conn, catalog, actor, timestamp):
        self.conn, self.catalog, self.actor, self.now = conn, catalog, actor, timestamp
        self.present = tables(conn)
        self.changes, self.mappings = [], []
        self.traits = {t.casefold(): t for c in catalog['characters'] for t in c['translated_traits']}
        translations = json.loads((PACKAGE / 'trait_translations.json').read_text(encoding='utf-8'))
        self.trait_map = {**{k.casefold(): v for k, v in translations.items()}, **OLD_TRAITS, **self.traits}

    def set(self, table, where, values):
        clause = ' AND '.join(quote(k) + '=?' for k in where)
        old = self.conn.execute('SELECT * FROM ' + quote(table) + ' WHERE ' + clause, tuple(where.values())).fetchone()
        changed = {k: v for k, v in values.items() if old is None or old[k] != v}
        if not changed:
            return
        self.changes.append({'table': table, 'key': where, 'action': 'create' if old is None else 'update',
                             'fields': {k: {'old': old[k] if old else None, 'new': v} for k, v in changed.items()}})
        if old is None:
            merged = {**where, **values}
            self.conn.execute('INSERT INTO ' + quote(table) + '(' + ','.join(map(quote, merged)) + ') VALUES(' +
                              ','.join('?' for _ in merged) + ')', tuple(merged.values()))
        else:
            self.conn.execute('UPDATE ' + quote(table) + ' SET ' + ','.join(quote(k) + '=?' for k in changed) +
                              ' WHERE ' + clause, (*changed.values(), *where.values()))

    def delete(self, table, column, value):
        if table not in self.present:
            return
        old = [dict(r) for r in self.conn.execute('SELECT * FROM ' + quote(table) + ' WHERE ' + quote(column) + '=?', (value,))]
        if old:
            self.changes.append({'table': table, 'action': 'delete', 'key': {column: value}, 'rows': len(old)})
            self.conn.execute('DELETE FROM ' + quote(table) + ' WHERE ' + quote(column) + '=?', (value,))

    def trait(self, value):
        if not value:
            return value
        result = self.trait_map.get(str(value).strip().casefold(), 'Strategist')
        if result != value:
            self.mappings.append({'kind': 'trait', 'old': value, 'new': result})
        return result

    def card_reference(self, value):
        if value and value not in self.card_map and value not in {c['db_id'] for c in self.catalog['characters']}:
            self.card_map[value] = self.catalog['characters'][0]['db_id']
            self.mappings.append({'kind': 'dangling_card_reference', 'old': value, 'new': self.card_map[value]})
        return self.card_map.get(value, value)

    def identities(self):
        existing = rows(self.conn, 'cards')
        claimed, match = set(), {}
        for char in self.catalog['characters']:
            names = {identity(n) for n in [char['name'], *char['aliases']]}
            candidates = [c for c in existing if c['origin'] == 'official' and c['rarity'] != 'rare'
                          and identity(c['name']) in names]
            if len(candidates) > 1:
                raise ValueError('Ambiguous character; provide reviewed aliases: ' + char['name'])
            old = candidates[0] if candidates else None
            cid = old['card_id'] if old else 'catalog-' + re.sub('[^a-z0-9]+', '-', char['canonical_name'].lower()).strip('-')
            if cid in claimed or (not old and any(c['card_id'] == cid for c in existing)):
                raise ValueError('Stable identity collision: ' + cid)
            claimed.add(cid)
            match[char['character_id']] = cid
            char['db_id'] = cid
            char['db_name'] = old['name'] if old else char['canonical_name']
            char['existing'] = old is not None
        self.removed = [c for c in existing if c['card_id'] not in claimed]
        removed_ids = {c['card_id'] for c in self.removed}
        self.affected_users = sorted({r['user_id'] for table in ('player_cards', 'player_card_stacks')
                                      for r in rows(self.conn, table) if r['card_id'] in removed_ids})
        self.affected_decks = [r['deck_id'] for r in rows(self.conn, 'player_decks')
                               if any(r[k] in removed_ids for k in ('card_id_1', 'card_id_2', 'card_id_3'))]
        self.card_map = {}
        for old in self.removed:
            # Deterministic replacement by type; delegated selection is reported.
            target = next((c for c in self.catalog['characters'] if c['card_type'] == old['card_type']), self.catalog['characters'][0])
            self.card_map[old['card_id']] = target['db_id']
            self.mappings.append({'kind': 'card', 'old': old['card_id'], 'old_name': old['name'],
                                  'new': target['db_id'], 'new_name': target['db_name']})
        return match

    def rewrite(self, value):
        if isinstance(value, list):
            return [self.rewrite(v) for v in value]
        if not isinstance(value, dict):
            return value
        old_id = value.get('card_id')
        result = {}
        for key, entry in value.items():
            if key in ('card_id', 'official_card_id', 'target_card') and isinstance(entry, str):
                result[key] = self.card_reference(entry)
            elif key in ('trait', 'required_trait') and isinstance(entry, str):
                result[key] = self.trait(entry)
            elif key == 'trait_ranks':
                seen, ranks = set(), []
                for tier in entry:
                    values = []
                    for name in tier:
                        name = self.trait(name)
                        if name.casefold() not in seen:
                            values.append(name)
                            seen.add(name.casefold())
                    if values:
                        ranks.append(values)
                result[key] = ranks
            else:
                result[key] = self.rewrite(entry)
        if old_id in self.card_map:
            if result.get('rarity') == 'rare' or result.get('rarity') not in RARITIES:
                result['rarity'] = 'normal'
            # NPC explicit art must not continue to show the removed character.
            if 'sticker_file_id' in result:
                result['sticker_file_id'] = ''
            if 'name' in result:
                result['name'] = next(c['db_name'] for c in self.catalog['characters'] if c['db_id'] == result['card_id'])
        return result

    def save_characters(self):
        hidden = {k: 50 for k in easy_catalog_in(self.conn)['stats'] if k not in CORE_STATS}
        for char in self.catalog['characters']:
            cid = char['db_id']
            current = self.conn.execute('SELECT * FROM cards WHERE card_id=?', (cid,)).fetchone()
            base_rarity = current['rarity'] if current else 'normal'
            base = next(c for c in char['cards'] if c['rarity'].lower() == base_rarity)
            dialogs = json.loads(current['dialogs'] or '[]') if current else []
            if not dialogs:
                from core.card_content import content_for_card, load_card_content
                fallback = content_for_card(char['db_name'], load_card_content()) or {}
                dialogs = fallback.get('victory_lines') or ['من بردم']
            values = {**base['stats'], 'abilities': '[]', 'card_effects': '[]', 'dialogs': encoded(dialogs), 'card_type': char['card_type']}
            if not current:
                values.update(name=char['db_name'], rarity='normal', biography='', image_path='', created_at=self.now, origin='official')
            self.set('cards', {'card_id': cid}, values)
            # Include custom hidden dimensions already authored on this character.
            old_meta = self.conn.execute('SELECT hidden_stats FROM card_mode_metadata WHERE card_id=?', (cid,)).fetchone()
            dimensions = {**(json.loads(old_meta[0]) if old_meta else {}), **hidden}
            dimensions = {k: 50 for k in dimensions if k not in CORE_STATS}
            self.set('card_mode_metadata', {'card_id': cid}, {'traits': encoded(char['translated_traits'][:1]),
                     'series': stored_collections(char['collections']), 'hidden_stats': encoded(dimensions), 'passive': '{}'})
            for n, card in enumerate(char['cards'], 1):
                rarity = card['rarity'].lower()
                old = self.conn.execute('SELECT variant_id FROM card_variants WHERE card_id=? AND rarity=?', (cid, rarity)).fetchone()
                form = {**card['stats'], 'card_type': char['card_type'], 'abilities': '[]', 'card_effects': '[]',
                        'passive': '{}', 'traits': encoded(char['translated_traits'][:n])}
                if not old:
                    form.update(variant_id='catalog-form-' + digest([cid, rarity])[:28], image_path='', created_at=self.now, updated_at=self.now)
                self.set('card_variants', {'card_id': cid, 'rarity': rarity}, form)
            if not self.conn.execute('SELECT 1 FROM economy_character_rules WHERE card_id=?', (cid,)).fetchone():
                self.set('economy_character_rules', {'card_id': cid}, {'legend_recipe_tier': 'A'})
            if not self.conn.execute('SELECT 1 FROM card_missions WHERE card_id=?', (cid,)).fetchone():
                self.set('card_missions', {'card_id': cid}, {'mission_type': 'total_wins', 'target': 5, 'target_card': None, 'created_at': self.now})
            for form in self.conn.execute("SELECT variant_id FROM card_variants WHERE card_id=? AND rarity NOT IN ('normal','epic','legend')", (cid,)).fetchall():
                self.delete('card_variant_media_cache', 'variant_id', form[0])
                self.delete('card_variants', 'variant_id', form[0])

    def references(self):
        for row in rows(self.conn, 'card_missions'):
            if row['card_id'] not in self.card_map and row['target_card']:
                self.set('card_missions', {'card_id': row['card_id']}, {'target_card': self.card_reference(row['target_card'])})
        for table, key, field in [('economy_missions', 'mission_id', 'definition_json'), ('easter_rules', 'rule_id', 'payload_json')]:
            if table not in self.present:
                continue
            for row in rows(self.conn, table):
                value = json.loads(row[field])
                changed = self.rewrite(value)
                if changed != value:
                    if table == 'economy_missions' and changed['filters'] != value['filters']:
                        self.set('foundation_settings', {'key': 'catalog_mission_history:' + row[key]},
                                 {'value_json': encoded({'cutover_at': self.now, 'filters_before': value['filters'],
                                                       'filters_after': changed['filters'], 'type': changed['type']})})
                    self.set(table, {key: row[key]}, {field: encoded(changed),
                             ('version' if table == 'economy_missions' else 'revision'): row['version' if table == 'economy_missions' else 'revision'] + 1,
                             'actor': self.actor, 'updated_at': self.now})
        # Only live definitions; immutable events, receipts and attack snapshots remain intact.
        key = 'group-attacks:catalog'
        row = self.conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (key,)).fetchone()
        if row:
            old = json.loads(row[0]); value = self.rewrite(old)
            if value != old:
                value['revision'] += 1
                self.set('foundation_settings', {'key': key}, {'value_json': encoded(value)})
        from systems.easy_questions import CATALOG_KEY
        row = self.conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (CATALOG_KEY,)).fetchone()
        if row:
            old = json.loads(row[0]); value = copy.deepcopy(old)
            collections = sorted({v for c in self.catalog['characters'] for v in c['collections']})
            for question in value['questions']:
                if question['filter'] == 'trait' and question['filter_value']:
                    question['filter_value'] = self.trait(question['filter_value'])
                if question['filter'] == 'series' and question['filter_value'] not in ('', *collections):
                    previous = question['filter_value']
                    question['filter_value'] = collections[0]
                    self.mappings.append({'kind': 'collection_filter', 'old': previous, 'new': collections[0]})
            if value != old:
                value['revision'] += 1
                self.set('foundation_settings', {'key': CATALOG_KEY}, {'value_json': encoded(value)})
        self.arenas()
        from systems.progression_config import config_in, save_config_in
        _, config = config_in(self.conn)
        before = copy.deepcopy(config)
        for key in ('daily_pool', 'silver_pool'):
            config['claim'][key] = list(dict.fromkeys(self.card_reference(v) for v in config['claim'][key]))
        weights = {}
        for key, value in config['claim']['weights'].items():
            mapped = self.card_reference(key)
            weights[mapped] = weights.get(mapped, 0) + value
        config['claim']['weights'] = weights
        config['wheel']['pool'] = self.rewrite(config['wheel']['pool'])
        if 'legend' not in config['upgrade']:
            config['upgrade'] = {'epic': config['upgrade']['epic'], 'legend': config['upgrade']['legend_A']}
        if config != before:
            self.changes.append({'table': 'economy_config_versions', 'action': 'new_version', 'old': before, 'new': config})
            save_config_in(self.conn, config, self.actor)

    def arenas(self):
        from systems.arena_registry import ArenaRegistry
        registry = object.__new__(ArenaRegistry)
        for arena in rows(self.conn, 'arenas'):
            version = arena['current_published_version']
            if not version:
                continue
            old = registry._read_version(self.conn, arena['arena_id'], version)
            value = self.rewrite(old)
            if value == old:
                continue
            next_version = self.conn.execute('SELECT MAX(version)+1 FROM arena_versions WHERE arena_id=?', (arena['arena_id'],)).fetchone()[0]
            registry._insert_version(self.conn, arena['arena_id'], next_version, value, 'published', self.actor, self.now)
            for media in self.conn.execute('SELECT * FROM arena_media WHERE arena_id=? AND version=?', (arena['arena_id'], version)).fetchall():
                item = dict(media); item.update(media_id=digest([media['media_id'], next_version])[:32], version=next_version,
                                               created_at=self.now, created_by=self.actor)
                self.conn.execute('INSERT INTO arena_media(' + ','.join(item) + ') VALUES(' + ','.join('?' for _ in item) + ')', tuple(item.values()))
            registry._refresh_content_hash(self.conn, arena['arena_id'], next_version)
            self.set('arenas', {'arena_id': arena['arena_id']}, {'current_published_version': next_version, 'updated_at': self.now, 'updated_by': self.actor})
            registry._audit(self.conn, arena['arena_id'], next_version, 'catalog_trait_replacement', self.actor, None, old, value)
            registry._bump_version(self.conn)
            self.changes.append({'table': 'arena_versions', 'action': 'new_version', 'arena_id': arena['arena_id'],
                                 'old_version': version, 'new_version': next_version, 'profiles': value['profiles']})
        # Drafts are editable, so adapt their conditions too without touching published history.
        for row in self.conn.execute("SELECT * FROM arena_mode_profiles WHERE version IN (SELECT version FROM arena_versions v WHERE v.arena_id=arena_mode_profiles.arena_id AND version_status='draft')").fetchall():
            old = json.loads(row['rules_json']); value = self.rewrite(old)
            if value != old:
                self.set('arena_mode_profiles', {k: row[k] for k in ('arena_id', 'version', 'mode_key')},
                         {'rules_json': encoded(value), 'rules_hash': registry._hash(value)})
                registry._refresh_content_hash(self.conn, row['arena_id'], row['version'])

    def cleanup(self):
        dependent = ('player_card_stacks', 'player_cards', 'card_cooldowns', 'card_cooldown_settings',
                     'card_missions', 'player_card_missions', 'card_mode_metadata', 'card_media_cache',
                     'economy_character_rules', 'claim_receipts', 'card_avatars', 'player_avatar_choices',
                     'active_skins', 'rare_cards_info')
        for old in self.removed:
            cid = old['card_id']
            for row in self.conn.execute('SELECT deck_id FROM player_decks WHERE card_id_1=? OR card_id_2=? OR card_id_3=?', (cid, cid, cid)).fetchall():
                self.delete('player_decks', 'deck_id', row[0])
                self.delete('foundation_settings', 'key', 'deck_presentation:' + row[0])
            for row in self.conn.execute('SELECT skin_id FROM skins WHERE card_id=?', (cid,)).fetchall():
                self.delete('player_skins', 'skin_id', row[0])
                self.delete('active_skins', 'skin_id', row[0])
            self.delete('skins', 'card_id', cid)
            for row in self.conn.execute('SELECT variant_id FROM card_variants WHERE card_id=?', (cid,)).fetchall():
                self.delete('card_variant_media_cache', 'variant_id', row[0])
            self.delete('card_variants', 'card_id', cid)
            for table in dependent:
                self.delete(table, 'card_id', cid)
            for key, value in self.conn.execute('SELECT key,value_json FROM foundation_settings').fetchall():
                if key == 'card-voices:' + cid or key.startswith('voice-pref:') and key.endswith(':' + cid):
                    self.delete('foundation_settings', 'key', key)
                if key.startswith(('custom-card-notice:', 'rare-card-notice:')):
                    notice = json.loads(value)
                    if notice.get('card_id') == cid and notice.get('state') != 'sent':
                        notice.update(state='cancelled', lease=None, lease_until=0, reason='catalog_card_retired')
                        self.set('foundation_settings', {'key': key}, {'value_json': encoded(notice)})
            if 'custom_grants' in self.present:
                for grant in self.conn.execute('SELECT * FROM custom_grants WHERE card_id=?', (cid,)).fetchall():
                    self.set('custom_grants', {'card_id': cid, 'user_id': grant['user_id']}, {'active': 0})
                if self.conn.execute('SELECT 1 FROM custom_definitions WHERE card_id=?', (cid,)).fetchone():
                    self.set('custom_definitions', {'card_id': cid}, {'status': 'suspended'})
            # Payment, rare serial, match and reward records keep their original identity.
            self.delete('cards', 'card_id', cid)
        # Starter receipts remain immutable; checkpoint retired stickers as skipped
        # so a resumed /start never loops forever or grants a second starter pack.
        removed = set(self.card_map)
        for row in self.conn.execute("SELECT user_id,receipt_json FROM reward_ledger WHERE operation_id='starter_cards'").fetchall():
            receipt = json.loads(row['receipt_json'])
            retired = [cid for cid in receipt.get('card_ids', []) if cid in removed]
            if retired:
                key = 'starter_delivery:' + str(row['user_id'])
                current = self.conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (key,)).fetchone()
                value = json.loads(current[0]) if current else {'sent_ids': [], 'done': False}
                value['sent_ids'] = list(dict.fromkeys([*value['sent_ids'], *retired]))
                value['retired_ids'] = retired
                self.set('foundation_settings', {'key': key}, {'value_json': encoded(value)})

    def run(self):
        known = {'cards', 'card_variants', 'card_mode_metadata', 'player_cards', 'player_card_stacks',
                 'card_media_cache', 'card_cooldowns', 'card_cooldown_settings', 'card_missions',
                 'player_card_missions', 'skins', 'active_skins', 'economy_character_rules', 'claim_receipts',
                 'custom_orders', 'custom_definitions', 'custom_grants', 'custom_match_cards',
                 'rare_card_instances', 'rare_cards_info', 'rare_cards_log', 'card_avatars',
                 'player_avatar_choices', 'retired_card_catalog'}
        unknown = [table for table in self.present if 'card_id' in columns(self.conn, table) and table not in known]
        if unknown:
            raise ValueError('Unreviewed card references in tables: ' + ','.join(sorted(unknown)))
        require_quiet(self.conn)
        match = self.identities()
        self.conn.execute('CREATE TABLE IF NOT EXISTS retired_card_catalog '
                          '(card_id TEXT PRIMARY KEY,definition_json TEXT NOT NULL,retired_at TEXT NOT NULL)')
        for old in self.removed:
            self.set('retired_card_catalog', {'card_id': old['card_id']},
                     {'definition_json': encoded(old), 'retired_at': self.now})
            # A Rare with the same display name must be removed, not reused as Normal.
            if any(c['db_name'] == old['name'] for c in self.catalog['characters']):
                self.set('cards', {'card_id': old['card_id']}, {'name': '__retired:' + old['card_id']})
        self.save_characters()
        self.references()
        self.cleanup()
        self.conn.execute('DELETE FROM card_trait_registry')
        self.conn.executemany('INSERT INTO card_trait_registry VALUES(?,?)', sorted(self.traits.items()))
        remember_collections(self.conn, [])
        self.conn.execute('DELETE FROM card_collection_registry')
        remember_collections(self.conn, sorted({v for c in self.catalog['characters'] for v in c['collections']}))
        if self.conn.execute('SELECT count(*) FROM cards').fetchone()[0] != 60 or self.conn.execute('SELECT count(*) FROM card_variants').fetchone()[0] != 180:
            raise ValueError('Post-import catalog counts differ from 60 characters / 180 forms')
        violations = list(self.conn.execute('PRAGMA foreign_key_check'))
        if violations:
            raise ValueError('Foreign key violations: ' + str([tuple(v) for v in violations]))
        return {'matches': match, 'created': sum(not c['existing'] for c in self.catalog['characters']),
                'updated': sum(c['existing'] for c in self.catalog['characters']),
                'removed': [{'card_id': c['card_id'], 'name': c['name'], 'origin': c['origin'], 'rarity': c['rarity']} for c in self.removed],
                'affected_users': self.affected_users, 'affected_decks': sorted(self.affected_decks),
                'changes': self.changes, 'reference_mappings': [json.loads(v) for v in sorted({encoded(v) for v in self.mappings})],
                'counts': {'characters': 60, 'forms': 180, 'collections': 47, 'traits': 28}}


def preview_in(conn, catalog):
    if 'catalog_import_runs' in tables(conn):
        old = conn.execute('SELECT receipt_json FROM catalog_import_runs WHERE source_hash=? AND policy_hash=?',
                           (catalog['source_hash'], catalog['policy_hash'])).fetchone()
        if old:
            return {**json.loads(old[0]), 'replayed': True}
        if conn.execute('SELECT 1 FROM catalog_import_runs LIMIT 1').fetchone():
            raise ValueError('Catalog was already replaced; future additions belong in the admin panel')
    original = db_digest(conn)
    with closing(sqlite3.connect(':memory:')) as planned:
        planned.row_factory = sqlite3.Row
        conn.backup(planned)
        receipt = Replacement(planned, copy.deepcopy(catalog), 'catalog-import', 'CATALOG_APPLY_TIME').run()
    receipt.update(source_hash=catalog['source_hash'], policy_hash=catalog['policy_hash'], database_hash=original,
                   warnings=catalog['warnings'], replayed=False)
    receipt['plan_hash'] = digest(receipt)
    return receipt


def preview(db_path, catalog):
    path = Path(db_path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN')
        return preview_in(conn, catalog)


def apply(db_path, catalog, plan_hash, backup_path, actor):
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('Actor is required')
    path, backup = Path(db_path).resolve(strict=True), Path(backup_path).resolve()
    if backup.exists() or backup == path or not backup.parent.is_dir():
        raise ValueError('Backup must be a new file in an existing directory')
    with closing(sqlite3.connect(str(path), timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE')
            # Another connection can read while this one holds the reserved lock.
            # Planning uses that read snapshot, never backup() on the write-locked connection.
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as reader:
                reader.row_factory = sqlite3.Row
                reader.execute('BEGIN')
                receipt = preview_in(reader, catalog)
                if receipt['plan_hash'] != plan_hash:
                    raise ValueError('Plan is stale; preview the current database again')
                if receipt.get('replayed'):
                    conn.rollback()
                    return receipt
                with backup.open('xb'):
                    pass
                with closing(sqlite3.connect(str(backup))) as saved:
                    reader.backup(saved)
                    if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Backup integrity check failed')
            result = Replacement(conn, copy.deepcopy(catalog), actor, datetime.now(timezone.utc).isoformat()).run()
            if result['counts'] != receipt['counts']:
                raise ValueError('Apply differs from preview')
            conn.execute('CREATE TABLE catalog_import_runs(source_hash TEXT PRIMARY KEY,policy_hash TEXT NOT NULL,receipt_json TEXT NOT NULL)')
            conn.execute('INSERT INTO catalog_import_runs VALUES(?,?,?)', (catalog['source_hash'], catalog['policy_hash'], encoded(receipt)))
            conn.commit()
            return {**receipt, 'applied': True, 'backup': str(backup)}
        except Exception:
            conn.rollback()
            raise
