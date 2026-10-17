import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.game_modes import GameModeHandlersMixin
from bot.deck_reports import load_in, detail_text, round_snapshot_in
from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.game_mode_system import GameModeSystem
from systems.battle_system_3rounds import BattleSystem3Rounds
from systems.progression_config import seed_config, save_config_in


def readable(text):
    return text.translate(str.maketrans('', '', '\u2066\u2068\u2069'))


@pytest.mark.parametrize('variant', ['normal', 'random'])
def test_deck_group_invite_keeps_accept_button_and_short_copy(tmp_path, variant):
    handler = GameModeHandlersMixin()
    handler.db = DatabaseManager(str(tmp_path / 'invite.db'))
    handler.db.get_or_create_player(1, first_name='MH')
    handler.modes = GameModeSystem(handler.db)
    handler._schedule_mode_job = Mock()
    query = SimpleNamespace(data=f'gm_variant_deck_{variant}', from_user=SimpleNamespace(id=1, first_name='MH'),
                            message=SimpleNamespace(chat=SimpleNamespace(type='group'), chat_id=-100, message_id=5),
                            answer=AsyncMock(), edit_message_text=AsyncMock())
    asyncio.run(handler.game_variant_handler(SimpleNamespace(callback_query=query), SimpleNamespace()))
    call = query.edit_message_text.await_args
    assert readable(call.args[0]) == f'⚔️ کی حاضره نبرد Deck-{variant.title()} با MH رو بپذیره؟\n⏳ مهلت پذیرش: 60 ثانیه'
    button = call.kwargs['reply_markup'].inline_keyboard[0][0]
    assert button.text == '✊ قبول مبارزه' and button.callback_data.startswith('gm_accept_')
    assert handler._schedule_mode_job.call_args.args[2] == 60


