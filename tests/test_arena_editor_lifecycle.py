"""Arena authoring: media inheritance, pausing and exact Deck tier semantics."""
from io import BytesIO

import pytest
from PIL import Image
from core.database import DatabaseManager
from systems.arena_registry import ArenaRegistry,ArenaValidationError
from tests.test_arena_registry import _quick_payload
from web.web_api import WebAPI


@pytest.fixture
def editor(tmp_path,monkeypatch):
    monkeypatch.setenv('ARENA_ADMIN_TOKEN','offline-arena-editor')
    monkeypatch.setenv('MINIAPP_ARENA_MEDIA_DIR',str(tmp_path/'media'))
    db=DatabaseManager(str(tmp_path/'arena.db'))
    api=WebAPI(db);api.app.config['TESTING']=True
    return db,api,api.app.test_client(),{'X-Admin-Token':'offline-arena-editor'}


def image(color):
    stream=BytesIO();Image.new('RGB',(720,1280),color).save(stream,format='WEBP');stream.seek(0)
    return stream


def test_clone_inherits_only_ready_media_and_replacement_never_changes_old_version(editor):
    db,api,client,headers=editor;registry=api.arena_registry
    created=client.post('/api/arenas',headers=headers,json={'arena_id':'edit_arena',**_quick_payload(miniapp=True)})
    assert created.status_code==201
    first=client.post('/api/arenas/edit_arena/media',headers=headers,data={'version':'1','background':(image('blue'),'v1.webp')})
    assert first.status_code==201
    assert client.post('/api/arenas/edit_arena/publish',headers=headers,json={'draft_revision':1}).status_code==200
    snapshot=registry.snapshot_for_match('edit_arena','quick')
    original=registry.get_published('edit_arena')['content_hash']
    draft=client.post('/api/arenas/edit_arena/versions/1/clone-as-draft',headers=headers)
    assert draft.status_code==201
    result=client.get('/api/arenas/edit_arena',headers=headers).get_json()
    assert result['draft']['version']==2
    assert len(result['media'])==2 and result['media'][0]['storage_path']==first.get_json()['media']['storage_path']
    assert client.post('/api/arenas/edit_arena/validate',headers=headers).get_json()['valid']
    next_image=client.post('/api/arenas/edit_arena/media',headers=headers,data={'version':'2','background':(image('red'),'v2.webp')})
    assert next_image.status_code==201
    assert client.post('/api/arenas/edit_arena/publish',headers=headers,json={'draft_revision':1}).status_code==200
    assert registry.snapshot_for_match('edit_arena','quick')['background_url']!=snapshot['background_url']
    assert registry.get_version('edit_arena',1)['content_hash']==original
    assert registry.list_media('edit_arena',1)[0]['storage_path']==snapshot['background_url']
    # A later text-only edit also retains the replacement image, without reupload.
    assert client.post('/api/arenas/edit_arena/versions/2/clone-as-draft',headers=headers).status_code==201
    assert client.post('/api/arenas/edit_arena/validate',headers=headers).get_json()['valid']
    assert client.post('/api/arenas/edit_arena/publish',headers=headers,json={'draft_revision':1}).status_code==200
    assert registry.snapshot_for_match('edit_arena','quick')['background_url']==next_image.get_json()['media']['storage_path']


def test_existing_city_can_be_paused_and_resumed_without_fabricating_legacy_description(editor):
    db,api,client,headers=editor;registry=api.arena_registry
    snapshot=registry.snapshot_for_match('city','quick')
    assert snapshot and not snapshot['description_fa']
    draft=client.post('/api/arenas/city/versions/1/clone-as-draft',headers=headers).get_json()['arena']
    draft['profiles']['quick']['enabled']=False;draft['draft_revision']=1
    saved=client.put('/api/arenas/city/draft',headers=headers,json=draft)
    assert saved.status_code==200,saved.get_json()
    validation=client.post('/api/arenas/city/validate',headers=headers).get_json()
    assert validation['valid'] and any(i['code']=='arena_paused' for i in validation['issues'])
    assert registry.runtime('city','quick')  # Draft save alone does not stop games.
    assert client.post('/api/arenas/city/publish',headers=headers,json={'draft_revision':2}).status_code==200
    assert registry.runtime('city','quick') is None
    assert 'city' not in [a['arena_id'] for a in registry.list_active('quick','telegram')]
    assert snapshot['version']==1 and snapshot['effects']
    draft=registry.create_next_draft('city','admin')
    draft['profiles']['quick']['enabled']=True
    registry.update_draft('city',draft,'admin',draft['draft_revision'])
    registry.publish('city','admin',2)
    assert registry.runtime('city','quick')['version']==3


