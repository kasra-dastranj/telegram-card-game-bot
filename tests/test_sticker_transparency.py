"""Sticker alpha survives upload, decoding, fallback art, resizing and WebP send."""
import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image, ImageDraw
import pytest

from bot.battle_visual_delivery import card_art, read_bitmap
from bot.card_reward_presentation import send_card_sticker, sticker_bytes
from bot import battle_visuals
from core.database import DatabaseManager
from web.web_api import WebAPI
import web.web_api as web_module


def transparent_art(size=(512, 512), kind='WEBP'):
    width, height = size
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((width//3, height//3, 2*width//3, height-1), fill=(240, 180, 40, 128))
    draw.rectangle((2*width//3+1, height//3, width-1, height-1), fill=(240, 180, 40, 255))
    draw.polygon([(width//2, 0), (width//3, height//4), (2*width//3, height//4)], fill=(240, 180, 40, 255))
    output = BytesIO()
    image.save(output, kind, **({'lossless': True} if kind == 'WEBP' else {}))
    return output.getvalue()


def assert_transparency(raw):
    with Image.open(BytesIO(raw)) as image:
        image = image.convert('RGBA')
        width, height = image.size
        assert image.getpixel((0, 0))[3] == 0  # Empty space beside the crown.
        center = image.getpixel((width//2, 2*height//3))
        assert center[3] == 128 and center[0] > 200 and center[1] > 140
        assert image.getpixel((width-2, height-2))[3] == 255


@pytest.mark.parametrize('kind', ['PNG', 'WEBP'])
@pytest.mark.parametrize('size', [(512, 512), (1024, 512), (173, 301)])
def test_sticker_preserves_transparent_and_soft_edges_at_telegram_size(kind, size):
    raw = transparent_art(size, kind)
    result = sticker_bytes(raw)
    assert_transparency(result)
    with Image.open(BytesIO(result)) as image:
        assert image.format == 'WEBP' and max(image.size) == 512
        assert len(result) <= 512*1024
        if size == (512, 512):
            before = Image.open(BytesIO(raw)).convert('RGBA').getchannel('A')
            assert image.convert('RGBA').getchannel('A').tobytes() == before.tobytes()


def test_palette_png_transparency_survives_sticker_conversion():
    image = Image.new('P', (512, 512))
    image.putpalette([0, 0, 0, 240, 180, 40, 240, 180, 40] + [0]*759)
    image.info['transparency'] = bytes([0, 128, 255])
    image.paste(1, (200, 200, 350, 512))
    image.paste(2, (350, 200, 512, 512))
    stream = BytesIO()
    image.save(stream, 'PNG')
    assert_transparency(sticker_bytes(stream.getvalue()))


def test_local_photo_and_transparent_art_do_not_share_preprocessed_cache(tmp_path):
    path = tmp_path / 'crown.webp'
    path.write_bytes(transparent_art())
    photo = read_bitmap(path)
    alpha = read_bitmap(path, True)
    assert Image.open(BytesIO(photo)).format == 'JPEG'
    assert Image.open(BytesIO(alpha)).format == 'PNG'
    assert_transparency(alpha)
    assert read_bitmap(path) == photo and read_bitmap(path, True) == alpha
    assert battle_visuals.safe_bitmap(path.read_bytes()).mode == 'RGB'


def test_downloaded_photo_and_transparent_art_have_distinct_cache_entries():
    raw = transparent_art()
    remote = SimpleNamespace(file_size=len(raw), download_as_bytearray=AsyncMock(return_value=bytearray(raw)))
    handler = SimpleNamespace(db=SimpleNamespace(get_card_variant_media_file_id=lambda cid, rarity, kind: 'remote' if kind == 'sticker' else None))
    card = SimpleNamespace(card_id='test', rarity=SimpleNamespace(value='legend'), image_path='')
    context = SimpleNamespace(bot_data={}, bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
    async def run():
        photo = await card_art(handler, context, card)
        alpha = await card_art(handler, context, card, preserve_alpha=True)
        again = await card_art(handler, context, card, preserve_alpha=True)
        return photo, alpha, again
    photo, alpha, again = asyncio.run(run())
    assert Image.open(BytesIO(photo)).format == 'JPEG'
    assert_transparency(alpha)
    assert alpha == again and context.bot.get_file.await_count == 2


@pytest.mark.parametrize('source', ['uploaded_sticker', 'form_image'])
def test_uploaded_or_fallback_transparency_reaches_real_sticker_sender(tmp_path, monkeypatch, source):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_module, 'PROJECT_ROOT', tmp_path)
    db = DatabaseManager(str(tmp_path / 'cards.db'))
    api = WebAPI(db)
    raw = transparent_art()
    path = tmp_path / 'form.webp'
    path.write_bytes(raw)
    forms = {r: dict(power=5, speed=6, iq=7, popularity=8,
                     image_path=str(path) if source == 'form_image' else '') for r in ('normal', 'epic', 'legend')}
    client = api.app.test_client()
    created = client.post('/api/cards/family', json={'name': 'Heisenberg', 'variants': forms}).get_json()['card']
    cid = created['id']
    if source == 'uploaded_sticker':
        db.set_card_variant_media_file_id(cid, 'normal', 'old-file-id', 'sticker')
        response = client.post('/api/upload_sticker', data={'card_id': cid, 'card_name': 'Heisenberg', 'rarity': 'normal',
                                                          'sticker': (BytesIO(raw), 'crown.webp')})
        assert response.status_code == 200 and db.get_card_variant_media_file_id(cid, 'normal', 'sticker') is None
        assert (tmp_path / response.get_json()['sticker_path']).read_bytes() == raw
    sender = AsyncMock()
    assert asyncio.run(send_card_sticker(SimpleNamespace(db=db), SimpleNamespace(bot_data={}),
                                         db.get_card_by_id_for_rarity(cid, 'normal'), sender))
    sender.assert_awaited_once()
    assert_transparency(sender.await_args.args[0].getvalue())
    assert sender.await_args.kwargs['reply_markup'] is not None


def test_selected_avatar_transparency_reaches_telegram(tmp_path, monkeypatch):
    from systems import card_avatars
    path = tmp_path / 'avatar.png'
    path.write_bytes(transparent_art(kind='PNG'))
    monkeypatch.setattr(card_avatars, 'selected', lambda *args: {'path': path})
    context = SimpleNamespace(bot=SimpleNamespace(send_sticker=AsyncMock()))
    assert asyncio.run(card_avatars.send_sticker(SimpleNamespace(db=None), context, -1, 1, 'easy'))
    assert_transparency(context.bot.send_sticker.await_args.kwargs['sticker'].getvalue())


@pytest.mark.parametrize('raw', [b'not an image', b'x'*(8*1024*1024+1)], ids=['invalid', 'oversized'])
def test_transparency_path_keeps_existing_decode_size_guards(raw):
    with pytest.raises((OSError, ValueError)):
        sticker_bytes(raw)
