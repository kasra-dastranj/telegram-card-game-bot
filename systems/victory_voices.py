"""Private, bounded cosmetic audio. No gameplay flags, migrations or wallet writes."""
import hashlib
import json
import re
import sqlite3
import struct
import uuid
from contextlib import closing
from datetime import datetime, timezone

from systems.custom_cards import media_root

MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 30


def read_in(conn, key, default=None):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put_in(conn, key, value):
    conn.execute('INSERT OR REPLACE INTO foundation_settings(key,value_json) VALUES (?,?)',
                 (key, json.dumps(value, ensure_ascii=False)))


def ogg_duration(raw):
    """Validate one complete Ogg/Opus stream, checksums, bounds and duration.

    Decoding/transcoding is deliberately outside the battle loop. Telegram still
    validates the codec payload; a rejected upload falls back to the text line.
    """
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('ویس باید حداکثر ۴ مگابایت باشد.')
    offset, serial, sequence, packets, packet, granule = 0, None, 0, [], b'', 0
    finished = False
    while offset < len(raw):
        header = raw[offset:offset + 27]
        if len(header) != 27 or header[:5] != b'OggS\0' or finished:
            raise ValueError('فایل باید یک ویس کامل OGG با کدک Opus باشد.')
        flags = header[5]
        segments = raw[offset + 27:offset + 27 + header[26]]
        end = offset + 27 + len(segments) + sum(segments)
        if len(segments) != header[26] or end > len(raw):
            raise ValueError('فایل ویس ناقص است.')
        page = bytearray(raw[offset:end])
        checksum = int.from_bytes(page[22:26], 'little')
        page[22:26] = b'\0' * 4
        crc = 0
        for byte in page:
            crc ^= byte << 24
            for _ in range(8):
                crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
        page_serial, page_sequence = struct.unpack_from('<II', header, 14)
        if (crc != checksum or flags & ~7 or page_sequence != sequence
                or sequence == 0 and (not flags & 2 or flags & 1)
                or sequence > 0 and (flags & 2 or page_serial != serial)
                or bool(flags & 1) != bool(packet)):
            raise ValueError('ساختار فایل OGG معتبر نیست.')
        serial, sequence = page_serial, sequence + 1
        pos = offset + 27 + len(segments)
        for length in segments:
            packet += raw[pos:pos + length]
            pos += length
            if length < 255:
                if len(packets) < 3:
                    packets.append(packet)
                packet = b''
        value = int.from_bytes(header[6:14], 'little')
        if value != 2**64 - 1:
            granule = value
        finished = bool(flags & 4)
        offset = end
    if (not finished or packet or len(packets) < 3 or len(packets[0]) < 19
            or not packets[0].startswith(b'OpusHead\x01') or packets[0][9] not in (1, 2)
            or not packets[1].startswith(b'OpusTags')):
        raise ValueError('فایل باید OGG با کدک Opus باشد؛ ویس تلگرام را دانلود کن.')
    duration = (granule - int.from_bytes(packets[0][10:12], 'little')) / 48000
    if not 0 < duration <= MAX_SECONDS:
        raise ValueError('مدت ویس باید بیشتر از صفر و حداکثر ۳۰ ثانیه باشد.')
    return duration


def root(db):
    return media_root(db) / 'voices'


def asset_in(conn, media_id, scope=None):
    if not isinstance(media_id, str) or not re.fullmatch('[a-f0-9]{32}', media_id):
        return None
    item = read_in(conn, 'voice-media:' + media_id)
    return item if item and (scope is None or item.get('scope') == scope) else None


def upload(db, raw, scope, actor):
    duration = ogg_duration(raw)
    media_id = uuid.uuid4().hex
    directory = root(db)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (media_id + '.ogg')
    with path.open('xb') as target:
        target.write(raw)
    try:
        with closing(sqlite3.connect(db.db_path)) as conn, conn:
            put_in(conn, 'voice-media:' + media_id, {'scope': scope, 'duration': duration,
                   'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'actor': actor,
                   'created_at': datetime.now(timezone.utc).isoformat()})
    except Exception:
        path.unlink()
        raise
    return media_id


