"""Reviewed first activation of v2; never rewrites existing player balances."""
import hashlib
import json
from datetime import datetime, timezone

from systems.progression_config import config_in, enabled_in, save_config_in, validate_config
from systems.progression_economy import ProgressionEconomy
from systems.progression_missions import save_mission_in
from systems.reward_ledger import capacities_in

ROLLOUT_KEY = 'progression_v2_rollout'
TESTER_MISSIONS = (
    ('tester-first-quick', 'سه نبرد Quick', 'سه نبرد واقعی Quick را تمام کن.', 'quick_games', 3, 10, 10, 'once'),
    ('tester-daily-claim', 'پاداش روزانه', 'پاداش روزانه را دریافت کن.', 'daily_claims', 1, 5, 5, 'daily'),
    ('tester-first-upgrade', 'اولین ارتقا', 'یک کارت رسمی را ارتقا بده.', 'official_upgrades', 1, 10, 20, 'once'),
    ('tester-weekly-wins', 'پنج برد هفتگی', 'در این هفته پنج نبرد واقعی را ببر.', 'competitive_wins', 5, 15, 25, 'weekly'),
)


def protected_digest(conn):
    """Compare all business tables, including inventories and battle history."""
    allowed = {'economy_state', 'economy_config_versions', 'economy_character_rules',
               'economy_missions', 'economy_mission_audit', 'economy_admin_audit',
               'progression_capacities', 'foundation_settings', 'sqlite_sequence'}
    result = hashlib.sha256()
    for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if name in allowed:
            continue
        escaped = '"' + name.replace('"', '""') + '"'
        result.update(name.encode('utf8'))
        # Ordering by every column is independent of rowid and includes duplicate rows.
        columns = len(conn.execute('PRAGMA table_info(' + escaped + ')').fetchall())
        for row in conn.execute('SELECT * FROM ' + escaped + ' ORDER BY ' + ','.join(str(i + 1) for i in range(columns))):
            result.update(repr(tuple(row)).encode('utf8'))
            result.update(b'\n')
    return result.hexdigest()


def activate_in(conn, actor, legend_default='B', now=None):
    """Caller owns BEGIN IMMEDIATE. Failure must roll back the whole transaction."""
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('admin_actor_required')
    if legend_default != 'B':
        raise ValueError('unapproved_legend_default')
    plan_hash = hashlib.sha256(json.dumps([legend_default, TESTER_MISSIONS], sort_keys=True).encode()).hexdigest()
    marker = conn.execute('SELECT value FROM economy_state WHERE key=?', (ROLLOUT_KEY,)).fetchone()
    if marker:
        prior = json.loads(marker[0])
        if prior['plan_hash'] != plan_hash:
            raise ValueError('rollout_plan_conflict')
        return {**prior, 'replayed': True, 'enabled': enabled_in(conn)}
    if enabled_in(conn):
        raise ValueError('already_enabled_without_reviewed_cutover')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('rollout_timezone_required')
    timestamp = now.astimezone(timezone.utc).isoformat()
    version, config = config_in(conn)
    validate_config(config)
    if config['migration']['legacy_user_policy'] != 'preserve_freeze_rewards':
        raise ValueError('legacy_policy_not_approved')
    if config['upgrade']['legend_B']['copies'] != 3 or config['upgrade']['legend_B']['items'] != 1:
        raise ValueError('legend_recipe_not_approved')
    if conn.execute('SELECT 1 FROM progression_capacities WHERE legacy=0 LIMIT 1').fetchone():
        raise ValueError('nonlegacy_accounts_require_review')
    official = [row[0] for row in conn.execute("SELECT card_id FROM cards WHERE origin='official' ORDER BY card_id")]
    if not official:
        raise ValueError('official_catalog_empty')
    for card in official:
        variants = conn.execute('SELECT rarity,power,speed,iq,popularity FROM card_variants WHERE card_id=?', (card,)).fetchall()
        complete = {row[0] for row in variants if all(value is not None for value in row[1:])}
        if not {'normal', 'epic', 'legend'} <= complete:
            raise ValueError('official_family_incomplete:' + card)
    if not all(ProgressionEconomy.pool(conn, config, kind) for kind in ('daily', 'silver')):
        raise ValueError('claim_pool_empty')
    if any(conn.execute('SELECT 1 FROM economy_missions WHERE mission_id=?', (mission[0],)).fetchone() for mission in TESTER_MISSIONS):
        raise ValueError('tester_mission_already_exists')
    before = protected_digest(conn)
    other_flags = conn.execute("SELECT * FROM foundation_settings WHERE key<>'progression_v2_enabled' ORDER BY key").fetchall()
    capacities_before = conn.execute('SELECT * FROM progression_capacities ORDER BY user_id').fetchall()
    for user, in conn.execute('SELECT user_id FROM players').fetchall():
        capacities_in(conn, user, config)
    recipes = 0
    for card in official:
        recipes += conn.execute('INSERT OR IGNORE INTO economy_character_rules VALUES(?,?)', (card, legend_default)).rowcount
    if recipes:
        # Invalidate any previews obtained before per-character recipes were assigned.
        version = save_config_in(conn, config, actor)
    for identity, title, description, kind, target, xp, coins, repeat in TESTER_MISSIONS:
        save_mission_in(conn, {'mission_id': identity, 'title': title, 'description': description,
            'start': timestamp, 'end': None, 'status': 'active', 'type': kind, 'target': target,
            'filters': {}, 'eligibility': {}, 'xp_reward': xp, 'coin_reward': coins, 'repeat_policy': repeat}, actor)
    if conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'").rowcount != 1:
        raise ValueError('progression_flag_missing')
    unchanged = protected_digest(conn) == before
    if not unchanged or other_flags != conn.execute("SELECT * FROM foundation_settings WHERE key<>'progression_v2_enabled' ORDER BY key").fetchall():
        raise ValueError('protected_data_changed')
    for row in capacities_before:
        if conn.execute('SELECT * FROM progression_capacities WHERE user_id=?', (row[0],)).fetchone() != row:
            raise ValueError('existing_capacity_changed')
    receipt = {'activated_at': timestamp, 'config_version': version, 'legend_default': legend_default,
        'recipes_added': recipes, 'missions_added': len(TESTER_MISSIONS), 'plan_hash': plan_hash,
        'legacy_accounts': conn.execute('SELECT COUNT(*) FROM progression_capacities WHERE legacy=1').fetchone()[0],
        'protected_digest': before, 'protected_data_unchanged': unchanged}
    encoded = json.dumps(receipt, sort_keys=True)
    conn.execute('INSERT INTO economy_state VALUES(?,?)', (ROLLOUT_KEY, encoded))
    conn.execute('INSERT INTO economy_admin_audit(action,details_json,actor,created_at) VALUES(?,?,?,?)',
                 ('progression_v2_rollout', encoded, actor, timestamp))
    return {**receipt, 'replayed': False, 'enabled': True}
