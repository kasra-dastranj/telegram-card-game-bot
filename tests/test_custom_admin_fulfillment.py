"""Admin-only manual delivery: atomic grants without a payment UI or wallet changes."""
import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from systems.custom_cards import CustomCards
from tests.test_custom_cards_phase3 import custom,post,define


def form(rarity='normal',users=None):
    return {'card':{'name':'شخصیت MH','rarity':rarity,'power':51,'speed':62,'iq':73,'popularity':84,
                    'biography':'داستان شخصیت','dialogs':['شعار من'],'traits':['hero','تازه'],
                    'series':'آزمایشی','abilities':['آزمایشی'],'card_effects':[],
                    'hidden_stats':{'survival':80,'management':60},'passive':{},'card_type':'IQ_TYPE'},
            'users':users or [1,2],'media_id':None,'review_confirmed':True}


def test_custom_legend_avatar_requires_admin_and_active_ownership(custom):
    from io import BytesIO
    from PIL import Image
    from systems import card_avatars
    card = post(custom, 'fulfill', form('legend')).get_json()['card_id']
    raw = BytesIO()
    Image.new('RGBA', (64, 64), 'green').save(raw, 'PNG')
    url = '/api/custom/avatar/' + card
    assert custom[2].post(url, data={'image': (BytesIO(raw.getvalue()), 'avatar.png')}).status_code == 401
    response = custom[2].post(url, data={'image': (BytesIO(raw.getvalue()), 'avatar.png')}, headers={'X-Admin-Token': 'synthetic-test-admin'})
    assert response.status_code == 200
    assert card_avatars.choices(custom[0], 1)[0]['card_id'] == card
    card_avatars.save_choice(custom[0], 1, 'profile', card, 'legend')
    assert card_avatars.selected(custom[0], 1, 'profile')
    # Cosmetic ownership is available even while custom gameplay is disabled.
    assert card_avatars.selected(custom[0], 1, 'profile')['card'].name == 'شخصیت MH'
    assert any(item['card_id'] == card for item in card_avatars.owned_forms(custom[0], 1))
    assert card_avatars.choices(custom[0], 3) == []
    post(custom, 'revoke', {'card_id': card, 'users': [1]})
    assert card_avatars.selected(custom[0], 1, 'profile') is None
    assert card_avatars.choices(custom[0], 1) == []


def count(custom,table):
    with sqlite3.connect(custom[0].db_path) as conn:return conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]


def definition(custom,card):
    with sqlite3.connect(custom[0].db_path) as conn:
        conn.row_factory=sqlite3.Row
        return dict(conn.execute('SELECT * FROM custom_definitions WHERE card_id=?',(card,)).fetchone())


def revise(custom,card):
    stored=definition(custom,card)
    return {'card_id':card,'card':form()['card'],'media_id':stored['media_id'],
            'expected_updated_at':stored['updated_at'],'review_confirmed':True}


@pytest.mark.parametrize('action',['fulfill','revise','deliver_existing','approve'])
def test_new_operations_require_admin(custom,action):
    assert post(custom,action,{},auth=False).status_code==401
    assert custom[2].get('/api/custom/players?q=1').status_code==401
    assert custom[2].get('/api/custom/records').status_code==401


@pytest.mark.parametrize('rarity',['normal','epic','legend'])
def test_fulfill_creates_one_active_definition_without_wallet_or_setting_changes(custom,rarity):
    with sqlite3.connect(custom[0].db_path) as conn:
        wallet=conn.execute('SELECT * FROM players').fetchall()
        progression=conn.execute('SELECT * FROM player_progression').fetchall()
        flags=conn.execute('SELECT * FROM foundation_settings ORDER BY key').fetchall()
    response=post(custom,'fulfill',form(rarity),key='create-once')
    assert response.status_code==200,response.get_json()
    card=response.get_json()['card_id']
    assert definition(custom,card)['status']=='active'
    assert post(custom,'fulfill',form(rarity),key='create-once').get_json()['replayed']
    assert count(custom,'custom_definitions')==count(custom,'custom_orders')==count(custom,'custom_operations')==1
    with sqlite3.connect(custom[0].db_path) as conn:
        assert conn.execute('SELECT * FROM players').fetchall()==wallet
        assert conn.execute('SELECT * FROM player_progression').fetchall()==progression
        assert conn.execute("SELECT * FROM foundation_settings WHERE key NOT LIKE 'custom-card-notice:%' ORDER BY key").fetchall()==flags
        assert conn.execute('SELECT user_id,active FROM custom_grants ORDER BY user_id').fetchall()==[(1,1),(2,1)]
        assert conn.execute('SELECT amount,currency,payment_status FROM custom_orders').fetchone()==('','','admin_managed')
        assert conn.execute('SELECT COUNT(*) FROM player_card_stacks WHERE card_id=?',(card,)).fetchone()[0]==0
        assert conn.execute('SELECT origin FROM cards WHERE card_id=?',(card,)).fetchone()[0]=='custom'
    post(custom,'settings',{'custom_cards_enabled':True})
    assert custom[0].get_card_by_id_for_player(card,1).name=='شخصیت MH'
    assert custom[0].get_card_by_id_for_player(card,3) is None


