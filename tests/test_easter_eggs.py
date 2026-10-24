import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from bot import easter_eggs as delivery
from core.models import Card, CardRarity
from systems import easter_eggs as eggs, easter_media, rare_delivery
from systems.card_inventory_system import CardInventorySystem
from systems.player_rewards_system import PlayerRewardsSystem
from tests.test_custom_cards_phase3 import custom, post
from tests.test_custom_admin_fulfillment import form
from tests.test_victory_voices import ogg
from tests.test_easy_presentation import scene

HEADERS = {'X-Admin-Token': 'synthetic-test-admin'}


def rule(**changes):
    value = dict(title='رمز آزمایشی', phrases=['پیو HESOYAM'], enabled=True, per_user_limit=1,
                 cooldown_seconds=0, responses=[{'text': 'cheat activated: {name} · {remaining}'}],
                 rewards=[{'kind': 'card', 'card_id': 'official', 'rarity': 'epic', 'quantity': 1}])
    return {**value, **changes}


def fire(db, user=1, message=10, chat=-100, phrase='پیو HESOYAM'):
    return eggs.execute(db, user, chat, message, phrase, 'private' if chat > 0 else 'supergroup')


def count(db, table):
    with sqlite3.connect(db.db_path) as conn:
        return conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]


def test_admin_authority_revision_aliases_delete_and_audit(custom):
    db, _, client = custom
    with client.get('/easter-eggs') as page:
        assert page.status_code == 200
    for path in ('catalog', 'history/unknown', 'media/' + 'a'*32):
        assert client.get('/api/easter/' + path).status_code == 403
    assert client.post('/api/easter/preview', json={'rule': rule()}).status_code == 403
    saved = client.post('/api/easter/catalog', json={'rule': rule()}, headers=HEADERS)
    assert saved.status_code == 200, saved.get_json()
    item = saved.get_json()['rule']
    key = item['rule_id']
    assert client.post('/api/easter/catalog', json={'rule': rule()}, headers=HEADERS).status_code == 400
    assert fire(db)['event_id']
    db.get_or_create_player(1, 'changed_username', 'نام تازه')
    assert not fire(db, message=11, chat=-200).get('event_id')
    revised = client.put('/api/easter/rules/'+key, json={'revision': 1, 'rule': rule(title='نام تازه')}, headers=HEADERS)
    assert revised.status_code == 200
    assert not fire(db, message=12).get('event_id')
    assert client.put('/api/easter/rules/'+key, json={'revision': 1, 'rule': rule()}, headers=HEADERS).status_code == 400
    assert client.delete('/api/easter/rules/'+key, json={'revision': 2}, headers=HEADERS).status_code == 200
    assert not fire(db, message=13)['matched']
    assert client.get('/api/easter/catalog', headers=HEADERS).get_json()['rules'] == []
    assert count(db, 'easter_events') == 1 and count(db, 'easter_audit') == 3
    history = client.get('/api/easter/history/'+key, headers=HEADERS).get_json()['users']
    assert history[0]['user_id'] == 1 and history[0]['uses'] == 1


def test_uid_quota_shared_aliases_and_global_cap_are_atomic(custom):
    db = custom[0]
    saved = eggs.save(db, 'admin', None, None, rule(phrases=['پیو HESOYAM', 'بتل خواب بودم'], per_user_limit=1, total_limit=2))
    with ThreadPoolExecutor(max_workers=6) as pool:
        first = list(pool.map(lambda i: fire(db, message=100+i, chat=-100-i), range(6)))
    assert sum(bool(item.get('event_id')) for item in first) == 1
    assert CardInventorySystem(db).counts(1, 'official')['epic'] == 1
    assert not fire(db, message=200, phrase='بتل خواب بودم').get('event_id')
    with ThreadPoolExecutor(max_workers=6) as pool:
        second = list(pool.map(lambda i: fire(db, user=i+2, message=300+i), range(6)))
    assert sum(bool(item.get('event_id')) for item in second) == 1
    assert count(db, 'easter_events') == 2
    assert sum(item['uses'] for item in eggs.history(db, saved['rule_id'])) == 2


