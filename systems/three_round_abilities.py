"""Shared three-round ability policy for Mini App PvP and ASO practice."""

import random

from systems.battle_system_3rounds import ARENAS
from systems.game_mode_system import ABILITY_DEFINITIONS

ABILITY_EFFECTS = frozenset({'reveal_opponent', 'reroll_arena', 'weaken_stat'})
SOLO_ABILITY_FIELD = '_three_round_ability'


def ability_definition(key):
    definition = ABILITY_DEFINITIONS.get(key)
    if not definition:
        raise ValueError('unknown_ability')
    if definition['effect']['type'] not in ABILITY_EFFECTS:
        raise ValueError('ability_not_supported')
    return definition


def available_abilities(modes, user_id):
    return [item for item in modes.list_player_abilities(user_id)
            if ABILITY_DEFINITIONS.get(item['ability_key'], {}).get('effect', {}).get('type')
            in ABILITY_EFFECTS]


def consume_ability(conn, user_id, key):
    result = conn.execute('''UPDATE player_ability_inventory SET quantity=quantity-1
        WHERE user_id=? AND ability_key=? AND quantity>0''', (user_id, key))
    if result.rowcount != 1:
        raise ValueError('ability_not_owned')


def select_arena(registry, exclude_id=None, allow_fallback=True):
    selected = registry.select_for_match(
        'three_round', 'miniapp', exclude_ids=[exclude_id] if exclude_id else None)
    if selected:
        # The registry can fall back to its complete pool if exclusion empties it.
        if selected['arena_id'] == exclude_id:
            raise ValueError('no_alternative_arena')
        return registry.snapshot_for_match(
            selected['arena_id'], 'three_round', 'miniapp', selected['version'])
    if not allow_fallback:
        raise ValueError('no_alternative_arena')
    candidates = [key for key in ARENAS if key != exclude_id]
    if not candidates:
        raise ValueError('no_alternative_arena')
    key = random.choice(candidates)
    return {'arena_id': key, 'version': None, 'mode': 'three_round', **ARENAS[key]}