def test_new_arena_cannot_publish_without_a_mode_or_description(editor):
    registry=editor[1].arena_registry
    payload=_quick_payload();payload['profiles']['quick']['enabled']=False
    registry.create_draft('empty_modes',payload,'admin')
    with pytest.raises(ArenaValidationError) as exc:registry.publish('empty_modes','admin',1)
    assert any(i['code']=='no_mode_enabled' for i in exc.value.issues)
    payload=_quick_payload();payload['description_fa']=''
    registry.create_draft('empty_desc',payload,'admin')
    with pytest.raises(ArenaValidationError) as exc:registry.publish('empty_desc','admin',1)
    assert any(i['code']=='description_required' for i in exc.value.issues)


def test_disable_quick_only_keeps_other_mode_and_rank_groups_intact(editor):
    registry=editor[1].arena_registry
    payload=_quick_payload()
    payload['profiles']['deck']={'enabled':True,'rules':{'compare_stat':'popularity','trait_ranks':[['hero','funny'],['leader','villain'],['monster']], 'stat_tiebreak_enabled':True}}
    registry.create_draft('two_modes',payload,'admin');registry.publish('two_modes','admin',1)
    registry.create_next_draft('two_modes','admin')
    payload['profiles']['quick']['enabled']=False
    registry.update_draft('two_modes',payload,'admin',1);registry.publish('two_modes','admin',2)
    assert registry.runtime('two_modes','quick') is None
    assert registry.runtime('two_modes','deck')['trait_ranks']==[['hero','funny'],['leader','villain'],['monster']]


def test_editor_options_authenticated_and_includes_custom_vocabulary(editor):
    _,api,client,headers=editor
    assert client.get('/api/arenas/editor-options').status_code==403
    api.trait_registry.add_trait('زامبی')
    response=client.get('/api/arenas/editor-options',headers=headers)
    assert response.status_code==200
    assert 'زامبی' in response.get_json()['traits'] and 'hero' in response.get_json()['traits']


def test_clone_conflict_does_not_overwrite_existing_draft(editor):
    registry=editor[1].arena_registry
    registry.create_next_draft('city','first')
    with pytest.raises(ValueError,match='draft_conflict'):registry.create_next_draft('city','second')
    assert len([v for v in registry.list_versions('city') if v['version_status']=='draft'])==1


def test_automatic_edit_refuses_stale_published_version_but_explicit_history_clone_remains(editor):
    _,api,client,headers=editor;registry=api.arena_registry
    registry.create_next_draft('city','other');registry.publish('city','other',1)
    response=client.post('/api/arenas/city/versions/1/clone-as-draft',headers=headers,json={'expected_current_version':1})
    assert response.status_code==409 and response.get_json()['error']=='published_conflict'
    assert not any(v['version_status']=='draft' for v in registry.list_versions('city'))
    assert client.post('/api/arenas/city/versions/1/clone-as-draft',headers=headers).status_code==201


def test_panel_background_replaces_cloned_telegram_override_atomically(editor):
    _,api,client,headers=editor;registry=api.arena_registry
    registry.create_draft('old_override',_quick_payload(),'admin')
    registry.add_media('old_override',1,'telegram','background','/old.webp','image/webp',5,'a'*64,720,1280,'admin')
    registry.publish('old_override','admin',1)
    registry.create_next_draft('old_override','admin')
    result=client.post('/api/arenas/old_override/media',headers=headers,data={'version':'2','background':(image('green'),'new.webp')})
    assert result.status_code==201
    registry.publish('old_override','admin',1)
    assert registry.snapshot_for_match('old_override','quick')['background_url']==result.get_json()['media']['storage_path']
    assert registry.list_media('old_override',1)[0]['storage_path']=='/old.webp'
