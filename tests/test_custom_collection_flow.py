"""Real Telegram callbacks: private grants stay visible without enabling gameplay."""
import asyncio
import sqlite3
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from telegram import CallbackQuery, Chat, Message, Update, User, PhotoSize

from bot.handlers.game_modes import GameModeHandlersMixin
from systems.card_collection import custom_collection, custom_owned_card
from systems.shared_foundation import context_in
from tests.test_bot_collection_flow import CollectionBot, event, text_of
from tests.test_custom_admin_fulfillment import form
from tests.test_custom_cards_phase3 import custom, post, enable_v2


@pytest.fixture
def scene(custom):
    db, api, client = custom
    db.get_or_create_player(101)
    db.add_card_to_player(101, 'official')
    handler = CollectionBot()
    handler.db, handler.modes = db, api.modes
    handler.skins = SimpleNamespace(get_card_skins=Mock(return_value=[]))
    handler.missions = SimpleNamespace(get_player_mission_progress=Mock(return_value=None))
    handler.is_user_in_channel = AsyncMock(return_value=True)
    handler._is_command_allowed_in_chat = Mock(return_value=True)
    response = post(custom, 'fulfill', form(users=[101]))
    assert response.status_code == 200
    return custom, handler, response.get_json()['card_id']


def buttons(bot):
    return [button for row in bot.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard for button in row]


def test_granted_card_visible_with_flags_off_without_changing_game_inventory(scene):
    custom, handler, card_id = scene
    assert all(c.origin == 'official' for c in handler.db.get_player_cards(101))
    assert handler.db.get_card_by_id_for_player(card_id, 101) is None
    for data in ('my_cards', 'mycards_menu_1'):
        update, bot = event(data)
        callback = handler.my_cards_handler if data == 'my_cards' else handler.mycards_navigation_handler
        asyncio.run(callback(update, SimpleNamespace()))
        menu = {b.callback_data:b.text for b in buttons(bot)}
        assert 'mycards_rare_1' in menu and '(0)' in menu['mycards_rare_1']
        assert '(1)' in menu['mycards_custom_1']
    update, bot = event('mycards_custom_1')
    asyncio.run(handler.mycards_navigation_handler(update, SimpleNamespace()))
    assert f'cardinfo_{card_id}' in {b.callback_data for b in buttons(bot)}
    assert 'غیرفعاله' in text_of(bot)
    assert custom_owned_card(handler.db, 1, card_id) is None


def test_custom_does_not_mix_into_normal_even_after_gameplay_is_enabled(scene):
    custom, handler, card_id = scene
    post(custom, 'settings', {'custom_cards_enabled':True})
    update, bot = event('mycards_normal_1')
    asyncio.run(handler.mycards_navigation_handler(update, SimpleNamespace()))
    ids = {b.callback_data for b in buttons(bot)}
    assert 'cardinfo_official' in ids and f'cardinfo_{card_id}' not in ids


def test_custom_pagination_and_outdated_page_reach_all_cards(scene):
    custom, handler, first = scene
    expected = {first}
    for index in range(7):
        data = form(users=[101]); data['card']['name'] = f'شخصیت {index}'
        expected.add(post(custom, 'fulfill', data).get_json()['card_id'])
    seen = set()
    for page in (1, 2):
        update, bot = event(f'mycards_custom_{page}')
        asyncio.run(handler.mycards_navigation_handler(update, SimpleNamespace()))
        seen.update(b.callback_data.removeprefix('cardinfo_') for b in buttons(bot) if b.callback_data.startswith('cardinfo_'))
    assert seen == expected
    update, bot = event('mycards_custom_999')
    asyncio.run(handler.mycards_navigation_handler(update, SimpleNamespace()))
    assert '2/2' in text_of(bot)
    assert any(b.callback_data.startswith('cardinfo_') for b in buttons(bot))


