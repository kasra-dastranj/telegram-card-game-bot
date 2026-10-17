import asyncio
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from PIL import Image
import pytest
from telegram.error import BadRequest

from bot import battle_visuals as visual
from bot.battle_visual_delivery import card_art, match_background, quick_model, send_arena, work
from bot.battle_visual_assets import resources
from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.game_modes import GameModeHandlersMixin
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import GameModeSystem, QUICK_ARENAS


class Handler(GameModeHandlersMixin, BattleHandlersMixin):
    pass


def png(color):
    stream = BytesIO()
    Image.new('RGB', (200, 300), color).save(stream, 'PNG')
    return stream.getvalue()


@pytest.fixture
def ui(tmp_path):
    handler = Handler()
    handler.db = DatabaseManager(str(tmp_path / 'visual.db'))
    handler.config = {}
    for uid, name in ((1, 'محمد MH'), (2, 'کسری')):
        handler.db.get_or_create_player(uid, first_name=name)
    for cid in ('alpha', 'beta', 'gamma'):
        handler.db.add_card(Card(cid, cid.title(), CardRarity.NORMAL, 60, 30, 50, 45, []))
        for rarity, color in (('normal', '#cc2222'), ('epic', '#2222cc'), ('legend', '#22cc22')):
            image = tmp_path / (cid + '-' + rarity + '.png')
            image.write_bytes(png(color))
            form = handler.db.get_card_variant(cid, rarity)
            handler.db.save_card_variant(cid, rarity, dict(form, image_path=str(image)))
        for uid in (1, 2):
            handler.db.add_card_to_player(uid, cid)
    with sqlite3.connect(handler.db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 1, 'alpha', 'epic')
    handler.db.set_player_card_rarity_override(1, 'alpha', 'epic')
    handler.modes = GameModeSystem(handler.db)
    handler.battle3 = BattleSystem3Rounds(handler.db)
    handler.modes._random_arena = lambda exclude=None: handler.modes._arena('city' if exclude else 'desert')
    handler._schedule_mode_job = Mock()
    handler._send_round_winner_card_media = AsyncMock(return_value=True)
    events = []

    async def photo(**kwargs):
        events.append(('photo', {**kwargs, 'raw': kwargs['photo'].getvalue()}))

    async def message(**kwargs):
        events.append(('message', kwargs))

    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(send_photo=AsyncMock(side_effect=photo),
                               send_message=AsyncMock(side_effect=message), username='OfflineTestBot'))
    return handler, context, events


def quick(ui, source='group'):
    handler = ui[0]
    request = (handler.modes.create_group_challenge(1, 'quick', 'normal', -100)
               if source == 'group' else handler.modes.create_inline_private_challenge(1, 'quick', 'normal'))
    key = request['request_id']
    assert handler.modes.accept_request(key, 2)[0]
    handler.modes.start_quick_match(key)
    handler.modes.select_quick_card(key, 1, 'alpha')
    state, _ = handler.modes.select_quick_card(key, 2, 'beta')
    return key, state


def complete(ui, key):
    handler = ui[0]
    handler.modes.select_quick_ability(key, 1, 'skip')
    handler.modes.select_quick_ability(key, 2, 'skip')
    handler.modes.select_quick_stat(key, 1, 'power')
    return handler.modes.select_quick_stat(key, 2, 'iq')[1]


@pytest.mark.parametrize('arena_id', ['city', 'desert', 'ice', 'forest', 'silent_temple', 'null_zone',
                                     'power_arena', 'speed_track', 'thinking_room', 'stage', 'new_arena'])
def test_each_ground_and_unknown_ground_have_a_packaged_bitmap(arena_id):
    image = Image.open(BytesIO(visual.background(arena_id)))
    assert image.format == 'JPEG' and min(image.size) >= 400
    assert len(resources()['font.ttf']) > 100_000
    assert b'SIL OPEN FONT LICENSE' in resources()['font-license.txt']


def test_asset_sources_match_bundle_and_licenses_ship_with_runtime():
    from scripts.build_battle_visual_assets import build
    from bot._vendor._licenses import LICENSES
    build(check=True)
    assert any('GNU LESSER GENERAL PUBLIC LICENSE' in text for text in LICENSES.values())
    assert any('Permission is hereby granted' in text for text in LICENSES.values())


