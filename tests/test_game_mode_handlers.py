import asyncio
import re
import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers.game_modes import GameModeHandlersMixin, GAME_INLINE_QUERY_PATTERN
from bot.handlers.pvp import PvPHandlersMixin
from core.models import FightStatus
from systems.deck_system import DECK_SELECTION_TTL_SECONDS
from systems.game_mode_system import EASY_LOBBY_TTL_SECONDS


def _readable_text(text):
    return text.translate(str.maketrans('', '', '\u2066\u2068\u2069'))


@pytest.mark.parametrize('variant,bot_username', [('normal', 'TelBattleTest_bot'), ('random', 'TelBattleProduction_bot')])
def test_quick_group_prompts_keep_buttons_acceptance_and_card_pagination(tmp_path, variant, bot_username):
    from core.database import DatabaseManager
    from core.models import Card, CardRarity
    from systems.game_mode_system import GameModeSystem

    handler = GameModeHandlersMixin()
    handler.db = DatabaseManager(str(tmp_path / 'quick-prompts.db'))
    for uid, name in [(1, 'MH'), (2, 'کسری')]:
        handler.db.get_or_create_player(uid, first_name=name)
    for index in range(9):
        card = Card(card_id=f'hero-{index}', name=f'Hero {index}', rarity=CardRarity.NORMAL,
                    power=5, speed=5, iq=5, popularity=5, abilities=[])
        handler.db.add_card(card)
        handler.db.add_card_to_player(1, card.card_id)
        handler.db.add_card_to_player(2, card.card_id)
    handler.modes = GameModeSystem(handler.db)
    handler._schedule_mode_job = Mock()
    handler._launch_mode_match = AsyncMock()
    context = SimpleNamespace(bot=SimpleNamespace(username=bot_username, send_message=AsyncMock()))
    message = SimpleNamespace(chat=SimpleNamespace(type='supergroup'), chat_id=-100123, message_id=12, reply_text=AsyncMock())
    actor = SimpleNamespace(id=1, first_name='MH')
    update = SimpleNamespace(effective_chat=message.chat, effective_user=actor, message=message)
    asyncio.run(handler.fight_command(update, context))
    assert message.reply_text.await_args.args[0] == '🎮 حالت بازی رو انتخاب کن:'
    assert [[b.callback_data for b in row] for row in message.reply_text.await_args.kwargs['reply_markup'].inline_keyboard] == [
        ['gm_mode_quick'], ['gm_mode_deck'], ['gm_mode_easy']]

    query = SimpleNamespace(data='gm_mode_quick', from_user=actor, message=message,
                            answer=AsyncMock(), edit_message_text=AsyncMock())
    update.callback_query = query
    asyncio.run(handler.game_mode_select_handler(update, context))
    assert query.edit_message_text.await_args.args[0] == '⚡ Quick Mode\nنوع بازی رو انتخاب کن:'
    assert [[b.callback_data for b in row] for row in query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard] == [
        ['gm_variant_quick_normal'], ['gm_variant_quick_random']]

    query.data = f'gm_variant_quick_{variant}'
    asyncio.run(handler.game_variant_handler(update, context))
    assert _readable_text(query.edit_message_text.await_args.args[0]) == (
        f'⚔️ کی حاضره نبرد Quick-{variant.title()} با MH رو بپذیره\n⏳ مهلت پذیرش: 60 ثانیه')
    button = query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[0][0]
    assert button.text == '✊ قبول مبارزه'
    request_id = button.callback_data.removeprefix('gm_accept_')
    request = handler.modes.get_request(request_id)
    assert request['creator_id'] == 1 and request['origin_chat_id'] == -100123
    assert handler._schedule_mode_job.call_args.args[2] == 60

    query.data = button.callback_data
    query.from_user = SimpleNamespace(id=2, first_name='کسری')
    asyncio.run(handler.game_accept_handler(update, context))
    assert _readable_text(query.edit_message_text.await_args.args[0]) == (
        f'✅ نبرد بین MH و کسری انجام میشه، بیاید اینجا @{bot_username} و آماده مبارزه شید!')
    accepted = handler.modes.get_request(request_id)
    assert accepted['opponent_id'] == 2
    handler._launch_mode_match.assert_awaited_once_with(context, accepted)

    # Normal card selection: names, callback IDs and next/previous pages remain usable.
    asyncio.run(handler._send_quick_card_page(context, request_id, 1, 0))
    sent = context.bot.send_message.await_args.kwargs
    assert sent['text'] == 'مبارزت رو انتخاب کن\n⏳ ۶۰ ثانیه وقت داری!'
    rows = sent['reply_markup'].inline_keyboard
    assert len(rows) == 9
    assert all(row[0].callback_data.startswith(f'gm_qcard_{request_id}_hero-') for row in rows[:-1])
    assert rows[-1][-1].callback_data == f'gm_qpage_{request_id}_1'
    query.data = rows[-1][-1].callback_data
    query.from_user = actor
    asyncio.run(handler.quick_card_page_handler(update, context))
    page = query.edit_message_text.await_args
    assert page.args[0] == sent['text']
    assert len(page.kwargs['reply_markup'].inline_keyboard) == 2
    assert page.kwargs['reply_markup'].inline_keyboard[-1][0].callback_data == f'gm_qpage_{request_id}_0'


