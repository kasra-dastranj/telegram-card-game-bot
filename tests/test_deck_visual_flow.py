import asyncio
from io import BytesIO
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from PIL import Image
import pytest
from telegram import Update
from telegram.ext import CallbackQueryHandler

from bot import battle_visuals as visual
from bot.deck_reports import snapshot_deck_selection, load_in, victory_caption
from bot.main import TelegramCardBot
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.deck_presentation import DEFAULT_SLOGAN, PREFIX
from systems.deck_system import DeckSystem
from systems.game_mode_system import GameModeSystem


@pytest.fixture
def flow(tmp_path, monkeypatch):
    bot = TelegramCardBot.__new__(TelegramCardBot)
    bot.db = DatabaseManager(str(tmp_path / 'decks.db'))
    bot.modes = GameModeSystem(bot.db)
    for uid in (1, 2):
        bot.db.get_or_create_player(uid)
    for cid in 'abcd':
        bot.db.add_card(Card(cid, cid.upper(), CardRarity.NORMAL, 60, 30, 40, 20, []))
        bot.db.add_card_to_player(1, cid)
        path = tmp_path / (cid + '.png')
        Image.new('RGB', (90, 130), {'a':'red', 'b':'green', 'c':'blue', 'd':'orange'}[cid]).save(path)
        variant = bot.db.get_card_variant(cid, 'normal')
        bot.db.save_card_variant(cid, 'normal', dict(variant, image_path=str(path)))
        bot.modes.set_card_metadata(cid, series='تسترها' if cid in 'abc' else 'متفاوت')
    routes = []
    bot.setup_handlers(SimpleNamespace(add_handler=routes.append))
    context = SimpleNamespace(user_data={}, bot_data={}, bot=SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock()))
    renderer = Mock(wraps=visual.render_deck)
    monkeypatch.setattr(visual, 'render_deck', renderer)

    def click(data, uid=1, photo=False):
        query = SimpleNamespace(data=data, from_user=SimpleNamespace(id=uid), message=SimpleNamespace(photo=['photo'] if photo else []),
                                answer=AsyncMock(), edit_message_text=AsyncMock(), edit_message_caption=AsyncMock())
        update = Update(1, callback_query=query)
        matched = [r for r in routes if isinstance(r, CallbackQueryHandler) and r.check_update(update)]
        assert len(matched) == 1, data
        asyncio.run(matched[0].callback(update, context))
        return query

    def text(value):
        message = SimpleNamespace(text=value, reply_text=AsyncMock())
        asyncio.run(bot._deck_name_message_router(SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message), context))
        return message

    return bot, context, click, text, renderer


def create(flow):
    bot, context, click, text, renderer = flow
    click('deck_create')
    for cid in 'abc':
        click('deck_build_pick_' + cid)
    text('تیم MH [1]')
    assert context.user_data['deck_build']['waiting_slogan']
    assert bot.db.count_player_decks(1) == 0
    text('همینه قدرت تیم ما!')
    return bot.db.get_player_decks(1)[0]['deck_id']


def test_create_edit_view_deck_photo_caption_and_actual_synergy(flow):
    bot, context, click, text, renderer = flow
    deck_id = create(flow)
    assert 'deck_build' not in context.user_data
    assert bot.db.count_player_decks(1) == 1
    deck = bot.db.get_deck_by_id(deck_id)
    assert deck['victory_slogan'] == 'همینه قدرت تیم ما!'
    picture = context.bot.send_photo.await_args.kwargs
    assert picture['chat_id'] == 1
    assert 'تیم MH [1]' in picture['caption'] and '+7' in picture['caption']
    assert 'سه کارت از تسترها' in picture['caption']
    assert Image.open(BytesIO(picture['photo'].getvalue())).size == (1200, 760)
    assert [item['name'] for item in renderer.call_args.args[0]] == ['A', 'B', 'C']
    assert all(item['image'] for item in renderer.call_args.args[0])
    # Real callback routing from a photo uses edit_caption, including back/category.
    query = click('deck_edit_' + deck_id, photo=True)
    query.edit_message_caption.assert_awaited_once()
    query.edit_message_text.assert_not_awaited()
    click('deck_build_cat_normal_1', photo=True)
    click('deck_build_back_step1', photo=True)
    for cid in 'abd':
        click('deck_build_pick_' + cid, photo=True)
    assert bot.db.count_player_decks(1) == 1
    assert bot.db.get_deck_by_id(deck_id)['card_id_3'] == 'd'
    assert [item['name'] for item in renderer.call_args.args[0]] == ['A', 'B', 'D']
    assert '+5' in context.bot.send_photo.await_args.kwargs['caption']
    click('deck_rename_' + deck_id, photo=True)
    text('تیم جدید')
    assert 'تیم جدید' in context.bot.send_photo.await_args.kwargs['caption']
    click('deck_slogan_' + deck_id, photo=True)
    text('اینم برد ما!')
    before = context.bot.send_photo.await_count
    click('deck_view_' + deck_id)
    assert context.bot.send_photo.await_count == before + 1
    assert 'اینم برد ما!' in context.bot.send_photo.await_args.kwargs['caption']
    # Persisted values survive a new manager, without any schema/data startup writes.
    with sqlite3.connect(bot.db.db_path) as conn:
        previous = list(conn.iterdump())
    reopened = DatabaseManager(bot.db.db_path)
    assert reopened.get_deck_by_id(deck_id)['victory_slogan'] == 'اینم برد ما!'
    with sqlite3.connect(bot.db.db_path) as conn:
        assert previous == list(conn.iterdump())


