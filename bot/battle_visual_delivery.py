"""Bounded, optional presentation work after the game engine has made its decision."""
import asyncio
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
import logging
import os
from pathlib import Path
import re

from PIL import Image

from bot import battle_visuals as visual

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def data(context):
    value = getattr(context, 'bot_data', None)
    return value if isinstance(value, dict) else {}


def limited_cache(context, name, limit):
    cache = data(context).setdefault(name, OrderedDict())
    while len(cache) >= limit:
        cache.popitem(last=False)
    return cache


@lru_cache(maxsize=24)
def local_bitmap(path, modified, size):
    if size > 8 * 1024 * 1024:
        raise ValueError('media_size_limit')
    image = visual.safe_bitmap(Path(path).read_bytes())
    image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    return visual.encode(image)


def read_bitmap(path):
    path = Path(path)
    stat = path.stat()
    return local_bitmap(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def choose_background(arena):
    arena_id = arena.get('arena_id') or arena.get('id') or 'default'
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,40}', str(arena_id)):
        return visual.background('default')
    # Fixed local image roots only. No URLs are fetched or interpreted as paths.
    roots = [Path(os.environ.get('TELBATTLE_BATTLE_MEDIA_DIR', ROOT / 'assets/battle_visuals/overrides'))]
    url = str(arena.get('background_url') or '')
    for root in roots:
        for extension in ('.webp', '.png', '.jpg', '.jpeg'):
            try:
                return read_bitmap(root / (arena_id + extension))
            except (OSError, ValueError):
                continue
    prefix = '/miniapp-assets/arena-backgrounds/'
    if url.startswith(prefix):
        filename = url[len(prefix):]
        root = Path(os.environ.get('MINIAPP_ARENA_MEDIA_DIR', ROOT / 'media/arena-backgrounds')).resolve()
        candidate = (root / filename).resolve()
        if (filename == Path(filename).name and root in candidate.parents
                and candidate.suffix.lower() in ('.webp', '.png', '.jpg', '.jpeg')):
            try:
                return read_bitmap(candidate)
            except (OSError, ValueError):
                pass
    return visual.background(arena_id)


async def work(context, function, *args):
    # Limit expensive image work without occupying the bot's event-loop thread.
    semaphore = data(context).setdefault('_battle_visual_worker', asyncio.Semaphore(1))
    await asyncio.wait_for(semaphore.acquire(), timeout=2)
    try:
        return await asyncio.to_thread(function, *args)
    finally:
        semaphore.release()


async def match_background(context, key, arena, mode):
    identity = (str(key), mode, arena.get('arena_id') or arena.get('id'), arena.get('version'))
    cache = limited_cache(context, '_battle_visual_backgrounds', 64)
    if identity not in cache:
        cache[identity] = await work(context, choose_background, arena)
    return cache[identity]


async def send_arena(context, user_id, key, arena, mode):
    if not callable(getattr(context.bot, 'send_photo', None)):
        return False
    identity = (str(key), user_id, mode, arena.get('arena_id') or arena.get('id'), arena.get('version'))
    sent = limited_cache(context, '_battle_visual_arena_sent', 256)
    if identity in sent:
        return True
    try:
        raw = await match_background(context, key, arena, mode)
        rendered = await work(context, visual.render_arena, arena, mode, raw)
        await context.bot.send_photo(chat_id=user_id, photo=BytesIO(rendered))
        sent[identity] = True
        return True
    except Exception:
        logger.warning('Arena image unavailable; keeping text presentation')
        return False


async def card_art(handler, context, card):
    if not card:
        return None
    # A form-specific file is preferred; never borrow another form's artwork.
    path = getattr(card, 'image_path', '')
    if path:
        try:
            return await work(context, read_bitmap, path)
        except (OSError, ValueError):
            pass
    rarity = str(getattr(getattr(card, 'rarity', None), 'value', getattr(card, 'rarity', 'normal')))
    getter = getattr(handler.db, 'get_card_variant_media_file_id', None)
    cache = limited_cache(context, '_battle_visual_card_media', 48)
    for kind in (('photo', 'sticker') if callable(getter) and callable(getattr(context.bot, 'get_file', None)) else ()):
        try:
            file_id = getter(card.card_id, rarity, kind)
            if not file_id:
                continue
            if file_id in cache:
                return cache[file_id]
            remote = await asyncio.wait_for(context.bot.get_file(file_id), timeout=3)
            if remote.file_size and remote.file_size > 8 * 1024 * 1024:
                continue
            raw = bytes(await asyncio.wait_for(remote.download_as_bytearray(), timeout=3))
            def reduce():
                bitmap = visual.safe_bitmap(raw)
                bitmap.thumbnail((480, 640), Image.Resampling.LANCZOS)
                return visual.encode(bitmap)
            cache[file_id] = await work(context, reduce)
            return cache[file_id]
        except Exception:
            continue
    # Older official Normal cards may only have the configured name-based image.
    # This lookup is safe solely for the base form; variants require their own media.
    base = handler.db.get_card_by_id(card.card_id)
    if base and base.rarity == card.rarity:
        for name in ('_resolve_card_photo_path', '_resolve_card_media_path'):
            resolver = getattr(handler, name, None)
            if callable(resolver):
                try:
                    path = resolver(card)
                    if path:
                        return await work(context, read_bitmap, path)
                except (OSError, ValueError, AttributeError):
                    continue
    return None