def audio_bytes(db, media_id, scope):
    """Resolve only opaque IDs inside the private media root; never remote URLs."""
    with closing(sqlite3.connect(db.db_path)) as conn:
        item = asset_in(conn, media_id, scope)
    if not item:
        raise ValueError('ویس در دسترس نیست.')
    directory = root(db).resolve()
    path = directory / (media_id + '.ogg')
    if path.resolve().parent != directory:
        raise ValueError('مسیر ویس معتبر نیست.')
    with path.open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise ValueError('فایل ویس تغییر کرده یا ناقص است.')
    return raw


def card_scope(conn, card_id):
    row = conn.execute('SELECT origin,rarity FROM cards WHERE card_id=?', (card_id,)).fetchone()
    if not row:
        raise ValueError('کارت پیدا نشد.')
    if row[0] == 'custom':
        if row[1] != 'legend':
            raise ValueError('ویس کارت فقط برای Legend است.')
    elif row[1] != 'legend' and not conn.execute(
            "SELECT 1 FROM card_variants WHERE card_id=? AND rarity='legend'", (card_id,)).fetchone():
        raise ValueError('فرم Legend این کارت آماده نیست.')
    return row[0]


def owned_in(conn, user_id, card_id):
    row = conn.execute('SELECT origin,rarity FROM cards WHERE card_id=?', (card_id,)).fetchone()
    if not row:
        return False
    if row[0] == 'official':
        return bool(conn.execute("SELECT 1 FROM player_card_stacks WHERE user_id=? AND card_id=? AND rarity='legend' AND quantity>0",
                                 (user_id, card_id)).fetchone())
    return row[1] == 'legend' and bool(conn.execute('''SELECT 1 FROM custom_grants g JOIN custom_definitions d USING(card_id)
        WHERE g.user_id=? AND g.card_id=? AND g.active=1 AND d.status='active' ''', (user_id, card_id)).fetchone())


def owned(db, user_id, card_id):
    with closing(sqlite3.connect(db.db_path)) as conn:
        return owned_in(conn, user_id, card_id)


def preference(db, user_id, card_id, mode=None):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        if mode is not None:
            conn.execute('BEGIN IMMEDIATE')
        if not owned_in(conn, user_id, card_id):
            raise ValueError('این کارت Legend رو نداری یا دیگه در دسترست نیست.')
        key = 'voice-pref:' + str(user_id) + ':' + card_id
        if mode is not None:
            if mode not in ('text', 'voice'):
                raise ValueError('متن یا ویس را انتخاب کن.')
            put_in(conn, key, mode)
        return read_in(conn, key, 'voice')


def card_settings_in(conn, card_id):
    return read_in(conn, 'card-voices:' + card_id, {'revision': 0, 'media_ids': []})


def save_card(db, card_id, value, actor):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        card_scope(conn, card_id)
        prior = card_settings_in(conn, card_id)
        if not isinstance(value, dict) or set(value) != {'revision', 'media_ids'}:
            raise ValueError('تنظیم ویس نامعتبر است.')
        if type(value['revision']) is not int or value['revision'] != prior['revision']:
            raise ValueError('تنظیم عوض شده؛ دوباره بارگذاری کن.')
        ids = value['media_ids']
        if not isinstance(ids, list) or len(ids) > 5 or len(set(map(str, ids))) != len(ids):
            raise ValueError('حداکثر پنج ویس متفاوت برای هر کارت مجاز است.')
        if any(not asset_in(conn, key, 'card:' + card_id) for key in ids):
            raise ValueError('ویس باید برای همین کارت آپلود شده باشد.')
        result = {'revision': prior['revision'] + 1, 'media_ids': ids}
        put_in(conn, 'card-voices:' + card_id, result)
        put_in(conn, 'voice-audit:' + uuid.uuid4().hex, {'card_id': card_id, 'actor': actor, **result})
        return result


def card_choices(db, user_id, card_id, rarity):
    if rarity != 'legend':
        return []
    with closing(sqlite3.connect(db.db_path)) as conn:
        if not owned_in(conn, user_id, card_id):
            return []
        if read_in(conn, 'voice-pref:' + str(user_id) + ':' + card_id, 'voice') != 'voice':
            return []
        return card_settings_in(conn, card_id)['media_ids']
