import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.game_modes import GameModeHandlersMixin
from bot.handlers.pvp import PvPHandlersMixin
from core.database import DatabaseManager
from core.models import Card, CardRarity, FightStatus
from systems.deck_system import DeckSystem
from systems.game_mode_system import GameModeSystem


class DeckHandlers(GameModeHandlersMixin, PvPHandlersMixin, BattleHandlersMixin):
    pass


@pytest.fixture
def deck_ui(tmp_path):
    handler = DeckHandlers()
    handler.db = DatabaseManager(str(tmp_path / 'deck-routes.db'))
    for uid, name in [(1, 'MH'), (2, 'Varan'), (3, 'Other')]:
        handler.db.get_or_create_player(uid, first_name=name)
    for cid in ('alpha', 'beta', 'gamma'):
        handler.db.add_card(Card(card_id=cid, name=cid.title(), rarity=CardRarity.NORMAL,
                                 power=60, speed=40, iq=50, popularity=30, abilities=[]))
        for uid in (1, 2, 3):
            handler.db.add_card_to_player(uid, cid)
    decks = {}
    for uid in (1, 2, 3):
        ok, deck_id = DeckSystem(handler.db).create_deck(uid, ['alpha', 'beta', 'gamma'])
        assert ok
        decks[uid] = deck_id
    handler.modes = GameModeSystem(handler.db)
    handler._schedule_mode_job = Mock()
    handler._cancel_mode_job = Mock()
    handler._init_3round_battle = AsyncMock()
    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(
        send_message=AsyncMock(side_effect=[SimpleNamespace(message_id=51), SimpleNamespace(message_id=52)]),
        edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock()))
    return handler, context, decks


def _launch(handler, context, source, variant='normal'):
    if source == 'inline_private':
        request = handler.modes.create_inline_private_challenge(1, 'deck', variant)
        handler.modes.update_inline_message_reference(request['request_id'], 'friend-invitation')
    else:
        request = handler.modes.create_group_challenge(1, 'deck', variant, -100123)
        handler.modes.update_message_reference(request['request_id'], -100123, 77)
    ok, _, accepted = handler.modes.accept_request(request['request_id'], 2)
    assert ok
    asyncio.run(handler._launch_deck_match(context, accepted))
    return accepted, handler.db.get_user_active_fights(1)[0]


def _query(data, uid):
    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=uid),
                           answer=AsyncMock(), edit_message_text=AsyncMock(),
                           edit_message_reply_markup=AsyncMock())


@pytest.mark.parametrize('order', [(1, 2), (2, 1)])
def test_group_deck_has_only_independent_bot_dm_pickers_and_starts_once(deck_ui, order):
    handler, context, decks = deck_ui
    _, key = _launch(handler, context, 'group_challenge')
    assert [c.kwargs['chat_id'] for c in context.bot.send_message.await_args_list] == [1, 2]
    for uid, call in zip((1, 2), context.bot.send_message.await_args_list):
        rows = call.kwargs['reply_markup'].inline_keyboard
        assert rows[0][0].callback_data == f'pvp_deck_{key}_{decks[uid]}'
        assert all(button.switch_inline_query_current_chat is None for row in rows for button in row)
    assert context.bot.edit_message_text.await_args.kwargs['chat_id'] == -100123
    assert 'گفت‌وگوی خصوصی با ربات' in context.bot.edit_message_text.await_args.kwargs['text']
    initial_edits = context.bot.edit_message_text.await_count

    first, second = order
    query = _query(f'pvp_deck_{key}_{decks[first]}', first)
    asyncio.run(handler.pvp_deck_select_handler(SimpleNamespace(callback_query=query), context))
    handler._init_3round_battle.assert_not_awaited()
    assert f'pvp_{key}_deck_expected_user' not in context.bot_data
    # No shared panel is sent to the group or to either player's DM after a choice.
    assert context.bot.send_message.await_count == 2
    assert context.bot.edit_message_text.await_count == initial_edits
    duplicate = asyncio.run(handler._record_pvp_deck_selection(context, key, first, decks[first]))
    assert duplicate[0] is False

    query = _query(f'pvp_deck_{key}_{decks[second]}', second)
    asyncio.run(handler.pvp_deck_select_handler(SimpleNamespace(callback_query=query), context))
    handler._init_3round_battle.assert_awaited_once()
    assert handler.db.get_battle_deck_state(key)['challenger_deck_selected']
    assert handler.db.get_battle_deck_state(key)['opponent_deck_selected']
    import sqlite3
    from bot.deck_reports import load_in
    with sqlite3.connect(handler.db.db_path) as conn:
        report = load_in(conn, key)
    assert report['decks']['1']['deck_id'] == decks[1]
    assert report['decks']['2']['deck_id'] == decks[2]
    assert context.bot.send_message.await_count == 2
    handler._cancel_mode_job.assert_called_once_with(context, f'gm-deck-selection-{key}')


