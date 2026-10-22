import asyncio
import uuid
from io import BytesIO
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image
import pytest

from bot.handlers import easy_victory
from bot.main import TelegramCardBot
from core.database import DatabaseManager
from core.game_logic import GameLogic
from core.models import Card, CardRarity
from systems import easy_presentation as settings
from systems.card_inventory_system import CardInventorySystem
from systems.game_mode_system import GameModeSystem


def readable(text):
    return text.translate(str.maketrans('', '', '\u2068\u2069'))


@pytest.fixture
def scene(tmp_path):
    db = DatabaseManager(str(tmp_path / 'easy-ui.db'))
    for user, name in [(1, 'MH_*'), (2, 'Varan'), (3, 'کسری'), (4, 'چهارم')]:
        db.get_or_create_player(user, first_name=name)
    db.add_card(Card('hero', 'قهرمان <MH>', CardRarity.NORMAL, 40, 30, 20, 10, []))
    db.add_card(Card('other', 'دیگری', CardRarity.NORMAL, 50, 50, 50, 50, []))
    with sqlite3.connect(db.db_path) as conn:
        CardInventorySystem.grant_in(conn, 1, 'hero', 'normal')
        CardInventorySystem.grant_in(conn, 1, 'hero', 'epic')
        CardInventorySystem.grant_in(conn, 2, 'other', 'normal')
    for rarity, color in [('normal', 'red'), ('epic', 'blue'), ('legend', 'green')]:
        image = tmp_path / (rarity + '.png')
        Image.new('RGB', (200, 300), color).save(image)
        form = db.get_card_variant('hero', rarity)
        db.save_card_variant('hero', rarity, dict(form, image_path=str(image)))
        db.set_card_variant_media_file_id('hero', rarity, rarity + '-sticker', 'sticker')
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db, bot.game, bot.config = db, GameLogic(db), {'image_settings': {'enable_images': True}}
    bot.modes = GameModeSystem(db)
    bot.is_user_in_channel = AsyncMock(return_value=True)
    user = SimpleNamespace(id=1, first_name='MH_*', username='mh')
    message = SimpleNamespace(text='', reply_text=AsyncMock(), chat=SimpleNamespace(type='private'))
    query = SimpleNamespace(data='easy_victory_menu', from_user=user, answer=AsyncMock(),
                            edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock(), message=message)
    update = SimpleNamespace(effective_user=user, effective_message=message, effective_chat=message.chat,
                             callback_query=query, message=message)
    events = []

    async def send_sticker(sticker, **kwargs):
        events.append(('sticker', sticker.getvalue() if isinstance(sticker, BytesIO) else sticker, kwargs))

    async def send_message(**kwargs):
        events.append(('message', kwargs['text'], kwargs))
        return SimpleNamespace(message_id=99)

    context = SimpleNamespace(user_data={}, bot_data={}, bot=SimpleNamespace(
        send_sticker=AsyncMock(side_effect=send_sticker), send_message=AsyncMock(side_effect=send_message),
        delete_message=AsyncMock(), edit_message_text=AsyncMock()))
    return bot, update, context, events


def test_settings_persist_exact_owned_forms_without_mutating_inventory_or_active_form(scene):
    bot, _, _, _ = scene
    before = CardInventorySystem(bot.db).counts(1, 'hero')
    active = bot.db.get_card_by_id_for_player('hero', 1).rarity
    settings.save(bot.db, 1, card_id='hero', rarity='epic', slogan='  بردیم!\n <hi>_* \u202e ')
    reopened = DatabaseManager(bot.db.db_path)
    assert settings.read(reopened, 1) == {'card_id': 'hero', 'rarity': 'epic', 'slogan': 'بردیم! <hi>_*'}
    assert CardInventorySystem(bot.db).counts(1, 'hero') == before
    assert bot.db.get_card_by_id_for_player('hero', 1).rarity == active
    choices = settings.choices(bot.db, 1)
    assert {(c['card_id'], c['rarity']) for c in choices} == {('hero', 'normal'), ('hero', 'epic')}
    for card_id, rarity in [('other', 'normal'), ('hero', 'legend'), ('missing', 'normal')]:
        with pytest.raises(ValueError):
            settings.save(bot.db, 1, card_id=card_id, rarity=rarity)
    settings.clear(bot.db, 1)
    assert settings.read(bot.db, 1) == {}


