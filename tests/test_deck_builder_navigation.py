import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Update
from telegram.ext import CallbackQueryHandler
from bot.main import TelegramCardBot
from core.database import DatabaseManager
from core.models import Card, CardRarity


@pytest.fixture
def builder(tmp_path):
    db = DatabaseManager(str(tmp_path / 'builder.db'))
    db.get_or_create_player(1)
    for cid, rarity in [('a','normal'),('b','normal'),('c','normal'),('sonic','epic')]:
        db.add_card(Card(cid, cid.title(), CardRarity(rarity), 30, 40, 50, 60, []))
        db.add_card_to_player(1, cid)
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db = db
    handlers = []
    bot.setup_handlers(SimpleNamespace(add_handler=handlers.append))
    context = SimpleNamespace(user_data={})

    def click(data):
        query = SimpleNamespace(data=data, from_user=SimpleNamespace(id=1),
                                answer=AsyncMock(), edit_message_text=AsyncMock())
        update = Update(1, callback_query=query)
        routes = [handler for handler in handlers
                  if isinstance(handler, CallbackQueryHandler) and handler.check_update(update)]
        assert len(routes) == 1, f'{data}: expected exactly one registered callback route'
        asyncio.run(routes[0].callback(update, context))
        return query

    return db, context, click


@pytest.mark.parametrize('step', [1, 2, 3])
def test_back_from_card_list_returns_to_current_categories_and_preserves_picks(builder, step):
    db, context, click = builder
    click('deck_create')
    for cid in ['a','b'][:step-1]:
        click('deck_build_cat_normal_1')
        click('deck_build_pick_' + cid)
    query = click('deck_build_cat_epic_1')
    back = query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[-1][0]
    assert back.text == '🔙 دسته‌بندی‌ها'
    before = copy.deepcopy(context.user_data)
    returned = click(back.callback_data)
    assert context.user_data == before
    assert f'کارت {step} از ۳' in returned.edit_message_text.await_args.args[0]
    buttons = returned.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert [row[0].callback_data for row in buttons] == [
        'deck_build_cat_legend_1','deck_build_cat_epic_1','deck_build_cat_normal_1','deck_menu']
    # An old step-1 button must not rewind step 2/3 or discard earlier picks.
    stale = click('deck_build_back_step1')
    assert f'کارت {step} از ۳' in stale.edit_message_text.await_args.args[0]
    assert context.user_data == before
    for cid in ['a','b','c'][step-1:]:
        listed = click('deck_build_cat_normal_1')
        offered = [b.callback_data for row in listed.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard for b in row]
        assert not any('deck_build_pick_' + chosen in offered for chosen in before['deck_build']['cards'])
        click('deck_build_pick_' + cid)
    click('deck_build_skip_name')
    assert context.user_data['deck_build']['waiting_slogan']
    click('deck_build_skip_slogan')
    assert 'deck_build' not in context.user_data
    assert db.count_player_decks(1) == 1
    deck = db.get_player_decks(1)[0]
    assert [deck[f'card_id_{i}'] for i in range(1, 4)] == ['a','b','c']


@pytest.mark.parametrize('build', [None, {'cards':['a','b','c'],'step':4,'waiting_name':True}])
def test_old_back_button_does_not_restart_missing_or_finished_selection(builder, build):
    _, context, click = builder
    if build is not None:
        context.user_data['deck_build'] = copy.deepcopy(build)
    before = copy.deepcopy(context.user_data)
    query = click('deck_build_back_step1')
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs['show_alert'] is True
    query.edit_message_text.assert_not_awaited()
    assert context.user_data == before
