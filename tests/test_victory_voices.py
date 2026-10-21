"""Offline voice authoring, ownership, presentation failures and event retries."""
import asyncio
import copy
import json
import sqlite3
import struct
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest, Forbidden
from bot.handlers import legend_voice
from bot.main import TelegramCardBot
from bot import victory_voices as delivery
from systems import victory_voices as voices
from systems.card_inventory_system import CardInventorySystem
from tests.test_custom_cards_phase3 import custom, activate, post
from tests.test_group_attacks import scene as attacks_scene, setup, play


def ogg(seconds=.02):
    """One silent Opus frame in a complete checksummed Ogg container."""
    packets = [b'OpusHead' + struct.pack('<BBHIhB', 1, 1, 0, 48000, 0, 0),
               b'OpusTags' + struct.pack('<II', 0, 0), b'\xf8\xff\xfe']
    pages = []
    for number, packet in enumerate(packets):
        header = b'OggS\0' + bytes([2 if number == 0 else 4 if number == 2 else 0])
        page = bytearray(header + struct.pack('<QIIIB', int(seconds*48000) if number == 2 else 0,
                                              123, number, 0, 1) + bytes([len(packet)]) + packet)
        crc = 0
        for byte in page:
            crc ^= byte << 24
            for _ in range(8):
                crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
        page[22:26] = struct.pack('<I', crc)
        pages.append(page)
    return b''.join(pages)


def upload_card(custom, card='official', kind='official', raw=None):
    client = custom[2]
    path = ('/api/custom/voices/' if kind=='custom' else '/api/voices/card/') + card
    response = client.post(path,
                           headers={'X-Admin-Token':'synthetic-test-admin'},
                           data={'voice':(BytesIO(ogg() if raw is None else raw),'line.ogg')})
    assert response.status_code == 201, response.get_json()
    key = response.get_json()['media_id']
    response = client.put(path,
                          headers={'X-Admin-Token':'synthetic-test-admin'},
                          json={'revision':0,'media_ids':[key]})
    assert response.status_code == 200, response.get_json()
    return key


def grant_legend(db, user=1, card='official'):
    with sqlite3.connect(db.db_path) as conn:
        CardInventorySystem.grant_in(conn, user, card, 'legend')


def test_ogg_duration_and_corrupt_or_long_audio_rejected():
    assert voices.ogg_duration(ogg()) == .02
    for raw in (b'', b'ID3mp3', ogg()[:-1], ogg()+b'extra', ogg()+ogg(), ogg(31), ogg(0), b'x'*(voices.MAX_BYTES+1)):
        with pytest.raises(ValueError):
            voices.ogg_duration(raw)
    corrupt = bytearray(ogg());corrupt[-1] ^= 1
    with pytest.raises(ValueError):
        voices.ogg_duration(corrupt)


def test_admin_upload_preview_save_revision_and_secretless_rejection(custom):
    client = custom[2]
    for path in ('cards','card/official','preview/'+'a'*32):
        assert client.get('/api/voices/'+path).status_code == 403
    assert client.post('/api/voices/attack').status_code == 403
    headers={'X-Admin-Token':'synthetic-test-admin'}
    for raw in (b'not audio', ogg(31)):
        response=client.post('/api/voices/card/official',headers=headers,data={'voice':(BytesIO(raw),'line.ogg')})
        assert response.status_code==400
    key=upload_card(custom)
    response=client.get('/api/voices/preview/'+key,headers=headers)
    assert response.status_code==200 and response.data==ogg()
    assert response.headers['Cache-Control']=='private, no-store'
    assert response.headers['X-Content-Type-Options']=='nosniff'
    assert client.get('/api/voices/preview/'+key).status_code==403
    response=client.put('/api/voices/card/official',headers=headers,json={'revision':0,'media_ids':[]})
    assert response.status_code==400 and 'عوض شده' in response.get_json()['error']
    response=client.put('/api/voices/card/official',headers=headers,json={'revision':1,'media_ids':['../'+key]})
    assert response.status_code==400
    assert client.put('/api/voices/card/official',headers=headers,json={'revision':1,'media_ids':[]}).status_code==200
    with sqlite3.connect(custom[0].db_path) as conn:
        assert voices.card_settings_in(conn,'official')['media_ids']==[]


