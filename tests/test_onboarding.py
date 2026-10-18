import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import CallbackQueryHandler

from bot.main import TelegramCardBot
from bot import onboarding
from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import GameModeSystem
from systems.starter_cards_system import grant_starter_cards, grant_starter_pack, starter_status


@pytest.fixture
def scene(tmp_path):
    db = DatabaseManager(str(tmp_path / 'welcome.db'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    for cid, name in [('wick', 'John Wick'), ('heis', 'Heisenberg'), ('rehi', 'Rehi')]:
        db.add_card(Card(cid, name, CardRarity.NORMAL, 10, 20, 30, 40, [], biography='نباید در شروع بیاد'))
        db.set_card_variant_media_file_id(cid, 'normal', cid + '-normal', 'sticker')
        db.set_card_variant_media_file_id(cid, 'legend', cid + '-legend', 'sticker')
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db, bot.game, bot.config = db, GameLogic(db), {}
    bot.modes = GameModeSystem(db)
    bot.is_user_in_channel = AsyncMock(return_value=True)
    bot.send_channel_join_message = AsyncMock()
    user = SimpleNamespace(id=1, first_name='Tester_*', username='tester')
    message = SimpleNamespace(reply_text=AsyncMock(), chat=SimpleNamespace(id=1, type='private'))
    query = SimpleNamespace(from_user=user, message=message, data='starter_receive', answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(effective_user=user, effective_chat=message.chat, effective_message=message,
                             message=message, callback_query=None)
    events = []

    async def sticker(*, chat_id, sticker):
        events.append(('sticker', sticker))

    async def text(*, chat_id, text, **kwargs):
        events.append(('text', text))

    context = SimpleNamespace(args=[], user_data={}, bot_data={}, bot=SimpleNamespace(
        send_sticker=AsyncMock(side_effect=sticker), send_message=AsyncMock(side_effect=text), username='TestBot'))
    return bot, update, context, events, query


def click(update, query):
    update.callback_query = query
    update.message = None


def counts(db):
    with sqlite3.connect(db.db_path) as conn:
        return conn.execute('SELECT card_id,rarity,quantity FROM player_card_stacks WHERE user_id=1 ORDER BY card_id').fetchall()


def test_first_start_offers_pack_without_granting_or_claiming_then_three_stickers(scene):
    bot, update, context, events, query = scene
    bot.game.claim_daily_card_with_ability = Mock(side_effect=AssertionError('daily claim must be explicit'))
    asyncio.run(bot.start_command(update, context))
    assert counts(bot.db) == [] and bot.db.get_player_decks(1) == []
    welcome = update.message.reply_text.await_args
    assert welcome.args[0] == onboarding.WELCOME
    assert welcome.kwargs['reply_markup'].inline_keyboard[0][0].callback_data == 'starter_receive'
    assert len(welcome.kwargs['reply_markup'].inline_keyboard) == 1
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert events[:3] == [('sticker', 'wick-normal'), ('sticker', 'heis-normal'), ('sticker', 'rehi-normal')]
    assert len(events) == 4 and '/claim' in events[-1][1]
    assert all(word not in events[-1][1] for word in ['قدرت', 'بیوگرافی', 'XP:', 'John Wick'])
    assert counts(bot.db) == [('heis', 'normal', 1), ('rehi', 'normal', 1), ('wick', 'normal', 1)]
    assert len(bot.db.get_player_decks(1)) == 1
    assert onboarding.delivery(bot.db, 1)['done']
    bot.game.claim_daily_card_with_ability.assert_not_called()
    before = list(events)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert events == before and 'قبلاً' in query.edit_message_text.await_args.args[0]
    # Returning /start opens the existing full main menu.
    update.message, update.callback_query = query.message, None
    asyncio.run(bot.start_command(update, context))
    rows = update.message.reply_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert any(b.callback_data == 'deck_menu' for row in rows for b in row)
    assert all(b.callback_data != 'starter_receive' for row in rows for b in row)


@pytest.mark.parametrize('entry', ['start_game', 'membership'])
def test_channel_and_existing_start_button_use_same_new_welcome(scene, entry):
    bot, update, context, events, query = scene
    click(update, query)
    asyncio.run(bot.start_game_handler(update, context) if entry == 'start_game' else bot.check_membership_handler(update, context))
    assert query.edit_message_text.await_args.args[0] == onboarding.WELCOME
    assert counts(bot.db) == [] and events == []


def test_nonmember_gets_no_cards_until_membership_and_explicit_receive(scene):
    bot, update, context, events, query = scene
    bot.is_user_in_channel.return_value = False
    asyncio.run(bot.start_command(update, context))
    bot.send_channel_join_message.assert_awaited_once()
    assert not update.message.reply_text.await_count and counts(bot.db) == []
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert counts(bot.db) == [] and events == []
    bot.is_user_in_channel.return_value = True
    asyncio.run(bot.check_membership_handler(update, context))
    assert query.edit_message_text.await_args.args[0] == onboarding.WELCOME
    asyncio.run(bot.starter_receive_handler(update, context))
    assert len(events) == 4


def test_group_start_or_receive_never_grants_pack(scene):
    bot, update, context, events, query = scene
    update.effective_chat.type = 'supergroup'
    asyncio.run(bot.start_command(update, context))
    assert counts(bot.db) == []
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert query.answer.await_args.kwargs['show_alert'] and counts(bot.db) == [] and events == []


@pytest.mark.parametrize('v2', [False, True])
def test_starter_receipt_survives_empty_inventory_and_concurrent_clicks(scene, v2):
    bot, _, _, _, _ = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json=? WHERE key='progression_v2_enabled'", ('true' if v2 else 'false',))
    bot.db.get_or_create_player(1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: grant_starter_pack(bot.db, 1), range(2)))
    assert all(r['ok'] for r in results) and sum(not r.get('replayed') for r in results) == 1
    assert len(counts(bot.db)) == 3
    with sqlite3.connect(bot.db.db_path) as conn:
        for cid in ['wick', 'heis', 'rehi']:
            CardInventorySystem.consume_in(conn, 1, cid, 'normal')
            CardInventorySystem.reconcile_active_in(conn, 1, cid)
    assert counts(bot.db) == [] and grant_starter_cards(bot.db, 1) == []
    assert grant_starter_pack(bot.db, 1)['replayed'] and counts(bot.db) == []


def test_failed_media_resumes_remaining_stickers_after_reopen_without_regrant(scene):
    bot, update, context, events, query = scene
    asyncio.run(bot.start_command(update, context))
    click(update, query)
    original = context.bot.send_sticker.side_effect

    async def failing(*, chat_id, sticker):
        if sticker == 'heis-normal':
            raise RuntimeError('offline missing media')
        return await original(chat_id=chat_id, sticker=sticker)

    context.bot.send_sticker.side_effect = failing
    # No image fallback for the card whose Telegram delivery failed.
    from unittest.mock import patch
    with patch('bot.battle_visual_delivery.card_art', new=AsyncMock(return_value=None)):
        asyncio.run(bot.starter_receive_handler(update, context))
    assert events == [('sticker', 'wick-normal')]
    assert onboarding.delivery(bot.db, 1)['sent_ids'] == ['wick']
    before = counts(bot.db)
    bot.db = DatabaseManager(bot.db.db_path)
    context.bot.send_sticker.side_effect = original
    asyncio.run(bot.starter_receive_handler(update, context))
    assert events[:3] == [('sticker', 'wick-normal'), ('sticker', 'heis-normal'), ('sticker', 'rehi-normal')]
    assert counts(bot.db) == before and len(bot.db.get_player_decks(1)) == 1


def test_daily_claim_before_receiving_does_not_remove_the_offered_pack(scene):
    bot, update, context, _, query = scene
    asyncio.run(bot.start_command(update, context))
    bot.db.add_card_to_player(1, 'wick')  # simulate a separate earlier daily award
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert CardInventorySystem(bot.db).counts(1, 'wick') == {'normal': 2}
    assert len(counts(bot.db)) == 3 and onboarding.delivery(bot.db, 1)['done']


def test_miniapp_and_bot_share_one_pack_and_display_original_normal_forms(scene):
    bot, update, context, events, query = scene
    bot.db.get_or_create_player(1)
    assert len(grant_starter_cards(bot.db, 1)) == 3  # same shared Mini App entry point
    before = counts(bot.db)
    with sqlite3.connect(bot.db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 1, 'wick', 'legend')
        conn.execute("UPDATE player_cards SET rarity_override='legend' WHERE user_id=1 AND card_id='wick'")
    asyncio.run(bot.start_command(update, context))
    assert update.message.reply_text.await_args.args[0] == onboarding.WELCOME
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert events[0] == ('sticker', 'wick-normal')
    assert CardInventorySystem(bot.db).counts(1, 'wick') == {'normal': 1, 'legend': 1}


def test_existing_accounts_keep_cutover_freeze_and_existing_cards(scene):
    bot, update, context, events, query = scene
    bot.db.get_or_create_player(1)
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE progression_capacities SET legacy=1 WHERE user_id=1')
    asyncio.run(bot.start_command(update, context))
    assert 'starter_receive' not in str(update.message.reply_text.await_args.kwargs['reply_markup'])
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert counts(bot.db) == [] and events == [] and starter_status(bot.db, 1)['reason'] == 'legacy'


def test_missing_catalog_is_atomic_and_receive_can_retry_when_fixed(scene):
    bot, update, context, events, query = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("DELETE FROM card_variants WHERE card_id='rehi'")
        conn.execute("DELETE FROM cards WHERE card_id='rehi'")
    asyncio.run(bot.start_command(update, context))
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert counts(bot.db) == [] and bot.db.get_player_decks(1) == [] and events == []
    bot.db.add_card(Card('rehi', 'Rehi', CardRarity.NORMAL, 10, 20, 30, 40, []))
    bot.db.set_card_variant_media_file_id('rehi', 'normal', 'rehi-normal', 'sticker')
    asyncio.run(bot.starter_receive_handler(update, context))
    assert len(events) == 4


@pytest.mark.parametrize('wait_for_membership', [False, True])
def test_invite_is_retained_until_starters_are_received_then_accepted(scene, wait_for_membership):
    bot, update, context, events, query = scene
    bot.db.get_or_create_player(2)
    bot.db.add_card_to_player(2, 'wick')
    invite = bot.modes.create_invite(2, 'quick', 'normal', 2)
    context.args = ['gm_' + invite['invite_token']]
    bot._launch_mode_match = AsyncMock()
    bot._edit_request_panel = AsyncMock()
    bot.is_user_in_channel.return_value = not wait_for_membership
    asyncio.run(bot.start_command(update, context))
    click(update, query)
    if wait_for_membership:
        bot.is_user_in_channel.return_value = True
        context.args = []  # Telegram callback carries no original /start payload.
        asyncio.run(bot.check_membership_handler(update, context))
    assert bot.modes.get_request(invite['request_id'])['status'] == 'waiting'
    asyncio.run(bot.starter_receive_handler(update, context))
    assert bot.modes.get_request(invite['request_id'])['opponent_id'] == 1
    bot._launch_mode_match.assert_awaited_once()
    assert [e[0] for e in events] == ['sticker', 'sticker', 'sticker', 'text']
    assert 'onboarding_invite' not in context.user_data


def test_receive_callback_is_registered_once(scene):
    bot, _, _, _, _ = scene
    app = Mock()
    bot.setup_handlers(app)
    matches = [c.args[0] for c in app.add_handler.call_args_list if isinstance(c.args[0], CallbackQueryHandler)
               and c.args[0].pattern and c.args[0].pattern.match('starter_receive')]
    assert len(matches) == 1


def test_failed_deck_insert_rolls_back_cards_and_receipt_before_retry(scene):
    bot, _, _, _, _ = scene
    bot.db.get_or_create_player(1)
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("""CREATE TRIGGER fail_starter_deck BEFORE INSERT ON player_decks
            WHEN NEW.player_id=1 BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        grant_starter_pack(bot.db, 1)
    assert counts(bot.db) == [] and starter_status(bot.db, 1).get('pending')
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM reward_ledger WHERE user_id=1 AND operation_id='starter_cards'").fetchone()[0] == 0
        conn.execute('DROP TRIGGER fail_starter_deck')
    assert grant_starter_pack(bot.db, 1)['ok'] and len(counts(bot.db)) == 3


def test_concurrent_receive_delivers_one_sticker_sequence_and_releases_guard(scene):
    bot, update, context, events, query = scene
    asyncio.run(bot.start_command(update, context))
    click(update, query)
    original = context.bot.send_sticker.side_effect

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(*, chat_id, sticker):
            if sticker == 'wick-normal':
                entered.set()
                await release.wait()
            await original(chat_id=chat_id, sticker=sticker)

        context.bot.send_sticker.side_effect = delayed
        first = asyncio.create_task(bot.starter_receive_handler(update, context))
        await entered.wait()
        await bot.starter_receive_handler(update, context)
        release.set()
        await first

    asyncio.run(scenario())
    assert len(events) == 4 and len(counts(bot.db)) == 3
    assert context.bot_data['_starter_deliveries'] == set()


def test_instruction_send_failure_retries_only_text_and_keeps_main_menu_access(scene):
    bot, update, context, events, query = scene
    asyncio.run(bot.start_command(update, context))
    click(update, query)
    original = context.bot.send_message.side_effect
    context.bot.send_message.side_effect = RuntimeError('synthetic transport failure')
    asyncio.run(bot.starter_receive_handler(update, context))
    assert len(events) == 3 and not onboarding.delivery(bot.db, 1)['done']
    rows = query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert any(b.callback_data == 'back_to_main' for row in rows for b in row)
    context.bot.send_message.side_effect = original
    asyncio.run(bot.starter_receive_handler(update, context))
    assert len(events) == 4 and onboarding.delivery(bot.db, 1)['done'] and len(counts(bot.db)) == 3
