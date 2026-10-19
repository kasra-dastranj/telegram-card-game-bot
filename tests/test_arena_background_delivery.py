"""Panel upload -> immutable registry snapshot -> Telegram intro/result artwork."""
import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from bot import battle_visuals as visual
from bot.battle_visual_delivery import choose_background, match_background, quick_picture, read_bitmap, send_arena
from core.database import DatabaseManager
from tests.test_arena_registry_regressions import quick_payload
from web.web_api import WebAPI


@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.setenv('ARENA_ADMIN_TOKEN', 'offline-arena-background')
    monkeypatch.delenv('ARENA_ADMIN_PUBLISH_TOKEN', raising=False)
    monkeypatch.setenv('MINIAPP_ARENA_MEDIA_DIR', str(tmp_path / 'media'))
    monkeypatch.setenv('TELBATTLE_BATTLE_MEDIA_DIR', str(tmp_path / 'overrides'))
    api = WebAPI(DatabaseManager(str(tmp_path / 'arena.db')))
    api.app.config['TESTING'] = True
    client = api.app.test_client()
    headers = {'X-Admin-Token': 'offline-arena-background'}
    created = client.post('/api/arenas', json={'arena_id':'dead_map', **quick_payload()}, headers=headers)
    assert created.status_code == 201, created.get_json()
    return api, client, headers, tmp_path


def upload(panel, version=1, color='#1234dc'):
    _, client, headers, _ = panel
    stream = BytesIO()
    Image.new('RGB', (720,1280), color).save(stream, 'WEBP')
    stream.seek(0)
    response = client.post('/api/arenas/dead_map/media', headers=headers,
        data={'version':str(version), 'background':(stream,'dead-map.webp')})
    assert response.status_code == 201, response.get_json()
    return response.get_json()['media']['storage_path']


def publish(panel, revision=1):
    response = panel[1].post('/api/arenas/dead_map/publish', headers=panel[2], json={'draft_revision':revision})
    assert response.status_code == 200, response.get_json()


def test_quick_only_panel_upload_is_used_by_telegram_intro_and_result(panel, monkeypatch):
    api, _, _, root = panel
    url = upload(panel)
    assert api.arena_registry.runtime('dead_map','quick') is None  # Still draft.
    publish(panel)
    arena = api.arena_registry.snapshot_for_match('dead_map','quick')
    assert arena['background_url'] == url
    assert api.arena_registry.runtime('dead_map','quick','miniapp') is None
    expected = read_bitmap(root / 'media' / url.split('/arena-backgrounds/',1)[1])
    assert choose_background(arena) == expected
    pixel = Image.open(BytesIO(expected)).getpixel((30,30))
    assert pixel[2] > 180 and pixel[0] < 60
    intro = Mock(wraps=visual.render_arena)
    result = Mock(wraps=visual.render_result)
    monkeypatch.setattr(visual,'render_arena',intro)
    monkeypatch.setattr(visual,'render_result',result)
    context = SimpleNamespace(bot_data={},bot=SimpleNamespace(send_photo=AsyncMock()))
    assert asyncio.run(send_arena(context,1,'match1',arena,'quick'))
    assert intro.call_args.args[2] == expected
    report = {'request_id':'match1','arena':'dead_map','arena_data':arena,'winner_id':None,'players':[]}
    assert asyncio.run(quick_picture(SimpleNamespace(),context,report))
    assert result.call_args.args[1] == expected


def test_new_version_cannot_replace_an_existing_match_snapshot(panel):
    api, client, headers, _ = panel
    first_url = upload(panel)
    publish(panel)
    first = api.arena_registry.snapshot_for_match('dead_map','quick')
    context = SimpleNamespace(bot_data={})
    first_image = asyncio.run(match_background(context,'old-match',first,'quick'))
    draft = client.post('/api/arenas/dead_map/versions/1/clone-as-draft',headers=headers)
    assert draft.status_code == 201
    new = draft.get_json()['arena']
    second_url = upload(panel,new['version'],'#dc3412')
    publish(panel,new['draft_revision'])
    second = api.arena_registry.snapshot_for_match('dead_map','quick')
    assert first['version'] == 1 and second['version'] == 2
    assert first['background_url'] == first_url and second['background_url'] == second_url
    assert api.arena_registry.runtime('dead_map','quick',version=1)['background_url'] == first_url
    assert asyncio.run(match_background(context,'old-match',first,'quick')) == first_image
    assert asyncio.run(match_background(context,'new-match',second,'quick')) != first_image