def test_reassigning_ground_images_requires_rebuilding_bundle(tmp_path, monkeypatch):
    import json
    from scripts import build_battle_visual_assets as builder
    manifest = json.loads(builder.MANIFEST.read_text(encoding='utf-8'))
    manifest['arena/city'], manifest['arena/desert'] = manifest['arena/desert'], manifest['arena/city']
    changed = tmp_path / 'sources.json'
    changed.write_text(json.dumps(manifest), encoding='utf-8')
    monkeypatch.setattr(builder, 'MANIFEST', changed)
    with pytest.raises(ValueError, match='artwork changed'):
        builder.build(check=True)


def test_persian_shaping_preserves_signed_numbers_latin_names_and_rejects_overrides():
    value = visual.display('قدرت +2 و سرعت -1 برای MH')
    assert '+2' in value and '-1' in value and 'MH' in value
    assert '2+' not in value and 'HM' not in value
    assert '\u202e' not in visual.clean('Ali\u202e123\nنام')
    assert '\u200c' in visual.clean('می\u200cخوام')


def test_rule_image_keeps_all_tier_members_and_snapshot_flags():
    arena = {'trait_ranks': [['hero', 'funny'], ['leader', 'villain'], ['monster']],
             'compare_stat': 'speed', 'stat_tiebreak_enabled': True}
    lines = visual.rule_lines(arena, 'deck')
    assert lines[1:4] == ['T1: قهرمان / کمدی', 'T2: رهبر / شرور', 'T3: هیولا']
    assert 'سرعت' in lines[-1]
    quick_arena = next(a for a in QUICK_ARENAS if a['id'] == 'silent_temple')
    quick_lines = '\n'.join(visual.rule_lines(quick_arena, 'quick'))
    assert 'سرعت' in quick_lines and 'Ability غیرفعاله' in quick_lines and '+2' in quick_lines


def test_intro_is_private_before_buttons_deduplicated_and_uses_frozen_rules(ui, monkeypatch):
    handler, context, events = ui
    key, state = quick(ui)
    arena = dict(state['arena_snapshot'], name='زمین قدیمی', effects=[{'card_type': 'iq', 'stat': 'iq', 'delta': 7}])
    state['arena_snapshot'] = arena
    renderer = Mock(wraps=visual.render_arena)
    monkeypatch.setattr(visual, 'render_arena', renderer)
    monkeypatch.setattr(handler.modes, '_arena', Mock(side_effect=AssertionError('read frozen snapshot')))
    asyncio.run(handler._send_quick_ability_panels(context, key, state))
    assert [(kind, item['chat_id']) for kind, item in events] == [('photo', 1), ('message', 1), ('photo', 2), ('message', 2)]
    assert renderer.call_args.args[0]['effects'][0]['delta'] == 7
    assert all(item.get('caption') is None for kind, item in events if kind == 'photo')
    for kind, item in events:
        if kind == 'photo':
            assert Image.open(BytesIO(item['raw'])).size == (1200, 800)
    asyncio.run(handler._send_quick_arena_message(context, 1, state, key))
    assert context.bot.send_photo.await_count == 2


def test_reroll_gets_new_picture_and_result_uses_the_final_ground(ui, monkeypatch):
    handler, context, events = ui
    key, state = quick(ui)
    asyncio.run(handler._send_quick_ability_panels(context, key, state))
    handler.modes.grant_ability(1, 'reroll_arena')
    handler.modes.select_quick_ability(key, 1, 'reroll_arena')
    state, _ = handler.modes.select_quick_ability(key, 2, 'skip')
    asyncio.run(handler._send_quick_stat_panels(context, key, state))
    photos = [item for kind, item in events if kind == 'photo']
    assert [item['chat_id'] for item in photos] == [1, 2, 1, 2]
    assert photos[0]['raw'] != photos[2]['raw']
    handler.modes.select_quick_stat(key, 1, 'power')
    report = handler.modes.select_quick_stat(key, 2, 'iq')[1]
    renderer = Mock(wraps=visual.render_result)
    monkeypatch.setattr(visual, 'render_result', renderer)
    asyncio.run(handler._announce_quick_result(context, report))
    assert renderer.call_args.args[1] == visual.background('city')
    assert renderer.call_args.args[0]['arena_name'] == 'شهر'