def test_peer_private_deck_only_updates_shared_invitation_and_keeps_turns(deck_ui):
    handler, context, decks = deck_ui
    _, key = _launch(handler, context, 'inline_private')
    context.bot.send_message.assert_not_awaited()
    first = context.bot.edit_message_text.await_args.kwargs
    assert first['inline_message_id'] == 'friend-invitation'
    assert 'ربات' not in first['text']
    rows = first['reply_markup'].inline_keyboard
    assert len(rows) == 1 and len(rows[0]) == 1
    assert rows[0][0].switch_inline_query_current_chat == f'pvpdeck {key} 1'

    # A player cannot use the other player's button, or choose out of turn.
    query = SimpleNamespace(query=f'pvpdeck {key} 1', from_user=SimpleNamespace(id=2), answer=AsyncMock())
    asyncio.run(handler._answer_pvp_deck_inline_query(SimpleNamespace(inline_query=query), context))
    assert query.answer.await_args.args[0][0].id == 'locked_deck_picker'
    assert not asyncio.run(handler._record_pvp_deck_selection(context, key, 2, decks[2]))[0]
    query.from_user.id = 1
    asyncio.run(handler._answer_pvp_deck_inline_query(SimpleNamespace(inline_query=query), context))
    result = query.answer.await_args.args[0][0]
    assert result.id == handler._inline_deck_result_id(key, 1, decks[1])

    # Telegram chosen-inline feedback and its fallback confirmation share one locked choice.
    chosen = SimpleNamespace(result_id=result.id, from_user=SimpleNamespace(id=1), inline_message_id='choice-1')
    asyncio.run(handler.r3_chosen_inline_card_handler(SimpleNamespace(chosen_inline_result=chosen), context))
    next_panel = context.bot.edit_message_text.await_args.kwargs
    assert next_panel['inline_message_id'] == 'friend-invitation'
    assert next_panel['reply_markup'].inline_keyboard[0][0].switch_inline_query_current_chat == f'pvpdeck {key} 2'
    edit_count = context.bot.edit_message_text.await_count
    duplicate = _query(result.id, 1)
    asyncio.run(handler.pvp_inline_deck_confirm_handler(SimpleNamespace(callback_query=duplicate), context))
    assert duplicate.answer.await_args.kwargs['show_alert'] is True
    assert context.bot.edit_message_text.await_count == edit_count

    confirm = _query(handler._inline_deck_result_id(key, 2, decks[2]), 2)
    asyncio.run(handler.pvp_inline_deck_confirm_handler(SimpleNamespace(callback_query=confirm), context))
    handler._init_3round_battle.assert_awaited_once()
    context.bot.send_message.assert_not_awaited()
    assert not any(k.startswith('deck_selection_panel_') for k in context.bot_data)
    assert f'pvp_{key}_deck_expected_user' not in context.bot_data
    assert context.bot_data[f'deck_{key}_inline_message_id'] == 'friend-invitation'