def test_separate_custom_admin_authority_and_no_cross_card_asset_reuse(custom,monkeypatch):
    _,card=activate(custom,'legend',[1])
    key=upload_card(custom,card,'custom')
    monkeypatch.setenv('ARENA_ADMIN_TOKEN','other-arena-admin')
    client=custom[2]
    headers={'X-Admin-Token':'synthetic-test-admin'}
    assert client.get('/api/voices/cards?kind=custom',headers=headers).status_code==200
    assert client.get('/api/voices/cards?kind=custom',headers=headers).get_json()['cards'][0]['name']=='Same name'
    assert client.get('/api/voices/card/'+card,headers=headers).status_code==403
    assert client.get('/api/voices/cards',headers=headers).status_code==403
    assert client.get('/api/voices/preview/'+key,headers={'X-Admin-Token':'other-arena-admin'}).status_code==403
    assert client.get('/api/voices/preview/'+key+'?kind=custom',headers=headers).status_code==200
    with pytest.raises(ValueError):
        voices.save_card(custom[0],'official',{'revision':0,'media_ids':[key]},'test')
    _,normal=activate(custom,'normal',[1])
    assert client.get('/api/custom/voices/'+normal,headers=headers).status_code==400


def test_preferences_owned_legend_only_isolated_persistent_without_inventory_changes(custom):
    db=custom[0];grant_legend(db)
    key=upload_card(custom)
    with sqlite3.connect(db.db_path) as conn:
        before=conn.execute('SELECT * FROM player_card_stacks').fetchall()
        wallets=conn.execute('SELECT * FROM players').fetchall()
    assert voices.card_choices(db,1,'official','normal')==[]
    assert voices.card_choices(db,1,'official','epic')==[]
    assert voices.card_choices(db,2,'official','legend')==[]
    assert voices.card_choices(db,1,'official','legend')==[key]
    assert voices.preference(db,1,'official','text')=='text'
    assert voices.card_choices(db,1,'official','legend')==[]
    grant_legend(db,2)
    assert voices.preference(db,2,'official')=='voice'
    assert voices.preference(db,1,'official')=='text'
    with pytest.raises(ValueError):voices.preference(db,3,'official','voice')
    with pytest.raises(ValueError):voices.preference(db,1,'official','random')
    with sqlite3.connect(db.db_path) as conn:
        # Only the explicitly granted second user's stack was added.
        assert conn.execute('SELECT * FROM player_card_stacks WHERE user_id!=2').fetchall()==[r for r in before if r[0]!=2]
        assert conn.execute('SELECT * FROM players').fetchall()==wallets
        CardInventorySystem.consume_in(conn,1,'official','legend')
    assert voices.card_choices(db,1,'official','legend')==[]
    with pytest.raises(ValueError):voices.preference(db,1,'official','voice')


@pytest.mark.parametrize('action',['revoke','suspend'])
def test_custom_legend_pref_and_media_require_current_private_grant(custom,action):
    db=custom[0];_,card=activate(custom,'legend',[1])
    key=upload_card(custom,card,'custom')
    # Display settings are accessible even if admission to gameplay is disabled.
    post(custom,'settings',{'custom_cards_enabled':False})
    assert voices.preference(db,1,card)=='voice'
    assert voices.card_choices(db,1,card,'legend')==[key]
    assert voices.card_choices(db,2,card,'legend')==[]
    if action=='revoke':post(custom,'revoke',{'card_id':card,'users':[1]})
    else:post(custom,'status',{'card_id':card,'status':'suspended'})
    assert voices.card_choices(db,1,card,'legend')==[]
    with pytest.raises(ValueError):voices.preference(db,1,card,'voice')


