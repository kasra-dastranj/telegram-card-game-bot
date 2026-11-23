import sqlite3
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems import avatar_cosmetics as art, card_avatars
from systems.card_inventory_system import CardInventorySystem as Inventory
from systems.progression_economy import ProgressionEconomy
from web.web_api import WebAPI


def raw(color='red', opaque=False):
    image=Image.new('RGBA',(128,128),color if opaque else (0,0,0,0))
    if not opaque:ImageDraw.Draw(image).ellipse((35,25,95,100),fill=color)
    out=BytesIO();image.save(out,'PNG');return out.getvalue()


@pytest.fixture
def scene(tmp_path):
    db=DatabaseManager(str(tmp_path/'avatars.db'))
    for user in (1,2):db.get_or_create_player(user,first_name='Test')
    db.add_card(Card('hero','Hero',CardRarity.NORMAL,10,20,30,40,[]))
    db.save_card_variant('hero','legend',dict(power=40,speed=40,iq=40,popularity=40))
    db.add_card(Card('rare','Rare',CardRarity.RARE,10,20,30,40,[]))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json='true' WHERE key='progression_v2_enabled'")
        conn.execute('UPDATE players SET coins=2000')
        Inventory.grant_in(conn,1,'hero','legend')
        Inventory.grant_in(conn,1,'rare','rare')
        Inventory.grant_in(conn,2,'hero','normal')
    card_avatars.save_upload(db,'hero','legend',raw('yellow'),kind='portrait')
    card_avatars.save_upload(db,'rare','rare',raw('green'),kind='portrait')
    return db


def item(db,key='gold',**changes):
    with sqlite3.connect(db.db_path) as conn:
        value=art.item_in(conn,key)
    for field in ('free','enabled','for_sale'):value[field]=bool(value[field])
    value.update(changes)
    return art.save_item(db,'synthetic-admin',value)


def ready_gold(db):
    return item(db,filename=art.upload(db,raw('cyan'),transparent=True))


def save(db,face='hero',rarity='legend',slot='profile',frame='silver',bg='red',inherit=False):
    return art.save_style(db,1,dict(slot=slot,inherit_profile=inherit,card_id=face,rarity=rarity,
                                   frame_id=frame,background_id=bg))


def scalar(db,sql,args=()):
    with sqlite3.connect(db.db_path) as conn:return conn.execute(sql,args).fetchone()[0]


def test_defaults_migration_existing_and_new_users_is_repeatable(scene):
    db=scene
    before=scalar(db,'SELECT coins FROM players WHERE user_id=1')
    first=art.catalog(db,1)
    assert len([i for i in first['items'] if i['owned']])==5
    assert len(first['faces'])==3
    assert len(art.catalog(db,2)['faces'])==1
    save(db,bg='purple')
    DatabaseManager(db.db_path)
    assert art.catalog(db,1)['selections']['profile']['background']['item_id']=='purple'
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==before
    db.get_or_create_player(3)
    assert len([i for i in art.catalog(db,3)['items'] if i['owned']])==5
    with sqlite3.connect(db.db_path) as conn:
        before=list(conn.iterdump())
    DatabaseManager(db.db_path)
    with sqlite3.connect(db.db_path) as conn:
        assert before==list(conn.iterdump())


def test_first_rollout_backfills_existing_players_once_without_resetting_choices(scene):
    db=scene;save(db,bg='purple')
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("DELETE FROM avatar_settings WHERE key='defaults_backfilled_v1'")
        conn.execute('DELETE FROM player_avatar_items')
        wallet=conn.execute('SELECT * FROM players ORDER BY user_id').fetchall()
    DatabaseManager(db.db_path)
    assert scalar(db,'SELECT count(*) FROM player_avatar_items')==10
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT * FROM players ORDER BY user_id').fetchall()==wallet
    assert art.catalog(db,1)['selections']['profile']['background']['item_id']=='purple'


