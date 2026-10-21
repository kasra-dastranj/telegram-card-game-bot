"""Cosmetic delivery; Telegram errors never propagate into battle settlement."""
import asyncio
import logging
from contextlib import closing
from io import BytesIO
import sqlite3

from telegram.error import BadRequest
from systems.victory_voices import audio_bytes, read_in, put_in, card_choices

logger = logging.getLogger(__name__)


async def send(db, context, chat_id, media_id, scope, markup=None, owner_id=None):
    try:
        if owner_id is not None and (not scope.startswith('card:')
                or media_id not in card_choices(db, owner_id, scope[5:], 'legend')):
            return False
        # Resolve/hash even for cached Telegram IDs, so removed/private files do
        # not remain deliverable through an old public media cache.
        raw = await asyncio.wait_for(asyncio.to_thread(audio_bytes, db, media_id, scope), 5)
        try:
            bot_id = context.bot.id
        except (AttributeError, RuntimeError):
            bot_id = None
        cache_key = 'voice-cache:' + str(bot_id) + ':' + media_id if type(bot_id) is int else None
        with closing(sqlite3.connect(db.db_path)) as conn:
            cached = read_in(conn, cache_key) if cache_key else None
        async def upload(voice):
            return await asyncio.wait_for(context.bot.send_voice(
                chat_id=chat_id, voice=voice, reply_markup=markup), 10)
        result = None
        if cached:
            try:
                result = await upload(cached)
            except BadRequest:
                pass
        if result is None:
            stream = BytesIO(raw)
            stream.name = 'victory.ogg'
            result = await upload(stream)
        file_id = getattr(getattr(result, 'voice', None), 'file_id', None)
        if cache_key and isinstance(file_id, str) and file_id:
            with closing(sqlite3.connect(db.db_path)) as conn, conn:
                put_in(conn, cache_key, file_id)
        return True
    except Exception:
        logger.warning('Victory voice unavailable; using text dialogue')
        return False