def test_private_player_controls_recheck_ownership_and_bound_tokens(custom):
    db=custom[0];grant_legend(db)
    context=NS(user_data={})
    for _ in range(50):button=legend_voice.button(context,'official')
    assert len(context.user_data['legend_voice_choices'])==40
    query=NS(data=button.callback_data,from_user=NS(id=1),answer=AsyncMock(),edit_message_text=AsyncMock())
    update=NS(callback_query=query,effective_chat=NS(type='private'))
    asyncio.run(legend_voice.handle(NS(db=db),update,context))
    assert query.edit_message_text.await_count==1
    query.data=query.data.removesuffix(':menu')+':text'
    asyncio.run(legend_voice.handle(NS(db=db),update,context))
    assert voices.preference(db,1,'official')=='text'
    query.from_user.id=2
    asyncio.run(legend_voice.handle(NS(db=db),update,context))
    assert query.answer.await_args.kwargs['show_alert']
    query.from_user.id=1;update.effective_chat.type='group'
    asyncio.run(legend_voice.handle(NS(db=db),update,context))
    assert query.answer.await_args.kwargs['show_alert']
    update.effective_chat.type='private'
    asyncio.run(legend_voice.handle(NS(db=db),update,NS(user_data={})))
    assert query.answer.await_args.kwargs['show_alert']


def test_voice_transport_caches_per_bot_recovers_bad_file_id_and_missing_file(custom):
    db=custom[0];key=upload_card(custom)
    telegram=NS(id=123,send_voice=AsyncMock(return_value=NS(voice=NS(file_id='telegram-voice'))))
    context=NS(bot=telegram)
    assert asyncio.run(delivery.send(db,context,1,key,'card:official'))
    assert telegram.send_voice.await_args.kwargs['voice'].getvalue()==ogg()
    assert asyncio.run(delivery.send(db,context,1,key,'card:official'))
    assert telegram.send_voice.await_args.kwargs['voice']=='telegram-voice'
    telegram.send_voice.side_effect=[BadRequest('file reference expired'),NS(voice=NS(file_id='renewed'))]
    assert asyncio.run(delivery.send(db,context,1,key,'card:official'))
    assert isinstance(telegram.send_voice.await_args.kwargs['voice'],BytesIO)
    telegram.send_voice.side_effect=None
    (voices.root(db)/(key+'.ogg')).unlink()
    count=telegram.send_voice.await_count
    assert not asyncio.run(delivery.send(db,context,1,key,'card:official'))
    assert telegram.send_voice.await_count==count


def test_send_rechecks_preference_after_result_picture_before_voice(custom):
    db=custom[0];grant_legend(db);key=upload_card(custom)
    voices.preference(db,1,'official','text')
    telegram=NS(send_voice=AsyncMock())
    assert not asyncio.run(delivery.send(db,NS(bot=telegram),1,key,'card:official',owner_id=1))
    telegram.send_voice.assert_not_awaited()


@pytest.mark.parametrize('error',[Forbidden('blocked'),BadRequest('invalid voice'),RuntimeError('offline')])
def test_voice_transport_failure_never_raises_or_mutates_wallet(custom,error):
    db=custom[0];key=upload_card(custom)
    with sqlite3.connect(db.db_path) as conn:before=conn.execute('SELECT * FROM players').fetchall()
    context=NS(bot=NS(send_voice=AsyncMock(side_effect=error)))
    assert not asyncio.run(delivery.send(db,context,1,key,'card:official'))
    with sqlite3.connect(db.db_path) as conn:assert conn.execute('SELECT * FROM players').fetchall()==before


