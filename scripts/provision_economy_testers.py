"""Explicit owner tester kit: adopt v2 without deleting progress or inventory.

Preview on a private copy; apply under the owner's deployment lock with services
stopped. A repeated batch returns its receipt and never refills spent test stock.
"""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from migrations.migrate_card_trait_registry import copy_database
from systems.card_inventory_system import CardInventorySystem
from systems.card_upgrade_system import CardUpgradeSystem
from systems.game_mode_system import ABILITY_DEFINITIONS
from systems.progression_config import config_in, enabled_in
from systems.reward_ledger import capacities_in, items_in, receipt_in, record_in

KIT = {'coins': 20000, 'forms': {'normal': 9, 'epic': 3, 'legend': 1},
       'abilities': 20, 'items': {'upgrade_card': 20, 'silver_ticket': 30, 'free_silver_claim': 3}}


def unrelated_snapshot(conn, users):
    """Every unrelated record and every global content/config table must survive."""
    editable = {'players': 'user_id', 'player_progression': 'user_id',
        'progression_capacities': 'user_id', 'player_cards': 'user_id',
        'player_card_stacks': 'user_id', 'player_ability_inventory': 'user_id',
        'player_economy_items': 'user_id', 'reward_ledger': 'user_id'}
    snapshot = {}
    placeholders = ','.join('?' for _ in users)
    for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if name in ('economy_admin_audit', 'sqlite_sequence'):
            continue
        escaped = '"' + name.replace('"', '""') + '"'
        sql = 'SELECT * FROM ' + escaped
        args = ()
        if name in editable:
            sql += ' WHERE ' + editable[name] + ' NOT IN (' + placeholders + ')'
            args = tuple(users)
        columns = len(conn.execute('PRAGMA table_info(' + escaped + ')').fetchall())
        snapshot[name] = conn.execute(sql + ' ORDER BY ' + ','.join(str(i+1) for i in range(columns)), args).fetchall()
    return snapshot