@pytest.mark.parametrize('entry', ['cardinfo_', 'card_view_'])
def test_detail_has_public_stats_traits_but_never_hidden_easy_values(scene, entry):
    _, handler, card_id = scene
    update, bot = event(entry+card_id)
    asyncio.run((handler.cardinfo_handler if entry == 'cardinfo_' else handler.card_view_handler)(update, SimpleNamespace()))
    text = text_of(bot)
    assert 'شخصیت MH' in text and '51' in text and '84' in text
    assert 'تریت‌ها' in text and 'hero' in text
    assert all(value not in text for value in ('ویژگی‌های Easy','⁨مدیریت⁩','کاریزما'))
    with sqlite3.connect(handler.db.db_path) as conn:
        import json
        assert json.loads(conn.execute('SELECT hidden_stats FROM card_mode_metadata WHERE card_id=?',(card_id,)).fetchone()[0]) == {'survival':80,'management':60}
    assert {b.callback_data for b in buttons(bot)} == {'mycards_custom_1'}
    assert handler.db.get_card_by_id_for_player(card_id, 101) is None


@pytest.mark.parametrize('action', ['revoke', 'status'])
def test_revoke_or_suspend_removes_list_and_stale_detail_without_media_leak(scene, action):
    custom, handler, card_id = scene
    data = {'card_id':card_id, 'users':[101]} if action == 'revoke' else {'card_id':card_id, 'status':'suspended'}
    assert post(custom, action, data).status_code == 200
    assert not custom_collection(handler.db, 101)
    update, bot = event('cardinfo_'+card_id)
    bot.send_sticker = AsyncMock()
    asyncio.run(handler.cardinfo_handler(update, SimpleNamespace(bot_data={})))
    bot.edit_message_text.assert_not_awaited()
    bot.send_sticker.assert_not_awaited()
    assert bot.answer_callback_query.await_args.kwargs['show_alert']


def test_private_image_sends_sticker_with_flags_off_not_public_cache(scene, monkeypatch):
    custom, handler, _ = scene
    stream=BytesIO(); Image.new('RGB',(180,240),'navy').save(stream,'PNG'); stream.seek(0)
    upload=custom[2].post('/api/custom/media', data={'image':(stream,'portrait.png')}, headers={'X-Admin-Token':'synthetic-test-admin'})
    assert upload.status_code == 201, upload.get_json()
    data=form(users=[101]);data['media_id']=upload.get_json()['media_id']
    card_id=post(custom,'fulfill',data).get_json()['card_id']
    cache=Mock(side_effect=AssertionError('Private cards must not use public cache'))
    monkeypatch.setattr(handler.db,'get_card_variant_media_file_id',cache)
    update, bot=event('cardinfo_'+card_id); bot.send_sticker=AsyncMock()
    asyncio.run(handler.cardinfo_handler(update,SimpleNamespace(bot_data={})))
    bot.send_sticker.assert_awaited_once()
    cache.assert_not_called()
    raw=bot.send_sticker.await_args.kwargs['sticker'].getvalue()
    assert Image.open(BytesIO(raw)).format == 'WEBP'


@pytest.mark.parametrize('kind', ['custom','rare'])
def test_details_from_photo_receipt_open_sticker_and_text_menu_with_working_back(scene,kind):
    _,handler,custom_id=scene
    card_id=custom_id
    if kind=='rare':
        from core.models import Card,CardRarity
        handler.db.add_card(Card('rare-receipt','Rare receipt',CardRarity.RARE,15,26,37,48,[]))
        handler.db.add_card_to_player(101,'rare-receipt')
        card_id='rare-receipt'
    update,bot=event('cardinfo_'+card_id)
    photo=Message(15,datetime.now(timezone.utc),Chat(101,'private'),
                  photo=[PhotoSize('photo','unique',120,180)],caption='مبارکت باشه!')
    photo.set_bot(bot)
    callback=CallbackQuery('receipt',update.callback_query.from_user,'chat',message=photo,data='cardinfo_'+card_id)
    callback.set_bot(bot)
    handler._send_owned_card_sticker=AsyncMock()
    asyncio.run(handler.cardinfo_handler(Update(2,callback_query=callback),SimpleNamespace(bot_data={})))
    handler._send_owned_card_sticker.assert_awaited_once()
    bot.edit_message_text.assert_not_awaited();bot.send_message.assert_awaited_once()
    details=bot.send_message.await_args.kwargs
    assert ('شخصیت MH' if kind=='custom' else 'Rare receipt') in details['text']
    assert all(label in details['text'] for label in ('قدرت','سرعت','هوش','محبوبیت'))
    assert 'ویژگی‌های Easy' not in details['text'] and '⁨مدیریت⁩' not in details['text']
    back=details['reply_markup'].inline_keyboard[-1][0].callback_data
    update,bot=event(back)
    asyncio.run(handler.mycards_navigation_handler(update,SimpleNamespace()))
    assert bot.edit_message_text.await_count==1


