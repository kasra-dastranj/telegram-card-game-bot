"""Opaque, bounded media uploads under the existing shared private root."""
import gzip
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 7 * 1024 * 1024


def root(db):
    from systems.custom_cards import media_root
    return media_root(db) / 'easter-eggs'


def ensure_in(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS easter_media(
        media_id TEXT PRIMARY KEY,kind TEXT NOT NULL,filename TEXT NOT NULL,mime TEXT NOT NULL,
        sha256 TEXT NOT NULL,size INTEGER NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)''')


def metadata_in(conn, media_id):
    ensure_in(conn)
    if not isinstance(media_id, str) or len(media_id) != 32 or any(c not in '0123456789abcdef' for c in media_id):
        return None
    row = conn.execute('SELECT kind,filename,mime,sha256,size FROM easter_media WHERE media_id=?', (media_id,)).fetchone()
    return dict(kind=row[0], filename=row[1], mime=row[2], sha256=row[3], size=row[4]) if row else None


def prepare(kind, raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('رسانه باید حداکثر ۷ مگابایت باشد.')
    if kind == 'voice':
        from systems.victory_voices import ogg_duration
        ogg_duration(raw)
        return raw, '.ogg', 'audio/ogg'
    if kind in ('photo', 'sticker'):
        if kind == 'sticker' and raw.startswith(b'\x1f\x8b'):
            if len(raw) > 64 * 1024:
                raise ValueError('استیکر TGS حداکثر ۶۴ کیلوبایت است.')
            try:
                with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                    data = stream.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError()
                value = json.loads(data)
                if not isinstance(value, dict) or not all(key in value for key in ('v', 'fr', 'ip', 'op', 'layers')) or value.get('w') != 512 or value.get('h') != 512:
                    raise ValueError()
            except (ValueError, OSError, EOFError):
                raise ValueError('استیکر TGS معتبر نیست.')
            return raw, '.tgs', 'application/x-tgsticker'
        if kind == 'sticker' and raw.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in raw[:128]:
            if len(raw) > 256 * 1024:
                raise ValueError('استیکر ویدیویی WEBM حداکثر ۲۵۶ کیلوبایت است.')
            return raw, '.webm', 'video/webm'
        try:
            with Image.open(BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > 16_000_000:
                    raise ValueError('تصویر باید PNG، JPG یا WEBP با اندازهٔ مجاز باشد.')
                source.load()
                size = 512 if kind == 'sticker' else 1600
                image = ImageOps.contain(ImageOps.exif_transpose(source).convert('RGBA'), (size, size), Image.Resampling.LANCZOS)
                if kind == 'sticker':
                    canvas = Image.new('RGBA', (512, 512))
                    canvas.alpha_composite(image, ((512-image.width)//2, (512-image.height)//2))
                    image = canvas
                output = BytesIO()
                image.save(output, 'WEBP' if kind == 'sticker' else 'PNG')
                result = output.getvalue()
                if len(result) > (512 * 1024 if kind == 'sticker' else MAX_BYTES):
                    raise ValueError('حجم خروجی تصویر بیش از حد مجاز است.')
                return result, '.webp' if kind == 'sticker' else '.png', 'image/webp' if kind == 'sticker' else 'image/png'
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError('فایل تصویر یا استیکر معتبر نیست.') from error
    if kind == 'video':
        if len(raw) >= 16 and raw[4:8] == b'ftyp':
            return raw, '.mp4', 'video/mp4'
        if raw.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in raw[:128]:
            return raw, '.webm', 'video/webm'
        raise ValueError('ویدئو باید MP4 یا WEBM باشد.')
    raise ValueError('نوع رسانه معتبر نیست.')


def upload(db, actor, kind, raw):
    from systems.easter_eggs import now
    raw, suffix, mime = prepare(kind, raw)
    media_id = uuid.uuid4().hex
    directory = root(db)
    directory.mkdir(parents=True, exist_ok=True)
    filename = media_id + suffix
    path = directory / filename
    path.write_bytes(raw)
    try:
        with closing(sqlite3.connect(db.db_path)) as conn, conn:
            ensure_in(conn)
            conn.execute('INSERT INTO easter_media VALUES(?,?,?,?,?,?,?,?)',
                         (media_id, kind, filename, mime, hashlib.sha256(raw).hexdigest(), len(raw), actor, now()))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return media_id


def read(db, media_id):
    with closing(sqlite3.connect(db.db_path)) as conn:
        item = metadata_in(conn, media_id)
    if not item:
        raise ValueError('رسانه پیدا نشد.')
    directory = root(db).resolve()
    path = (directory / item['filename']).resolve()
    if path.parent != directory:
        raise ValueError('مسیر رسانه معتبر نیست.')
    with path.open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise ValueError('فایل رسانه تغییر کرده یا ناقص است.')
    return item, raw
