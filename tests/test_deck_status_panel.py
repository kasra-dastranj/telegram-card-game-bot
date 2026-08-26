import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram import InlineQueryResultArticle

from bot.handlers.battle import (
    BattleHandlersMixin,
    DECK_TURN_TIMEOUT_SECONDS,
)
from core.database import DatabaseManager


def test_battle_deck_state_exposes_live_score_and_arena(tmp_path):
    db = DatabaseManager(str(tmp_path / "deck-status.sqlite"))
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        """INSERT INTO battle_states
           (fight_id, challenger_id, opponent_id, challenger_card_id, opponent_card_id,
            arena, current_round, challenger_rounds_won, opponent_rounds_won,
            challenger_used_stats, opponent_used_stats,
            challenger_current_stats, opponent_current_stats, status, created_at,
            challenger_deck_cards, opponent_deck_cards,
            challenger_remaining_cards, opponent_remaining_cards,
            challenger_deck_selected, opponent_deck_selected)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "fight-1", 1, 2, "a", "b", "thinking_room", 2, 1, 0,
            "[]", "[]", "{}", "{}", "round_2", "2026-08-22T00:00:00",
            '["a","c","e"]', '["b","d","f"]', '["c","e"]', '["d","f"]', 1, 1,
        ),
    )
    conn.commit()
    conn.close()

    state = db.get_battle_deck_state("fight-1")

    assert state["arena"] == "thinking_room"
    assert state["current_round"] == 2
    assert state["challenger_rounds_won"] == 1
    assert state["opponent_rounds_won"] == 0
    assert state["status"] == "round_2"


def test_deck_status_message_is_created_once_then_edited():
    handler = BattleHandlersMixin()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        edit_message_text=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot, bot_data={})

    asyncio.run(handler._upsert_deck_status_message(context, "fight-1", -100, "شروع"))
    asyncio.run(handler._upsert_deck_status_message(context, "fight-1", -100, "راند دوم"))

    assert bot.send_message.await_count == 1
    bot.edit_message_text.assert_awaited_once_with(
        chat_id=-100,
        message_id=77,
        text="راند دوم",
        reply_markup=None,
    )


def test_deck_final_status_never_creates_a_duplicate_when_edit_fails():
    handler = BattleHandlersMixin()
    bot = SimpleNamespace(
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(side_effect=RuntimeError("temporary edit failure")),
    )
    context = SimpleNamespace(
        bot=bot,
        bot_data={
            "deck_fight-1_status_message": {"chat_id": -100, "message_id": 77}
        },
    )

    result = asyncio.run(
        handler._upsert_deck_status_message(
            context,
            "fight-1",
            -100,
            "نتیجه نهایی",
            allow_create=False,
        )
    )

    assert result == 77
    bot.send_message.assert_not_awaited()
    assert context.bot_data["deck_fight-1_status_message"]["message_id"] == 77


def test_deck_status_edits_the_shared_inline_message_in_peer_private_chat():
    handler = BattleHandlersMixin()
    bot = SimpleNamespace(
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    context = SimpleNamespace(
        bot=bot,
        bot_data={"deck_fight-1_inline_message_id": "inline-77"},
    )

    asyncio.run(handler._upsert_deck_status_message(context, "fight-1", 101, "راند اول"))

    bot.edit_message_text.assert_awaited_once_with(
        inline_message_id="inline-77",
        text="راند اول",
        reply_markup=None,
    )
    bot.send_message.assert_not_awaited()


def test_deck_round_panel_shows_score_arena_rule_and_uses_sixty_seconds():
    handler = BattleHandlersMixin()
    fight = SimpleNamespace(chat_id=-100, challenger_id=1, opponent_id=2)
    players = {
        1: SimpleNamespace(first_name="Blue", username=None),
        2: SimpleNamespace(first_name="Red", username=None),
    }
    handler.db = SimpleNamespace(
        get_fight_by_id=Mock(return_value=fight),
        get_or_create_player=Mock(side_effect=lambda user_id: players[user_id]),
        get_battle_deck_state=Mock(
            return_value={"challenger_rounds_won": 0, "opponent_rounds_won": 0}
        ),
    )
    handler._upsert_deck_status_message = AsyncMock(return_value=77)
    job_queue = SimpleNamespace(run_once=Mock())
    context = SimpleNamespace(bot_data={}, job_queue=job_queue)

    asyncio.run(
        handler._send_round_card_selection_panel(
            context,
            "fight-1",
            1,
            2,
            ["a", "b", "c"],
            ["d", "e", "f"],
            "power_arena",
            1,
        )
    )

    status_text = handler._upsert_deck_status_message.await_args.args[3]
    assert "📊 🔵 Blue 0 — 0 Red 🔴" in status_text
    assert "🎴 راند 1 از ۳" in status_text
    assert "اول Tierِ Trait زمین" in status_text
    assert "💪 قدرت بیشتر" in status_text
    assert "T1 خدا/هیولا" in status_text
    assert DECK_TURN_TIMEOUT_SECONDS == 60
    assert job_queue.run_once.call_args.args[1] == 60


def test_deck_final_card_is_not_auto_selected_and_requires_manual_confirmation():
    handler = BattleHandlersMixin()
    fight = SimpleNamespace(chat_id=-100, challenger_id=1, opponent_id=2)
    players = {
        1: SimpleNamespace(first_name="Blue", username=None),
        2: SimpleNamespace(first_name="Red", username=None),
    }
    handler.db = SimpleNamespace(
        get_fight_by_id=Mock(return_value=fight),
        get_or_create_player=Mock(side_effect=lambda user_id: players[user_id]),
        get_battle_deck_state=Mock(
            return_value={"challenger_rounds_won": 1, "opponent_rounds_won": 1}
        ),
    )
    handler._upsert_deck_status_message = AsyncMock(return_value=77)
    context = SimpleNamespace(bot_data={}, job_queue=None)

    asyncio.run(
        handler._send_round_card_selection_panel(
            context,
            "fight-1",
            1,
            2,
            ["last-blue"],
            ["last-red"],
            "power_arena",
            3,
        )
    )

    assert "r3_fight-1_challenger_card" not in context.bot_data
    assert "r3_fight-1_opponent_card" not in context.bot_data
    assert context.bot_data["r3_fight-1_expected_role"] == "challenger"
    status_text = handler._upsert_deck_status_message.await_args.args[3]
    markup = handler._upsert_deck_status_message.await_args.args[4]
    assert "کارت آخر را دستی تأیید کنید" in status_text
    assert "پس از انتخاب هر دو بازیکن" in status_text
    assert markup.inline_keyboard[0][0].switch_inline_query_current_chat.startswith(
        "r3pick fight-1 "
    )


def test_deck_final_inline_pick_hides_card_until_both_players_confirm(tmp_path):
    db_path = tmp_path / "deck-final-pick.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE battle_states (
               fight_id TEXT PRIMARY KEY,
               challenger_id INTEGER,
               opponent_id INTEGER,
               challenger_remaining_cards TEXT,
               opponent_remaining_cards TEXT,
               arena TEXT,
               current_round INTEGER,
               status TEXT
           )"""
    )
    conn.execute(
        "INSERT INTO battle_states VALUES (?,?,?,?,?,?,?,?)",
        (
            "final123",
            1,
            2,
            '["secret-blue"]',
            '["secret-red"]',
            "power_arena",
            3,
            "round_3",
        ),
    )
    conn.commit()
    conn.close()

    final_card = SimpleNamespace(card_id="secret-blue", name="Final Secret")
    handler = BattleHandlersMixin()
    handler.db = SimpleNamespace(
        db_path=str(db_path),
        get_card_by_id_for_player=Mock(return_value=final_card),
        get_card_by_id=Mock(return_value=final_card),
    )
    handler._battle_player_name = Mock(return_value="Blue")
    handler._round_card_description = Mock(return_value="قدرت")
    handler._get_inline_card_sticker_file_id = AsyncMock(return_value="sticker-id")
    handler._get_inline_card_photo_file_id = AsyncMock(return_value="photo-id")

    inline_query = SimpleNamespace(
        query=f"r3pick final123 {handler._inline_user_token(1)}",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )
    update = SimpleNamespace(inline_query=inline_query)
    context = SimpleNamespace(
        bot_data={"r3_final123_expected_role": "challenger"},
    )

    asyncio.run(handler.r3_inline_card_query_handler(update, context))

    results = inline_query.answer.await_args.args[0]
    assert len(results) == 1
    assert isinstance(results[0], InlineQueryResultArticle)
    assert results[0].title == "Final Secret"
    assert "Final Secret" not in results[0].input_message_content.message_text
    handler._get_inline_card_sticker_file_id.assert_not_awaited()
    handler._get_inline_card_photo_file_id.assert_not_awaited()
    assert context.bot_data[
        "r3_final123_1_secret-blue_inline_media"
    ] is False
    assert context.bot_data[
        "r3_final123_1_secret-blue_explicit_confirm"
    ] is True


