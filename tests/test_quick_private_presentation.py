import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from bot.handlers.game_modes import GameModeHandlersMixin
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.game_mode_system import GameModeSystem


def _readable(text):
    return text.translate(str.maketrans('', '', '\u2066\u2068\u2069'))


@pytest.fixture
def quick_ui(tmp_path):
    db = DatabaseManager(str(tmp_path / 'presentation.db'))
    for uid, name in [(1, 'MH'), (2, 'Varan')]:
        db.get_or_create_player(uid, first_name=name)
    for cid in ('alpha', 'beta'):
        db.add_card(Card(card_id=cid, name=cid.title(), rarity=CardRarity.NORMAL,
                         power=60, speed=40, iq=50, popularity=30, abilities=[], card_type='POWER_TYPE'))
        for uid in (1, 2):
            db.add_card_to_player(uid, cid)
        for rarity in ('normal', 'epic', 'legend'):
            db.set_card_variant_media_file_id(cid, rarity, f'{cid}-{rarity}-sticker', 'sticker')
    db.set_player_card_rarity_override(1, 'alpha', 'epic')
    modes = GameModeSystem(db)
    modes._random_arena = lambda exclude=None: modes._arena('city' if exclude else 'desert')
    handler = GameModeHandlersMixin()
    handler.db, handler.modes = db, modes
    handler._schedule_mode_job = Mock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(), send_sticker=AsyncMock(), send_photo=AsyncMock()))
    return handler, context


def _request(handler, variant='normal'):
    request = handler.modes.create_group_challenge(1, 'quick', variant, -100123)
    assert handler.modes.accept_request(request['request_id'], 2)[0]
    return handler.modes.get_request(request['request_id'])


def _query(data, uid=1):
    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=uid), answer=AsyncMock(), edit_message_text=AsyncMock())


def test_inline_invitation_stays_started_and_both_players_receive_winner_sticker_then_result(quick_ui, tmp_path):
    from bot.handlers.battle import BattleHandlersMixin

    handler, context = quick_ui
    context.bot.username = 'TelBattleTest_bot'
    context.bot.edit_message_text = AsyncMock()
    # Use the normal winner media sender with a synthetic, local sticker.
    sticker = tmp_path / 'winner.webp'
    sticker.write_bytes(b'synthetic winner sticker')
    handler._resolve_card_media_path = Mock(return_value=str(sticker))
    handler._send_round_winner_card_media = BattleHandlersMixin._send_round_winner_card_media.__get__(handler)
    request = handler.modes.create_inline_private_challenge(1, 'quick', 'normal')
    key = request['request_id']
    invitation = _query(f'gm_inline_accept_{key}', 2)
    invitation.inline_message_id = 'friend-private-invitation'
    asyncio.run(handler.game_inline_accept_handler(SimpleNamespace(callback_query=invitation), context))
    invitation.edit_message_text.assert_awaited_once_with(
        '✅ نبرد شروع شد، بیا اینجا @TelBattleTest_bot بازی کنیم')
    handler.modes.select_quick_card(key, 1, 'alpha')
    handler.modes.select_quick_card(key, 2, 'beta')
    handler.modes.select_quick_ability(key, 1, 'skip')
    handler.modes.select_quick_ability(key, 2, 'skip')
    handler.modes.select_quick_stat(key, 1, 'power')
    context.bot.send_message.reset_mock()
    context.bot.send_sticker.reset_mock()
    delivery = Mock()
    delivery.attach_mock(context.bot.send_sticker, 'sticker')
    delivery.attach_mock(context.bot.send_message, 'message')

    asyncio.run(handler.quick_stat_handler(
        SimpleNamespace(callback_query=_query(f'gm_qstat_{key}_iq', 2)), context))

    report = handler.modes.get_report(key)
    assert report['winner_id'] == 1  # Alpha's Epic form beats Beta's Normal form.
    assert [(call[0], call.kwargs['chat_id']) for call in delivery.mock_calls] == [
        ('sticker', 1), ('message', 1), ('sticker', 2), ('message', 2)]
    for call in context.bot.send_message.await_args_list:
        assert call.kwargs['text'].startswith('💬 «')
        button = call.kwargs['reply_markup'].inline_keyboard[0][0]
        assert button.text == '📋 مشاهده جزئیات'
        assert button.callback_data == f'gm_report_{key}'
    assert invitation.edit_message_text.await_count == 1
    context.bot.edit_message_text.assert_not_awaited()
    assert handler.modes.get_request(key)['origin_inline_message_id'] == invitation.inline_message_id


