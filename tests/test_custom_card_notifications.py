"""Offline, transactional admin handoff to private Telegram card-ready messages."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from telegram.error import BadRequest, Forbidden, RetryAfter

from bot.custom_card_notifications import deliver, text
from systems.custom_card_notices import PREFIX, claim, checkpoint, wake_user
from tests.test_custom_admin_fulfillment import form, revise
from tests.test_custom_cards_phase3 import custom, post, define


def notices(db):
    with sqlite3.connect(db.db_path) as conn:
        return {key:json.loads(value) for key,value in conn.execute(
            'SELECT key,value_json FROM foundation_settings WHERE key LIKE ?', (PREFIX+'%',))}


def due(db):
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE foundation_settings SET value_json=json_set(value_json,'$.next_attempt',0,'$.lease_until',0) WHERE key LIKE ?",(PREFIX+'%',))


def scene(custom, *, image=False, users=None, biography=None):
    data=form(users=users or [1,2])
    if biography is not None:data['card']['biography']=biography
    if image:
        stream=BytesIO();Image.new('RGB',(150,220),'navy').save(stream,'PNG');stream.seek(0)
        uploaded=custom[2].post('/api/custom/media',data={'image':(stream,'portrait.png')},
            headers={'X-Admin-Token':'synthetic-test-admin'})
        assert uploaded.status_code==201
        data['media_id']=uploaded.get_json()['media_id']
    response=post(custom,'fulfill',data)
    assert response.status_code==200,response.get_json()
    bot=SimpleNamespace(db=custom[0])
    context=SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock(),send_message=AsyncMock()))
    return bot,context,response.get_json()


@pytest.mark.parametrize('image',[False,True])
def test_fulfill_commits_private_receipts_and_delivers_card_stats_without_reward_writes(custom,image):
    db=custom[0]
    with sqlite3.connect(db.db_path) as conn:
        wallet=conn.execute('SELECT * FROM players').fetchall()
        progression=conn.execute('SELECT * FROM player_progression').fetchall()
    bot,context,result=scene(custom,image=image)
    assert result['notification_users']==[1,2]
    assert len(notices(db))==2
    asyncio.run(deliver(bot,context))
    sender=context.bot.send_photo if image else context.bot.send_message
    assert sender.await_count==2
    for call,user in zip(sender.await_args_list,(1,2)):
        assert call.kwargs['chat_id']==user and call.kwargs['parse_mode'] is None
        body=call.kwargs['caption' if image else 'text']
        assert all(value in body for value in ('مبارکت','شخصیت MH','51','62','73','84','270','داستان شخصیت','hero'))
        assert 'شعار من' not in body
        callbacks=[b.callback_data for row in call.kwargs['reply_markup'].inline_keyboard for b in row]
        assert callbacks==['cardinfo_'+result['card_id'],'mycards_custom_1']
    assert all(n['state']=='sent' for n in notices(db).values())
    asyncio.run(deliver(bot,context))
    assert sender.await_count==2  # No repeated completed deliveries.
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute('SELECT * FROM players').fetchall()==wallet
        assert conn.execute('SELECT * FROM player_progression').fetchall()==progression
        assert conn.execute("SELECT COUNT(*) FROM player_card_stacks WHERE card_id=?",(result['card_id'],)).fetchone()[0]==0
        assert conn.execute("SELECT value_json FROM foundation_settings WHERE key='custom_cards_enabled'").fetchone()[0]=='false'


def test_duplicate_request_or_existing_active_grant_does_not_queue_another_message(custom):
    bot,context,result=scene(custom,users=[1])
    asyncio.run(deliver(bot,context))
    first=notices(bot.db)
    response=post(custom,'deliver_existing',{'card_id':result['card_id'],'users':[1,2],'review_confirmed':True},key='same-delivery')
    assert response.get_json()['notification_users']==[2]
    assert post(custom,'deliver_existing',{'card_id':result['card_id'],'users':[1,2],'review_confirmed':True},key='same-delivery').get_json()['replayed']
    asyncio.run(deliver(bot,context))
    assert [call.kwargs['chat_id'] for call in context.bot.send_message.await_args_list]==[1,2]
    assert notices(bot.db)[next(iter(first))]==next(iter(first.values()))


def test_legacy_grant_also_notifies_but_edit_does_not_redeliver(custom):
    order,card=define(custom,users=[1])
    assert not notices(custom[0])
    post(custom,'payment',{'order_id':order})
    post(custom,'status',{'card_id':card,'status':'active','review_confirmed':True})
    assert not notices(custom[0])
    post(custom,'grant',{'card_id':card,'order_id':order,'users':[1]})
    first=notices(custom[0])
    post(custom,'grant',{'card_id':card,'order_id':order,'users':[1]})
    assert notices(custom[0])==first
    assert post(custom,'revise',revise(custom,card)).status_code==200
    assert notices(custom[0])==first


@pytest.mark.parametrize('action',['revoke','status','remove_image'])
def test_removed_access_before_delivery_cancels_without_sending_any_content(custom,action):
    bot,context,result=scene(custom,image=True,users=[1])
    data={'card_id':result['card_id']}
    if action=='revoke':data['users']=[1]
    if action=='status':data['status']='suspended'
    assert post(custom,action,data).status_code==200
    asyncio.run(deliver(bot,context))
    context.bot.send_photo.assert_not_awaited();context.bot.send_message.assert_not_awaited()
    assert next(iter(notices(bot.db).values()))['state']=='cancelled'


def test_transaction_failure_rolls_back_card_grants_and_notices_together(custom,monkeypatch):
    import systems.custom_card_notices as outbox
    original=outbox.queue_in
    def fail_second(conn,user,card):
        original(conn,user,card)
        if user==2:raise ValueError('offline simulated failure')
    monkeypatch.setattr(outbox,'queue_in',fail_second)
    assert post(custom,'fulfill',form()).status_code==400
    assert not notices(custom[0])
    with sqlite3.connect(custom[0].db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM custom_grants').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM custom_definitions').fetchone()[0]==0


def test_photo_success_text_failure_retries_only_remaining_text_after_restart(custom):
    bot,context,result=scene(custom,image=True,users=[1],biography='قصهٔ شخصیت 🎴\n'*180)
    context.bot.send_message.side_effect=RuntimeError('offline')
    asyncio.run(deliver(bot,context))
    entry=next(iter(notices(bot.db).values()))
    assert entry['state']=='retry' and entry['photo_done'] and entry['text_next']==1
    context.bot.send_photo.assert_awaited_once()
    new_context=SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock(),send_message=AsyncMock()))
    due(bot.db)
    asyncio.run(deliver(bot,new_context))
    new_context.bot.send_photo.assert_not_awaited()
    sent=[context.bot.send_photo.await_args.kwargs['caption']]+[call.kwargs['text'] for call in new_context.bot.send_message.await_args_list]
    assert ''.join(sent)==text(entry['payload'])
    assert all(len(part.encode('utf-16-le'))//2<=1000 for part in sent)
    assert next(iter(notices(bot.db).values()))['state']=='sent'


@pytest.mark.parametrize('failure',['rejected','missing','corrupt'])
def test_rejected_or_missing_image_still_delivers_stats_with_no_public_art_fallback(custom,failure,monkeypatch):
    bot,context,result=scene(custom,image=True,users=[1])
    public_cache=Mock(side_effect=AssertionError('Private notification must never use public art cache'))
    monkeypatch.setattr(bot.db,'get_card_variant_media_file_id',public_cache)
    if failure=='rejected':
        context.bot.send_photo.side_effect=BadRequest('invalid photo')
    else:
        from pathlib import Path
        from systems.card_collection import custom_owned_card
        path=Path(custom_owned_card(bot.db,1,result['card_id']).image_path).resolve()
        assert Path(bot.db.db_path).resolve().parent in path.parents
        if failure=='missing':path.unlink()
        else:path.write_bytes(b'not a valid image')
    asyncio.run(deliver(bot,context))
    assert 'شخصیت MH' in context.bot.send_message.await_args.kwargs['text']
    assert next(iter(notices(bot.db).values()))['state']=='sent'
    public_cache.assert_not_called()


def test_blocked_bot_waits_for_private_start_and_sent_receipts_are_not_rewoken(custom):
    bot,context,result=scene(custom,users=[1,2])
    async def send(**kwargs):
        if kwargs['chat_id']==1:raise Forbidden('bot was blocked')
    context.bot.send_message.side_effect=send
    asyncio.run(deliver(bot,context))
    entries=notices(bot.db)
    assert {n['state'] for n in entries.values()}=={'blocked','sent'}
    due(bot.db);asyncio.run(deliver(bot,context))
    assert context.bot.send_message.await_count==2
    wake_user(bot.db,2)
    assert notices(bot.db)==entries  # No wake for another user/sent receipt.
    wake_user(bot.db,1)
    context.bot.send_message.side_effect=None
    asyncio.run(deliver(bot,context))
    assert context.bot.send_message.await_count==3
    assert all(n['state']=='sent' for n in notices(bot.db).values())


def test_db_lease_prevents_two_workers_and_stale_checkpoint_cannot_ack_new_owner(custom):
    bot,_,_=scene(custom,users=[1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:claim(bot.db),range(2)))
    assert sum(item is not None for item in results)==1
    key,old=next(item for item in results if item)
    due(bot.db)
    new_key,new=claim(bot.db)
    assert new_key==key and new['lease']!=old['lease']
    assert not checkpoint(bot.db,key,old,state='sent')
    assert checkpoint(bot.db,key,new,state='sent')


def test_regrant_replaces_cancelled_generation_and_old_worker_cannot_send_or_ack(custom):
    bot,context,result=scene(custom,users=[1])
    key,old=claim(bot.db)
    post(custom,'revoke',{'card_id':result['card_id'],'users':[1]})
    post(custom,'deliver_existing',{'card_id':result['card_id'],'users':[1],'review_confirmed':True})
    assert not checkpoint(bot.db,key,old,state='sent')
    assert notices(bot.db)[key]['generation']!=old['generation']
    asyncio.run(deliver(bot,context))
    context.bot.send_message.assert_awaited_once()


def test_send_time_revocation_stops_remaining_chunks(custom):
    bot,context,result=scene(custom,image=True,users=[1],biography='قصه 🎴 '*400)
    async def revoke_after_photo(**kwargs):
        post(custom,'revoke',{'card_id':result['card_id'],'users':[1]})
    context.bot.send_photo.side_effect=revoke_after_photo
    asyncio.run(deliver(bot,context))
    context.bot.send_photo.assert_awaited_once();context.bot.send_message.assert_not_awaited()
    assert next(iter(notices(bot.db).values()))['state']=='cancelled'


def test_retry_after_is_not_immediately_retried(custom):
    bot,context,_=scene(custom,users=[1,2])
    context.bot.send_message.side_effect=RetryAfter(90)
    asyncio.run(deliver(bot,context))
    assert {n['state'] for n in notices(bot.db).values()}=={'pending','retry'}
    asyncio.run(deliver(bot,context))
    context.bot.send_message.assert_awaited_once()


def test_busy_image_worker_retries_photo_instead_of_silently_dropping_it(custom,monkeypatch):
    bot,context,_=scene(custom,image=True,users=[1])
    stream=BytesIO();Image.new('RGB',(30,40),'navy').save(stream,'PNG')
    monkeypatch.setattr('bot.custom_card_notifications.work',AsyncMock(side_effect=[asyncio.TimeoutError(),stream.getvalue()]))
    asyncio.run(deliver(bot,context))
    entry=next(iter(notices(bot.db).values()))
    assert entry['state']=='retry' and not entry['photo_done']
    context.bot.send_message.assert_not_awaited()
    due(bot.db)
    asyncio.run(deliver(bot,context))
    context.bot.send_photo.assert_awaited_once()
    assert next(iter(notices(bot.db).values()))['state']=='sent'


def test_legacy_csv_fields_use_canonical_traits_and_abilities(custom):
    data=form(users=[1])
    data['card']['traits']='hero, تازه'
    data['card']['abilities']='اثر اول, اثر دوم'
    response=post(custom,'fulfill',data)
    assert response.status_code==200,response.get_json()
    entry=next(iter(notices(custom[0]).values()))
    assert entry['payload']['traits']==['hero','تازه']
    assert entry['payload']['abilities']==['اثر اول','اثر دوم']