def test_three_uses_replay_and_toggle_never_reset_allowance(custom):
    db = custom[0]
    value = rule(per_user_limit=3)
    saved = eggs.save(db, 'admin', None, None, value)
    results = [fire(db, message=i) for i in range(1, 6)]
    assert sum(bool(item.get('event_id')) for item in results) == 3
    replay = fire(db, message=1)
    assert replay['replayed'] and replay['event_id'] == results[0]['event_id']
    off = eggs.save(db, 'admin', saved['rule_id'], 1, {**value, 'enabled': False})
    assert fire(db, message=10)['silent']
    eggs.save(db, 'admin', saved['rule_id'], off['revision'], value)
    assert not fire(db, message=11).get('event_id')
    assert CardInventorySystem(db).counts(1, 'official')['epic'] == 3


def test_rare_supply_and_all_rewards_rollback_together(custom):
    db = custom[0]
    db.add_card(Card('rare', 'نادر', CardRarity.RARE, 50, 50, 50, 50, []))
    rare_delivery.set_supply(db, 'admin', 'rare', 0, None)
    value = rule(rewards=[{'kind': 'card', 'card_id': 'official', 'rarity': 'legend'},
                          {'kind': 'card', 'card_id': 'rare', 'rarity': 'rare'}])
    eggs.save(db, 'admin', None, None, value)
    with pytest.raises(ValueError, match='rare_supply_empty'):
        fire(db)
    assert 'legend' not in CardInventorySystem(db).counts(1, 'official')
    assert count(db, 'easter_events') == 0
    rare_delivery.set_supply(db, 'admin', 'rare', 1, 0)
    assert fire(db)['event_id']
    assert CardInventorySystem(db).counts(1, 'rare')['rare'] == 1
    assert rare_delivery.catalog(db)[0]['issued'] == 1


@pytest.mark.parametrize('v2', [False, True])
def test_extra_daily_claim_preserves_normal_claim_timer_and_grants_ability(custom, monkeypatch, v2):
    db = custom[0]
    if v2:
        with sqlite3.connect(db.db_path) as conn:
            conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    monkeypatch.setattr('systems.easter_eggs.random.random', lambda: 1.0)
    assert PlayerRewardsSystem(db).claim_daily(1)['ok']
    with sqlite3.connect(db.db_path) as conn:
        before = conn.execute('SELECT last_claim,coins,total_score FROM players WHERE user_id=1').fetchone()
        abilities = conn.execute('SELECT SUM(quantity) FROM player_ability_inventory WHERE user_id=1').fetchone()[0]
    old_count = CardInventorySystem(db).counts(1, 'official')['normal']
    eggs.save(db, 'admin', None, None, rule(phrases=['بتل کلیم کلیم'], rewards=[{'kind': 'daily_claim'}]))
    assert fire(db, phrase='بتل کلیم کلیم')['event_id']
    assert CardInventorySystem(db).counts(1, 'official')['normal'] == old_count + 1
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT last_claim,coins,total_score FROM players WHERE user_id=1').fetchone() == before
        assert conn.execute('SELECT SUM(quantity) FROM player_ability_inventory WHERE user_id=1').fetchone()[0] == abilities + 1
    assert not PlayerRewardsSystem(db).claim_status(1)['can_claim']
    assert not fire(db, message=11, phrase='بتل کلیم کلیم').get('event_id')


def test_refill_full_health_does_not_burn_a_use_and_silver_is_stored(custom):
    db = custom[0]
    eggs.save(db, 'admin', None, None, rule(rewards=[{'kind': 'refill_hearts'}]))
    assert not fire(db).get('event_id')
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('UPDATE players SET hearts=1 WHERE user_id=1')
    assert fire(db, message=11)['event_id']
    with sqlite3.connect(db.db_path) as conn:
        hearts, cap = conn.execute('SELECT hearts,max_hearts FROM players WHERE user_id=1').fetchone()
        assert hearts == cap
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    eggs.save(db, 'admin', None, None, rule(phrases=['پیو سیلور'], rewards=[{'kind': 'silver_claim', 'quantity': 2}]))
    assert fire(db, message=12, phrase='پیو سیلور')['event_id']
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT quantity FROM player_economy_items WHERE user_id=1 AND item='free_silver_claim'").fetchone()[0] == 2