def test_group_stale_inline_deck_button_no_longer_offers_an_extra_picker(deck_ui):
    handler, context, _ = deck_ui
    _, key = _launch(handler, context, 'group_challenge')
    query = SimpleNamespace(query=f'pvpdeck {key} 1', from_user=SimpleNamespace(id=1), answer=AsyncMock())
    asyncio.run(handler._answer_pvp_deck_inline_query(SimpleNamespace(inline_query=query), context))
    query.answer.assert_awaited_once_with([], cache_time=0, is_personal=True)


@pytest.mark.parametrize('source', ['group_challenge', 'inline_private'])
def test_deck_timeout_closes_only_the_panels_for_its_route(deck_ui, source):
    handler, context, decks = deck_ui
    request, key = _launch(handler, context, source)
    context.bot.edit_message_text.reset_mock()
    context.job = SimpleNamespace(data={'fight_id': key, 'request_id': request['request_id'], 'player_ids': [1, 2]})
    asyncio.run(handler.deck_selection_timeout_job(context))
    assert handler.db.get_fight_by_id(key).status == FightStatus.CANCELLED
    edits = context.bot.edit_message_text.await_args_list
    if source == 'inline_private':
        assert len(edits) == 1 and edits[0].kwargs['inline_message_id'] == 'friend-invitation'
        context.bot.send_message.assert_not_awaited()
    else:
        assert [c.kwargs['chat_id'] for c in edits] == [-100123, 1, 2]
    assert not any(k.startswith('deck_selection_panel_') for k in context.bot_data)
    assert f'pvp_{key}_deck_expected_user' not in context.bot_data
    assert not asyncio.run(handler._record_pvp_deck_selection(context, key, 1, decks[1]))[0]
    handler._init_3round_battle.assert_not_awaited()


@pytest.mark.parametrize('source', ['group_challenge', 'inline_private'])
def test_random_deck_keeps_automatic_selection_without_any_picker(deck_ui, source):
    handler, context, _ = deck_ui
    _, key = _launch(handler, context, source, 'random')
    handler._init_3round_battle.assert_awaited_once()
    context.bot.send_message.assert_not_awaited()
    context.bot.edit_message_text.assert_not_awaited()
    handler._schedule_mode_job.assert_not_called()
    state = handler.db.get_battle_deck_state(key)
    assert state['challenger_deck_selected'] and state['opponent_deck_selected']
    assert len(state['challenger_remaining_cards']) == len(state['opponent_remaining_cards']) == 3


def test_group_deck_rejects_another_players_deck_and_expired_choices(deck_ui):
    handler, context, decks = deck_ui
    _, key = _launch(handler, context, 'group_challenge')
    assert not asyncio.run(handler._record_pvp_deck_selection(context, key, 1, decks[2]))[0]
    assert not asyncio.run(handler._record_pvp_deck_selection(context, key, 3, decks[3]))[0]
    assert not handler.db.get_battle_deck_state(key).get('challenger_deck_selected')
    handler.db.update_fight(key, expires_at=datetime(2000, 1, 1).isoformat())
    assert not asyncio.run(handler._record_pvp_deck_selection(context, key, 1, decks[1]))[0]
    handler._init_3round_battle.assert_not_awaited()


def test_legacy_group_acceptance_also_sends_only_private_deck_lists(deck_ui):
    handler, context, _ = deck_ui
    key = handler.db.create_fight(1, 0, -100123)
    query = _query(f'pvp_accept_{key}', 2)
    with patch('bot.handlers.pvp.check_user_started_bot', new=AsyncMock(return_value=True)):
        asyncio.run(handler.accept_pvp_fight_handler(SimpleNamespace(callback_query=query), context))
    assert [c.kwargs['chat_id'] for c in context.bot.send_message.await_args_list] == [1, 2]
    assert 'پیوی ربات' in query.edit_message_text.await_args.args[0]
    context.bot.edit_message_text.assert_not_awaited()