def test_quick_arena_text_names_target_card_type_and_affected_stat():
    handler = GameModeHandlersMixin()
    handler.modes = SimpleNamespace(
        _arena=Mock(
            return_value={
                "emoji": "🏜️",
                "name": "بیابان",
                "effects": [
                    {"card_type": "power", "stat": "power", "delta": 2},
                    {"card_type": "speed", "stat": "speed", "delta": -1},
                ],
                "disabled_stats": [],
                "abilities_enabled": True,
                "passives_enabled": True,
            }
        )
    )

    text = handler._quick_arena_text({"arena": "desert"})

    assert "کارت‌های قدرتی: 💪 قدرت" in text
    assert "کارت‌های سرعتی: ⚡ سرعت" in text
    assert "+2" in text
    assert "-1" in text


def test_quick_random_ability_panel_reveals_auto_selected_card():
    alpha = SimpleNamespace(name="Alpha")
    beta = SimpleNamespace(name="Beta")
    cards = {"alpha": alpha, "beta": beta}
    handler = GameModeHandlersMixin()
    handler.db = SimpleNamespace(
        get_card_by_id_for_player=Mock(side_effect=lambda card_id, _user_id: cards.get(card_id)),
        get_card_by_id=Mock(side_effect=lambda card_id: cards.get(card_id)),
    )
    handler.modes = SimpleNamespace(
        _arena=Mock(return_value={"abilities_enabled": True}),
        list_player_abilities=Mock(return_value=[]),
    )
    handler._quick_arena_text = Mock(return_value="🏛️ زمین: معبد خاموش")
    handler._send_quick_card_preview = AsyncMock()
    handler._schedule_mode_job = Mock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    state = {
        "variant": "random",
        "arena": "silent_temple",
        "players": [1, 2],
        "cards": {"1": "alpha", "2": "beta"},
    }

    asyncio.run(handler._send_quick_ability_panels(context, "request-random", state))

    handler._send_quick_card_preview.assert_any_await(context, 1, alpha)
    sent = context.bot.send_message.await_args_list
    assert [(call.kwargs['chat_id'], call.kwargs['text']) for call in sent] == [
        (1, '🏛️ زمین: معبد خاموش'), (1, 'از کدوم Ability card استفاده میکنی؟'),
        (2, '🏛️ زمین: معبد خاموش'), (2, 'از کدوم Ability card استفاده میکنی؟')]
    assert sent[1].kwargs['reply_markup'].inline_keyboard[-1][0].callback_data == 'gm_qability_request-random_skip'


def test_quick_stat_panel_shows_selected_card_and_final_values():
    handler = GameModeHandlersMixin()
    handler.db = SimpleNamespace(get_card_by_id=Mock(return_value=None))
    handler.modes = SimpleNamespace(
        allowed_quick_stats=Mock(return_value=["power", "speed", "iq", "popularity"]),
        quick_stat_preview=Mock(
            return_value={
                "card_name": "Alpha",
                "final_values": {"power": 93, "speed": 29, "iq": 40, "popularity": 50},
            }
        ),
    )
    handler._quick_arena_text = Mock(return_value="🏜️ زمین: بیابان")
    handler._schedule_mode_job = Mock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    state = {
        "players": [1, 2],
        "ability_choices": {"1": "skip", "2": "skip"},
        "cards": {"1": "alpha", "2": "beta"},
    }

    asyncio.run(handler._send_quick_stat_panels(context, "request-1", state))

    first_message = context.bot.send_message.await_args_list[0].kwargs
    assert first_message['text'] == 'یه ویژگی انتخاب کن، ۶۰ ثانیه ⏳ وقت داری\n(عددهای زیر با اثر زمین، Passive و Ability محاسبه شدن)'
    assert context.bot.send_message.await_count == 2
    button_texts = [row[0].text for row in first_message["reply_markup"].inline_keyboard]
    assert button_texts == ["💪 قدرت: 93", "⚡ سرعت: 29", "🧠 هوش: 40", "❤️ محبوبیت: 50"]


@pytest.mark.parametrize('variant', ['normal', 'random'])
def test_inline_private_quick_query_builds_an_accept_invitation(tmp_path, variant):
    handler = GameModeHandlersMixin()
    handler.db = SimpleNamespace(get_player_cards=Mock(return_value=[SimpleNamespace()]))
    from core.database import DatabaseManager
    handler.db.db_path = DatabaseManager(str(tmp_path/'inline.db')).db_path
    handler.modes = SimpleNamespace(
        mode_access=SimpleNamespace(check=Mock(return_value=(True, ""))),
        create_inline_private_challenge=Mock(
            return_value={"request_id": "request-1"}
        )
    )
    inline_query = SimpleNamespace(
        query=f"game quick {variant}",
        from_user=SimpleNamespace(id=1, first_name="Ali"),
        answer=AsyncMock(),
    )
    context = SimpleNamespace(bot=SimpleNamespace(username="TelBattleBot"))

    asyncio.run(
        handler.game_inline_query_handler(
            SimpleNamespace(inline_query=inline_query), context
        )
    )

    results = inline_query.answer.await_args.args[0]
    assert len(results) == 1
    assert results[0].id == "gmi|request-1"
    assert results[0].input_message_content.message_text == (
        f"🎮 بیا یه دست بازی کنیم\nQuick mode ({variant.title()})"
    )
    handler.modes.create_inline_private_challenge.assert_called_once_with(1, 'quick', variant)
    assert results[0].reply_markup.inline_keyboard[0][0].callback_data == (
        "gm_inline_accept_request-1"
    )