def test_existing_custom_card_can_be_granted_without_enabling_gameplay(custom):
    db = custom[0]
    card_id = post(custom, 'fulfill', form('legend', [1])).get_json()['card_id']
    eggs.save(db, 'admin', None, None, rule(rewards=[{'kind': 'card', 'card_id': card_id, 'rarity': 'legend'}]))
    assert fire(db, user=2)['event_id']
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT active FROM custom_grants WHERE card_id=? AND user_id=2', (card_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT value_json FROM foundation_settings WHERE key='custom_cards_enabled'").fetchone()[0] == 'false'


def test_scopes_schedules_reserved_commands_and_preview_no_payout(custom):
    db, _, client = custom
    with pytest.raises(ValueError):
        eggs.save(db, 'admin', None, None, rule(phrases=['بتل کلیم']))
    value = rule(scope='private', user_ids=[1])
    saved = eggs.save(db, 'admin', None, None, value)
    assert fire(db)['silent'] and fire(db, user=2, chat=2)['silent']
    assert fire(db, chat=1)['event_id']
    preview = client.post('/api/easter/preview', json={'rule': value}, headers=HEADERS)
    assert preview.status_code == 200 and count(db, 'easter_events') == 1
    eggs.save(db, 'admin', saved['rule_id'], 1, {**value, 'starts_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
    assert fire(db, user=1, message=50, chat=1)['silent']


def test_media_upload_auth_and_persisted_photo_voice_sticker(custom):
    db, _, client = custom
    raw = BytesIO(); Image.new('RGBA', (80, 90), 'orange').save(raw, 'PNG')
    assert client.post('/api/easter/media', data={'kind': 'photo', 'file': (BytesIO(raw.getvalue()), 'x.png')}).status_code == 403
    for kind, data, name in [('photo', raw.getvalue(), 'x.png'), ('sticker', raw.getvalue(), 'x.png'), ('voice', ogg(), 'x.ogg')]:
        response = client.post('/api/easter/media', headers=HEADERS, data={'kind': kind, 'file': (BytesIO(data), name)})
        assert response.status_code == 201, response.get_json()
        item, content = easter_media.read(db, response.get_json()['media_id'])
        assert item['kind'] == kind and content
        with client.get('/api/easter/media/'+response.get_json()['media_id'], headers=HEADERS) as preview:
            assert preview.status_code == 200
    with pytest.raises(ValueError):
        easter_media.upload(db, 'admin', 'photo', b'<svg onload=alert(1)>')


def test_response_delivery_replies_to_sender_and_retry_never_reawards(custom):
    db = custom[0]
    image = BytesIO(); Image.new('RGB', (40, 40), 'blue').save(image, 'PNG')
    media_id = easter_media.upload(db, 'admin', 'photo', image.getvalue())
    eggs.save(db, 'admin', None, None, rule(responses=[{'text': 'تبریک', 'media_id': media_id}]))
    message = NS(message_id=10, text='پیو HESOYAM', reply_text=AsyncMock(), reply_to_message=NS(from_user=NS(id=2)))
    update = NS(message=message, effective_user=NS(id=1, is_bot=False), effective_chat=NS(id=-100, type='supergroup'))
    context = NS(user_data={}, bot=NS(send_message=AsyncMock(), send_photo=AsyncMock(side_effect=RuntimeError('offline'))))
    assert asyncio.run(delivery.handle(NS(db=db), update, context))
    assert CardInventorySystem(db).counts(1, 'official')['epic'] == 1
    assert 'epic' not in CardInventorySystem(db).counts(2, 'official')
    with sqlite3.connect(db.db_path) as conn:
        event_id, state = conn.execute('SELECT event_id,delivery_json FROM easter_events').fetchone()
        state = json.loads(state); state['next_attempt'] = 0
        conn.execute('UPDATE easter_events SET delivery_json=?', (json.dumps(state),))
    context.bot.send_photo.side_effect = None
    asyncio.run(delivery.drain(NS(db=db), context))
    assert context.bot.send_message.await_count == 1
    assert context.bot.send_photo.await_args.kwargs['reply_to_message_id'] == 10
    assert context.bot.send_photo.await_args.kwargs['chat_id'] == -100
    assert asyncio.run(delivery.handle(NS(db=db), update, context))
    assert count(db, 'easter_events') == 1
    assert CardInventorySystem(db).counts(1, 'official')['epic'] == 1
    assert eggs.claim_delivery(db, event_id) is None


def test_full_admin_authority_required_when_arena_has_separate_token(custom, monkeypatch):
    client = custom[2]
    monkeypatch.setenv('ARENA_ADMIN_TOKEN', 'synthetic-arena-only')
    assert client.get('/api/easter/catalog', headers={'X-Admin-Token': 'synthetic-arena-only'}).status_code == 403
    assert client.get('/api/easter/catalog', headers=HEADERS).status_code == 200


def test_response_only_unregistered_uid_random_choice_frozen_and_delivery_leased(custom):
    db = custom[0]
    eggs.save(db, 'admin', None, None, rule(rewards=[], per_user_limit=None,
        responses=[{'text': 'یکی'}, {'text': 'دو'}]))
    first = fire(db, user=9999)
    assert first['event_id'] and first['receipt']['remaining'] is None
    assert fire(db, user=9999)['receipt'] == first['receipt']
    with ThreadPoolExecutor(max_workers=5) as pool:
        leases = list(pool.map(lambda _: eggs.claim_delivery(db, first['event_id']), range(5)))
    assert sum(item is not None for item in leases) == 1
    assert fire(db, user=9999, message=11)['event_id']


def test_active_match_blocks_rewards_without_consuming_quota(custom):
    from systems.match_activity import ActiveMatchError
    db = custom[0]
    eggs.save(db, 'admin', None, None, rule())
    fight = db.create_solo_fight(1, 'easy')
    with pytest.raises(ActiveMatchError):
        fire(db)
    assert count(db, 'easter_events') == 0
    assert 'epic' not in CardInventorySystem(db).counts(1, 'official')
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE solo_fights SET status='completed' WHERE fight_id=?", (fight,))
    assert fire(db)['event_id']


def test_normal_claim_alias_and_secret_claim_router(scene):
    bot, update, context, _ = scene
    bot.claim_command = AsyncMock()
    update.effective_chat.id = 1
    update.message.message_id = 100
    update.message.sender_chat = None
    update.message.text = 'بتل کلیم'
    asyncio.run(bot._deck_name_message_router(update, context))
    bot.claim_command.assert_awaited_once_with(update, context)
    eggs.save(bot.db, 'admin', None, None, rule(phrases=['بتل کلیم کلیم'], rewards=[{'kind': 'daily_claim'}]))
    update.message.text = 'بتل کلیم کلیم'
    update.message.message_id = 101
    asyncio.run(bot._deck_name_message_router(update, context))
    assert count(bot.db, 'easter_events') == 1
    bot.claim_command.assert_awaited_once()


def test_browser_utc_schedule_works_on_server_python39(custom, monkeypatch):
    class Python39DateTime(datetime):
        @classmethod
        def fromisoformat(cls, value):
            if value.endswith('Z'):
                raise ValueError('Python 3.9 does not accept Z')
            return super().fromisoformat(value)
    monkeypatch.setattr(eggs, 'datetime', Python39DateTime)
    with sqlite3.connect(custom[0].db_path) as conn:
        result = eggs.validate_in(conn, rule(starts_at='2026-10-24T00:00:00.000Z',
                                              ends_at='2026-10-25T00:00:00.000Z'))
    assert result['starts_at'] == '2026-10-24T00:00:00+00:00'
    assert result['ends_at'] == '2026-10-25T00:00:00+00:00'