@pytest.mark.parametrize('text', ['', 'x' * 121, '\u202e\u2066'])
def test_invalid_slogan_preserves_previous_settings(scene, text):
    bot, _, _, _ = scene
    settings.save(bot.db, 1, slogan='قبلی')
    with pytest.raises(ValueError):
        settings.save(bot.db, 1, slogan=text)
    assert settings.read(bot.db, 1)['slogan'] == 'قبلی'


def test_profile_command_and_callback_offer_settings_without_changing_main_menu(scene):
    bot, update, context, _ = scene
    update.callback_query = None
    asyncio.run(bot.profile_command(update, context))
    markup = update.message.reply_text.await_args.kwargs['reply_markup']
    assert any(b.callback_data == 'easy_victory_menu' for row in markup.inline_keyboard for b in row)
    assert 'MH\\_\\*' in update.message.reply_text.await_args.args[0]
    context.user_data['easy_victory_draft'] = {'expires_at': time.time() + 600}
    update.callback_query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
    asyncio.run(bot.profile_command(update, context))
    assert 'easy_victory_draft' not in context.user_data
    assert update.callback_query.edit_message_text.await_count == 1


def test_picker_paginates_and_scopes_tokens_to_current_user_and_owned_form(scene):
    bot, update, context, _ = scene
    for i in range(9):
        bot.db.add_card(Card('extra' + str(i), 'Extra ' + str(i), CardRarity.NORMAL, 10, 10, 10, 10, []))
        bot.db.add_card_to_player(1, 'extra' + str(i))
    query = update.callback_query
    query.data = 'easy_victory_cards_0'
    asyncio.run(easy_victory.handle(bot, update, context))
    rows = query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    first_pick = rows[0][0].callback_data
    assert len(context.user_data['easy_victory_choices']) == 8
    assert any(b.callback_data == 'easy_victory_cards_1' for row in rows for b in row)
    query.data = 'easy_victory_cards_1'
    asyncio.run(easy_victory.handle(bot, update, context))
    query.data = first_pick
    asyncio.run(easy_victory.handle(bot, update, context))
    assert 'قدیمیه' in query.edit_message_text.await_args.args[0]
    assert settings.read(bot.db, 1) == {}
    token, choice = next(iter(context.user_data['easy_victory_choices'].items()))
    query.data = 'easy_victory_pick_' + token
    # A forwarded/crafted button has no action in another player's user_data.
    outsider = SimpleNamespace(user_data={})
    query.from_user = SimpleNamespace(id=2)
    asyncio.run(easy_victory.handle(bot, update, outsider))
    assert settings.read(bot.db, 2) == {}
    query.from_user = update.effective_user
    asyncio.run(easy_victory.handle(bot, update, context))
    assert settings.read(bot.db, 1)['card_id'] == choice['card_id']
    assert settings.read(bot.db, 1)['rarity'] == choice['rarity']


def test_picker_rechecks_ownership_if_form_is_consumed_after_menu(scene):
    bot, update, context, _ = scene
    update.callback_query.data = 'easy_victory_cards_0'
    asyncio.run(easy_victory.handle(bot, update, context))
    token = next(t for t, c in context.user_data['easy_victory_choices'].items() if c['rarity'] == 'epic')
    with sqlite3.connect(bot.db.db_path) as conn:
        CardInventorySystem.consume_in(conn, 1, 'hero', 'epic')
    update.callback_query.data = 'easy_victory_pick_' + token
    asyncio.run(easy_victory.handle(bot, update, context))
    assert 'نداری' in update.callback_query.edit_message_text.await_args.args[0]
    assert settings.read(bot.db, 1) == {}