def test_manual_choice_sends_actual_form_immediately_and_duplicate_click_does_not_resend(quick_ui):
    handler, context = quick_ui
    key = _request(handler)['request_id']
    handler.modes.start_quick_match(key)
    query = _query(f'gm_qcard_{key}_alpha')
    asyncio.run(handler.quick_card_handler(SimpleNamespace(callback_query=query), context))
    context.bot.send_sticker.assert_awaited_once_with(chat_id=1, sticker='alpha-epic-sticker')
    assert handler.modes.get_state(key)['phase'] == 'card_selection'
    context.bot.send_message.assert_not_awaited()
    asyncio.run(handler.quick_card_handler(SimpleNamespace(callback_query=query), context))
    assert context.bot.send_sticker.await_count == 1
    assert query.answer.await_args.kwargs['show_alert'] is True
    query = _query(f'gm_qcard_{key}_beta', 2)
    asyncio.run(handler.quick_card_handler(SimpleNamespace(callback_query=query), context))
    assert context.bot.send_sticker.await_args.kwargs == {'chat_id': 2, 'sticker': 'beta-normal-sticker'}
    assert handler.modes.get_state(key)['phase'] == 'ability_selection'
    sent = context.bot.send_message.await_args_list
    assert [c.kwargs['chat_id'] for c in sent] == [1, 1, 2, 2]
    assert all('🏜️ زمین: بیابان' in sent[i].kwargs['text'] for i in (0, 2))
    assert all(sent[i].kwargs['text'] == 'از کدوم Ability card استفاده میکنی؟' for i in (1, 3))
    assert all(sent[i].kwargs['reply_markup'].inline_keyboard[-1][0].callback_data == f'gm_qability_{key}_skip' for i in (1, 3))


def test_random_start_sends_each_players_auto_selected_form_and_arena_before_ability(quick_ui):
    handler, context = quick_ui
    request = _request(handler, 'random')
    asyncio.run(handler._launch_quick_match(context, request))
    state = handler.modes.get_state(request['request_id'])
    assert state['phase'] == 'ability_selection'
    for call in context.bot.send_sticker.await_args_list:
        uid = call.kwargs['chat_id']
        card = handler.db.get_card_by_id_for_player(state['cards'][str(uid)], uid)
        assert call.kwargs['sticker'] == f'{card.card_id}-{card.rarity.value}-sticker'
    assert context.bot.send_sticker.await_count == 2
    assert [c.kwargs['chat_id'] for c in context.bot.send_message.await_args_list] == [1, 1, 2, 2]


def test_reroll_sends_new_arena_separately_and_reveal_is_only_sent_to_its_owner(quick_ui):
    handler, context = quick_ui
    key = _request(handler)['request_id']
    handler.modes.start_quick_match(key)
    handler.modes.select_quick_card(key, 1, 'alpha')
    state, _ = handler.modes.select_quick_card(key, 2, 'beta')
    # Published edits cannot change a match's displayed snapshot or available abilities.
    with patch.object(handler.modes, '_arena', side_effect=AssertionError('use match snapshot')):
        asyncio.run(handler._send_quick_ability_panels(context, key, state))
    assert 'بیابان' in context.bot.send_message.await_args_list[0].kwargs['text']
    context.bot.send_message.reset_mock()
    handler.modes.grant_ability(1, 'reveal_opponent')
    handler.modes.grant_ability(2, 'reroll_arena')
    handler.modes.select_quick_ability(key, 1, 'reveal_opponent')
    state, advanced = handler.modes.select_quick_ability(key, 2, 'reroll_arena')
    assert advanced and state['arena'] == 'city'
    asyncio.run(handler._send_quick_stat_panels(context, key, state))
    calls = context.bot.send_message.await_args_list
    assert [c.kwargs['chat_id'] for c in calls] == [1, 1, 1, 2, 2]
    assert all('🏙️ زمین: شهر' in calls[i].kwargs['text'] for i in (0, 3))
    assert _readable(calls[1].kwargs['text']) == '👁 کارت حریف: Beta'
    expected = 'یه ویژگی انتخاب کن، ۶۰ ثانیه ⏳ وقت داری\n(عددهای زیر با اثر زمین، Passive و Ability محاسبه شدن)'
    assert calls[2].kwargs['text'] == calls[4].kwargs['text'] == expected
    power = handler.db.get_card_by_id_for_player('alpha', 1).power
    buttons = calls[2].kwargs['reply_markup'].inline_keyboard
    assert buttons[0][0].text == f'💪 قدرت: {power + 1}'
    assert buttons[0][0].callback_data == f'gm_qstat_{key}_power'
    assert handler._schedule_mode_job.call_args.args[2] == 60