def test_inline_private_blank_or_whitespace_query_shows_all_game_modes(tmp_path):
    handler = GameModeHandlersMixin()
    cards = [SimpleNamespace(), SimpleNamespace(), SimpleNamespace()]
    handler.db = SimpleNamespace(get_player_cards=Mock(return_value=cards))
    from core.database import DatabaseManager
    handler.db.db_path = DatabaseManager(str(tmp_path/'inline.db')).db_path
    handler.modes = SimpleNamespace(
        mode_access=SimpleNamespace(check=Mock(return_value=(True, ""))),
        create_inline_private_challenge=Mock(
            side_effect=lambda _user_id, mode, variant: {
                "request_id": f"{mode}-{variant}"
            }
        )
    )
    inline_query = SimpleNamespace(
        query="   ",
        chat_type="private",
        from_user=SimpleNamespace(id=1, first_name="Ali"),
        answer=AsyncMock(),
    )
    context = SimpleNamespace(bot=SimpleNamespace(username="TelBattleBot"))

    with patch("bot.handlers.game_modes.DeckSystem") as deck_system:
        deck_system.return_value.get_valid_decks.return_value = [SimpleNamespace()]
        asyncio.run(
            handler.game_inline_query_handler(
                SimpleNamespace(inline_query=inline_query), context
            )
        )

    results = inline_query.answer.await_args.args[0]
    assert [result.id for result in results] == [
        "gmi|quick-normal",
        "gmi|quick-random",
        "gmi|deck-normal",
        "gmi|deck-random",
    ]
    assert results[0].input_message_content.message_text == '🎮 بیا یه دست بازی کنیم\nQuick mode (Normal)'
    assert results[1].input_message_content.message_text == '🎮 بیا یه دست بازی کنیم\nQuick mode (Random)'
    assert results[2].input_message_content.message_text == '🃏 بیا یه دست بازی کنیم\nDeck mode (Normal)'
    assert results[3].input_message_content.message_text == '🃏 بیا یه دست بازی کنیم\nDeck mode (Random)'
    assert re.match(GAME_INLINE_QUERY_PATTERN, "")
    assert re.match(GAME_INLINE_QUERY_PATTERN, "   ")


def test_private_invite_button_opens_default_game_mode_picker():
    handler = GameModeHandlersMixin()
    handler.modes = SimpleNamespace(mode_access=SimpleNamespace(check=Mock(return_value=(True, ""))))
    query = SimpleNamespace(
        data="gm_variant_quick_normal",
        from_user=SimpleNamespace(id=1),
        message=SimpleNamespace(chat=SimpleNamespace(type="private")),
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )

    asyncio.run(
        handler.game_variant_handler(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        )
    )

    markup = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert query.edit_message_text.await_args.args[0] == '🎮 میخوای با کی بازی کنی؟'
    assert [row[0].callback_data for row in markup.inline_keyboard[1:]] == [
        'gm_source_quick_normal_queue', 'gm_source_quick_normal_invite']
    invite_button = markup.inline_keyboard[0][0]
    assert invite_button.text == "👤 انتخاب بازی در پی‌وی دوست"
    assert invite_button.switch_inline_query == ""


