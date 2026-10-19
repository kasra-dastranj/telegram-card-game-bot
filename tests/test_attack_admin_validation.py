"""The activity threshold is independent of a solo or squad enemy count."""
import copy
import sqlite3

import pytest

from systems.attack_catalog import defaults,example,catalog_in,save_in
from tests.test_group_attacks import scene


@pytest.mark.parametrize('minimum',[None,0,1,4.5,True,'4'])
def test_invalid_activity_names_attack_and_explains_range_without_saving(scene,minimum):
    db,_=scene
    catalog=defaults();attack=example();attack['title']='حملهٔ تک‌نفرهٔ تست'
    attack['min_active']=minimum;catalog['attacks']=[attack]
    with sqlite3.connect(db.db_path) as conn:
        before=catalog_in(conn)
        with pytest.raises(ValueError) as failure:save_in(conn,catalog,'admin')
        message=str(failure.value)
        assert attack['title'] in message
        assert 'حداقل بازیکنان فعال امروز گروه' in message
        assert '4' in message and '10000' in message
        assert 'min_active' not in message
        assert catalog_in(conn)==before


@pytest.mark.parametrize('enemies',[1,4])
def test_four_active_players_can_enable_either_solo_or_squad_definition(scene,enemies):
    db,_=scene
    catalog=defaults();attack=example()
    attack['enemies']=[copy.deepcopy(attack['enemies'][0]) for _ in range(enemies)]
    catalog['attacks']=[attack]
    with sqlite3.connect(db.db_path) as conn:
        saved=save_in(conn,catalog,'admin')
        assert saved['attacks'][0]['min_active']==4
        assert len(catalog_in(conn)['attacks'][0]['enemies'])==enemies
