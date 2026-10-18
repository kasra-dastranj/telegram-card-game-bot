import asyncio
import sqlite3
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot.main import TelegramCardBot
from bot.handlers.progression import handle, show_menu
from bot.handlers.silver_claim import card_text
from bot.player_messages import error_text
from core.database import DatabaseManager
from core.display_text import clean, isolate, ltr, ratio, signed, markdown_name
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.progression_config import config_in, save_config_in
from systems.progression_economy import ProgressionEconomy
from systems.reward_ledger import items_in


def readable(value):
    return value.translate(str.maketrans('', '', '\u2066\u2068\u2069'))


@pytest.mark.parametrize('value', ['MH', 'کسری ۱۲', 'Batman (Epic)', '🃏 بردیم! می‌ریم', 'الف_*<b>'])
def test_display_fragments_keep_text_and_balance_direction_controls(value):
    assert isolate(value) == '\u2068' + value + '\u2069'
    assert ltr(value) == '\u2066' + value + '\u2069'
    # Input isolates/overrides cannot escape the caller's display fragment.
    dirty = '\u202e\u2069' + value + '\u2066'
    assert clean(dirty) == value and isolate(dirty) == isolate(value)
    assert markdown_name(dirty).count('\u2068') == markdown_name(dirty).count('\u2069') == 1


def test_signed_rewards_ratios_and_arrows_keep_their_logical_order():
    assert signed(-2, 'Score') == '\u2066-2 Score\u2069'
    assert signed(10, 'XP') == '\u2066+10 XP\u2069'
    assert ratio(2, 15) == '\u20662/15\u2069'
    assert ltr('Normal → Epic') == '\u2066Normal → Epic\u2069'
    assert markdown_name('MH_*') == '\u2068MH\\_\\*\u2069'


@pytest.fixture
def scene(tmp_path):
    db = DatabaseManager(str(tmp_path / 'copy.db'))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
    db.get_or_create_player(1, 'mh', 'کسری MH_*')
    db.get_or_create_player(2, 'other', 'Varan')
    db.add_card(Card('hero', 'Batman_<b>', CardRarity.NORMAL, 40, 30, 20, 10, []))
    with sqlite3.connect(db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 1, 'hero', 'normal', 1)
        CardInventorySystem.grant_in(conn, 1, 'hero', 'epic', 2)
        conn.execute("INSERT INTO economy_character_rules VALUES('hero','A')")
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db, bot.game, bot.config = db, GameLogic(db), {}
    bot.is_user_in_channel = AsyncMock(return_value=True)
    user = SimpleNamespace(id=1, username='mh', first_name='کسری MH_*')
    message = SimpleNamespace(reply_text=AsyncMock(), chat=SimpleNamespace(type='private'))
    query = SimpleNamespace(data='v2_silver_claim', from_user=user, message=message,
                            answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_user=user, effective_chat=message.chat,
                             effective_message=message, message=message)
    context = SimpleNamespace(user_data={}, bot_data={}, bot=SimpleNamespace(send_message=AsyncMock()))
    return bot, update, context


def test_real_silver_shortage_uses_current_rule_and_exact_missing_count_without_spending(scene):
    bot, update, context = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        _, config = config_in(conn)
        config['claim']['silver_tickets'] = 5
        items_in(conn, 1, 'silver_ticket', 3)
        save_config_in(conn, config, 'synthetic-copy-test')
    economy = ProgressionEconomy(bot.db)
    inventory = economy.inventory(1)
    cost = inventory['silver_claim_tickets']
    assert cost == 5
    context.user_data['economy_actions'] = {'try': {'kind': 'silver_craft',
        'request_key': 'copy-test', 'config_version': inventory['config_version']}}
    update.callback_query.data = 'v2_action_try'
    asyncio.run(handle(bot, update, context))
    text = readable(update.callback_query.edit_message_text.await_args.args[0])
    assert 'هنوز 2 تا دیگه لازم داری' in text
    after = economy.inventory(1)['items']
    assert after['silver_ticket'] == 3 and after.get('free_silver_claim', 0) == 0


