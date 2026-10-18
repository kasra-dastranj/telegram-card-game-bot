import asyncio
import copy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.game_mode_system import GameModeSystem
from systems.easy_questions import default_catalog, catalog_in, save_catalog_in, formula_terms, CatalogConflict
from bot.handlers.game_modes import GameModeHandlersMixin
from web.web_api import WebAPI


@pytest.fixture
def modes(tmp_path):
    db = DatabaseManager(str(tmp_path / 'easy.db'))
    modes = GameModeSystem(db)
    for i in range(7):
        card = Card(f'c{i}', f'Card {i}', CardRarity.NORMAL, 20+i, 30+i, 40+i, 50+i, [])
        db.add_card(card)
        modes.set_card_metadata(card.card_id, traits=['hero'] if i == 0 else [],
                                hidden_stats={'scary': i+1, 'survival': 20+i, 'management': 10+i})
    for user in (1, 2, 3):
        db.get_or_create_player(user, first_name=f'P{user}')
        for i in range(7):
            db.add_card_to_player(user, f'c{i}')
    return modes


def save(modes, catalog):
    with modes._connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        return save_catalog_in(conn, catalog, 'offline-editor')


def begin(modes, question=None, rounds=1):
    req = modes.create_easy_lobby(1, -100, rounds)
    key = req['request_id']
    for uid in (2, 3):
        assert modes.join_easy_lobby(key, uid)[0]
    assert modes.start_easy_match(key)[0]
    if question:
        state = modes.get_state(key)
        state['question'] = question
        with modes._connect() as conn:
            modes._save_state(conn, key, state)
    return key


@pytest.mark.parametrize('expression', ["__import__('os')", 'scary * iq', 'scary / 0', '(scary + iq)',
    'scary + 20', 'unknown + iq', 'scary; iq', 'scary ** iq', 'scary + '])
def test_formula_rejects_code_and_unsupported_operators(expression):
    with pytest.raises(ValueError):
        formula_terms(expression, default_catalog()['stats'])


def test_catalog_edits_persist_and_revision_conflicts_do_not_overwrite(modes):
    catalog = default_catalog()
    catalog['stats']['strategy'] = 'استراتژی'
    catalog['questions'][0].update(text='کدوم تو زامبی‌ها به قدرت می‌رسه؟', formula='survival + management - scary')
    stored = save(modes, catalog)
    with modes._connect() as conn:
        assert catalog_in(conn) == stored
    assert GameModeSystem(modes.db)._easy_question_pool([1, 2])[0]['text'] == catalog['questions'][0]['text']
    with pytest.raises(CatalogConflict):
        save(modes, catalog)
    with modes._connect() as conn:
        assert catalog_in(conn)['revision'] == 1
    bad = copy.deepcopy(stored)
    for q in bad['questions']:
        q['enabled'] = False
    with pytest.raises(ValueError):
        save(modes, bad)


@pytest.mark.parametrize('choices,expected', [
    (['c0','c6','c5'], [1,2,3]),  # Right trait and scary=1 beats wrong trait and scary=7.
    (['c1','c6','c5'], [2,3,1]),  # Everyone wrong: compare the formula normally.
    (['c0','c0','c6'], [1,2,3]),  # Two matching ties share first, wrong follows.
])
def test_trait_priority_then_formula_includes_nonmatches(modes, choices, expected):
    key = begin(modes, {'id':'fixture','text':'ترسناک‌ترین قهرمان؟','formula':'scary','trait':'hero'})
    for uid, cid in zip((1,2,3), choices):
        assert len(modes.get_easy_options(key, uid)) == 7
        assert modes.select_easy_card(key, uid, cid)[0]
    entries = modes.resolve_easy_round(key)['round']['entries']
    assert [entry['user_id'] for entry in entries] == expected
    assert all(item['points'] > 0 for item in entries)
    if choices[0] == choices[1]:
        assert [item['points'] for item in entries] == [3,3,2]


def test_signed_formula_and_selected_values_are_frozen(modes):
    key = begin(modes, {'id':'fixture','text':'کدوم بهتره؟','formula':'management - survival - scary'})
    options = modes.get_easy_options(key, 1)
    assert len(options) == 5
    assert {c.card_id for c in options} == {c.card_id for c in modes.get_easy_options(key, 1)}
    selected = options[0].card_id
    assert modes.select_easy_card(key, 1, selected)[0]
    original = modes.get_state(key)['choice_scores']['1']
    modes.set_card_metadata(selected, traits=[], hidden_stats={'management':100,'survival':1,'scary':1})
    entries = modes.resolve_easy_round(key)['round']['entries']
    assert entries[0]['hidden_value'] == original['hidden_value'] < 0
    assert entries[0]['points'] == 3


def test_match_catalog_is_frozen_and_disabled_questions_do_not_reappear(modes):
    catalog = default_catalog()
    for q in catalog['questions']:
        q['enabled'] = q['id'] == 'scary'
    saved = save(modes, catalog)
    key = begin(modes, rounds=3)
    before = modes.get_state(key)['question']
    assert before['id'] == 'scary'
    saved['questions'][5].update(text='متن تازه', formula='management')
    save(modes, saved)
    result = modes.resolve_easy_round(key)
    assert result['state']['question'] == before
    assert GameModeSystem(modes.db).get_state(key)['question_catalog']['revision'] == 1


