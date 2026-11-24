import sqlite3
from contextlib import closing
from io import BytesIO

import pytest
from PIL import Image

from tests.test_avatar_cosmetics import scene,raw,scalar
from systems import avatar_cosmetics as art,card_avatars
from core.database import DatabaseManager
from systems.card_inventory_system import CardInventorySystem as Inventory
from web.web_api import WebAPI


def create(db,key='first',color='cyan',**changes):
    data=dict(face_id=key,title='چهره '+key,filename=art.upload(db,raw(color),transparent=True),
              enabled=True,sort_order=5,scale=1,offset_x=0,offset_y=0)
    data.update(changes)
    return art.save_free_face(db,'synthetic-owner',data)


def select(db,key,user=2,slot='profile',**changes):
    data=dict(slot=slot,inherit_profile=False,free_face_id=key,card_id=None,rarity=None,
              frame_id='silver',background_id='red')
    data.update(changes)
    return art.save_style(db,user,data)


def defaults(db,key):
    art.set_defaults(db,'owner',dict(face=key,frame='silver',background='red'))


def test_free_heads_available_to_all_without_card_or_wallet_mutations(scene):
    db=scene
    with closing(sqlite3.connect(db.db_path)) as conn:
        before={t:conn.execute('SELECT * FROM '+t).fetchall() for t in ('players','player_card_stacks','player_avatar_items','reward_ledger')}
    create(db);create(db,'second','lime')
    catalog=art.catalog(db,2)
    assert [f['free_face_id'] for f in catalog['faces']]==['generic','first','second']
    assert not any(f['card_id']=='hero' for f in catalog['faces'])
    select(db,'first');select(db,'second')
    with closing(sqlite3.connect(db.db_path)) as conn:
        assert all(conn.execute('SELECT * FROM '+t).fetchall()==rows for t,rows in before.items())
    assert art.catalog(db,2)['selections']['profile']['face']['free_face_id']=='second'


def test_owner_default_changes_unselected_users_preserves_explicit_card_and_free_choices(scene):
    db=scene;create(db);create(db,'second','lime');defaults(db,'first')
    assert all(s['face']['free_face_id']=='first' for s in art.catalog(db,2)['selections'].values())
    card_avatars.save_choice(db,1,'profile','hero','legend')
    select(db,'first')
    defaults(db,'second')
    assert art.catalog(db,2)['selections']['profile']['face']['free_face_id']=='first'
    assert art.catalog(db,1)['selections']['profile']['face']['card_id']=='hero'
    db.get_or_create_player(3)
    assert art.catalog(db,3)['selections']['profile']['face']['free_face_id']=='second'
    with closing(sqlite3.connect(db.db_path)) as conn:before=list(conn.iterdump())
    DatabaseManager(db.db_path)
    with closing(sqlite3.connect(db.db_path)) as conn:assert list(conn.iterdump())==before


def test_lost_card_disabled_or_missing_free_head_falls_back_to_owner_default(scene):
    db=scene;first=create(db);second=create(db,'second','lime');defaults(db,'first')
    card_avatars.save_choice(db,1,'profile','hero','legend')
    with closing(sqlite3.connect(db.db_path)) as conn,conn:Inventory.consume_in(conn,1,'hero','legend')
    assert art.catalog(db,1)['selections']['profile']['face']['free_face_id']=='first'
    select(db,'second')
    art.save_free_face(db,'owner',{**second,'enabled':False})
    assert art.catalog(db,2)['selections']['profile']['face']['free_face_id']=='first'
    (art.root(db)/second['filename']).unlink()
    (art.root(db)/first['filename']).unlink()
    assert art.catalog(db,2)['selections']['profile']['face']['free_face_id']=='generic'
    Image.open(BytesIO(art.render(db,2))).verify()


def test_default_cannot_be_disabled_and_legacy_default_api_preserves_head(scene):
    db=scene;first=create(db);defaults(db,'first')
    with pytest.raises(ValueError):art.save_free_face(db,'owner',{**first,'enabled':False})
    art.set_defaults(db,'owner',dict(frame='silver',background='blue'))
    assert art.catalog(db,2)['selections']['profile']['face']['free_face_id']=='first'
    with pytest.raises(ValueError):defaults(db,'missing')
    assert art.catalog(db,2)['selections']['profile']['background']['item_id']=='blue'


def test_free_head_independent_slots_and_existing_bot_card_picker(scene):
    db=scene;create(db);create(db,'second','lime')
    select(db,'first',user=1)
    assert art.catalog(db,1)['selections']['deck']['face']['free_face_id']=='first'
    select(db,'second',user=1,slot='deck')
    assert art.catalog(db,1)['selections']['deck']['face']['free_face_id']=='second'
    card_avatars.save_choice(db,1,'deck','hero','legend')
    assert art.catalog(db,1)['selections']['deck']['face']['card_id']=='hero'
    assert scalar(db,"SELECT count(*) FROM player_avatar_free_choices WHERE user_id=1 AND slot='deck'")==0
    select(db,'second',user=1,slot='deck',inherit_profile=True)
    assert art.catalog(db,1)['selections']['deck']['face']['free_face_id']=='first'