@pytest.mark.parametrize('access_removed', ['grant', 'flag'])
def test_custom_victory_character_requires_current_grant_and_global_access(scene, access_removed):
    from systems.custom_cards import CustomCards
    from web.web_api import WebAPI
    bot, _, context, events = scene
    custom = CustomCards(bot.db)
    validator = WebAPI(bot.db)._validate_card_payload

    def mutate(action, data):
        return custom.mutate('synthetic-admin', uuid.uuid4().hex, action, data, validator=validator)

    order = mutate('order', {'buyer_id': 1, 'recipients': [1], 'rarity': 'epic',
                             'amount': '0', 'currency': 'TEST'})['order_id']
    card_id = mutate('create', {'order_id': order, 'card': {
        'name': 'شخصیت من', 'rarity': 'epic', 'power': 5, 'speed': 6, 'iq': 7,
        'popularity': 8, 'abilities': [], 'traits': [], 'hidden_stats': {}}})['card_id']
    mutate('payment', {'order_id': order})
    mutate('status', {'card_id': card_id, 'status': 'active', 'review_confirmed': True})
    mutate('grant', {'order_id': order, 'card_id': card_id, 'users': [1]})
    mutate('settings', {'custom_cards_enabled': True})
    assert any(c['card_id'] == card_id and c['rarity'] == 'epic' for c in settings.choices(bot.db, 1))
    assert not any(c['card_id'] == card_id for c in settings.choices(bot.db, 2))
    settings.save(bot.db, 1, card_id=card_id, rarity='epic', slogan='ایول!')
    if access_removed == 'grant':
        mutate('revoke', {'card_id': card_id, 'users': [1]})
    else:
        mutate('settings', {'custom_cards_enabled': False})
    assert settings.owned_card(bot.db, 1, card_id, 'epic') is None
    assert not any(c['card_id'] == card_id for c in settings.choices(bot.db, 1))
    asyncio.run(easy_victory.announce(bot, context, {'origin_chat_id': -100}, {'winner_ids': [1]}))
    assert [e[0] for e in events] == ['message']


def test_slogan_router_validates_saves_and_cancels_without_stealing_deck_input(scene):
    bot, update, context, _ = scene
    query = update.callback_query
    query.data = 'easy_victory_slogan'
    asyncio.run(easy_victory.handle(bot, update, context))
    update.message.text = 'x' * 121
    asyncio.run(bot._deck_name_message_router(update, context))
    assert 'easy_victory_draft' in context.user_data and settings.read(bot.db, 1) == {}
    update.message.text = 'این تازه شروعشه! <win>_*'
    asyncio.run(bot._deck_name_message_router(update, context))
    assert settings.read(bot.db, 1)['slogan'] == update.message.text
    assert 'easy_victory_draft' not in context.user_data
    assert update.message.reply_text.await_args.kwargs.get('parse_mode') is None
    asyncio.run(easy_victory.handle(bot, update, context))
    query.data = 'easy_victory_menu'
    asyncio.run(easy_victory.handle(bot, update, context))
    update.message.text = 'نباید ذخیره بشه'
    asyncio.run(bot._deck_name_message_router(update, context))
    assert settings.read(bot.db, 1)['slogan'] != update.message.text
    context.user_data.update(deck_build={'waiting_name': True})
    query.data = 'easy_victory_slogan'
    asyncio.run(easy_victory.handle(bot, update, context))
    assert 'easy_victory_draft' not in context.user_data
    bot.deck_name_message_handler = AsyncMock()
    context.user_data['easy_victory_draft'] = {'expires_at': time.time() + 600}
    asyncio.run(bot._deck_name_message_router(update, context))
    bot.deck_name_message_handler.assert_awaited_once_with(update, context)
    assert 'easy_victory_draft' not in context.user_data


def test_expired_draft_and_nonprivate_callback_do_not_write(scene):
    bot, update, context, _ = scene
    context.user_data['easy_victory_draft'] = {'expires_at': time.time() - 1}
    update.message.text = 'دیر شد'
    asyncio.run(bot._deck_name_message_router(update, context))
    assert settings.read(bot.db, 1) == {} and 'easy_victory_draft' not in context.user_data
    update.effective_chat.type = 'group'
    update.callback_query.data = 'easy_victory_slogan'
    asyncio.run(easy_victory.handle(bot, update, context))
    assert 'easy_victory_draft' not in context.user_data
    assert update.callback_query.answer.await_args.kwargs['show_alert']


