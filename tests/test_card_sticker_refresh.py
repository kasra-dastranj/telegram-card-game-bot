"""Regression: replacing form artwork must also replace its Telegram sticker."""
import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from bot.card_reward_presentation import send_card_sticker
from bot.handlers.battle import BattleHandlersMixin
from core.card_media import sticker_path
from core.database import DatabaseManager
import web.web_api as web_api_module
from web.web_api import WebAPI


def bitmap(color, kind='WEBP'):
    stream = BytesIO()
    Image.new('RGB', (128, 128), color).save(stream, kind)
    return stream.getvalue()


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api_module, 'PROJECT_ROOT', tmp_path)
    db = DatabaseManager(str(tmp_path / 'cards.db'))
    client = WebAPI(db).app.test_client()
    forms = {}
    for rarity in ('normal', 'epic', 'legend'):
        path = tmp_path / (rarity + '.png')
        path.write_bytes(bitmap('blue', 'PNG'))
        forms[rarity] = dict(power=5, speed=6, iq=7, popularity=8,
                             card_type='IQ_TYPE', image_path=str(path),
                             photo_file_id='old-photo-' + rarity,
                             sticker_file_id='old-sticker-' + rarity)
    payload = dict(name='Heisenberg', biography='Story', dialogs=['Victory'], variants=forms)
    response = client.post('/api/cards/family', json=payload)
    assert response.status_code == 201, response.get_json()
    key = response.get_json()['card']['id']
    db.get_or_create_player(1)
    db.add_card_to_player(1, key)
    return db, client, key, payload


@pytest.mark.parametrize('kind', ['image', 'sticker'])
@pytest.mark.parametrize('rarity', ['normal', 'epic'])
def test_upload_expires_only_target_form_even_when_file_path_is_reused(editor, kind, rarity):
    db, client, key, _ = editor
    inventory_before = db.get_player_card_counts(1)
    paths = []
    for color in ('red', 'green'):
        response = client.post('/api/upload_' + kind, data={
            'card_id': key, 'card_name': 'Renamed before saving', 'rarity': rarity,
            kind: (BytesIO(bitmap(color)), 'replacement.webp'),
        })
        assert response.status_code == 200, response.get_json()
        paths.append(response.get_json()[kind + '_path'])
        assert db.get_card_variant_media_file_id(key, rarity, 'sticker') is None
        photo = db.get_card_variant_media_file_id(key, rarity, 'photo')
        assert photo == ('old-photo-' + rarity if kind == 'sticker' else None)
        for other in {'normal', 'epic', 'legend'} - {rarity}:
            assert db.get_card_variant_media_file_id(key, other, 'sticker') == 'old-sticker-' + other
        if rarity == 'normal':
            assert db.get_card_media_file_id(key, 'sticker') is None
        else:
            assert db.get_card_media_file_id(key, 'sticker') == 'old-sticker-normal'
        db.set_card_variant_media_file_id(key, rarity, 'old-sticker-' + rarity, 'sticker')
    assert paths[0] == paths[1]
    assert db.get_player_card_counts(1) == inventory_before


def test_uploaded_form_sticker_reaches_victory_instead_of_old_id_or_card_photo(editor):
    db, client, key, _ = editor
    response = client.post('/api/upload_sticker', data={
        'card_name': 'Heisenberg', 'rarity': 'normal',
        'sticker': (BytesIO(bitmap('red')), 'winner.webp'),
    })
    assert response.status_code == 200
    card = db.get_card_by_id_for_rarity(key, 'normal')
    context = SimpleNamespace(bot_data={})
    send = AsyncMock()
    assert asyncio.run(send_card_sticker(SimpleNamespace(db=db), context, card, send))
    sent = Image.open(BytesIO(send.await_args.args[0].getvalue())).convert('RGB')
    assert sent.getpixel((30, 30))[0] > 200
    assert sent.getpixel((30, 30))[2] < 40  # Red sticker, not blue card art.
    from pathlib import Path
    assert Path(BattleHandlersMixin()._resolve_card_sticker_path(card)).resolve() == Path(
        response.get_json()['sticker_path']).resolve()
    handler = BattleHandlersMixin()
    handler.db, handler.config = db, {}
    telegram = SimpleNamespace(send_sticker=AsyncMock(), send_photo=AsyncMock())
    assert asyncio.run(handler._send_round_winner_card_media(SimpleNamespace(bot=telegram), 1, card))
    telegram.send_sticker.assert_awaited_once()
    telegram.send_photo.assert_not_awaited()


@pytest.mark.parametrize('endpoint', ['family', 'variant'])
@pytest.mark.parametrize('explicit_new_id', [False, True])
def test_image_path_change_expires_old_ids_but_preserves_new_explicit_ids(editor, endpoint, explicit_new_id):
    db, client, key, payload = editor
    form = payload['variants']['normal']
    form['image_path'] = 'assets/card_images/replacement.png'
    if explicit_new_id:
        form.update(photo_file_id='new-photo', sticker_file_id='new-sticker')
    if endpoint == 'family':
        response = client.put('/api/cards/' + key + '/family', json=payload)
    else:
        response = client.put('/api/cards/' + key + '/variants/normal',
                              json=dict(form, name=payload['name'], rarity='normal'))
    assert response.status_code == 200, response.get_json()
    assert db.get_card_variant_media_file_id(key, 'normal', 'sticker') == ('new-sticker' if explicit_new_id else None)
    assert db.get_card_variant_media_file_id(key, 'normal', 'photo') == ('new-photo' if explicit_new_id else None)
    assert db.get_card_variant_media_file_id(key, 'epic', 'sticker') == 'old-sticker-epic'


def test_image_upload_fallback_uses_new_art_not_legacy_shared_sticker(editor):
    db, client, key, payload = editor
    from pathlib import Path
    legacy = Path('assets/stickers/HEISENBERG.webp')
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(bitmap('green'))
    response = client.post('/api/upload_image', data={
        'card_name': 'Heisenberg', 'rarity': 'normal',
        'image': (BytesIO(bitmap('red', 'PNG')), 'new.png'),
    })
    assert response.status_code == 200
    form = payload['variants']['normal']
    form.update(image_path=response.get_json()['image_path'], photo_file_id='', sticker_file_id='')
    assert client.put('/api/cards/' + key + '/family', json=payload).status_code == 200
    card = db.get_card_by_id_for_rarity(key, 'normal')
    assert sticker_path(card) is None
    send = AsyncMock()
    assert asyncio.run(send_card_sticker(SimpleNamespace(db=db), SimpleNamespace(bot_data={}), card, send))
    sent = Image.open(BytesIO(send.await_args.args[0].getvalue())).convert('RGB')
    assert sent.getpixel((30, 30))[0] > 200


def test_form_stickers_never_leak_to_other_forms_or_custom_cards(editor):
    db, _, key, _ = editor
    from pathlib import Path
    path = Path('assets/stickers/HEISENBERG_NORMAL.webp')
    path.parent.mkdir(parents=True)
    path.write_bytes(bitmap('red'))
    assert sticker_path(db.get_card_by_id_for_rarity(key, 'epic')) is None
    card = db.get_card_by_id_for_rarity(key, 'normal')
    card.origin = 'custom'
    assert sticker_path(card) is None