def test_common_trait_is_required_for_each_player_including_active_form(modes):
    from systems.card_trait_registry import save_variant_traits
    assert any(q.get('trait') == 'hero' for q in modes._easy_question_pool([1,2,3]))
    with modes._connect() as conn:
        save_variant_traits(conn, 'c0', 'epic', [])
    modes.db.set_player_card_rarity_override(3, 'c0', 'epic')
    assert not any(q.get('trait') == 'hero' for q in modes._easy_question_pool([1,2,3]))


def test_editor_api_requires_auth_validates_and_does_not_change_schema(modes, monkeypatch):
    monkeypatch.setenv('ADMIN_API_TOKEN', 'synthetic-test-only')
    monkeypatch.delenv('ARENA_ADMIN_TOKEN', raising=False)
    api = WebAPI(modes.db)
    client = api.app.test_client()
    headers = {'X-Admin-Token':'synthetic-test-only'}
    with modes._connect() as conn:
        schema = conn.execute('SELECT sql FROM sqlite_master ORDER BY name').fetchall()
    assert client.get('/api/easy/catalog').status_code == 403
    assert client.put('/api/easy/catalog', json=default_catalog()).status_code == 403
    catalog = client.get('/api/easy/catalog', headers=headers).get_json()['catalog']
    catalog['questions'].append(dict(id='zombie',text='کدوم تو دنیای زامبی‌ها به قدرت می‌رسه؟',
        formula='survival + management',enabled=True,filter='none',filter_value=''))
    response = client.put('/api/easy/catalog', json=catalog, headers=headers)
    assert response.status_code == 200 and response.get_json()['catalog']['revision'] == 1
    assert client.put('/api/easy/catalog', json=catalog, headers=headers).status_code == 409
    bad = copy.deepcopy(response.get_json()['catalog'])
    bad['questions'][0]['formula'] = 'iq * 999'
    assert client.put('/api/easy/catalog', json=bad, headers=headers).status_code == 400
    assert client.get('/api/card-editor/options').get_json()['easy_stats']['survival']
    with modes._connect() as conn:
        assert [tuple(row) for row in conn.execute('SELECT sql FROM sqlite_master ORDER BY name')] == [tuple(row) for row in schema]


def test_easy_custom_choice_menu_is_visible_and_disabled_yes_does_not_create_lobby(modes):
    handler = GameModeHandlersMixin()
    handler.db, handler.modes = modes.db, modes
    handler._schedule_mode_job = Mock()
    query = SimpleNamespace(data='gm_erounds_3', from_user=SimpleNamespace(id=1),
        message=SimpleNamespace(chat=SimpleNamespace(type='group'),chat_id=-100,message_id=4),
        answer=AsyncMock(),edit_message_text=AsyncMock())
    context=SimpleNamespace()
    asyncio.run(handler.easy_round_count_handler(SimpleNamespace(callback_query=query),context))
    buttons=query.edit_message_text.await_args.kwargs['reply_markup'].inline_keyboard[0]
    assert [b.callback_data for b in buttons] == ['gm_erounds_3_no','gm_erounds_3_yes']
    query.data='gm_erounds_3_yes'
    asyncio.run(handler.easy_round_count_handler(SimpleNamespace(callback_query=query),context))
    assert query.answer.await_args.kwargs['show_alert'] is True
    handler._schedule_mode_job.assert_not_called()
    query.data='gm_erounds_3_no'
    asyncio.run(handler.easy_round_count_handler(SimpleNamespace(callback_query=query),context))
    assert handler._schedule_mode_job.call_count == 1


def test_trait_picker_paginates_all_cards_without_filtering_the_answer(modes):
    handler = GameModeHandlersMixin()
    cards = [SimpleNamespace(card_id=f'card{i}',name=f'C{i}') for i in range(107)]
    handler.modes = SimpleNamespace(get_easy_options=Mock(return_value=cards))
    handler._get_inline_card_sticker_file_id=AsyncMock(return_value=None)
    handler._get_inline_card_photo_file_id=AsyncMock(return_value=None)
    all_ids=[]
    for offset, next_offset in (('', '50'), ('50','100'), ('100','')):
        query=SimpleNamespace(query='easy match',offset=offset,from_user=SimpleNamespace(id=1),answer=AsyncMock())
        asyncio.run(handler.easy_inline_query_handler(SimpleNamespace(inline_query=query),SimpleNamespace()))
        result=query.answer.await_args
        all_ids += [r.id.rsplit('|',1)[-1] for r in result.args[0]]
        assert result.kwargs['next_offset'] == next_offset and len(result.args[0]) <= 50
    assert all_ids == [card.card_id for card in cards]


def test_late_selection_is_rejected_without_consuming_the_next_round(modes):
    key = begin(modes, {'id':'fixture','text':'کدوم؟','formula':'scary'})
    options = modes.get_easy_options(key, 1)
    state = modes.get_state(key)
    state['deadline'] = (datetime.now() - timedelta(days=1)).isoformat()
    with modes._connect() as conn:
        modes._save_state(conn, key, state)
    ok, reason, state = modes.select_easy_card(key, 1, options[0].card_id)
    assert not ok and reason == 'expired' and state['choices'] == {}
    assert modes.resolve_easy_round(key)['round']['entries'] == []