@pytest.mark.parametrize('media', ['cached', 'bitmap', 'unavailable', 'lost_card'])
def test_unique_winner_gets_exact_form_sticker_before_plain_text_slogan(scene, media):
    bot, _, context, events = scene
    settings.save(bot.db, 1, card_id='hero', rarity='epic', slogan='بُردیم <win>_*')
    if media in ('bitmap', 'unavailable'):
        with sqlite3.connect(bot.db.db_path) as conn:
            conn.execute('DELETE FROM card_variant_media_cache')
    if media == 'lost_card':
        with sqlite3.connect(bot.db.db_path) as conn:
            CardInventorySystem.consume_in(conn, 1, 'hero', 'epic')
    if media == 'unavailable':
        context.bot.send_sticker.side_effect = RuntimeError('Telegram unavailable')
    asyncio.run(easy_victory.announce(bot, context, {'origin_chat_id': -100}, {'winner_ids': [1]}))
    if media == 'cached':
        assert [e[0] for e in events] == ['sticker', 'message']
        assert events[0][1] == 'epic-sticker'
    elif media == 'bitmap':
        assert [e[0] for e in events] == ['sticker', 'message']
        image = Image.open(BytesIO(events[0][1])).convert('RGB')
        assert max(image.size) == 512 and image.getpixel((100, 100))[2] > 200
    else:
        assert [e[0] for e in events] == ['message']
    assert readable(events[-1][1]) == '🏆 MH_*: "بُردیم <win>_*"'
    assert events[-1][2]['chat_id'] == -100 and events[-1][2].get('parse_mode') is None


@pytest.mark.parametrize('winners', [[], [1, 2]])
def test_no_single_winner_sends_no_victory_sticker_or_slogan(scene, winners):
    bot, update, context, events = scene
    settings.save(bot.db, 1, card_id='hero', rarity='normal', slogan='شعار')
    asyncio.run(easy_victory.announce(bot, context, {'origin_chat_id': -100}, {'winner_ids': winners}))
    assert events == []