def provision_in(conn, accounts, actor, batch):
    if not actor or not isinstance(batch, str) or not batch.strip() or len(batch) > 100:
        raise ValueError('invalid_admin_identity')
    if not accounts or len(set(accounts.values())) != len(accounts):
        raise ValueError('invalid_tester_accounts')
    if not enabled_in(conn):
        raise ValueError('progression_v2_disabled')
    operation = 'admin:tester-kit:' + batch
    version, config = config_in(conn)
    payload = {'kit': KIT, 'progression': 'preserve', 'accounts': sorted(accounts.items())}
    # JSON normalizes tuple pairs into lists before comparing persisted receipts.
    payload = json.loads(json.dumps(payload))
    existing = [receipt_in(conn, operation, user, payload) for user in accounts.values()]
    if any(existing):
        if not all(existing):
            raise ValueError('incomplete_batch_receipts')
        return {'ok': True, 'replayed': True, 'accounts': existing}
    official = [row[0] for row in conn.execute("SELECT card_id FROM cards WHERE origin='official' ORDER BY card_id")]
    if not official:
        raise ValueError('official_catalog_empty')
    for card in official:
        forms = {row[0] for row in conn.execute('SELECT rarity FROM card_variants WHERE card_id=?', (card,))}
        if not set(KIT['forms']) <= forms:
            raise ValueError('official_family_incomplete:' + card)
    definitions = {row[0] for row in conn.execute('SELECT ability_key FROM ability_definitions')}
    if not set(ABILITY_DEFINITIONS) <= definitions:
        raise ValueError('ability_definitions_missing')
    for name, user in accounts.items():
        player = conn.execute('SELECT username,max_hearts FROM players WHERE user_id=?', (user,)).fetchone()
        if not player or (player[0] or '').lstrip('@').casefold() != name.lstrip('@').casefold():
            raise ValueError('tester_identity_mismatch:' + name)
        if player[1] > config['hearts']['cap']:
            raise ValueError('tester_heart_capacity_requires_review:' + name)
        if CardUpgradeSystem._active_match(conn, user):
            raise ValueError('tester_in_active_match:' + name)
        if not conn.execute('SELECT 1 FROM player_progression WHERE user_id=?', (user,)).fetchone():
            raise ValueError('tester_progression_missing:' + name)
    before_unrelated = unrelated_snapshot(conn, accounts.values())
    results = []
    for name, user in accounts.items():
        before = conn.execute('SELECT coins,hearts,max_hearts,total_score,last_claim FROM players WHERE user_id=?', (user,)).fetchone()
        progression = conn.execute('SELECT * FROM player_progression WHERE user_id=?', (user,)).fetchone()
        capacity = capacities_in(conn, user, config)
        # Preserve higher existing heart/deck capacities; future levels earn v2 prizes.
        conn.execute('UPDATE progression_capacities SET legacy=0 WHERE user_id=?', (user,))
        conn.execute('UPDATE players SET coins=MAX(coins,?),hearts=max_hearts WHERE user_id=?', (KIT['coins'], user))
        inventory = {}
        for card in official:
            counts = CardInventorySystem.counts_in(conn, user, card)
            for form, minimum in KIT['forms'].items():
                delta = max(0, minimum - counts.get(form, 0))
                if delta:
                    CardInventorySystem.grant_in(conn, user, card, form, delta)
                    inventory[card+':'+form] = delta
        for ability in ABILITY_DEFINITIONS:
            owned = conn.execute('SELECT quantity FROM player_ability_inventory WHERE user_id=? AND ability_key=?', (user, ability)).fetchone()
            delta = max(0, KIT['abilities'] - (owned[0] if owned else 0))
            conn.execute('INSERT INTO player_ability_inventory VALUES(?,?,?) ON CONFLICT(user_id,ability_key) DO UPDATE SET quantity=MAX(quantity,excluded.quantity)', (user, ability, KIT['abilities']))
            if delta:
                inventory['ability:'+ability] = delta
        for item, minimum in KIT['items'].items():
            delta = max(0, minimum - items_in(conn, user, item))
            items_in(conn, user, item, delta)
            if delta:
                inventory[item] = delta
        after = conn.execute('SELECT coins,hearts,max_hearts,total_score,last_claim FROM players WHERE user_id=?', (user,)).fetchone()
        if after[2:] != before[2:] or progression != conn.execute('SELECT * FROM player_progression WHERE user_id=?', (user,)).fetchone():
            raise ValueError('tester_progression_or_history_changed')
        level, xp = conn.execute('SELECT level,total_xp FROM player_progression WHERE user_id=?', (user,)).fetchone()
        result = {'ok': True, 'username': name, 'user_id': user, 'legacy': False,
            'level': level, 'xp': xp, 'coins': after[0], 'hearts': after[1],
            'characters': len(official), 'forms': len(official)*len(KIT['forms']),
            'abilities': len(ABILITY_DEFINITIONS), 'kit': KIT, 'old_capacity': capacity,
            'coins_added': after[0]-before[0], 'hearts_added': after[1]-before[1]}
        record_in(conn, operation, user, 'admin', 'tester_provision', payload, result, version,
                  coins=after[0]-before[0], hearts=after[1]-before[1], inventory=inventory)
        results.append(result)
    if unrelated_snapshot(conn, accounts.values()) != before_unrelated:
        raise ValueError('unrelated_data_changed')
    receipt = {'ok': True, 'replayed': False, 'batch': batch, 'accounts': results, 'unrelated_data_unchanged': True}
    conn.execute('INSERT INTO economy_admin_audit(action,details_json,actor,created_at) VALUES(?,?,?,CURRENT_TIMESTAMP)',
                 ('tester_provision', json.dumps(receipt, sort_keys=True), actor))
    return receipt


def provision(database, accounts, actor, batch):
    path = Path(database).resolve(strict=True)
    with closing(sqlite3.connect(str(path), timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        violations = conn.execute('PRAGMA foreign_key_check').fetchall()
        if conn.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('database_integrity_failed')
        receipt = provision_in(conn, accounts, actor, batch)
        if conn.execute('PRAGMA quick_check').fetchone() != ('ok',) or conn.execute('PRAGMA foreign_key_check').fetchall() != violations:
            raise ValueError('provision_integrity_failed')
        receipt['existing_foreign_key_violations'] = len(violations)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--account', action='append', required=True, help='verified username:numeric_user_id')
    parser.add_argument('--actor', required=True)
    parser.add_argument('--batch', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview-copy', type=Path)
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error('--apply requires a new --backup')
    if args.preview_copy and args.backup:
        parser.error('--backup requires --apply')
    accounts = {}
    for entry in args.account:
        name, numeric_id = entry.rsplit(':', 1)
        if name in accounts:
            parser.error('duplicate username')
        accounts[name] = int(numeric_id)
    if args.preview_copy:
        target = copy_database(args.database, args.preview_copy)
    else:
        copy_database(args.database, args.backup)
        target = args.database
    print(json.dumps({'preview': bool(args.preview_copy), **provision(target, accounts, args.actor, args.batch)}, sort_keys=True))


if __name__ == '__main__':
    main()