@pytest.mark.parametrize('policy', ['legacy', 'v2', 'v2_two_hearts'])
@pytest.mark.parametrize('inline', [False, True])
@pytest.mark.parametrize('with_photo', [False, True])
def test_three_round_deck_final_and_private_history_survive_fight_deletion_and_card_edits(tmp_path, monkeypatch, policy, inline, with_photo):
    db = DatabaseManager(str(tmp_path / 'deck.db'))
    modes = GameModeSystem(db)
    if policy != 'legacy':
        with sqlite3.connect(db.db_path) as conn:
            conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
            if policy == 'v2_two_hearts':
                config = seed_config()
                config['match']['deck']['loss_hearts'] = 2
                save_config_in(conn, config, 'offline-test')
    for uid, name in ((1, 'MH'), (2, 'Varan')):
        db.get_or_create_player(uid, first_name=name)
    definitions = [('a', 'Mamooti', 'normal', 90, 20, 30, 55, []),
                   ('b', 'Blue Hero', 'normal', 10, 20, 100, 10, ['hero']),
                   ('c', 'Blue Last', 'epic', 20, 30, 40, 65, []),
                   ('d', 'Heshmat Ferdous', 'epic', 95, 20, 30, 60, []),
                   ('e', 'Red Leader', 'normal', 10, 100, 20, 90, ['leader']),
                   ('f', 'Red Last', 'normal', 10, 20, 100, 60, [])]
    for cid, name, form, power, speed, iq, popularity, traits in definitions:
        db.add_card(Card(cid, name, CardRarity(form), power, speed, iq, popularity, []))
        db.add_card_to_player(1 if cid in 'abc' else 2, cid)
        modes.set_card_metadata(cid, traits=traits, series='چهره‌های ایرانی' if cid in 'de' else None)
    key = db.create_fight(1, 2, -100, mode='deck')
    arena = {'name_fa': 'صحنه', 'emoji': '⭐', 'compare_stat': 'popularity',
             'trait_ranks': [['hero', 'funny'], ['leader', 'villain'], ['monster']],
             'stat_tiebreak_enabled': True}
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("""INSERT INTO battle_states
            (fight_id,challenger_id,opponent_id,challenger_card_id,opponent_card_id,
             arena,challenger_current_stats,opponent_current_stats,status,created_at,
             challenger_deck_cards,opponent_deck_cards)
            VALUES (?,1,2,'a','d','stage','{}','{}','round_1','2026-10-16','["a","b","c"]','["d","e","f"]')""", (key,))
    handler = BattleHandlersMixin()
    handler.db, handler.modes, handler.battle3 = db, modes, BattleSystem3Rounds(db)
    handler._battle_arena_snapshot = Mock(return_value=arena)
    handler._arena_runtime_for_fight = Mock(return_value=arena)
    handler._send_next_round_card_selection = AsyncMock()
    context = SimpleNamespace(bot_data={
        f'deck_{key}_inline_message_id': 'friend-invite'} if inline else {
        f'deck_{key}_status_message': {'chat_id': -100, 'message_id': 77}},
        bot=SimpleNamespace(edit_message_text=AsyncMock(), send_message=AsyncMock()))
    if with_photo:
        context.bot.send_photo = AsyncMock()
        from bot import battle_visuals
        from unittest.mock import Mock as Capture
        renderer = Capture(wraps=battle_visuals.render_result)
        monkeypatch.setattr(battle_visuals, 'render_result', renderer)
    before = db.get_or_create_player(2).hearts
    from systems.legacy_fight_rewards_system import LegacyFightRewardsSystem
    from systems.match_activity import active_in
    settle = LegacyFightRewardsSystem.settle_three_round

    def settle_while_still_busy(self, *args, **kwargs):
        with sqlite3.connect(db.db_path) as conn:
            assert conn.execute('SELECT status FROM battle_states WHERE fight_id=?', (key,)).fetchone()[0] == 'settling'
            assert active_in(conn, 1) and active_in(conn, 2)
        return settle(self, *args, **kwargs)

    monkeypatch.setattr(LegacyFightRewardsSystem, 'settle_three_round', settle_while_still_busy)
    for number, ch_cid, op_cid, ch_wins, op_wins in ((1, 'a', 'd', 0, 0), (2, 'b', 'e', 0, 1), (3, 'c', 'f', 1, 1)):
        ch_card, op_card = db.get_card_by_id_for_player(ch_cid, 1), db.get_card_by_id_for_player(op_cid, 2)
        asyncio.run(handler._resolve_deck_round(context, key, 1, 2, ch_card, op_card,
                                               'stage', number, ch_wins, op_wins, [], [], {}, {}))
    assert db.get_fight_by_id(key) is None
    final = context.bot.edit_message_text.await_args.kwargs
    text = readable(final['text'])
    assert text.startswith('بازی تمام شد، مبارک خیلیا\n\n🏟️ زمین: ⭐ صحنه')
    assert 'T1: قهرمان/کمدی\nT2: رهبر/شرور\nT3: هیولا' in text
    assert 'معیار برد دوم: ❤️ محبوبیت بیشتر' in text
    assert 'برنده راوند ۱: Varan\nبرنده راوند ۲: MH\nبرنده راوند ۳: MH' in text
    assert 'MH: 10 + 0 = 10' in text and 'Varan: 5 + 2 = 7' in text
    assert '🏆 MH  |  10 — 7' in text
    expected_win_xp = 10 if policy == 'legacy' else 15
    expected_hearts = 2 if policy == 'v2_two_hearts' else 1
    assert f'⭐ MH: +{expected_win_xp} XP' in text
    assert f'⭐ Varan: +3 XP · -{expected_hearts} ❤️' in text
    assert db.get_or_create_player(2).hearts == before - expected_hearts
    assert 'Mamooti' not in text and 'Trait tier' not in text and 'نتیجه راند قبل' not in text
    button = final['reply_markup'].inline_keyboard[0][0]
    assert button.callback_data == f'deck_report_{key}'
    if inline:
        assert final['inline_message_id'] == 'friend-invite'
    else:
        assert final['chat_id'] == -100 and final['message_id'] == 77
    if with_photo:
        assert [call.kwargs['chat_id'] for call in context.bot.send_photo.await_args_list] == [1, 2]
        from PIL import Image
        assert Image.open(context.bot.send_photo.await_args.kwargs['photo']).size == (1200, 1080)
        model = renderer.call_args.args[0]
        assert [p['score'] for p in model['players']] == [10, 7]
        assert [len(p['cards']) for p in model['players']] == [3, 3]
        assert model['players'][1]['cards'][0]['rarity'] == 'epic'
        assert model['players'][1]['reward']['hearts_lost'] == expected_hearts
        assert model['players'][1]['equation'] == '5 + 2 = 7'
        assert len(model['round_lines']) == 3 and model['winner_name'] == 'MH'
        context.bot.send_message.assert_not_awaited()
    else:
        assert [call.kwargs['chat_id'] for call in context.bot.send_message.await_args_list] == [1, 2]
    context.bot.send_message.reset_mock()
    # A new handler after restart reads the saved cards, forms and causes.
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE cards SET name='Edited later ' || card_id,popularity=1")
    restored = BattleHandlersMixin()
    restored.db = DatabaseManager(db.db_path)
    query = SimpleNamespace(data=button.callback_data, from_user=SimpleNamespace(id=1), answer=AsyncMock())
    asyncio.run(restored.deck_report_handler(SimpleNamespace(callback_query=query), context))
    details = readable(context.bot.send_message.await_args.kwargs['text'])
    assert context.bot.send_message.await_args.kwargs['chat_id'] == 1
    assert all(f'برنده راوند {number}' in details for number in ('۱', '۲', '۳'))
    assert 'Mamooti (🟢 Normal)' in details and 'Heshmat Ferdous (🟣 Epic)' in details
    assert 'محبوبیت: ۵۵' in details and 'محبوبیت: ۶۰' in details
    assert 'علت برد: تریت با اولویت بالاتر' in details and 'اولویت تریت: T1' in details
    assert '5 + 2 = 7' in details and 'دو کارت از چهره‌های ایرانی' in details
    assert 'Edited later' not in details
    for uid in (2, 999):
        context.bot.send_message.reset_mock()
        query.from_user.id = uid
        asyncio.run(restored.deck_report_handler(SimpleNamespace(callback_query=query), context))
        if uid == 2:
            assert context.bot.send_message.await_args.kwargs['chat_id'] == 2
        else:
            query.answer.assert_awaited_with('گزارش برای شما در دسترس نیست.', show_alert=True)
            context.bot.send_message.assert_not_awaited()