def test_cosmetic_purchase_does_not_unlock_character_or_change_game_stats(scene):
    db=scene;ready_gold(db);economy=ProgressionEconomy(db)
    with sqlite3.connect(db.db_path) as conn:
        cards=conn.execute('SELECT * FROM player_card_stacks').fetchall()
        stats=conn.execute('SELECT total_score,hearts,max_hearts FROM players WHERE user_id=2').fetchone()
        xp=conn.execute('SELECT total_xp FROM player_progression WHERE user_id=2').fetchone()
    quote=economy.quote(2,'avatar:gold');assert quote['ok']
    assert economy.purchase(2,quote['quote_id'])['ok']
    assert len(art.catalog(db,2)['faces'])==1
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT * FROM player_card_stacks').fetchall()==cards
        assert conn.execute('SELECT total_score,hearts,max_hearts FROM players WHERE user_id=2').fetchone()==stats
        assert conn.execute('SELECT total_xp FROM player_progression WHERE user_id=2').fetchone()==xp


def test_purchase_uses_shared_ledger_and_concurrent_replay(scene):
    db=scene;ready_gold(db);economy=ProgressionEconomy(db)
    quote=economy.quote(1,'avatar:gold');assert quote['ok'] and quote['price']==150
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:economy.purchase(1,quote['quote_id']),range(2)))
    assert all(r['ok'] for r in results)
    assert sum(bool(r.get('replayed')) for r in results)==1
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==1850
    assert scalar(db,"SELECT count(*) FROM reward_ledger WHERE source='shop'")==1
    assert scalar(db,"SELECT count(*) FROM player_avatar_items WHERE user_id=1 AND item_id='gold'")==1
    assert economy.quote(1,'avatar:gold')['error_code']=='already_owned'
    save(db,frame='gold')
    with sqlite3.connect(db.db_path) as conn:Inventory.consume_in(conn,1,'hero','legend')
    appearance=art.catalog(db,1)['selections']['profile']
    assert appearance['face']['card_id'] is None and appearance['frame']['item_id']=='gold'
    assert scalar(db,"SELECT count(*) FROM player_avatar_items WHERE user_id=1 AND item_id='gold'")==1


@pytest.mark.parametrize('reason',['missing_art','disabled','sale_disabled','insufficient','price_changed','art_changed','other_user','duplicate_quotes'])
def test_bad_purchases_never_charge_or_grant(scene,reason):
    db=scene;economy=ProgressionEconomy(db)
    if reason=='missing_art':
        assert not economy.quote(1,'avatar:gold')['ok'];return
    ready_gold(db)
    quote=economy.quote(1,'avatar:gold');assert quote['ok']
    if reason=='disabled':item(db,enabled=False)
    elif reason=='sale_disabled':item(db,for_sale=False)
    elif reason=='price_changed':item(db,price=151)
    elif reason=='art_changed':item(db,filename=art.upload(db,raw('lime'),transparent=True))
    elif reason=='insufficient':
        with sqlite3.connect(db.db_path) as conn:conn.execute('UPDATE players SET coins=0 WHERE user_id=1')
    elif reason=='duplicate_quotes':
        other=economy.quote(1,'avatar:gold')
        assert economy.purchase(1,other['quote_id'])['ok']
    balance=scalar(db,'SELECT coins FROM players WHERE user_id=1')
    result=economy.purchase(2 if reason=='other_user' else 1,quote['quote_id'])
    assert not result['ok']
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==balance