@pytest.mark.parametrize('bot_username', ['TelBattleTest_bot', 'TelBattleProduction_bot'])
def test_inline_accept_records_shared_message_before_launching_match(bot_username):
    handler = GameModeHandlersMixin()
    request = {
        "request_id": "request-1",
        "creator_id": 1,
        "mode": "quick",
        "variant": "normal",
        "source": "inline_private",
    }
    accepted = {**request, "opponent_id": 2, "origin_inline_message_id": "inline-1"}
    handler.db = SimpleNamespace(get_player_cards=Mock(return_value=[SimpleNamespace()]))
    handler.modes = SimpleNamespace(
        get_request=Mock(return_value=request),
        update_inline_message_reference=Mock(),
        accept_request=Mock(return_value=(True, "accepted", accepted)),
    )
    handler._launch_mode_match = AsyncMock()
    query = SimpleNamespace(
        data="gm_inline_accept_request-1",
        from_user=SimpleNamespace(id=2),
        inline_message_id="inline-1",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    context = SimpleNamespace(bot=SimpleNamespace(username=bot_username))

    asyncio.run(
        handler.game_inline_accept_handler(
            SimpleNamespace(callback_query=query), context
        )
    )

    handler.modes.update_inline_message_reference.assert_called_once_with(
        "request-1", "inline-1"
    )
    handler._launch_mode_match.assert_awaited_once_with(context, accepted)
    query.edit_message_text.assert_awaited_once_with(
        f'✅ نبرد شروع شد، بیا اینجا @{bot_username} بازی کنیم')


def test_easy_inline_result_has_fallback_confirmation_button():
    handler = GameModeHandlersMixin()
    card = SimpleNamespace(card_id="card-1", name="Alpha")
    handler.modes = SimpleNamespace(get_easy_options=Mock(return_value=[card]))
    handler._get_inline_card_sticker_file_id = AsyncMock(return_value=None)
    handler._get_inline_card_photo_file_id = AsyncMock(return_value=None)
    inline_query = SimpleNamespace(
        query="easy request-1",
        from_user=SimpleNamespace(id=2),
        answer=AsyncMock(),
    )

    asyncio.run(
        handler.easy_inline_query_handler(
            SimpleNamespace(inline_query=inline_query), SimpleNamespace()
        )
    )

    result = inline_query.answer.await_args.args[0][0]
    assert result.reply_markup.inline_keyboard[0][0].callback_data == (
        "ez|request-1|2|card-1"
    )


def test_easy_inline_confirmation_records_choice_and_resolves_when_ready():
    handler = GameModeHandlersMixin()
    handler.modes = SimpleNamespace(
        select_easy_card=Mock(return_value=(True, "all_selected", {}))
    )
    handler._resolve_and_announce_easy = AsyncMock()
    query = SimpleNamespace(
        data="ez|request-1|2|card-1",
        from_user=SimpleNamespace(id=2),
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    context = SimpleNamespace()

    asyncio.run(
        handler.easy_inline_confirm_handler(
            SimpleNamespace(callback_query=query), context
        )
    )

    handler.modes.select_easy_card.assert_called_once_with(
        "request-1", 2, "card-1"
    )
    handler._resolve_and_announce_easy.assert_awaited_once_with(context, "request-1")


def test_easy_duplicate_last_confirmation_recovers_without_waiting_for_timer():
    handler = GameModeHandlersMixin()
    completed_state = {
        "phase": "selection",
        "players": [1, 2],
        "choices": {"1": "card-1", "2": "card-2"},
    }
    handler.modes = SimpleNamespace(
        select_easy_card=Mock(
            return_value=(False, "choice_locked", completed_state)
        )
    )
    handler._resolve_and_announce_easy = AsyncMock()
    query = SimpleNamespace(
        data="ez|request-1|2|card-2",
        from_user=SimpleNamespace(id=2),
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    context = SimpleNamespace()

    asyncio.run(
        handler.easy_inline_confirm_handler(
            SimpleNamespace(callback_query=query), context
        )
    )

    handler._resolve_and_announce_easy.assert_awaited_once_with(
        context, "request-1"
    )


@pytest.mark.parametrize('source', ['group_challenge', 'inline_private', 'invite_link'])
@pytest.mark.parametrize('variant', ['normal', 'friendly'])
def test_quick_result_shows_only_card_slogan_with_details_button(source, variant):
    handler = GameModeHandlersMixin()
    winner_card = SimpleNamespace(
        card_id="winner-card",
        name="Abbas Araqchi",
        dialogs=["میز مذاکره هم گاهی میدان نبرد است."],
    )
    request = {
        "request_id": "request-1",
        "source": source,
        "origin_chat_id": -100123,
    }
    handler.modes = SimpleNamespace(get_request=Mock(return_value=request))
    handler.db = SimpleNamespace(
        get_or_create_player=Mock(
            side_effect=lambda user_id: SimpleNamespace(
                first_name="Ali" if user_id == 1 else "Reza"
            )
        ),
        get_card_by_id_for_player=Mock(return_value=winner_card),
        get_card_by_id=Mock(return_value=None),
    )
    handler._send_round_winner_card_media = AsyncMock(return_value=True)
    handler._edit_request_panel = AsyncMock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    delivery = Mock()
    delivery.attach_mock(handler._send_round_winner_card_media, 'media')
    delivery.attach_mock(context.bot.send_message, 'message')
    report = {
        "request_id": "request-1",
        "players": [1, 2],
        "winner_id": 1,
        "is_tie": False,
        "variant": variant,
        "rewards": {'1': {'xp': 10, 'score': 1}, '2': {'xp': 1, 'score': 0}},
        "breakdown": {
            "1": {"card_id": "winner-card", "card_name": "Abbas Araqchi", "scored_stats": ["power", "iq"]},
            "2": {"card_id": "loser-card", "card_name": "Other", "scored_stats": ["iq", "power"]},
        },
    }

    asyncio.run(handler._announce_quick_result(context, report))

    expected = '💬 «میز مذاکره هم گاهی میدان نبرد است.»'
    targets = [-100123] if source == 'group_challenge' else [1, 2]
    handler._edit_request_panel.assert_not_awaited()
    message_targets = targets + ([1, 2] if source == 'group_challenge' else [])
    assert [call.kwargs['chat_id'] for call in context.bot.send_message.await_args_list] == message_targets
    assert [call.args[1] for call in handler._send_round_winner_card_media.await_args_list] == targets
    assert all(call.kwargs['text'] == expected for call in context.bot.send_message.await_args_list)
    assert [(call[0], call.args[1] if call[0] == 'media' else call.kwargs['chat_id'])
            for call in delivery.mock_calls] == [
        item for uid in targets for item in [('media', uid), ('message', uid)]] + (
            [('message', 1), ('message', 2)] if source == 'group_challenge' else [])
    markup = context.bot.send_message.await_args.kwargs['reply_markup']
    assert markup.inline_keyboard[0][0].text == '📋 مشاهده جزئیات'
    assert markup.inline_keyboard[0][0].callback_data == 'gm_report_request-1'


@pytest.mark.parametrize('outcome', ['tie', 'timeout', 'missing_media', 'blocked_dm', 'custom'])
def test_inline_quick_result_handles_unavailable_media_and_non_winning_results(outcome):
    handler = GameModeHandlersMixin()
    handler.modes = SimpleNamespace(get_request=Mock(return_value={
        'source': 'inline_private', 'origin_inline_message_id': 'keep-invitation'}))
    card = SimpleNamespace(name='Alpha', origin='custom' if outcome == 'custom' else 'official',
                           dialogs=['آماده بودم!'])
    handler.db = SimpleNamespace(get_card_by_id_for_player=Mock(return_value=card))
    handler._send_round_winner_card_media = AsyncMock(return_value=False)
    handler._edit_request_panel = AsyncMock()
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    if outcome == 'blocked_dm':
        context.bot.send_message.side_effect = [RuntimeError('bot blocked by first player'), None]
    report = {'request_id': 'request-1', 'players': [1, 2], 'winner_id': 1,
              'is_tie': outcome == 'tie', 'forfeit': outcome == 'timeout',
              'breakdown': {'1': {'card_id': 'alpha', 'card_name': 'Alpha'}}}

    asyncio.run(handler._announce_quick_result(context, report))

    handler._edit_request_panel.assert_not_awaited()
    assert [call.kwargs['chat_id'] for call in context.bot.send_message.await_args_list] == [1, 2]
    if outcome in ('tie', 'timeout', 'custom'):
        handler._send_round_winner_card_media.assert_not_awaited()
    else:
        assert handler._send_round_winner_card_media.await_count == 2
    for call in context.bot.send_message.await_args_list:
        assert call.kwargs['reply_markup'].inline_keyboard[0][0].callback_data == 'gm_report_request-1'
        if outcome == 'tie':
            assert call.kwargs['text'] == '🤝 نبرد Quick مساوی شد.'
        elif outcome == 'timeout':
            assert call.kwargs['text'] == '⏳ وقت انتخاب تموم شد.'
        else:
            assert call.kwargs['text'] == '💬 «آماده بودم!»'


def test_quick_group_details_are_delivered_privately_to_clicking_player():
    handler = GameModeHandlersMixin()
    report = {
        "request_id": "request-1",
        "mode": "quick",
        "players": [1, 2],
        "winner_id": 1,
        "initial_arena": "city",
        "arena": "city",
        "breakdown": {
            "1": {
                "card_name": "Alpha",
                "selected_stat": "power",
                "base_value": 80,
                "final_value": 90,
                "ability_used": "skip",
                "passive": None,
            }
        },
    }
    handler.modes = SimpleNamespace(
        get_report=Mock(return_value=report),
        get_request=Mock(
            return_value={"source": "group_challenge", "origin_chat_id": -100123}
        ),
        _arena=Mock(
            return_value={
                "id": "city",
                "name": "شهر",
                "emoji": "🏙️",
                "effects": [],
                "disabled_stats": [],
                "abilities_enabled": True,
                "passives_enabled": True,
            }
        ),
    )
    handler.db = SimpleNamespace(
        get_or_create_player=Mock(return_value=SimpleNamespace(first_name="Ali"))
    )
    query = SimpleNamespace(
        data="gm_report_request-1",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    asyncio.run(
        handler.game_report_handler(SimpleNamespace(callback_query=query), context)
    )

    assert context.bot.send_message.await_args.kwargs["chat_id"] == 1
    text = context.bot.send_message.await_args.kwargs['text']
    assert 'عدد پایه: 80 → نهایی: 90' in text  # Older single-stat reports remain readable.
    assert 'زمین:' not in text


def test_quick_report_explains_both_components_and_effects():
    handler = GameModeHandlersMixin()
    arena_snapshot = {"id": "desert", "name": "بیابان", "emoji": "🏜️",
                      "effects": [], "disabled_stats": [], "abilities_enabled": True,
                      "passives_enabled": True}
    report = {
        "request_id": "sum-report", "mode": "quick", "players": [1, 2],
        'winner_id': 1, 'is_tie': False,
        'rewards': {'1': {'xp': 10, 'score': 1}, '2': {'xp': 1, 'score': 0}},
        "initial_arena": "desert", "arena": "desert",
        "initial_arena_data": arena_snapshot, "arena_data": arena_snapshot,
        "breakdown": {
            "1": {
                "card_name": "Alpha", "card_rarity": "epic", "selected_stat": "power", "opponent_selected_stat": "iq",
                "scored_stats": ["power", "iq"], "base_components": [90, 40],
                "final_components": [93, 40], "base_value": 130, "final_value": 133,
                "arena_effects": [{"card_type": "power", "stat": "power", "delta": 2}],
                "passive": {"name": "Desert strength", "stat": "power", "delta": 3},
                "opponent_ability_effect": {"ability": "weaken_power", "stat": "power", "delta": -2},
                "ability_used": "skip",
            },
        },
    }
    handler.modes = SimpleNamespace(
        get_report=Mock(return_value=report), get_request=Mock(return_value=None),
        _arena=Mock(side_effect=AssertionError("The stored arena snapshot must be used")),
    )
    handler.db = SimpleNamespace(get_or_create_player=Mock(return_value=SimpleNamespace(first_name="Ali")))
    query = SimpleNamespace(data="gm_report_sum-report", from_user=SimpleNamespace(id=1), answer=AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    asyncio.run(handler.game_report_handler(SimpleNamespace(callback_query=query), context))
    raw_text = context.bot.send_message.await_args.kwargs["text"]
    assert '\u2066' in raw_text and '\u2068Ali\u2069' in raw_text
    text = _readable_text(raw_text)
    assert text.startswith('📋 جزئیات بازی Quick\n🏆 Ali برنده شد')
    assert 'Alpha (Epic)' in text
    assert '90 → 93' in text and '40 → 40' in text
    assert "امتیاز نهایی: 93 + 40 = 133" in text
    assert 'ابیلیتی حریف' in text
    assert "Desert strength" in text
    assert '🎁 +10 XP · +1 Score' in text
    assert '🎁 +1 XP · +0 Score' in text
    assert '🏜️' not in text and 'امتیاز = جمع' not in text
    assert 'جمع پایه' not in text and 'Ability: skip' not in text
    assert 'فعال نشد' not in text and 'دو بار' not in text


@pytest.mark.parametrize('outcome', ['tie', 'forfeit_win', 'forfeit_both'])
def test_quick_private_details_include_non_win_results_and_rewards(outcome):
    handler = GameModeHandlersMixin()
    forfeit = outcome.startswith('forfeit')
    arena = {'id': 'city', 'name': 'شهر', 'emoji': '🏙️', 'effects': []}
    report = {'request_id': 'finished', 'mode': 'quick', 'players': [1, 2],
              'winner_id': 1 if outcome == 'forfeit_win' else None,
              'is_tie': outcome != 'forfeit_win', 'forfeit': forfeit,
              'loser_ids': [2] if outcome == 'forfeit_win' else [1, 2],
              'initial_arena_data': arena, 'arena_data': arena, 'breakdown': {},
              'rewards': {'1': {'xp': 3, 'score': 0}, '2': {'xp': 3, 'score': 0}}}
    handler.modes = SimpleNamespace(get_report=Mock(return_value=report))
    handler.db = SimpleNamespace(get_or_create_player=Mock(side_effect=lambda uid: SimpleNamespace(first_name={1: 'MH', 2: 'ßoozad'}[uid])))
    query = SimpleNamespace(data='gm_report_finished', from_user=SimpleNamespace(id=2), answer=AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(handler.game_report_handler(SimpleNamespace(callback_query=query), context))
    sent = context.bot.send_message.await_args.kwargs
    assert sent['chat_id'] == 2
    text = _readable_text(sent['text'])
    expected = 'MH برنده شد' if outcome == 'forfeit_win' else 'بدون برنده' if forfeit else 'مساوی شد!'
    assert expected in text
    if forfeit:
        assert 'انتخاب' in sent['text'] and 'ßoozad' in sent['text']
    assert text.count('🎁 +3 XP · +0 Score') == 2


def test_quick_details_keep_changed_arena_duplicate_stat_and_friendly_cost_private():
    handler = GameModeHandlersMixin()
    initial = {'id': 'desert', 'name': 'بیابان', 'emoji': '🏜️', 'effects': []}
    arena = {'id': 'city', 'name': 'شهر', 'emoji': '🏙️', 'effects': [], 'disabled_stats': ['iq']}
    report = {'request_id': 'friendly', 'mode': 'quick', 'players': [1, 2], 'winner_id': 1,
              'variant': 'friendly', 'initial_arena_data': initial, 'arena_data': arena,
              'breakdown': {'1': {'card_name': 'Alpha', 'scored_stats': ['power', 'power'],
                  'base_components': [80, 80], 'final_components': [78, 78], 'final_value': 156,
                  'ability_used': 'reveal_opponent'}},
              'rewards': {'1': {'xp': 0, 'score': 0}, '2': {'xp': 0, 'score': 0, 'hearts_lost': 1}}}
    handler.modes = SimpleNamespace(get_report=Mock(return_value=report), _arena=Mock(side_effect=AssertionError('use snapshot')))
    handler.db = SimpleNamespace(get_or_create_player=Mock(side_effect=lambda uid: SimpleNamespace(first_name=f'P{uid}')))
    query = SimpleNamespace(data='gm_report_friendly', from_user=SimpleNamespace(id=1), answer=AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(handler.game_report_handler(SimpleNamespace(callback_query=query), context))
    text = _readable_text(context.bot.send_message.await_args.kwargs['text'])
    assert '🏜️' not in text and '🏙️' not in text
    assert 'غیرفعال:' not in text and 'دو بار' not in text
    assert '78 + 78 = 156' in text
    assert '👁 مشاهده کارت حریف' in text and 'reveal_opponent' not in text
    assert 'دوستانه · بدون XP، Score و Coin' in text and '-1 ❤️' in text


def test_quick_details_are_not_sent_to_a_nonparticipant():
    handler = GameModeHandlersMixin()
    handler.modes = SimpleNamespace(get_report=Mock(return_value={'players': [1, 2], 'mode': 'quick'}))
    query = SimpleNamespace(data='gm_report_private', from_user=SimpleNamespace(id=3), answer=AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(handler.game_report_handler(SimpleNamespace(callback_query=query), context))
    context.bot.send_message.assert_not_awaited()
    assert query.answer.await_args.kwargs['show_alert'] is True


def test_easy_lobby_waits_three_minutes_before_auto_start():
    handler = GameModeHandlersMixin()
    handler.db = SimpleNamespace(get_or_create_player=Mock(return_value=SimpleNamespace(first_name='MH')))
    handler.modes = SimpleNamespace(
        get_state=Mock(return_value={"players": [1], "rounds": 5})
    )

    text = handler._easy_lobby_text("request-1")

    assert EASY_LOBBY_TTL_SECONDS == 180
    assert "۳ دقیقه" in text
    assert '\u2068MH\u2069' in text
    assert "۳۰ ثانیه" not in text


def test_easy_completed_selection_cancels_round_timer_and_advances_immediately():
    handler = GameModeHandlersMixin()
    handler.modes = SimpleNamespace(
        get_state=Mock(return_value={"current_round": 1, "phase": "selection"}),
        resolve_easy_round=Mock(
            return_value={
                "round": {
                    "round": 1,
                    "entries": [
                        {
                            "user_id": 1,
                            "points": 3,
                            "card_name": "Alpha",
                        }
                    ],
                },
                "completed": False,
                "report": None,
                "state": {"current_round": 2},
            }
        ),
        get_request=Mock(return_value={"origin_chat_id": -100123}),
    )
    handler.db = SimpleNamespace(
        get_or_create_player=Mock(return_value=SimpleNamespace(first_name="Ali"))
    )
    handler._send_easy_question = AsyncMock()
    timer_job = SimpleNamespace(schedule_removal=Mock())
    job_queue = SimpleNamespace(
        get_jobs_by_name=Mock(return_value=(timer_job,))
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(send_message=AsyncMock()),
        job_queue=job_queue,
    )

    asyncio.run(handler._resolve_and_announce_easy(context, "request-1"))

    job_queue.get_jobs_by_name.assert_called_once_with(
        "gm-easy-round-request-1-1"
    )
    timer_job.schedule_removal.assert_called_once_with()
    handler._send_easy_question.assert_awaited_once_with(
        context,
        "request-1",
        {"current_round": 2},
        previous_round={
            "round": 1,
            "entries": [
                {
                    "user_id": 1,
                    "points": 3,
                    "card_name": "Alpha",
                }
            ],
        },
    )


def test_easy_round_reuses_main_panel_and_replaces_reply_prompt():
    handler = GameModeHandlersMixin()
    request = {
        "request_id": "request-1",
        "origin_chat_id": -100123,
        "origin_message_id": 77,
    }
    handler.modes = SimpleNamespace(get_request=Mock(return_value=request))
    handler.db = SimpleNamespace(
        get_or_create_player=Mock(return_value=SimpleNamespace(first_name="Ali"))
    )
    handler._edit_request_panel = AsyncMock()
    handler._schedule_mode_job = Mock()
    old_prompt = {"chat_id": -100123, "message_id": 88}
    context = SimpleNamespace(
        bot_data={handler._easy_prompt_key("request-1"): old_prompt},
        bot=SimpleNamespace(
            delete_message=AsyncMock(),
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
        ),
    )
    state = {
        "current_round": 2,
        "rounds": 5,
        "scores": {"1": 3},
        "question": {"text": "بامزه‌ترین شخصیت کیست؟"},
    }
    previous_round = {
        "round": 1,
        "entries": [
            {"user_id": 1, "points": 3, "card_name": "Alpha"}
        ],
    }

    asyncio.run(
        handler._send_easy_question(
            context,
            "request-1",
            state,
            previous_round=previous_round,
        )
    )

    context.bot.delete_message.assert_awaited_once_with(
        chat_id=-100123, message_id=88
    )
    panel_text = handler._edit_request_panel.await_args.args[2]
    assert "راند 2 از 5" in panel_text
    assert "نتیجه راند 1" in panel_text
    assert "بامزه‌ترین شخصیت کیست؟" not in panel_text
    assert "\u2068Ali: 3\u2069" in panel_text
    assert "\u2068Alpha\u2069" in panel_text
    prompt = context.bot.send_message.await_args.kwargs
    assert prompt["reply_to_message_id"] == 77
    assert "🎯 راند 2\nبامزه‌ترین شخصیت کیست؟" in prompt["text"]
    assert '۳۰ ثانیه' in prompt['text']
    assert prompt["reply_markup"].inline_keyboard[0][0].switch_inline_query_current_chat == (
        "easy request-1"
    )
    assert context.bot_data[handler._easy_prompt_key("request-1")] == {
        "chat_id": -100123,
        "message_id": 99,
    }


def test_easy_final_result_edits_main_panel_and_deletes_prompt():
    handler = GameModeHandlersMixin()
    request = {
        "request_id": "request-1",
        "origin_chat_id": -100123,
        "origin_message_id": 77,
    }
    handler.modes = SimpleNamespace(
        get_state=Mock(return_value={"current_round": 3}),
        resolve_easy_round=Mock(
            return_value={
                "round": {"round": 3, "entries": []},
                "completed": True,
                "state": {"phase": "completed"},
                "report": {
                    "scores": {"1": 7, "2": 4},
                    "winner_ids": [1],
                },
            }
        ),
        get_request=Mock(return_value=request),
    )
    handler.db = SimpleNamespace(
        get_or_create_player=Mock(
            side_effect=lambda user_id: SimpleNamespace(
                first_name="Ali" if user_id == 1 else "Reza"
            )
        )
    )
    handler._edit_request_panel = AsyncMock()
    handler._cancel_mode_job = Mock()
    context = SimpleNamespace(
        bot_data={
            handler._easy_prompt_key("request-1"): {
                "chat_id": -100123,
                "message_id": 99,
            }
        },
        bot=SimpleNamespace(delete_message=AsyncMock(), send_message=AsyncMock()),
    )

    with patch('bot.handlers.easy_victory.announce', new_callable=AsyncMock) as announce:
        asyncio.run(handler._resolve_and_announce_easy(context, "request-1"))
        announce.assert_awaited_once_with(handler, context, request, handler.modes.resolve_easy_round.return_value['report'])

    context.bot.delete_message.assert_awaited_once_with(
        chat_id=-100123, message_id=99
    )
    final_text = handler._edit_request_panel.await_args.args[2]
    assert "پایان Easy Mode" in final_text
    assert "Ali: 7" in final_text
    assert "🥇 \u2068Ali: 7\u2069" in final_text
    assert "🥈 \u2068Reza: 4\u2069" in final_text
    assert "برنده:" not in final_text
    context.bot.send_message.assert_not_awaited()


def test_private_deck_picker_displays_one_minute_and_tracks_panel():
    handler = PvPHandlersMixin()
    card = SimpleNamespace(
        name="Alpha",
        rarity=SimpleNamespace(value="normal"),
    )
    valid_decks = [
        {"deck_id": "deck-1", "deck_name": "Main", "cards": [card]}
    ]
    handler.db = SimpleNamespace()
    context = SimpleNamespace(
        bot_data={},
        bot=SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=55))
        ),
    )

    with patch("bot.handlers.pvp.DeckSystem") as deck_system:
        deck_system.return_value.get_valid_decks.return_value = valid_decks
        asyncio.run(handler._send_deck_selection(context, "fight-1", 1))

    sent = context.bot.send_message.await_args.kwargs
    assert sent["reply_markup"].inline_keyboard[-1][0].text == "⏱ مهلت: ۱ دقیقه"
    assert context.bot_data["deck_selection_panel_fight-1_1"] == 55


def test_normal_deck_match_schedules_real_one_minute_timeout():
    handler = GameModeHandlersMixin()
    handler.db = SimpleNamespace(
        create_fight=Mock(return_value="fight-1"),
        update_fight=Mock(return_value=True),
    )
    handler._edit_request_panel = AsyncMock()
    handler._send_deck_selection_panels = AsyncMock()
    handler._schedule_mode_job = Mock()
    context = SimpleNamespace(bot_data={})
    request = {
        "request_id": "request-1",
        "creator_id": 1,
        "opponent_id": 2,
        "origin_chat_id": -100123,
        "variant": "normal",
    }

    with patch("bot.handlers.game_modes.DeckSystem") as deck_system:
        deck_system.return_value.get_valid_decks.return_value = [SimpleNamespace()]
        asyncio.run(handler._launch_deck_match(context, request))

    assert DECK_SELECTION_TTL_SECONDS == 60
    expires_at = handler.db.update_fight.call_args.kwargs["expires_at"]
    remaining = datetime.fromisoformat(expires_at) - datetime.now()
    assert 55 <= remaining.total_seconds() <= 60
    scheduled = handler._schedule_mode_job.call_args.args
    assert scheduled[2] == 60
    assert scheduled[4] == "gm-deck-selection-fight-1"


def test_deck_selection_timeout_cancels_fight_and_closes_private_panels():
    handler = GameModeHandlersMixin()
    handler.db = SimpleNamespace(
        get_battle_deck_state=Mock(
            return_value={
                "challenger_deck_selected": True,
                "opponent_deck_selected": False,
            }
        ),
        get_fight_by_id=Mock(
            return_value=SimpleNamespace(status=FightStatus.WAITING_FOR_OPPONENT)
        ),
        update_fight=Mock(return_value=True),
    )
    handler.modes = SimpleNamespace(
        get_request=Mock(return_value={"origin_chat_id": -100123})
    )
    handler._edit_request_panel = AsyncMock()
    context = SimpleNamespace(
        job=SimpleNamespace(
            data={
                "fight_id": "fight-1",
                "request_id": "request-1",
                "player_ids": [1, 2],
            }
        ),
        bot_data={
            "deck_selection_panel_fight-1_1": 51,
            "deck_selection_panel_fight-1_2": 52,
        },
        bot=SimpleNamespace(edit_message_text=AsyncMock()),
    )

    asyncio.run(handler.deck_selection_timeout_job(context))

    handler.db.update_fight.assert_called_once_with(
        "fight-1", status=FightStatus.CANCELLED
    )
    assert context.bot.edit_message_text.await_count == 2
    assert not any(
        key.startswith("deck_selection_panel_fight-1")
        for key in context.bot_data
    )