def test_explicit_telegram_background_remains_preferred_over_shared_bitmap(panel):
    api, _, _, _ = panel
    shared = upload(panel)
    api.arena_registry.add_media('dead_map',1,'telegram','background','/telegram-specific.webp',
        'image/webp',100,'a'*64,720,1280,'offline')
    publish(panel)
    assert api.arena_registry.runtime('dead_map','quick')['background_url'] == '/telegram-specific.webp'
    assert api.arena_registry.preview('dead_map','quick','miniapp')['background_url'] == shared


@pytest.mark.parametrize('status',['pending','failed','retired'])
def test_unready_shared_media_is_never_exposed_to_telegram(panel, status):
    api, _, _, _ = panel
    api.arena_registry.add_media('dead_map',1,'miniapp','background','/missing.webp',
        'image/webp',100,'a'*64,720,1280,'offline',readiness_status=status)
    publish(panel)
    assert api.arena_registry.runtime('dead_map','quick')['background_url'] is None


@pytest.mark.parametrize('url',[
    '/miniapp-assets/arena-backgrounds/../outside.webp',
    '/miniapp-assets/arena-backgrounds/dead_map/../../outside.webp',
    '/miniapp-assets/arena-backgrounds/other/v1-blue.webp',
    '/miniapp-assets/arena-backgrounds/dead_map/../other/v1-blue.webp',
    '/miniapp-assets/arena-backgrounds/dead_map\\v1-blue.webp',
    '/miniapp-assets/arena-backgrounds/dead_map/%2e%2e/other/v1-blue.webp',
    '/miniapp-assets/arena-backgrounds//outside.webp',
    '/miniapp-assets/arena-backgrounds/dead_map//v1-blue.webp',
    '/miniapp-assets/arena-backgrounds/dead_map/./v1-blue.webp',
    'https://example.invalid/outside.webp',
    'file:///tmp/outside.webp',
])
def test_background_path_cannot_read_other_folders_or_fetch_urls(tmp_path, monkeypatch, url):
    root = tmp_path / 'media'
    (root/'other').mkdir(parents=True)
    (root/'dead_map').mkdir()
    stream = BytesIO(); Image.new('RGB',(40,40),'blue').save(stream,'WEBP')
    for path in (tmp_path/'outside.webp',root/'outside.webp',root/'other/v1-blue.webp',root/'dead_map/v1-blue.webp'):
        path.write_bytes(stream.getvalue())
    monkeypatch.setenv('MINIAPP_ARENA_MEDIA_DIR',str(root))
    monkeypatch.setenv('TELBATTLE_BATTLE_MEDIA_DIR',str(tmp_path/'no-overrides'))
    assert choose_background({'arena_id':'dead_map','background_url':url}) == visual.background('dead_map')


def test_corrupt_uploaded_background_uses_existing_fallback(tmp_path, monkeypatch):
    root = tmp_path / 'media'
    (root/'dead_map').mkdir(parents=True)
    (root/'dead_map/v1-broken.webp').write_bytes(b'not a bitmap')
    monkeypatch.setenv('MINIAPP_ARENA_MEDIA_DIR',str(root))
    monkeypatch.setenv('TELBATTLE_BATTLE_MEDIA_DIR',str(tmp_path/'no-overrides'))
    assert choose_background({'arena_id':'dead_map','background_url':'/miniapp-assets/arena-backgrounds/dead_map/v1-broken.webp'}) == visual.background('dead_map')