@pytest.mark.parametrize('stat,label', [('power', 'قدرت'), ('speed', 'سرعت'), ('iq', 'هوش'), ('popularity', 'محبوبیت')])
@pytest.mark.parametrize('equal', [False, True])
def test_private_report_names_the_actual_compared_stat_and_ties(tmp_path, stat, label, equal):
    db = DatabaseManager(str(tmp_path / 'stats.db'))
    GameModeSystem(db)
    cards = [Card('a', 'First', CardRarity.NORMAL, 30, 30, 30, 30, []),
             Card('b', 'Second', CardRarity.EPIC, 30, 30, 30, 30, [])]
    for card in cards:
        db.add_card(card)
    if not equal:
        setattr(cards[1], stat, 45)
    arena = {'compare_stat': stat, 'trait_ranks': [], 'stat_tiebreak_enabled': True}
    result = BattleSystem3Rounds(db).resolve_deck_cards(*cards, 'stage', arena)
    with sqlite3.connect(db.db_path) as conn:
        round_snapshot_in(conn, 'stat-test', (1, 2), {'1': 'MH', '2': 'Varan'}, arena, 1, result, cards)
        report = load_in(conn, 'stat-test')
    text = readable(detail_text(report))
    assert f'{label}: ۳۰' in text
    assert 'First (🟢 Normal)' in text and 'Second (🟣 Epic)' in text
    if equal:
        assert 'برنده راوند ۱: مساوی' in text and 'نتیجهٔ مقایسه: مساوی' in text
        assert 'علت برد:' not in text
    else:
        assert f'{label}: ۴۵' in text and f'علت برد: {label} بیشتر' in text
        assert 'برنده راوند ۱: Varan' in text