def test_invalid_slogan_retries_cancel_stale_buttons_and_owner_checks(flow):
    bot, context, click, text, _ = flow
    click('deck_create')
    for cid in 'abc':
        click('deck_build_pick_' + cid)
    text('x' * 21).reply_text.assert_awaited_once()
    assert context.user_data['deck_build']['waiting_name']
    click('deck_build_skip_name')
    text('x' * 121).reply_text.assert_awaited_once()
    assert context.user_data['deck_build']['waiting_slogan']
    click('deck_build_skip_slogan')
    deck = bot.db.get_player_decks(1)[0]
    assert deck['victory_slogan'] == DEFAULT_SLOGAN
    click('deck_build_skip_slogan')  # Old button cannot create a duplicate.
    assert bot.db.count_player_decks(1) == 1
    click('deck_edit_' + deck['deck_id'], uid=2).answer.assert_awaited_once()
    assert not context.user_data.get('deck_build')
    click('deck_slogan_' + deck['deck_id'])
    click('deck_menu')
    text('این نباید ذخیره بشه')
    assert bot.db.get_deck_by_id(deck['deck_id'])['victory_slogan'] == DEFAULT_SLOGAN


def test_media_failure_preserves_deck_name_cards_bonuses_slogan_buttons(flow):
    bot, context, click, text, _ = flow
    context.bot.send_photo.side_effect = RuntimeError('offline media failure')
    deck_id = create(flow)
    assert bot.db.count_player_decks(1) == 1
    result = context.bot.send_message.await_args.kwargs
    assert all(value in result['text'] for value in ('تیم MH [1]', 'همینه قدرت تیم ما!', '+7', 'A (Normal)', 'B (Normal)', 'C (Normal)'))
    assert any(b.callback_data == 'deck_edit_' + deck_id for row in result['reply_markup'].inline_keyboard for b in row)


def test_legacy_deck_metadata_atomic_validation_cleanup_and_ownership(flow):
    bot, _, _, _, _ = flow
    deck_id = bot.db.create_deck(1, 'قدیمی', 'a', 'b', 'c')
    decks = DeckSystem(bot.db)
    assert not bot.db.get_deck_by_id(deck_id).get('victory_slogan')
    assert decks.get_valid_decks(1)[0]['deck_id'] == deck_id
    assert decks.update_deck(1, deck_id, victory_slogan='ما \u202e بردیم')[0]
    assert bot.db.get_deck_by_id(deck_id)['victory_slogan'] == 'ما بردیم'
    assert not decks.update_deck(2, deck_id, victory_slogan='نه')[0]
    assert not decks.update_deck(1, deck_id, name='جدید', victory_slogan=' ' * 4)[0]
    assert bot.db.get_deck_by_id(deck_id)['deck_name'] == 'قدیمی'
    with pytest.raises(ValueError):
        bot.db.create_deck(1, 'نباید ذخیره شه', 'a', 'b', 'c', victory_slogan='')
    assert bot.db.count_player_decks(1) == 1
    assert decks.delete_deck(1, deck_id)[0]
    with sqlite3.connect(bot.db.db_path) as conn:
        assert not conn.execute('SELECT 1 FROM foundation_settings WHERE key=?', (PREFIX + deck_id,)).fetchone()