def test_replacing_free_image_invalidates_cached_render_and_keeps_choices(scene):
    db=scene;first=create(db);select(db,'first')
    before=art.render(db,2)
    newer={**first,'filename':art.upload(db,raw('lime'),transparent=True),'scale':.8,'enabled':True}
    art.save_free_face(db,'owner',newer)
    assert art.render(db,2)!=before
    face=art.catalog(db,2)['selections']['profile']['face']
    assert face['free_face_id']=='first' and face['scale']==.8
    with pytest.raises(ValueError,match='ویرایش'):art.save_free_face(db,'owner',newer)


@pytest.mark.parametrize('key',['missing','disabled','generic;DROP TABLE players'])
def test_unavailable_or_forged_free_selection_never_changes_saved_choice(scene,key):
    db=scene;create(db);create(db,'disabled',enabled=False);select(db,'first')
    with pytest.raises(ValueError):select(db,key)
    assert art.catalog(db,2)['selections']['profile']['face']['free_face_id']=='first'
    with pytest.raises(ValueError):select(db,'first',card_id='hero',rarity='legend')


def test_paid_cosmetics_still_card_independent_and_free_heads_not_sale_products(scene):
    db=scene;create(db,'gold');defaults(db,'gold')
    from systems.progression_economy import ProgressionEconomy
    # A face named gold does not make the separately named Gold frame a default.
    with closing(sqlite3.connect(db.db_path)) as conn:item=art.item_in(conn,'gold')
    item.update(free=False,enabled=False,for_sale=True)
    art.save_item(db,'owner',item)
    assert not ProgressionEconomy(db).quote(2,'avatar:first')['ok']


def test_existing_avatar_schema_migrates_without_resetting_old_choices(scene):
    db=scene;card_avatars.save_choice(db,1,'profile','hero','legend')
    with closing(sqlite3.connect(db.db_path)) as conn,conn:
        conn.execute('DROP TABLE avatar_free_faces');conn.execute('DROP TABLE player_avatar_free_choices')
        conn.execute("DELETE FROM avatar_settings WHERE key='face'")
        before=conn.execute('SELECT * FROM player_avatar_choices').fetchall()
    DatabaseManager(db.db_path)
    with closing(sqlite3.connect(db.db_path)) as conn:
        assert conn.execute('SELECT * FROM player_avatar_choices').fetchall()==before
    assert art.catalog(db,1)['selections']['profile']['face']['card_id']=='hero'


def test_free_heads_admin_authority_player_api_and_image_access(scene,monkeypatch):
    db=scene;monkeypatch.setenv('ADMIN_API_TOKEN','synthetic-free-admin')
    client=WebAPI(db).app.test_client();headers={'X-Admin-Token':'synthetic-free-admin'}
    body=dict(face_id='public-head',title='چهرهٔ رایگان',filename=art.upload(db,raw('cyan'),transparent=True),enabled=True,sort_order=1,scale=1,offset_x=0,offset_y=0)
    assert client.post('/api/avatar-admin/free-faces',json=body).status_code==403
    assert client.post('/api/avatar-admin/free-faces',json=body,headers=headers).status_code==200
    assert client.put('/api/avatar-admin/defaults',json={'face':'public-head','frame':'silver','background':'red'},headers=headers).status_code==200
    assert client.post('/api/avatar-admin/preview',json={'free_face_id':'public-head'},headers=headers).mimetype=='image/png'
    import web.miniapp_api as mini
    monkeypatch.setattr(mini,'db',db);monkeypatch.setattr(mini.app,'debug',True)
    player=mini.app.test_client();h={'X-Debug-User-Id':'2'}
    assert player.get('/api/v1/avatar/free-face/public-head',headers=h).mimetype=='image/png'
    assert player.get('/api/v1/avatar',headers=h).json['selections']['profile']['face']['free_face_id']=='public-head'
    data=dict(slot='profile',inherit_profile=False,free_face_id='public-head',frame_id='silver',background_id='red')
    assert player.put('/api/v1/avatar',json=data,headers=h).status_code==200
    assert player.get('/api/v1/avatar/face/hero/legend',headers=h).status_code==404
    monkeypatch.setattr(mini.app,'debug',False);monkeypatch.delenv('FLASK_DEBUG',raising=False)
    assert player.get('/api/v1/avatar/free-face/public-head').status_code==401