async def quick_model(handler, context, report):
    players = []
    for uid in report['players']:
        item = report.get('breakdown', {}).get(str(uid), {})
        player = handler.db.get_or_create_player(uid)
        cards = []
        if item:
            card = handler.db.get_card_by_id_for_rarity(item['card_id'], item.get('card_rarity', 'normal'))
            cards = [{'name': item['card_name'], 'rarity': item.get('card_rarity', 'normal'),
                      'image': await card_art(handler, context, card)}]
        components = item.get('final_components', [])
        players.append({'id': uid, 'name': player.first_name or str(uid), 'cards': cards,
                        'score': item.get('final_value'),
                        'reward': report.get('rewards', {}).get(str(uid), {}),
                        'equation': ' + '.join(map(str, components)) + ' = ' + str(item['final_value']) if components else ''})
    winner = next((p['name'] for p in players if p['id'] == report.get('winner_id')), None)
    arena = report.get('arena_data') or {}
    return {'mode': 'quick', 'arena_name': arena.get('name_fa') or arena.get('name', ''),
            'winner_name': winner, 'players': players, 'forfeit': report.get('forfeit')}


async def quick_picture(handler, context, report):
    if not callable(getattr(context.bot, 'send_photo', None)):
        return None
    try:
        arena = report.get('arena_data') or dict(handler.modes._arena(report['arena']))
        arena = dict(arena, arena_id=report.get('arena') or arena.get('arena_id'))
        model = await quick_model(handler, context, dict(report, arena_data=arena))
        raw = await match_background(context, report['request_id'], arena, 'quick')
        return await work(context, visual.render_result, model, raw)
    except Exception:
        logger.warning('Quick result image unavailable; keeping text result')
        return None


async def deck_picture(handler, context, fight_id, fight, cards, scores, winner_id, report, awards):
    if not callable(getattr(context.bot, 'send_photo', None)):
        return None
    try:
        arena = handler._battle_arena_snapshot(fight_id) or (report or {}).get('arena') or {}
        state = handler.db.get_battle_deck_state(fight_id)
        arena_id = arena.get('arena_id') or state.get('arena') or getattr(fight, 'arena_type', None) or 'default'
        arena = dict(arena, arena_id=arena_id)
        mode = handler._fight_arena_mode(fight_id)
        players = []
        for uid, role, last_card, score in zip((fight.challenger_id, fight.opponent_id), ('challenger', 'opponent'), cards, scores):
            items = []
            played = [item.get('cards', {}).get(str(uid)) for item in (report or {}).get('rounds', [])]
            played = [item for item in played if item]
            if played:
                for item in played[:3]:
                    cid = item.get('card_id')
                    card = handler.db.get_card_by_id_for_rarity(cid, item['rarity']) if cid else None
                    items.append({'name': item['name'], 'rarity': item['rarity'],
                                  'image': await card_art(handler, context, card)})
            elif mode != 'deck':
                items.append({'name': last_card.name, 'rarity': last_card.rarity.value,
                              'image': await card_art(handler, context, last_card)})
            players.append({'id': uid, 'name': handler._battle_player_name(uid, 'Player'),
                            'cards': items, 'score': score, 'reward': awards[str(uid)]})
            total = (report or {}).get('totals', {}).get(str(uid))
            if total:
                players[-1]['equation'] = f"{total['base']} + {total['bonus']} = {total['total']}"
        from bot.deck_reports import winner_lines
        model = {'mode': 'deck' if mode == 'deck' else 'three_round', 'arena_name': arena.get('name_fa', ''),
                 'winner_name': next((p['name'] for p in players if p['id'] == winner_id), None),
                 'players': players, 'round_lines': winner_lines(report).splitlines() if report else []}
        raw = await match_background(context, fight_id, arena, mode)
        return await work(context, visual.render_result, model, raw)
    except Exception:
        logger.warning('Deck result image unavailable; keeping text result')
        return None


async def send_result(context, chat_id, image, text, markup):
    if not image:
        return False
    try:
        await context.bot.send_photo(chat_id=chat_id, photo=BytesIO(image), caption=text, reply_markup=markup)
        return True
    except Exception:
        logger.warning('Result photo delivery failed; keeping text result')
        return False