@pytest.mark.parametrize('rarity', ['normal', 'epic', 'legend'])
def test_report_keeps_played_rarity_after_active_form_changes_and_restart(quick_ui, rarity):
    handler, context = quick_ui
    handler.db.set_player_card_rarity_override(1, 'alpha', rarity)
    key = _request(handler)['request_id']
    handler.modes.start_quick_match(key)
    handler.modes.select_quick_card(key, 1, 'alpha')
    handler.modes.select_quick_card(key, 2, 'beta')
    handler.modes.select_quick_ability(key, 1, 'skip')
    handler.modes.select_quick_ability(key, 2, 'skip')
    handler.modes.select_quick_stat(key, 1, 'power')
    _, report = handler.modes.select_quick_stat(key, 2, 'iq')
    assert report['breakdown']['1']['card_rarity'] == rarity
    assert report['breakdown']['2']['card_rarity'] == 'normal'
    handler.db.set_player_card_rarity_override(1, 'alpha', 'normal' if rarity != 'normal' else 'legend')
    handler.modes = GameModeSystem(DatabaseManager(handler.db.db_path))
    query = _query(f'gm_report_{key}')
    asyncio.run(handler.game_report_handler(SimpleNamespace(callback_query=query), context))
    text = _readable(context.bot.send_message.await_args.kwargs['text'])
    assert f'Alpha ({rarity.title()})' in text and 'Beta (Normal)' in text
    assert text.startswith('📋 جزئیات بازی Quick\n')
    assert '🏜️' not in text and 'امتیاز = جمع' not in text
    assert 'امتیاز نهایی:' in text and 'XP' in text


def test_stale_cached_sticker_falls_back_to_local_sticker(quick_ui, tmp_path):
    handler, context = quick_ui
    image = tmp_path / 'epic.webp'
    image.write_bytes(b'synthetic media')
    handler._resolve_card_media_path = Mock(return_value=str(image))
    context.bot.send_sticker.side_effect = [RuntimeError('stale file_id'), None]
    card = handler.db.get_card_by_id_for_player('alpha', 1)
    asyncio.run(handler._send_quick_card_preview(context, 1, card))
    assert context.bot.send_sticker.await_count == 2
    assert context.bot.send_sticker.await_args.kwargs['chat_id'] == 1
    assert context.bot.send_sticker.await_args.kwargs['sticker'].name == str(image)
    context.bot.send_message.assert_not_awaited()


def test_unavailable_media_falls_back_to_card_information_without_stopping_play(quick_ui):
    handler, context = quick_ui
    context.bot.send_sticker.side_effect = RuntimeError('media unavailable')
    handler._resolve_card_media_path = Mock(return_value=None)
    key = _request(handler)['request_id']
    handler.modes.start_quick_match(key)
    query = _query(f'gm_qcard_{key}_alpha')
    asyncio.run(handler.quick_card_handler(SimpleNamespace(callback_query=query), context))
    sent = context.bot.send_message.await_args.kwargs
    assert sent['chat_id'] == 1
    assert 'Alpha (Epic)' in _readable(sent['text']) and '💪 قدرت:' in sent['text']
    assert handler.modes.get_state(key)['cards']['1'] == 'alpha'


def test_custom_card_preview_uses_only_private_image_and_not_public_sticker_cache(quick_ui, tmp_path):
    handler, context = quick_ui
    image = tmp_path / 'private.png'
    image.write_bytes(b'private synthetic media')
    card = SimpleNamespace(card_id='private-alpha', name='Private', rarity='legend', origin='custom', image_path=str(image))
    handler._resolve_card_media_path = Mock(side_effect=AssertionError('public resolver forbidden'))
    with patch.object(handler.db, 'get_card_variant_media_file_id', side_effect=AssertionError('public cache forbidden')):
        asyncio.run(handler._send_quick_card_preview(context, 1, card))
    context.bot.send_sticker.assert_not_awaited()
    assert context.bot.send_photo.await_args.kwargs['chat_id'] == 1
    assert context.bot.send_photo.await_args.kwargs['photo'].name == str(image)