@pytest.mark.parametrize('v2', [False, True])
def test_real_easy_match_keeps_question_lifecycle_rewards_and_single_settlement(scene, v2):
    bot, update, context, events = scene
    if v2:
        with sqlite3.connect(bot.db.db_path) as conn:
            conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
            conn.execute('UPDATE player_progression SET level=5,total_xp=700 WHERE user_id IN (1,2)')
    bot._schedule_mode_job = Mock()
    bot._cancel_mode_job = Mock()
    request = bot.modes.create_easy_lobby(1, -100, 1)
    key = request['request_id']
    bot.modes.update_message_reference(key, -100, 77)
    assert bot.modes.join_easy_lobby(key, 2)[0]
    text = readable(bot._easy_lobby_text(key))
    assert 'MH_*' in text and 'Varan' in text
    ok, _, state = bot.modes.start_easy_match(key)
    assert ok
    # Deterministic authored question, retaining the real selection and settlement.
    with bot.modes._connect() as conn:
        state['question'] = {'id': 'simple', 'text': 'کدوم قوی‌تره؟', 'formula': 'power', 'terms': [['power', 1]], 'kind': 'simple'}
        bot.modes._save_state(conn, key, state)
    asyncio.run(bot._send_easy_question(context, key, state))
    assert 'کدوم قوی‌تره؟' not in context.bot.edit_message_text.await_args.kwargs['text']
    assert 'کدوم قوی‌تره؟' in events[-1][1]
    for user, card_id in [(1, 'hero'), (2, 'other')]:
        bot.modes.get_easy_options(key, user)
        assert bot.modes.select_easy_card(key, user, card_id)[0]
    settings.save(bot.db, 2, card_id='other', rarity='normal', slogan='بردم!')
    bot.db.set_card_variant_media_file_id('other', 'normal', 'other-sticker', 'sticker')
    asyncio.run(bot._resolve_and_announce_easy(context, key))
    context.bot.delete_message.assert_awaited_once_with(chat_id=-100, message_id=99)
    final = readable(context.bot.edit_message_text.await_args.kwargs['text'])
    assert '🥇 Varan: 3' in final and '🥈 MH_*: 2' in final and 'برنده:' not in final
    assert [e[0] for e in events[-2:]] == ['sticker', 'message']
    assert readable(events[-1][1]) == '🏆 Varan: "بردم!"'
    button = events[-1][2]['reply_markup'].inline_keyboard[0][0]
    assert button.text == 'مشاهده جزئیات'
    assert button.callback_data == f'easy_details_{key}'
    report = bot.modes.get_state(key)['report']
    assert (report['rewards']['1']['xp'], report['rewards']['2']['xp']) == ((0, 0) if v2 else (3, 10))
    with sqlite3.connect(bot.db.db_path) as conn:
        count = conn.execute('SELECT COUNT(*) FROM match_reward_events WHERE request_id=?', (key,)).fetchone()[0]
    update.effective_chat = SimpleNamespace(type='private', id=1)
    update.callback_query.data = button.callback_data
    update.callback_query.message = SimpleNamespace(message_id=99)
    before = len(events)
    asyncio.run(easy_victory.show_details(bot, update, context))
    assert len(events) == before
    update.effective_chat = SimpleNamespace(type='group', id=-100)
    send_message = context.bot.send_message.side_effect
    context.bot.send_message.side_effect = RuntimeError('temporary Telegram error')
    asyncio.run(easy_victory.show_details(bot, update, context))
    assert not bot.modes.get_state(key).get('easy_details_shown')
    assert len(events) == before
    context.bot.send_message.side_effect = send_message
    asyncio.run(easy_victory.show_details(bot, update, context))
    detail = readable(events[-1][1])
    assert '🎯 راند 1: کدوم قوی‌تره؟' in detail
    assert '🥇 اول · Varan: دیگری' in detail
    assert '🥈 دوم · MH_*: قهرمان <MH>' in detail
    assert events[-1][2]['chat_id'] == -100
    assert events[-1][2]['reply_to_message_id'] == 99
    context.bot.send_message.reset_mock()
    asyncio.run(easy_victory.show_details(bot, update, context))
    context.bot.send_message.assert_not_awaited()
    before = len(events)
    asyncio.run(bot._resolve_and_announce_easy(context, key))
    assert len(events) == before
    with sqlite3.connect(bot.db.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM match_reward_events WHERE request_id=?', (key,)).fetchone()[0] == count


def test_shared_first_place_medals_use_same_competition_rank_as_rewards(scene):
    bot, _, context, events = scene
    bot._cancel_mode_job = Mock()
    report = {'request_id': 'tied', 'scores': {'1': 9, '2': 9, '3': 5, '4': 2}, 'winner_ids': [1, 2]}
    bot.modes = SimpleNamespace(get_state=Mock(return_value={'current_round': 3}),
        get_request=Mock(return_value={'origin_chat_id': -100, 'origin_message_id': 77}),
        resolve_easy_round=Mock(return_value={'completed': True, 'report': report}))
    asyncio.run(bot._resolve_and_announce_easy(context, 'tied'))
    text = readable(context.bot.edit_message_text.await_args.kwargs['text'])
    assert '🥇 MH_*: 9' in text and '🥇 Varan: 9' in text and '🥉 کسری: 5' in text
    assert '🥈' not in text and '• چهارم: 2' in text and 'برنده:' not in text
    markup = context.bot.edit_message_text.await_args.kwargs['reply_markup']
    assert markup.inline_keyboard[0][0].callback_data == 'easy_details_tied'
    assert events == []


def test_easy_details_keep_tied_places_and_all_rounds_within_message_limit(scene):
    bot, _, _, _ = scene
    round_result = {'round': 1, 'question': {'text': 'کدام قوی‌تر است؟'}, 'entries': [
        {'user_id': 2, 'card_name': 'دیگری', 'eligible': True, 'hidden_value': 9},
        {'user_id': 1, 'card_name': 'قهرمان <MH>', 'eligible': True, 'hidden_value': 9},
        {'user_id': 3, 'card_name': 'سومی', 'eligible': False, 'hidden_value': 20},
    ]}
    report = {'scores': {'1': 3, '2': 3, '3': 1, '4': 0},
              'round_history': [round_result, dict(round_result, round=2)]}
    parts = easy_victory.details_parts(report, bot.db, limit=110)
    combined = readable('\n'.join(parts))
    assert len(parts) > 1 and all(len(part) <= 110 for part in parts)
    assert '🎯 راند 1: کدام قوی‌تر است؟' in combined
    assert '🎯 راند 2: کدام قوی‌تر است؟' in combined
    assert '🥇 اول · Varan: دیگری' in combined
    assert '🥇 اول · MH_*: قهرمان <MH>' in combined
    assert '🥈 دوم · کسری: سومی' in combined
    assert 'چهارم: انتخاب نکرد' in combined
    assert 'hidden_value' not in combined


def test_profile_handlers_are_registered_and_callback_data_fits_telegram_limit(scene):
    from telegram.ext import CallbackQueryHandler
    bot, update, context, _ = scene
    app = Mock()
    bot.setup_handlers(app)
    handlers = [call.args[0] for call in app.add_handler.call_args_list]
    callbacks = [h for h in handlers if isinstance(h, CallbackQueryHandler)]
    for data in ['easy_victory_menu', 'easy_victory_slogan', 'easy_details_game123', 'easy_profile']:
        assert len([h for h in callbacks if h.pattern and h.pattern.match(data)]) == 1
    update.callback_query.data = 'easy_victory_cards_0'
    asyncio.run(easy_victory.handle(bot, update, context))
    rows = update.callback_query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard
    assert all(len(b.callback_data.encode('utf-8')) <= 64 for row in rows for b in row)


@pytest.mark.parametrize('limit,card_name,question', [
    (4000, '🎴' * 180, 'سؤال ' + '🌟' * 80),
    (110, 'کارت ' + '🎴' * 120, 'سؤال ' + '🌟' * 120),
], ids=['emoji-report', 'oversized-line'])
def test_easy_details_bound_emoji_and_individual_long_lines(scene, limit, card_name, question):
    bot, _, _, _ = scene
    entries = [{'user_id': user, 'card_name': card_name, 'hidden_value': user, 'eligible': True}
               for user in range(1, 5)]
    report = {'scores': {str(user): 1 for user in range(1, 5)}, 'round_history': [
        {'round': index, 'question': {'text': question}, 'entries': entries}
        for index in range(1, 5)]}
    parts = easy_victory.details_parts(report, bot.db, limit=limit)
    assert all(len(part.encode('utf-16-le')) // 2 <= limit for part in parts)
    combined = ''.join(parts)
    assert combined.count(card_name) == 16
    assert combined.count(question) >= 4


def test_easy_details_claim_is_atomic_and_other_groups_cannot_consume_it(scene):
    from concurrent.futures import ThreadPoolExecutor
    bot, update, context, _ = scene
    request = bot.modes.create_easy_lobby(1, -100, 1)
    key = request['request_id']
    report = {'request_id': key, 'mode': 'easy', 'scores': {'1': 3}, 'round_history': []}
    with bot.modes._connect() as conn:
        bot.modes._save_state(conn, key, {'phase': 'completed', 'report': report})
    update.callback_query.data = 'easy_details_' + key
    update.effective_chat = SimpleNamespace(type='supergroup', id=-200)
    asyncio.run(easy_victory.show_details(bot, update, context))
    assert not bot.modes.get_state(key).get('easy_details_shown')
    context.bot.send_message.assert_not_awaited()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(bot.modes.claim_easy_details, [key, key]))
    assert sum(result is not None for result in results) == 1
    assert next(result for result in results if result is not None) == report
    bot.modes.release_easy_details(key)
    assert bot.modes.claim_easy_details(key) == report
    assert bot.modes.claim_easy_details(key) is None