@pytest.mark.parametrize('source',['group_challenge','inline_invite'])
@pytest.mark.parametrize('use_voice',[True,False])
def test_quick_result_exact_rarity_voice_order_buttons_and_text_fallback(custom,monkeypatch,source,use_voice):
    from bot import battle_visual_delivery
    db=custom[0];grant_legend(db);upload_card(custom)
    if not use_voice:voices.preference(db,1,'official','text')
    bot=TelegramCardBot.__new__(TelegramCardBot);bot.db=db
    bot.modes=NS(get_request=lambda _: {'source':source,'origin_chat_id':-100})
    events=[]
    async def sticker(*args):events.append('sticker')
    async def picture(*args):events.append('picture');return True
    async def voice(**kwargs):events.append('voice');return NS(voice=NS(file_id='voice'))
    async def text(**kwargs):events.append('text');return NS(message_id=1)
    bot._send_round_winner_card_media=sticker
    monkeypatch.setattr(battle_visual_delivery,'quick_picture',AsyncMock(return_value=b'image'))
    monkeypatch.setattr(battle_visual_delivery,'send_result',picture)
    context=NS(bot=NS(send_voice=AsyncMock(side_effect=voice),send_message=AsyncMock(side_effect=text)))
    report={'request_id':'test','players':[1,2],'winner_id':1,'breakdown':{
        '1':{'card_id':'official','card_name':'Same name','card_rarity':'legend'}}}
    asyncio.run(bot._announce_quick_result(context,report))
    if use_voice:
        assert events.index('sticker')<events.index('voice')
        assert context.bot.send_voice.await_count==(1 if source=='group_challenge' else 2)
        assert context.bot.send_message.await_count==0
    else:
        assert context.bot.send_voice.await_count==0
    context.bot.send_voice.reset_mock();context.bot.send_voice.side_effect=BadRequest('bad voice')
    voices.preference(db,1,'official','voice')
    asyncio.run(bot._announce_quick_result(context,report))
    assert context.bot.send_message.await_count>0
    assert context.bot.send_message.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data=='gm_report_test'
    context.bot.send_voice.reset_mock();report['breakdown']['1']['card_rarity']='normal'
    asyncio.run(bot._announce_quick_result(context,report))
    assert context.bot.send_voice.await_count==0


def test_attack_audio_validation_requires_upload_and_keeps_old_catalog_valid(attacks_scene):
    from systems.attack_catalog import catalog_in, validate
    db,_=attacks_scene
    event=setup(attacks_scene)
    with sqlite3.connect(db.db_path) as conn:
        catalog=catalog_in(conn)
        assert validate(conn,catalog)
    key=voices.upload(db,ogg(),'attack','offline')
    attack=catalog['attacks'][0]
    attack['voice_dialogues']={'intro':{'mode':'random','media_ids':[key]}}
    with sqlite3.connect(db.db_path) as conn:
        assert validate(conn,catalog)
        for config in ({'mode':'bad','media_ids':[key]},{'mode':'voice','media_ids':[]},
                       {'mode':'voice','media_ids':['missing']},{'mode':'voice','media_ids':[[key]]}):
            attack['voice_dialogues']['intro']=config
            with pytest.raises(ValueError):validate(conn,catalog)


def test_multiple_attacks_with_voice_keep_duplicate_id_validation(attacks_scene):
    from systems.attack_catalog import catalog_in, validate
    db, _ = attacks_scene
    setup(attacks_scene)
    key = voices.upload(db, ogg(), 'attack', 'offline')
    with sqlite3.connect(db.db_path) as conn:
        catalog = catalog_in(conn)
        first = catalog['attacks'][0]
        first['voice_dialogues'] = {'intro': {'mode': 'voice', 'media_ids': [key]}}
        second = copy.deepcopy(first)
        second['id'] = first['id'] + '-second'
        catalog['attacks'].append(second)
        assert validate(conn, catalog)
        second['id'] = first['id']
        with pytest.raises(ValueError, match='شناسه'):
            validate(conn, catalog)


@pytest.mark.parametrize('status,killed,key', [('open',False,'intro'),('win',False,'loss'),
    ('win',True,'death'),('loss',False,'win'),('tie',False,'tie'),('void',False,'expired')])
