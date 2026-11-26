import json
import sqlite3

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.easy_questions import default_catalog, evaluate_card, save_catalog_in
from systems.game_mode_system import GameModeSystem


def test_leading_negative_survives_save_reload_and_ranks_lower_iq_first(tmp_path):
    db = DatabaseManager(str(tmp_path / 'negative.db'))
    modes = GameModeSystem(db)
    for cid, iq in [('smart', 90), ('less_smart', 20)]:
        db.add_card(Card(cid, cid, CardRarity.NORMAL, 1, 2, 3, 4, []))
        modes.set_card_metadata(cid, hidden_stats={'iq': iq, 'cute': 50})
    catalog = default_catalog()
    catalog['questions'][0]['formula'] = '-iq + cute'
    with modes._connect() as conn:
        saved = save_catalog_in(conn, catalog, 'test')
    question = saved['questions'][0]
    assert question['formula'] == '- iq + cute'
    reopened = GameModeSystem(db)
    results = [evaluate_card(reopened, db.get_card_by_id(cid), question)
               for cid in ('smart', 'less_smart')]
    assert [result['hidden_value'] for result in results] == [-40, 30]
    catalog = saved
    catalog['questions'][0]['formula'] = '-iq'
    with modes._connect() as conn:
        assert save_catalog_in(conn, catalog, 'test')['questions'][0]['formula'] == '- iq'


def test_backfill_uses_legend_or_single_form_once_and_keeps_manual_values(tmp_path):
    db = DatabaseManager(str(tmp_path / 'backfill.db'))
    for cid, rarity in [('hero', CardRarity.NORMAL), ('rare', CardRarity.RARE), ('custom', CardRarity.LEGEND)]:
        db.add_card(Card(cid, cid, rarity, 2, 3, 4, 5, []))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE cards SET origin='custom' WHERE card_id='custom'")
        conn.execute("UPDATE card_variants SET power=10,speed=6,iq=8,popularity=9 WHERE card_id='hero' AND rarity='legend'")
    modes = GameModeSystem(db)
    expected = dict(power=100, speed=60, iq=80, popularity=90)
    for rarity in ('normal', 'epic', 'legend'):
        assert modes.get_card_metadata('hero', rarity)['hidden_stats'] == expected
    assert modes.get_card_metadata('rare')['hidden_stats'] == dict(power=20, speed=30, iq=40, popularity=50)
    assert modes.get_card_metadata('custom')['hidden_stats'] == dict(power=20, speed=30, iq=40, popularity=50)
    modes.set_card_metadata('hero', hidden_stats={'speed': 77, 'cute': 55})
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE card_variants SET power=1,speed=1,iq=1,popularity=1 WHERE card_id='hero'")
        conn.execute("UPDATE cards SET power=1,speed=1,iq=1,popularity=1 WHERE card_id='hero'")
    reopened = GameModeSystem(db)
    assert reopened.get_card_metadata('hero')['hidden_stats'] == {**expected, 'speed': 77, 'cute': 55}
    for rarity in ('normal', 'epic', 'legend'):
        card = db.get_card_by_id_for_rarity('hero', rarity)
        assert reopened._hidden_stat_value(card, 'power') == 100
        assert reopened._hidden_stat_value(card, 'speed') == 77
    # Blank cells in an older metadata row are filled without replacing other fields.
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE card_mode_metadata SET hidden_stats=? WHERE card_id='hero'",
                     (json.dumps({'speed': None, 'power': 31, 'cute': 55}),))
    assert GameModeSystem(db).get_card_metadata('hero')['hidden_stats'] == {
        'power': 31, 'speed': 10, 'iq': 10, 'popularity': 10, 'cute': 55,
    }