def test_victory_uses_selected_deck_snapshot_after_edit_and_deletion(flow):
    bot, _, _, _, _ = flow
    deck_id = create(flow)
    fight = bot.db.create_fight(1, 2, -100, mode='deck')
    snapshot_deck_selection(bot.db.db_path, fight, 1, bot.db.get_deck_by_id(deck_id))
    bot.db.update_deck(deck_id, victory_slogan='شعار بعدی')
    snapshot_deck_selection(bot.db.db_path, fight, 1, bot.db.get_deck_by_id(deck_id))
    bot.db.delete_deck(deck_id)
    with sqlite3.connect(bot.db.db_path) as conn:
        report = load_in(conn, fight)
    assert 'همینه قدرت تیم ما!' in victory_caption(report, 1)
    assert 'شعار بعدی' not in victory_caption(report, 1)
    assert victory_caption(report, None) == 'این دست مساوی شد!'
    assert DEFAULT_SLOGAN in victory_caption({}, 1)


def test_deck_editor_refuses_changes_during_active_match_without_losing_deck(flow, monkeypatch):
    bot, context, click, _, _ = flow
    deck_id = create(flow)
    monkeypatch.setattr(bot, '_deck_edit_locked', lambda uid: True)
    query = click('deck_edit_' + deck_id, photo=True)
    assert query.answer.await_args.kwargs['show_alert']
    assert 'deck_build' not in context.user_data
    assert bot.db.get_deck_by_id(deck_id)['card_id_3'] == 'c'


def test_template_is_bundled_and_three_slots_render_without_external_assets():
    assert 'deck/template' in visual.resources()
    raw = visual.render_deck([], visual.resources()['deck/template'])
    assert Image.open(BytesIO(raw)).size == (1200, 760)


def test_pre_round_timeout_report_keeps_names_and_slogan(flow):
    bot, _, _, _, _ = flow
    deck_id = create(flow)
    fight = bot.db.create_fight(1, 2, -100, mode='deck')
    snapshot_deck_selection(bot.db.db_path, fight, 1, bot.db.get_deck_by_id(deck_id))
    from bot.deck_reports import finish, reward_lines
    from systems.match_rewards_system import MatchRewardsSystem
    with sqlite3.connect(bot.db.db_path) as conn:
        MatchRewardsSystem.award(conn, 'fight:' + fight, 'deck', {})
    report = finish(bot.db.db_path, fight, (1, 2), {'1': 'MH', '2': 'Varan'},
                    {'1': {'xp': 15}, '2': {'xp': 3}})
    assert 'MH' in reward_lines(report)
    assert 'همینه قدرت تیم ما!' in victory_caption(report, 1)


def test_miniapp_deck_updates_preserve_optional_slogan_and_enforce_ownership(flow, monkeypatch):
    bot, _, _, _, _ = flow
    import web.miniapp_api as miniapp
    monkeypatch.setattr(miniapp, 'db', bot.db)
    monkeypatch.setattr(miniapp, 'quick_modes', bot.modes)
    monkeypatch.setitem(miniapp.app.config, 'TESTING', True)
    monkeypatch.setitem(miniapp.app.config, 'DEBUG', True)
    client = miniapp.app.test_client()
    headers = {'X-Debug-User-Id': '1'}
    result = client.post('/api/v1/decks', json={'card_ids': list('abc'), 'name': 'API Deck', 'victory_slogan': 'ما بردیم!'}, headers=headers)
    assert result.status_code == 201
    deck_id = result.get_json()['data']['deck_id']
    result = client.put('/api/v1/decks/' + deck_id, json={'name': 'API 2'}, headers=headers)
    assert result.status_code == 200 and result.get_json()['data']['victory_slogan'] == 'ما بردیم!'
    assert client.put('/api/v1/decks/' + deck_id, json={'victory_slogan': 123}, headers=headers).status_code == 400
    assert client.put('/api/v1/decks/' + deck_id, json={'victory_slogan': 'نه'}, headers={'X-Debug-User-Id': '2'}).status_code == 403
    assert bot.db.get_deck_by_id(deck_id)['victory_slogan'] == 'ما بردیم!'