@pytest.mark.parametrize('source', ['group', 'inline'])
def test_result_photos_go_to_both_bot_dms_preserve_public_slogan_and_use_recorded_forms(ui, source, monkeypatch):
    handler, context, events = ui
    key, _ = quick(ui, source)
    report = complete(ui, key)
    # Collection changes after the match cannot turn the awarded result card into another form.
    handler.db.set_player_card_rarity_override(1, 'alpha', 'normal')
    renderer = Mock(wraps=visual.render_result)
    monkeypatch.setattr(visual, 'render_result', renderer)
    asyncio.run(handler._announce_quick_result(context, report))
    photos = [item for kind, item in events if kind == 'photo']
    assert [item['chat_id'] for item in photos] == [1, 2]
    assert all(Image.open(BytesIO(item['raw'])).size == (1200, 1020) for item in photos)
    model = renderer.call_args.args[0]
    assert model['players'][0]['cards'][0]['rarity'] == 'epic'
    color = Image.open(BytesIO(model['players'][0]['cards'][0]['image'])).getpixel((50, 50))
    assert color[2] > 150 and color[0] < 80
    assert [p['score'] for p in model['players']] == [report['breakdown'][str(uid)]['final_value'] for uid in (1, 2)]
    assert all(p['reply_markup'].inline_keyboard[0][0].callback_data == 'gm_report_' + key for p in photos)
    messages = [item for kind, item in events if kind == 'message']
    assert [item['chat_id'] for item in messages] == ([-100] if source == 'group' else [])
    assert all(item['text'].startswith('💬 «') for item in messages)
    with sqlite3.connect(handler.db.db_path) as conn:
        before = conn.execute('SELECT SUM(xp),COUNT(*) FROM match_reward_events').fetchone()
    asyncio.run(handler._announce_quick_result(context, report))
    with sqlite3.connect(handler.db.db_path) as conn:
        assert conn.execute('SELECT SUM(xp),COUNT(*) FROM match_reward_events').fetchone() == before


def test_missing_epic_art_is_not_replaced_with_normal_or_legend(ui):
    handler, context, _ = ui
    card = handler.db.get_card_by_id_for_rarity('alpha', 'epic')
    card.image_path = 'missing-epic.png'
    handler.db.set_card_variant_media_file_id('alpha', 'legend', 'legend-file', 'photo')
    context.bot.get_file = AsyncMock()
    assert asyncio.run(card_art(handler, context, card)) is None
    context.bot.get_file.assert_not_awaited()


def test_telegram_photo_cache_downloads_once_and_bounds_invalid_files(ui):
    handler, context, _ = ui
    card = handler.db.get_card_by_id_for_rarity('alpha', 'epic')
    card.image_path = ''
    handler.db.set_card_variant_media_file_id('alpha', 'epic', 'epic-file', 'photo')
    remote = SimpleNamespace(file_size=200, download_as_bytearray=AsyncMock(return_value=bytearray(png('#1122aa'))))
    context.bot.get_file = AsyncMock(return_value=remote)
    first = asyncio.run(card_art(handler, context, card))
    assert first and asyncio.run(card_art(handler, context, card)) == first
    context.bot.get_file.assert_awaited_once_with('epic-file')
    remote.download_as_bytearray.assert_awaited_once()


def test_photo_errors_fall_back_to_text_without_interrupting_game_or_spending_again(ui):
    handler, context, events = ui
    context.bot.send_photo.side_effect = BadRequest('simulated offline failure')
    key, state = quick(ui)
    asyncio.run(handler._send_quick_ability_panels(context, key, state))
    assert [item['chat_id'] for _, item in events] == [1, 1, 2, 2]
    assert 'بیابان' in events[0][1]['text']
    report = complete(ui, key)
    asyncio.run(handler._announce_quick_result(context, report))
    assert handler.modes.get_request(key)['status'] == 'completed'
    assert events[-1][1]['chat_id'] == 2 and events[-2][1]['chat_id'] == 1
    assert events[-1][1]['reply_markup'].inline_keyboard[0][0].callback_data == 'gm_report_' + key