def test_purchase_rolls_back_wallet_inventory_and_receipt_together(scene):
    db=scene;ready_gold(db);economy=ProgressionEconomy(db)
    quote=economy.quote(1,'avatar:gold')
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("CREATE TRIGGER deny_receipt BEFORE INSERT ON reward_ledger BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError):economy.purchase(1,quote['quote_id'])
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==2000
    assert scalar(db,"SELECT count(*) FROM player_avatar_items WHERE item_id='gold'")==0
    assert scalar(db,'SELECT used FROM shop_quotes WHERE quote_id=?',(quote['quote_id'],))==0


def test_ownership_is_rechecked_for_legends_rares_and_disabled_portraits(scene):
    db=scene;art.catalog(db,1)
    with pytest.raises(ValueError):
        art.save_style(db,2,dict(slot='profile',inherit_profile=False,card_id='hero',rarity='legend',frame_id='silver',background_id='red'))
    with pytest.raises(ValueError):save(db,frame='gold')
    save(db,face='rare',rarity='rare')
    with sqlite3.connect(db.db_path) as conn:Inventory.consume_in(conn,1,'rare','rare')
    assert art.catalog(db,1)['selections']['profile']['face']['card_id'] is None
    art.configure_face(db,'admin','hero','legend',dict(kind='portrait',enabled=False,scale=1,offset_x=0,offset_y=0))
    with pytest.raises(ValueError):save(db)
    assert card_avatars.choices(db,1)==[]


def test_inheritance_and_old_independent_choices_are_preserved(scene):
    db=scene
    card_avatars.save_choice(db,1,'deck','rare','rare')
    save(db,bg='blue')
    selections=art.catalog(db,1)['selections']
    assert selections['easy']['inherit_profile'] and selections['easy']['face']['card_id']=='hero'
    assert not selections['deck']['inherit_profile'] and selections['deck']['face']['card_id']=='rare'
    save(db,slot='deck',inherit=True)
    assert art.catalog(db,1)['selections']['deck']['face']['card_id']=='hero'
    card_avatars.save_choice(db,1,'deck','rare','rare')
    assert art.catalog(db,1)['selections']['deck']['face']['card_id']=='rare'


@pytest.mark.parametrize('geometry',['circle','square','diamond','ruby','custom'])
def test_shapes_keep_alpha_and_mask_only_inner_layers(scene,geometry):
    db=scene
    # A small cyan crest above the opening must remain outside the mask.
    image=Image.new('RGBA',(128,128))
    ImageDraw.Draw(image).rectangle((60,0,68,4),fill='cyan')
    out=BytesIO();image.save(out,'PNG')
    frame=item(db,'silver',filename=art.upload(db,out.getvalue(),transparent=True),geometry=geometry,
               mask_filename=art.upload(db,raw('white'),mask=True) if geometry=='custom' else None)
    save(db)
    result=Image.open(BytesIO(art.render(db,1))).convert('RGBA')
    assert result.size==(512,512) and result.getpixel((0,0))[3]==0
    assert result.getpixel((256,6))[1]>200 and result.getpixel((256,6))[3]>200
    assert result.getpixel((256,256))[0]>200  # yellow head over red background
    if geometry=='diamond':assert result.getpixel((65,65))[3]==0


def test_replace_art_cache_defaults_and_unavailable_media(scene):
    db=scene;save(db)
    before=art.render(db,1)
    card_avatars.save_upload(db,'hero','legend',raw('lime'),kind='portrait')
    assert art.render(db,1)!=before
    art.set_defaults(db,'admin',{'frame':'silver','background':'blue'})
    assert art.catalog(db,2)['selections']['profile']['background']['item_id']=='blue'
    card_avatars.path_for(db,'hero','legend').unlink()
    assert art.catalog(db,1)['selections']['profile']['face']['card_id'] is None
    assert Image.open(BytesIO(art.render(db,1))).size==(512,512)


def test_legacy_full_avatar_is_not_double_framed(scene):
    db=scene;card_avatars.save_upload(db,'hero','legend',raw('magenta',opaque=True))
    save(db,bg='blue')
    image=Image.open(BytesIO(art.render(db,1))).convert('RGBA')
    assert image.getpixel((0,0))==(255,0,255,255)


@pytest.mark.parametrize('bad',['opaque_head','opaque_frame','opaque_mask','nonsquare','path','negative_price','stale_revision'])
def test_admin_validation(scene,bad):
    db=scene
    with pytest.raises((ValueError,OSError)):
        if bad=='opaque_head':card_avatars.save_upload(db,'hero','legend',raw(opaque=True),kind='portrait')
        elif bad=='opaque_frame':art.upload(db,raw(opaque=True),transparent=True)
        elif bad=='opaque_mask':art.upload(db,raw(opaque=True),mask=True)
        elif bad=='nonsquare':
            output=BytesIO();Image.new('RGBA',(128,64),'red').save(output,'PNG');art.upload(db,output.getvalue())
        elif bad=='path':item(db,filename='../private.png')
        elif bad=='negative_price':item(db,price=-5)
        else:item(db,revision=0)


def test_admin_and_player_api_authority_and_atomic_save(scene,monkeypatch):
    db=scene;monkeypatch.setenv('ADMIN_API_TOKEN','synthetic-avatar-admin')
    admin=WebAPI(db).app.test_client();headers={'X-Admin-Token':'synthetic-avatar-admin'}
    assert admin.get('/api/avatar-admin/catalog').status_code==403
    assert admin.get('/api/avatar-admin/catalog',headers=headers).status_code==200
    response=admin.post('/api/avatar-admin/media',headers=headers,data={'kind':'frame','file':(BytesIO(raw('cyan')),'frame.png')})
    assert response.status_code==200
    old=item(db)
    old={**old,'free':False,'enabled':True,'for_sale':True,'filename':response.json['filename']}
    assert admin.post('/api/avatar-admin/catalog',headers=headers,json=old).status_code==200
    assert admin.post('/api/avatar-admin/preview',headers=headers,json={'frame_id':'gold','background_id':'red'}).mimetype=='image/png'
    import web.miniapp_api as mini
    monkeypatch.setattr(mini,'db',db);monkeypatch.setattr(mini.app,'debug',False)
    monkeypatch.delenv('FLASK_DEBUG',raising=False)
    client=mini.app.test_client()
    assert client.get('/api/v1/avatar').status_code==401
    assert client.get('/api/v1/avatar/render').status_code==401
    monkeypatch.setattr(mini.app,'debug',True)
    assert client.get('/api/v1/avatar').json['faces'][1]['card_id']
    assert client.get('/api/v1/avatar/face/hero/legend',headers={'X-Debug-User-Id':'2'}).status_code==404
    assert client.get('/api/v1/avatar/render').mimetype=='image/png'
    result=client.put('/api/v1/avatar',json={'slot':'profile','inherit_profile':False,'card_id':'hero','rarity':'legend','frame_id':'gold','background_id':'red'})
    assert result.status_code==409
    assert scalar(db,'SELECT count(*) FROM player_avatar_choices')==0
    assert scalar(db,'SELECT coins FROM players WHERE user_id=1')==2000


def test_portrait_upload_and_admin_controls_stay_attached_to_character(scene,monkeypatch):
    db=scene;monkeypatch.setenv('ADMIN_API_TOKEN','synthetic-avatar-admin')
    client=WebAPI(db).app.test_client();headers={'X-Admin-Token':'synthetic-avatar-admin'}
    url='/api/cards/hero/avatar/legend'
    assert client.post(url,data={'kind':'portrait','image':(BytesIO(raw(opaque=True)),'bad.png')}).status_code==400
    assert client.post(url,data={'kind':'portrait','image':(BytesIO(raw('blue')),'head.png')}).status_code==200
    with Image.open(card_avatars.path_for(db,'hero','legend')) as image:
        assert image.size==(1024,1024)
    body=dict(kind='portrait',enabled=True,scale=.8,offset_x=.1,offset_y=-.1)
    assert client.put('/api/avatar-admin/face/hero/legend',headers=headers,json=body).status_code==200
    save(db)
    appearance=art.catalog(db,1)['selections']['profile']
    assert appearance['face']['scale']==.8 and appearance['face']['offset_x']==.1
    assert len(art.catalog(db,2)['faces'])==1


def test_private_shop_links_reuse_configured_miniapp_and_keep_parameters(monkeypatch):
    from types import SimpleNamespace
    from urllib.parse import parse_qs,urlsplit
    from bot.avatar_links import button
    monkeypatch.delenv('MINIAPP_URL',raising=False)
    bot=SimpleNamespace(config={'miniapp_url':'https://example.test/miniapp?keep=1'})
    link=button(bot,category='frame')
    assert parse_qs(urlsplit(link.web_app.url).query)=={'keep':['1'],'avatar':['1'],'avatar_shop':['frame']}
    assert button(SimpleNamespace()) is None