def test_attack_dialogue_stage_and_multiline_text_omission(attacks_scene,status,killed,key):
    from bot.group_attacks import dialogue_key,group_panel
    event=setup(attacks_scene)
    event.update(status=status,killed=killed)
    event['attack']['dialogues'][key]=['متن چندخطی\nکه باید حذف شود']
    phase='intro' if status=='open' else 'final'
    event['voice_choices']={phase:{'text':event['attack']['dialogues'][key][0],'media_id':'unused'}}
    assert dialogue_key(event)==key
    text,_=group_panel(event,omit_dialogue=True)
    assert 'چندخطی' not in text and 'حذف شود' not in text
    assert len(text)>20


@pytest.mark.parametrize('pick_voice',[True,False])
def test_attack_random_choice_is_frozen_in_database(attacks_scene,monkeypatch,pick_voice):
    from bot import group_attacks
    db,system=attacks_scene
    media=voices.upload(db,ogg(),'attack','offline')
    event=setup(attacks_scene,mutate=lambda c,a:a.update(voice_dialogues={'intro':{'mode':'random','media_ids':[media]}}))
    original=group_attacks.random.choice
    monkeypatch.setattr(group_attacks.random,'choice',lambda values:pick_voice if values==[True,False] else original(values))
    frozen=group_attacks.freeze_dialogue(system,event)
    assert bool(frozen['voice_choices']['intro']['media_id'])==pick_voice
    monkeypatch.setattr(group_attacks.random,'choice',Mock(side_effect=AssertionError('must not choose again')))
    assert group_attacks.freeze_dialogue(system,system.get(event['id']))['voice_choices']==frozen['voice_choices']


@pytest.mark.parametrize('voice_success',[True,False])
def test_attack_intro_and_final_audio_checkpoint_not_repeated_on_panel_retry(attacks_scene,monkeypatch,voice_success):
    from bot import group_attacks
    from systems.attack_catalog import read,write
    db,system=attacks_scene
    key=voices.upload(db,ogg(),'attack','offline')
    def change(config,attack):
        attack['voice_dialogues']={stage:{'mode':'voice','media_ids':[key]} for stage in attack['dialogues']}
    event=setup(attacks_scene,mutate=change)
    telegram=NS(id=42,send_voice=AsyncMock(return_value=NS(voice=NS(file_id='voice'))),send_message=AsyncMock(side_effect=RuntimeError('panel offline')),
                edit_message_text=AsyncMock(),edit_message_reply_markup=AsyncMock())
    if not voice_success:telegram.send_voice.side_effect=BadRequest('cannot send')
    bot=NS(db=db,modes=system.modes);context=NS(bot=telegram,bot_data={})
    monkeypatch.setattr(group_attacks,'send_snapshot',AsyncMock())
    asyncio.run(group_attacks.maintenance(bot,context))
    saved=system.get(event['id'])
    assert saved['delivery']['intro_voice_done']
    assert saved['voice_choices']['intro']['media_id']==key
    assert telegram.send_voice.await_count==1
    telegram.send_message.side_effect=None;telegram.send_message.return_value=NS(message_id=10)
    with sqlite3.connect(db.db_path) as conn:write(conn,'notice:'+event['id'],True)
    asyncio.run(group_attacks.maintenance(bot,context))
    assert telegram.send_voice.await_count==1
    text=telegram.send_message.await_args.kwargs['text']
    assert ('بیگ مسعود ریخته' in text) != voice_success
    assert 'سهم هر شرکت‌کننده' in text
    result=play(system,event,0,1)
    assert result['status']=='win'
    asyncio.run(group_attacks.maintenance(bot,context))
    assert telegram.send_voice.await_count==2
    assert system.get(event['id'])['delivery']['final_voice_done']
    asyncio.run(group_attacks.maintenance(bot,context))
    assert telegram.send_voice.await_count==2
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT coins FROM players WHERE user_id=1').fetchone()[0]==1020
