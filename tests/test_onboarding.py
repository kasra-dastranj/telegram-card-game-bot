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
def scene(tmp_path, monkeypatch):
    db = DatabaseManager(str(tmp_path / 'welcome.db'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    for cid, name in [('wick', 'John Wick'), ('heis', 'Heisenberg'), ('rehi', 'Rehi')]:
        db.add_card(Card(cid, name, CardRarity.NORMAL, 10, 20, 30, 40, [], biography='نباید در شروع بیاد'))
        db.set_card_variant_media_file_id(cid, 'normal', cid + '-normal', 'sticker')
        db.set_card_variant_media_file_id(cid, 'legend', cid + '-legend', 'sticker')
    for index in range(12):
        cid = 'extra-' + str(index)
        db.add_card(Card(cid, cid, CardRarity.NORMAL, 5, 5, 5, 5, []))
        db.set_card_variant_media_file_id(cid, 'normal', cid + '-normal', 'sticker')
    monkeypatch.setattr('systems.starter_cards_system.random.sample', lambda pool, size:
        sorted(pool, key=lambda card: ({'wick': 0, 'heis': 1, 'rehi': 2}.get(card.card_id, 3), card.card_id))[:size])
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

    async def sticker(*, chat_id, sticker, **kwargs):
        markup = kwargs['reply_markup']
        assert markup.inline_keyboard[0][0].callback_data == 'card_stats:normal:' + sticker.removesuffix('-normal')
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


def test_start_automatically_grants_ten_and_repeat_start_does_not_claim_or_grant(scene):
    bot, update, context, events, query = scene
    bot.game.claim_daily_card_with_ability = Mock(side_effect=AssertionError('daily claim must be explicit'))
    asyncio.run(bot.start_command(update, context))
    assert len(counts(bot.db)) == 10 and len(bot.db.get_player_decks(1)) == 1
    assert len([e for e in events if e[0] == 'sticker']) == 10
    assert onboarding.delivery(bot.db, 1)['done']
    bot.game.claim_daily_card_with_ability.assert_not_called()
    before = list(events), counts(bot.db)
    asyncio.run(bot.start_command(update, context))
    assert (events, counts(bot.db)) == before
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert (events, counts(bot.db)) == before


@pytest.mark.parametrize('entry', ['start_game', 'membership'])
def test_start_and_membership_buttons_receive_the_same_pack(scene, entry):
    bot, update, context, events, query = scene
    click(update, query)
    asyncio.run(bot.start_game_handler(update, context) if entry == 'start_game' else bot.check_membership_handler(update, context))
    assert len(counts(bot.db)) == 10 and onboarding.delivery(bot.db, 1)['done']


def test_membership_is_required_and_rechecking_delivers_automatically(scene):
    bot, update, context, events, query = scene
    bot.is_user_in_channel.return_value = False
    asyncio.run(bot.start_command(update, context))
    assert counts(bot.db) == [] and events == []
    bot.is_user_in_channel.return_value = True
    click(update, query)
    asyncio.run(bot.check_membership_handler(update, context))
    assert len(counts(bot.db)) == 10


def test_group_start_and_stale_group_receive_do_not_grant(scene):
    bot, update, context, events, query = scene
    update.effective_chat.type = 'supergroup'
    asyncio.run(bot.start_command(update, context))
    click(update, query)
    asyncio.run(bot.starter_receive_handler(update, context))
    assert counts(bot.db) == [] and events == []
    assert query.answer.await_args.kwargs['show_alert']


@pytest.mark.parametrize('v2', [False, True])
def test_concurrent_grants_and_selling_every_card_never_reissue(scene, v2):
    bot, _, _, _, _ = scene
    bot.db.get_or_create_player(1)
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json=? WHERE key='progression_v2_enabled'", ('true' if v2 else 'false',))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: grant_starter_pack(bot.db, 1), range(2)))
    assert all(r['ok'] for r in results) and sum(not r.get('replayed') for r in results) == 1
    assert len(counts(bot.db)) == 10
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('DELETE FROM player_cards WHERE user_id=1')
        conn.execute('DELETE FROM player_card_stacks WHERE user_id=1')
    assert grant_starter_cards(bot.db, 1) == [] and counts(bot.db) == []


def test_failed_sticker_resumes_the_original_draw_on_next_start(scene):
    bot, update, context, events, _ = scene
    original = context.bot.send_sticker.side_effect
    async def fail(*, chat_id, sticker, **kwargs):
        if sticker == 'heis-normal':raise RuntimeError('offline')
        return await original(chat_id=chat_id, sticker=sticker, **kwargs)
    context.bot.send_sticker.side_effect = fail
    from unittest.mock import patch
    with patch('bot.battle_visual_delivery.card_art', new=AsyncMock(return_value=None)):
        asyncio.run(bot.start_command(update, context))
    assert events == [('sticker', 'wick-normal')]
    before = counts(bot.db)
    bot.db = DatabaseManager(bot.db.db_path)
    context.bot.send_sticker.side_effect = original
    asyncio.run(bot.start_command(update, context))
    assert counts(bot.db) == before and onboarding.delivery(bot.db, 1)['done']
    assert len([e for e in events if e[0] == 'sticker']) == 10


def test_old_three_card_receipt_and_delivery_do_not_block_the_new_bonus(scene):
    bot, update, context, events, _ = scene
    bot.db.get_or_create_player(1)
    from systems.reward_ledger import record_in
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE progression_capacities SET legacy=1 WHERE user_id=1')
        for cid in ('wick', 'heis', 'rehi'):CardInventorySystem.grant_in(conn, 1, cid, 'epic')
        record_in(conn, 'starter_cards', 1, 'starter', 'starter_grant', {}, {'ok': True, 'card_ids': ['wick','heis','rehi']}, 1)
        conn.execute("INSERT INTO foundation_settings VALUES('starter_delivery:1','{\"done\":true}')")
    asyncio.run(bot.start_command(update, context))
    assert len(counts(bot.db)) == 13
    assert sum(row[2] for row in counts(bot.db)) == 13
    assert sum(row[1] == 'normal' for row in counts(bot.db)) == 10
    assert all(CardInventorySystem(bot.db).counts(1, cid) == {'epic': 1} for cid in ('wick','heis','rehi'))
    assert onboarding.delivery(bot.db, 1)['done']
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute('SELECT legacy FROM progression_capacities WHERE user_id=1').fetchone()[0] == 1


def test_ten_existing_characters_do_not_qualify_even_after_spending(scene):
    bot, update, context, events, _ = scene
    bot.db.get_or_create_player(1)
    for card in bot.db.get_all_cards()[:10]:bot.db.add_card_to_player(1, card.card_id)
    asyncio.run(bot.start_command(update, context))
    assert events == []
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('DELETE FROM player_cards WHERE user_id=1')
        conn.execute('DELETE FROM player_card_stacks WHERE user_id=1')
    asyncio.run(bot.start_command(update, context))
    assert events == [] and counts(bot.db) == []


def test_miniapp_and_bot_share_the_receipt_without_changing_active_forms(scene):
    bot, update, context, events, _ = scene
    bot.db.get_or_create_player(1)
    assert len(grant_starter_cards(bot.db, 1)) == 10
    before = counts(bot.db)
    asyncio.run(bot.start_command(update, context))
    assert counts(bot.db) == before and len(events) == 11


def test_missing_catalog_grants_nothing_and_retry_remains_possible(scene):
    bot, update, context, events, _ = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("DELETE FROM card_variants WHERE card_id LIKE 'extra-%'")
        conn.execute("DELETE FROM cards WHERE card_id LIKE 'extra-%'")
    asyncio.run(bot.start_command(update, context))
    assert counts(bot.db) == [] and bot.db.get_player_decks(1) == [] and events == []
    for i in range(7):
        cid = 'fixed-' + str(i)
        bot.db.add_card(Card(cid, cid, CardRarity.NORMAL, 1, 1, 1, 1, []))
        bot.db.set_card_variant_media_file_id(cid, 'normal', cid + '-normal', 'sticker')
    asyncio.run(bot.start_command(update, context))
    assert len(counts(bot.db)) == 10


@pytest.mark.parametrize('wait', [False, True])
def test_invite_survives_auto_delivery_and_membership(scene, wait):
    bot, update, context, events, query = scene
    bot.db.get_or_create_player(2)
    bot.db.add_card_to_player(2, 'wick')
    invite = bot.modes.create_invite(2, 'quick', 'normal', 2)
    context.args = ['gm_' + invite['invite_token']]
    bot._launch_mode_match, bot._edit_request_panel = AsyncMock(), AsyncMock()
    bot.is_user_in_channel.return_value = not wait
    asyncio.run(bot.start_command(update, context))
    if wait:
        bot.is_user_in_channel.return_value = True
        context.args = []
        click(update, query)
        asyncio.run(bot.check_membership_handler(update, context))
    assert bot.modes.get_request(invite['request_id'])['opponent_id'] == 1
    bot._launch_mode_match.assert_awaited_once()


def test_deck_failure_rolls_back_cards_and_new_receipt(scene):
    bot, _, _, _, _ = scene
    bot.db.get_or_create_player(1)
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_starter_deck BEFORE INSERT ON player_decks BEGIN SELECT RAISE(ABORT,'failure'); END")
    with pytest.raises(sqlite3.IntegrityError):grant_starter_pack(bot.db, 1)
    assert counts(bot.db) == [] and starter_status(bot.db, 1).get('pending')


def test_text_retry_does_not_repeat_any_sticker(scene):
    bot, update, context, events, _ = scene
    original = context.bot.send_message.side_effect
    context.bot.send_message.side_effect = RuntimeError('offline')
    asyncio.run(bot.start_command(update, context))
    assert len(events) == 10 and not onboarding.delivery(bot.db, 1)['done']
    context.bot.send_message.side_effect = original
    asyncio.run(bot.start_command(update, context))
    assert len(events) == 11 and onboarding.delivery(bot.db, 1)['done']


def test_concurrent_starts_deliver_one_sticker_sequence(scene):
    bot, update, context, events, _ = scene
    original = context.bot.send_sticker.side_effect
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(*, chat_id, sticker, **kwargs):
            if sticker == 'wick-normal':
                entered.set()
                await release.wait()
            await original(chat_id=chat_id, sticker=sticker, **kwargs)
        context.bot.send_sticker.side_effect = delayed
        first = asyncio.create_task(bot.start_command(update, context))
        await asyncio.wait_for(entered.wait(), timeout=5)
        await bot.start_command(update, context)
        release.set()
        await first
    asyncio.run(run())
    assert len(events) == 11 and len(counts(bot.db)) == 10
    assert context.bot_data['_starter_deliveries'] == set()