@pytest.mark.parametrize('bad',[
    {'users':[1,99999]}, {'users':[1,1]}, {'media_id':'missing'}, {'review_confirmed':False},
    {'card':{'rarity':'rare'}}, {'card':{**form()['card'],'power':101}}, {'amount':'100'},
])
def test_failed_fulfillment_leaves_no_partial_card_order_or_receipt(custom,bad):
    data=form();data.update(bad)
    response=post(custom,'fulfill',data)
    assert response.status_code==400,response.get_json()
    for table in ('custom_orders','custom_definitions','custom_grants','custom_operations','custom_audit'):
        assert count(custom,table)==0
    assert count(custom,'cards')==1  # Only the fixture's official card.


def test_concurrent_retries_grant_once(custom):
    db,api,_=custom
    service=CustomCards(db)
    def run(_):return service.mutate('admin','same-delivery','fulfill',copy.deepcopy(form()),api._validate_card_payload)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert results[0]['card_id']==results[1]['card_id']
    assert sum(bool(r.get('replayed')) for r in results)==1
    assert count(custom,'custom_definitions')==count(custom,'custom_audit')==1
    assert count(custom,'custom_grants')==2


def test_edit_preserves_access_metadata_and_rejects_stale_overwrite(custom):
    card=post(custom,'fulfill',form()).get_json()['card_id']
    request=revise(custom,card);request['card']['power']=95
    stale=copy.deepcopy(request)
    result=post(custom,'revise',request,key='edit-once')
    assert result.status_code==200,result.get_json()
    assert result.get_json()['status']=='active'
    assert post(custom,'revise',request,key='edit-once').get_json()['replayed']
    stale['card']['power']=5
    assert post(custom,'revise',stale).get_json()['error']=='definition_changed_reload'
    stored=json.loads(definition(custom,card)['payload_json'])
    assert stored['power']==95 and stored['dialogs']==['شعار من']
    assert stored['metadata']['hidden_stats']=={'survival':80,'management':60}
    assert stored['metadata']['traits']==['hero','تازه']
    assert count(custom,'custom_grants')==2
    post(custom,'status',{'card_id':card,'status':'suspended'})
    assert post(custom,'revise',revise(custom,card)).get_json()['status']=='pending_review'
    assert definition(custom,card)['status']=='pending_review'


def test_additional_recipient_uses_existing_definition_and_revokes_individually(custom):
    card=post(custom,'fulfill',form()).get_json()['card_id']
    data={'card_id':card,'users':[3,4],'review_confirmed':True}
    assert post(custom,'deliver_existing',data,key='share-once').status_code==200
    assert post(custom,'deliver_existing',data,key='share-once').get_json()['replayed']
    assert count(custom,'custom_definitions')==1
    assert count(custom,'custom_orders')==2
    assert count(custom,'custom_grants')==4
    post(custom,'revoke',{'card_id':card,'users':[3]})
    with sqlite3.connect(custom[0].db_path) as conn:
        assert conn.execute('SELECT user_id,active FROM custom_grants ORDER BY user_id').fetchall()==[(1,1),(2,1),(3,0),(4,1)]
    post(custom,'status',{'card_id':card,'status':'suspended'})
    assert post(custom,'deliver_existing',data).status_code==400
    assert count(custom,'custom_orders')==2
    assert post(custom,'deliver_existing',{**data,'card_id':'official'}).status_code==400


def test_legacy_unverified_order_still_needs_its_original_confirmation(custom):
    _,card=define(custom)
    assert post(custom,'revise',revise(custom,card)).status_code==200
    assert post(custom,'status',{'card_id':card,'status':'active','review_confirmed':True}).status_code==400
    assert post(custom,'deliver_existing',{'card_id':card,'users':[3],'review_confirmed':True}).status_code==400
    approval={'card_id':card,'expected_updated_at':definition(custom,card)['updated_at'],'review_confirmed':False}
    assert post(custom,'approve',approval).status_code==400
    approval['review_confirmed']=True
    assert post(custom,'approve',approval).get_json()['status']=='active'
    with sqlite3.connect(custom[0].db_path) as conn:
        assert conn.execute('SELECT payment_status FROM custom_orders').fetchone()[0]=='admin_managed'


def test_authenticated_lookup_and_records_support_plain_forms(custom):
    custom[0].get_or_create_player(123456,username='test_admin',first_name='محمد')
    headers={'X-Admin-Token':'synthetic-test-admin'}
    for query in ('@test_admin','محمد','123456','۱۲۳۴۵۶'):
        result=custom[2].get('/api/custom/players',query_string={'q':query},headers=headers)
        assert result.status_code==200 and result.get_json()['players'][0]['user_id']==123456
    assert custom[2].get('/api/custom/players?q=%25%25',headers=headers).get_json()['players']==[]
    records=custom[2].get('/api/custom/records',headers=headers)
    assert records.headers['Cache-Control']=='private, no-store'
    data=records.get_json()
    assert data['settings']['custom_cards_enabled'] is False
    assert 'survival' in data['options']['stats'] and 'hero' in data['options']['traits']