def test_group_and_other_user_callbacks_cannot_expose_private_definition(scene):
    _, handler, card_id=scene
    for user_id,chat_id in ((1,1),(101,-123)):
        update, bot=group_event('cardinfo_'+card_id, user_id=user_id, chat_id=chat_id)
        asyncio.run(handler.cardinfo_handler(update, SimpleNamespace()))
        bot.edit_message_text.assert_not_awaited()


def group_event(data, user_id=101, chat_id=-123):
    bot=SimpleNamespace(answer_callback_query=AsyncMock(),edit_message_text=AsyncMock(),send_message=AsyncMock())
    user=User(user_id,'Tester',False)
    message=Message(4,datetime.now(timezone.utc),Chat(chat_id,'supergroup' if chat_id<0 else 'private'),text='menu')
    message.set_bot(bot)
    query=CallbackQuery('query',user,'chat',message=message,data=data);query.set_bot(bot)
    return Update(1,callback_query=query),bot


@pytest.mark.parametrize('disabled_flag', ['custom_cards_enabled','easy_custom_cards_enabled','progression_v2_enabled',None])
def test_easy_yes_real_callback_is_answered_once_and_disabled_reason_stays_visible(scene, disabled_flag):
    custom, collection, _=scene
    enable_v2(custom,easy=True)
    post(custom,'settings',{'custom_cards_enabled':True})
    if disabled_flag:
        with sqlite3.connect(collection.db.db_path) as conn:
            conn.execute("UPDATE foundation_settings SET value_json='false' WHERE key=?",(disabled_flag,))
    handler=GameModeHandlersMixin();handler.db=collection.db;handler.modes=collection.modes
    handler._schedule_mode_job=Mock()
    update,bot=group_event('gm_erounds_3_yes')
    asyncio.run(handler.easy_round_count_handler(update, SimpleNamespace()))
    bot.answer_callback_query.assert_awaited_once()
    if disabled_flag:
        handler._schedule_mode_job.assert_not_called()
        assert 'تنظیمات مدیریت' in text_of(bot)
        assert 'خیر' in text_of(bot)
        update,bot=group_event('gm_erounds_3_no')
        asyncio.run(handler.easy_round_count_handler(update,SimpleNamespace()))
        assert handler._schedule_mode_job.call_count == 1
        key=handler._schedule_mode_job.call_args.args[3]['request_id']
        assert handler.modes.get_state(key)['allow_custom_cards'] is False
    else:
        key=handler._schedule_mode_job.call_args.args[3]['request_id']
        assert handler.modes.get_state(key)['allow_custom_cards'] is True
        with sqlite3.connect(handler.db.db_path) as conn:
            assert context_in(conn,key,'easy').allow_custom_cards
        assert handler.modes.join_easy_lobby(key, 2)[0]
        assert handler.modes.start_easy_match(key)[0]
        card_id = scene[2]
        assert card_id in {c.card_id for c in handler.modes.get_easy_options(key,101)}
        assert handler.modes.select_easy_card(key,101,card_id)[0]


def test_manual_admin_delivery_works_in_quick_friendly_without_entering_official_quick(scene):
    custom, handler, card_id = scene
    enable_v2(custom)
    post(custom,'settings',{'custom_cards_enabled':True})
    key=handler.modes.create_invite(101,'quick','friendly')['request_id']
    assert handler.modes.accept_request(key,2)[0]
    handler.modes.start_quick_match(key)
    assert handler.modes.select_quick_card(key,101,card_id)[0]
    assert handler.modes.select_quick_card(key,2,'official')[0]
    with sqlite3.connect(handler.db.db_path) as conn:
        assert context_in(conn,key,'quick').variant == 'friendly'
        assert conn.execute('SELECT 1 FROM custom_match_cards WHERE match_key=? AND card_id=?',(key,card_id)).fetchone()


def test_custom_only_player_can_open_collection(scene):
    _,handler,_=scene
    with sqlite3.connect(handler.db.db_path) as conn:
        conn.execute('DELETE FROM player_cards WHERE user_id=101')
    assert not handler.db.get_player_cards(101)
    update,bot=event('my_cards')
    asyncio.run(handler.my_cards_handler(update,SimpleNamespace()))
    assert 'mycards_custom_1' in {b.callback_data for b in buttons(bot)}