def test_deck_final_chosen_inline_waits_for_explicit_button_confirmation():
    handler = BattleHandlersMixin()
    handler._record_round_card_selection = AsyncMock()
    handler._after_round_card_selected = AsyncMock()
    result_id = handler._inline_card_result_id("final123", 1, "secret-blue")
    update = SimpleNamespace(
        chosen_inline_result=SimpleNamespace(
            result_id=result_id,
            from_user=SimpleNamespace(id=1),
            inline_message_id="inline-blue",
        )
    )
    context = SimpleNamespace(
        bot_data={
            "r3_final123_1_secret-blue_explicit_confirm": True,
        }
    )

    asyncio.run(handler.r3_chosen_inline_card_handler(update, context))

    handler._record_round_card_selection.assert_not_awaited()
    handler._after_round_card_selected.assert_not_awaited()


def test_deck_final_confirm_keeps_inline_message_id_for_delayed_reveal():
    handler = BattleHandlersMixin()
    card = SimpleNamespace(name="Blue Card")
    handler._record_round_card_selection = AsyncMock(
        return_value=(True, card, "challenger")
    )
    handler._after_round_card_selected = AsyncMock()
    callback_data = handler._inline_confirm_callback_data(
        "final123", 1, "secret-blue"
    )
    query = SimpleNamespace(
        data=callback_data,
        from_user=SimpleNamespace(id=1),
        inline_message_id="inline-blue",
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    context = SimpleNamespace(
        bot_data={
            "r3_final123_1_secret-blue_explicit_confirm": True,
            "r3_final123_1_secret-blue_inline_media": False,
        }
    )

    asyncio.run(
        handler.r3_inline_confirm_handler(
            SimpleNamespace(callback_query=query),
            context,
        )
    )

    assert "r3_final123_1_secret-blue_explicit_confirm" not in context.bot_data
    assert (
        context.bot_data[
            "r3_final123_challenger_hidden_inline_message_id"
        ]
        == "inline-blue"
    )
    handler._after_round_card_selected.assert_awaited_once_with(
        context,
        "final123",
        1,
        "challenger",
        card,
    )


def test_private_deck_final_cards_reveal_by_editing_hidden_inline_messages():
    handler = BattleHandlersMixin()
    handler._battle_player_name = Mock(side_effect=["Blue", "Red"])
    handler._get_inline_card_photo_file_id = AsyncMock(
        side_effect=["blue-photo", "red-photo"]
    )
    bot = SimpleNamespace(edit_message_media=AsyncMock(), edit_message_text=AsyncMock())
    context = SimpleNamespace(
        bot=bot,
        bot_data={
            "r3_final123_challenger_hidden_inline_message_id": "inline-blue",
            "r3_final123_opponent_hidden_inline_message_id": "inline-red",
        },
    )
    blue_card = SimpleNamespace(name="Blue Card")
    red_card = SimpleNamespace(name="Red Card")

    asyncio.run(
        handler._reveal_hidden_inline_round_card(
            context, "final123", "challenger", 1, blue_card
        )
    )
    asyncio.run(
        handler._reveal_hidden_inline_round_card(
            context, "final123", "opponent", 2, red_card
        )
    )

    assert bot.edit_message_media.await_count == 2
    first_call = bot.edit_message_media.await_args_list[0].kwargs
    second_call = bot.edit_message_media.await_args_list[1].kwargs
    assert first_call["inline_message_id"] == "inline-blue"
    assert first_call["media"].media == "blue-photo"
    assert "Blue Card" in first_call["media"].caption
    assert second_call["inline_message_id"] == "inline-red"
    assert second_call["media"].media == "red-photo"
    assert "Red Card" in second_call["media"].caption
    assert "r3_final123_challenger_hidden_inline_message_id" not in context.bot_data
    assert "r3_final123_opponent_hidden_inline_message_id" not in context.bot_data


def test_private_deck_final_card_falls_back_to_text_if_media_edit_fails():
    handler = BattleHandlersMixin()
    handler._battle_player_name = Mock(return_value="Blue")
    handler._get_inline_card_photo_file_id = AsyncMock(return_value="blue-photo")
    bot = SimpleNamespace(
        edit_message_media=AsyncMock(side_effect=RuntimeError("media rejected")),
        edit_message_text=AsyncMock(),
    )
    context = SimpleNamespace(
        bot=bot,
        bot_data={
            "r3_final123_challenger_hidden_inline_message_id": "inline-blue",
        },
    )

    asyncio.run(
        handler._reveal_hidden_inline_round_card(
            context,
            "final123",
            "challenger",
            1,
            SimpleNamespace(name="Blue Card"),
        )
    )

    bot.edit_message_text.assert_awaited_once_with(
        inline_message_id="inline-blue",
        text="🎴 Blue: Blue Card",
        reply_markup=None,
    )