def test_unknown_ground_can_be_overridden_and_active_match_keeps_its_background(ui, tmp_path, monkeypatch):
    _, context, _ = ui
    folder = tmp_path / 'overrides'
    folder.mkdir()
    monkeypatch.setenv('TELBATTLE_BATTLE_MEDIA_DIR', str(folder))
    path = folder / 'new_arena.png'
    path.write_bytes(png('#cc1111'))
    arena = {'arena_id': 'new_arena', 'version': 2}
    first = asyncio.run(match_background(context, 'match1', arena, 'quick'))
    path.write_bytes(png('#1111cc'))
    assert asyncio.run(match_background(context, 'match1', arena, 'quick')) == first
    second = asyncio.run(match_background(context, 'match2', arena, 'quick'))
    assert second != first


def test_corrupt_and_oversized_bitmaps_are_rejected():
    for raw in (b'not an image', b'x' * (8 * 1024 * 1024 + 1)):
        with pytest.raises((OSError, ValueError)):
            visual.safe_bitmap(raw)


def test_published_versioned_background_is_local_and_cannot_escape_media_root(ui, tmp_path, monkeypatch):
    from bot.battle_visual_delivery import choose_background
    root = tmp_path / 'arena-media'
    root.mkdir()
    (root / 'stage-version-2.png').write_bytes(png('#1122cc'))
    (tmp_path / 'outside.png').write_bytes(png('#cc2211'))
    monkeypatch.setenv('MINIAPP_ARENA_MEDIA_DIR', str(root))
    arena = {'arena_id': 'stage', 'background_url': '/miniapp-assets/arena-backgrounds/stage-version-2.png'}
    color = Image.open(BytesIO(choose_background(arena))).getpixel((50, 50))
    assert color[2] > 150 and color[0] < 80
    arena['background_url'] = '/miniapp-assets/arena-backgrounds/../outside.png'
    assert choose_background(arena) == visual.background('stage')


def test_image_worker_leaves_event_loop_responsive_and_serializes_jobs(ui):
    import time
    _, context, _ = ui
    ticks = []
    active = [0, 0]

    def slow():
        active[0] += 1
        active[1] = max(active)
        time.sleep(0.04)
        active[0] -= 1

    async def ticker():
        for _ in range(8):
            await asyncio.sleep(0.01)
            ticks.append(True)

    async def run():
        await asyncio.gather(ticker(), *(work(context, slow) for _ in range(3)))

    asyncio.run(run())
    assert len(ticks) == 8 and active == [0, 1]


def test_deck_ground_is_sent_privately_once_before_shared_choice_panel(ui):
    handler, context, events = ui
    key = handler.db.create_fight(1, 2, -100, mode='deck')
    fight = handler.db.get_fight_by_id(key)
    handler._send_round_card_selection_panel = AsyncMock()
    handler._upsert_deck_status_message = AsyncMock()
    # Initialize the same additive state row used by the Deck launcher.
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute("""INSERT OR IGNORE INTO battle_states
            (fight_id,challenger_id,opponent_id,challenger_card_id,opponent_card_id,arena,
             challenger_current_stats,opponent_current_stats,status,created_at)
            VALUES (?,1,2,'alpha','beta','stage','{}','{}','waiting_deck','2026-10-17')""", (key,))
    handler.db.update_battle_deck_state(key, 'challenger', ['alpha', 'beta', 'gamma'], selected=True)
    handler.db.update_battle_deck_state(key, 'opponent', ['alpha', 'beta', 'gamma'], selected=True)
    handler.db.init_battle_deck_cards(key, ['alpha', 'beta', 'gamma'], ['alpha', 'beta', 'gamma'])
    args = (context, key, fight, handler.db.get_card_by_id_for_player('alpha', 1),
            handler.db.get_card_by_id_for_player('beta', 2), 'stage', None)
    asyncio.run(handler._start_battle_with_arena(*args))
    assert [item['chat_id'] for kind, item in events if kind == 'photo'] == [1, 2]
    handler._send_round_card_selection_panel.assert_awaited_once()
    assert handler.db.get_battle_deck_state(key)['arena'] == 'stage'