def test_real_upgrade_preview_names_both_shortages_and_does_not_consume_cards(scene):
    bot, update, context = scene
    before = CardInventorySystem(bot.db).counts(1, 'hero')
    context.user_data['economy_actions'] = {'card': {'kind': 'card_menu', 'card_id': 'hero'}}
    update.callback_query.data = 'v2_action_card'
    asyncio.run(handle(bot, update, context))
    text = readable(update.callback_query.edit_message_text.await_args.args[0])
    assert 'Epic: هنوز 2 نسخه از همین فرم کارت دیگه لازم داری' in text
    assert 'Legend: هنوز 1 کارت ارتقا دیگه لازم داری' in text
    assert CardInventorySystem(bot.db).counts(1, 'hero') == before
    buttons = update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert buttons[-1][0].callback_data == 'v2_cards_0'
    assert context.user_data['economy_actions']['card']['card_id'] == 'hero'


def test_empty_missions_have_a_clear_message_and_original_back_button(scene):
    bot, update, context = scene
    asyncio.run(show_menu(bot, update, context, 'missions'))
    assert 'فعلاً مأموریتی نداری' in update.callback_query.edit_message_text.await_args.args[0]
    assert update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[-1][0].callback_data == 'back_to_main'


def test_profile_keeps_name_safe_and_current_max_hearts_in_a_single_ltr_fraction(scene):
    bot, update, context = scene
    with sqlite3.connect(bot.db.db_path) as conn:
        conn.execute('UPDATE players SET hearts=2,max_hearts=15 WHERE user_id=1')
    update.callback_query = None
    asyncio.run(bot.profile_command(update, context))
    text = update.message.reply_text.await_args.args[0]
    assert markdown_name('کسری MH_*') in text and ratio(2, 15) in text
    assert '\u2066Level 1\u2069' in text
    assert bot.db.get_or_create_player(1).hearts == 2


def test_no_hearts_message_has_actual_remaining_time_and_no_hardcoded_five_heart_promise(scene):
    bot, update, context = scene
    bot.game = SimpleNamespace(get_heart_reset_time_remaining=Mock(return_value=timedelta(minutes=17)),
                              format_time_remaining=Mock(return_value='۱۷ دقیقه'))
    asyncio.run(bot.send_no_hearts_message(update.callback_query, context, SimpleNamespace()))
    text = context.bot.send_message.await_args.kwargs['text']
    assert isolate('۱۷ دقیقه') in text and '۵ جان' not in text and '۲۴ ساعت' not in text
    assert update.callback_query.answer.await_args.kwargs['show_alert'] is True


def test_silver_card_name_is_html_escaped_without_altering_the_card():
    card = Card('id', 'Hero_<b>\u202e', CardRarity.EPIC, 40, 30, 20, 10, [])
    text = card_text(card)
    assert 'Hero_&lt;b&gt;' in text and '\u202e' not in text
    assert '<b>' + isolate('Hero_&lt;b&gt;') + '</b>' in text
    assert card.name.endswith('\u202e')


@pytest.mark.parametrize('code', ['quote_expired', 'stock_empty', 'active_match', 'insufficient_coins_or_player_missing'])
def test_sensitive_errors_are_actionable_and_do_not_claim_false_charge_or_shortage(code):
    text = error_text({'error_code': code, 'error': 'raw_internal_error'})
    assert 'raw_internal_error' not in text and '?' not in text
    assert '🙂' not in text and 'سکه کم نشد' not in text
    if code == 'insufficient_coins_or_player_missing':
        assert 'سکه‌هات کافی نیست' not in text


def test_risk_result_uses_real_safe_player_names_and_preserves_engine_values(scene):
    bot, _, context = scene
    result = {'success': True, 'round': 3, 'selected_stat': 'power', 'winner': 'challenger',
              'challenger_value': 50, 'opponent_value': 40, 'game_over': True, 'winner_id': 1}
    match = {'challenger_id': 1, 'opponent_id': 2, 'challenger_rounds_won': 2,
             'opponent_rounds_won': 1, 'current_pot': 300, 'chat_id': -100}
    bot.risk = SimpleNamespace(resolve_round=Mock(return_value=result), get_risk_match=Mock(return_value=match))
    before = (bot.db.get_or_create_player(1).coins, bot.db.get_or_create_player(2).coins)
    asyncio.run(bot._resolve_risk_round(context, 'synthetic-match'))
    text = context.bot.send_message.await_args.kwargs['text']
    assert markdown_name('کسری MH_*') in text and isolate('Varan') in text
    assert 'Challenger' not in text and 'Opponent' not in text
    assert ltr('2 — 1') in text and 'پات نهایی: ' + isolate(300) in text
    assert context.bot.send_message.await_args.kwargs['chat_id'] == -100
    bot.risk.resolve_round.assert_called_once_with('synthetic-match')
    assert (bot.db.get_or_create_player(1).coins, bot.db.get_or_create_player(2).coins) == before
