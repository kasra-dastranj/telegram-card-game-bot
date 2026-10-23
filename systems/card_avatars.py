"""Uploaded character avatars and independently selected display slots."""
import sqlite3
import uuid
from contextlib import closing
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


SLOTS = ('profile', 'easy', 'deck')
RARITIES = ('rare', 'legend')
MAX_UPLOAD = 8 * 1024 * 1024


def media_root(db):
    from systems.custom_cards import media_root as private_media_root
    return private_media_root(db) / 'avatars'


def ensure_in(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS card_avatars (
        card_id TEXT NOT NULL,rarity TEXT NOT NULL,filename TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(card_id,rarity))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS player_avatar_choices (
        user_id INTEGER NOT NULL,slot TEXT NOT NULL,card_id TEXT NOT NULL,rarity TEXT NOT NULL,
        PRIMARY KEY(user_id,slot))''')


def _valid_card_in(conn, card_id, rarity):
    if rarity not in RARITIES:
        return False
    row = conn.execute('SELECT origin,rarity FROM cards WHERE card_id=?', (card_id,)).fetchone()
    if not row:
        return False
    if row[0] == 'custom':
        return rarity == 'legend' and row[1] == 'legend'
    if row[0] != 'official':
        return False
    if rarity == 'rare':
        return row[1] == 'rare'
    return conn.execute('SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?',
                        (card_id, rarity)).fetchone() is not None


def prepare_image(raw):
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError('avatar_size_invalid')
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 16_000_000:
                raise ValueError('avatar_image_invalid')
            image.load()
            artwork = ImageOps.contain(image.convert('RGBA'), (512, 512), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
            canvas.alpha_composite(artwork, ((512 - artwork.width) // 2, (512 - artwork.height) // 2))
            output = BytesIO()
            canvas.save(output, format='PNG', optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('avatar_image_invalid') from error


def save_upload(db, card_id, rarity, raw):
    image = prepare_image(raw)
    root = media_root(db)
    root.mkdir(parents=True, exist_ok=True)
    filename = uuid.uuid4().hex + '.png'
    path = root / filename
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        ensure_in(conn)
        if not _valid_card_in(conn, card_id, rarity):
            raise ValueError('avatar_card_invalid')
        path.write_bytes(image)
        try:
            conn.execute('''INSERT INTO card_avatars(card_id,rarity,filename) VALUES(?,?,?)
                ON CONFLICT(card_id,rarity) DO UPDATE SET filename=excluded.filename,
                updated_at=CURRENT_TIMESTAMP''', (card_id, rarity, filename))
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return filename


def path_for(db, card_id, rarity):
    with closing(sqlite3.connect(db.db_path)) as conn:
        ensure_in(conn)
        row = conn.execute('SELECT filename FROM card_avatars WHERE card_id=? AND rarity=?',
                           (card_id, rarity)).fetchone()
    path = media_root(db) / row[0] if row else None
    return path if path and path.is_file() else None


def choices(db, user_id):
    from systems.easy_presentation import choices as owned_choices
    return [item for item in owned_choices(db, user_id)
            if item['rarity'] in RARITIES and path_for(db, item['card_id'], item['rarity'])]


def selected(db, user_id, slot):
    if slot not in SLOTS:
        raise ValueError('avatar_slot_invalid')
    with closing(sqlite3.connect(db.db_path)) as conn:
        ensure_in(conn)
        row = conn.execute('SELECT card_id,rarity FROM player_avatar_choices WHERE user_id=? AND slot=?',
                           (user_id, slot)).fetchone()
    if not row:
        return None
    from systems.easy_presentation import owned_card
    card = owned_card(db, user_id, row[0], row[1])
    path = path_for(db, row[0], row[1])
    return {'card': card, 'path': path, 'card_id': row[0], 'rarity': row[1]} if card and path else None


def save_choice(db, user_id, slot, card_id, rarity):
    if slot not in SLOTS:
        raise ValueError('avatar_slot_invalid')
    from systems.easy_presentation import owned_card_in
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        ensure_in(conn)
        if not owned_card_in(db, conn, user_id, card_id, rarity) or not path_for(db, card_id, rarity):
            raise ValueError('این آواتار را نداری یا تصویرش هنوز بارگذاری نشده است.')
        conn.execute('''INSERT INTO player_avatar_choices VALUES(?,?,?,?)
            ON CONFLICT(user_id,slot) DO UPDATE SET card_id=excluded.card_id,rarity=excluded.rarity''',
                     (user_id, slot, card_id, rarity))


def clear_choice(db, user_id, slot):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        ensure_in(conn)
        conn.execute('DELETE FROM player_avatar_choices WHERE user_id=? AND slot=?', (user_id, slot))


async def send_sticker(bot, context, chat_id, user_id, slot):
    choice = selected(bot.db, user_id, slot)
    if not choice:
        return False
    from bot.card_reward_presentation import sticker_bytes
    sticker = BytesIO(sticker_bytes(choice['path'].read_bytes()))
    sticker.name = 'avatar.webp'
    try:
        await context.bot.send_sticker(chat_id=chat_id, sticker=sticker)
        return True
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Could not send selected avatar', exc_info=True)
        return False
