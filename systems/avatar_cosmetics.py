"""Layered avatars. Card access is live; frame/background ownership is permanent."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import OrderedDict
from contextlib import closing
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.parse import quote

from PIL import Image, ImageChops, ImageDraw, ImageOps

from systems import card_avatars as faces

DEFAULTS = {'frame': 'silver', 'background': 'red'}
GEOMETRIES = ('circle', 'square', 'diamond', 'ruby', 'custom')
_cache, _lock = OrderedDict(), Lock()


def ensure_in(conn):
    faces.ensure_in(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS avatar_face_metadata (
        card_id TEXT NOT NULL,rarity TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'legacy',
        enabled INTEGER NOT NULL DEFAULT 1,scale REAL NOT NULL DEFAULT 1,
        offset_x REAL NOT NULL DEFAULT 0,offset_y REAL NOT NULL DEFAULT 0,
        PRIMARY KEY(card_id,rarity))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS avatar_cosmetics (
        item_id TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('frame','background')),
        title TEXT NOT NULL,price INTEGER NOT NULL CHECK(price>=0),free INTEGER NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,for_sale INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0,filename TEXT,mask_filename TEXT,
        geometry TEXT NOT NULL DEFAULT 'circle',color TEXT,revision INTEGER NOT NULL DEFAULT 1)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS player_avatar_items (
        user_id INTEGER NOT NULL,item_id TEXT NOT NULL,source TEXT NOT NULL,
        acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,item_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS player_avatar_styles (
        user_id INTEGER NOT NULL,slot TEXT NOT NULL,frame_id TEXT NOT NULL,
        background_id TEXT NOT NULL,inherit_profile INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id,slot))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS avatar_settings (
        key TEXT PRIMARY KEY,value TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS avatar_quote_versions (
        quote_id TEXT PRIMARY KEY,item_revision INTEGER NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS avatar_admin_history (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,
        payload_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for key, value in DEFAULTS.items():
        conn.execute('INSERT OR IGNORE INTO avatar_settings VALUES(?,?)', (key, value))
    for index, (key, title, price, geometry) in enumerate((
        ('silver', 'قاب نقره‌ای', 0, 'circle'), ('gold', 'قاب طلایی', 150, 'circle'),
        ('diamond', 'قاب الماس', 300, 'diamond'), ('ruby', 'قاب یاقوت', 500, 'ruby'))):
        conn.execute('''INSERT OR IGNORE INTO avatar_cosmetics
            (item_id,kind,title,price,free,sort_order,geometry) VALUES(?,?,?,?,?,?,?)''',
                     (key, 'frame', title, price, int(key == 'silver'), index, geometry))
    for index, (key, title, color) in enumerate((('red', 'قرمز', '#8c3045'),
        ('khaki', 'خاکی', '#8b815b'), ('blue', 'آبی', '#315c93'), ('purple', 'بنفش', '#674391'))):
        conn.execute('''INSERT OR IGNORE INTO avatar_cosmetics
            (item_id,kind,title,price,free,sort_order,color) VALUES(?,?,?,0,1,?,?)''',
                     (key, 'background', title, index, color))
    # One-time backfill; subsequent starts must leave player data unchanged.
    if not conn.execute("SELECT 1 FROM avatar_settings WHERE key='defaults_backfilled_v1'").fetchone():
        conn.execute('''INSERT OR IGNORE INTO player_avatar_items(user_id,item_id,source)
            SELECT p.user_id,c.item_id,'free' FROM players p CROSS JOIN avatar_cosmetics c WHERE c.free=1''')
        conn.execute("INSERT INTO avatar_settings VALUES('defaults_backfilled_v1','done')")


def grant_free_in(conn, user):
    conn.execute('''INSERT OR IGNORE INTO player_avatar_items(user_id,item_id,source)
        SELECT ?,item_id,'free' FROM avatar_cosmetics WHERE free=1''', (user,))


def root(db):
    return faces.media_root(db) / 'cosmetics'


def upload(db, raw, mask=False, transparent=False):
    if not raw or len(raw) > faces.MAX_UPLOAD:
        raise ValueError('حجم تصویر باید کمتر از ۸ مگابایت باشد.')
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ('PNG', 'WEBP', 'JPEG') or source.width * source.height > 16_000_000:
                raise ValueError('تصویر معتبر PNG یا WebP انتخاب کن.')
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGBA')
            if image.width != image.height:
                raise ValueError('تصویر آواتار، قاب و ماسک باید مربع باشد.')
            if (transparent or mask) and image.getchannel('A').getextrema() == (255, 255):
                raise ValueError('این تصویر باید پس‌زمینهٔ شفاف داشته باشد.')
            if image.getchannel('A').getextrema()[1] == 0:
                raise ValueError('تصویر کاملاً خالی است.')
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, 'PNG', optimize=True)
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('فایل تصویر خوانده نشد.') from error
    data = output.getvalue()
    name = hashlib.sha256(data).hexdigest() + '.png'
    folder = root(db)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        path.write_bytes(data)
    return name


def file_image(db, name, size=512):
    if not isinstance(name, str) or not re.fullmatch(r'[0-9a-f]{64}\.png', name):
        raise ValueError('فایل تصویر معتبر نیست.')
    with Image.open(root(db) / name) as image:
        return image.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)


def ready(db, item):
    return bool((item['filename'] and (root(db) / item['filename']).is_file()) or
                (item['kind'] == 'background' and item['color']) or item['item_id'] == 'silver') and (
                    item['geometry'] != 'custom' or bool(item['mask_filename'] and
                        (root(db) / item['mask_filename']).is_file()))


def item_in(conn, item_id):
    cursor = conn.execute('SELECT * FROM avatar_cosmetics WHERE item_id=?', (item_id,))
    row = cursor.fetchone()
    return dict(zip((d[0] for d in cursor.description),row)) if row else None


def audit_in(conn, actor, payload):
    conn.execute('INSERT INTO avatar_admin_history(actor,payload_json) VALUES(?,?)',
                 (actor, json.dumps(payload, ensure_ascii=False)))


def save_item(db, actor, data):
    if not isinstance(data, dict):
        raise ValueError('فرم معتبر نیست.')
    key = data.get('item_id')
    if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', key):
        raise ValueError('شناسه را با حروف کوچک انگلیسی، عدد و خط تیره بنویس.')
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN IMMEDIATE')
        old = item_in(conn, key)
        if old and data.get('revision') != old['revision']:
            raise ValueError('این آیتم ویرایش شده؛ فهرست را تازه کن.')
        kind = data.get('kind')
        if kind not in ('frame', 'background') or (old and old['kind'] != kind):
            raise ValueError('نوع آیتم معتبر نیست یا قابل تغییر نیست.')
        title, price = data.get('title'), data.get('price')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
            raise ValueError('عنوان بین ۱ تا ۸۰ حرف لازم است.')
        if type(price) is not int or not 0 <= price <= 1_000_000_000:
            raise ValueError('قیمت سکه معتبر نیست.')
        if any(type(data.get(k)) is not bool for k in ('free', 'enabled', 'for_sale')):
            raise ValueError('وضعیت آیتم معتبر نیست.')
        order = data.get('sort_order', 0)
        if type(order) is not int or not 0 <= order <= 10000:
            raise ValueError('ترتیب نمایش معتبر نیست.')
        geometry = data.get('geometry', 'circle')
        if geometry not in GEOMETRIES:
            raise ValueError('شکل قاب معتبر نیست.')
        color = data.get('color') or None
        if color and (kind != 'background' or not re.fullmatch(r'#[0-9a-fA-F]{6}', color)):
            raise ValueError('رنگ معتبر نیست.')
        for field in ('filename', 'mask_filename'):
            name = data.get(field)
            if name:
                file_image(db, name, 16)
        # Built-in defaults always remain usable; selling can be disabled separately.
        defaults = dict(conn.execute('SELECT key,value FROM avatar_settings'))
        if key in set(defaults.values()) | {'silver', 'red', 'khaki', 'blue', 'purple'} and (not data['free'] or not data['enabled']):
            raise ValueError('آیتم‌های پیش‌فرض باید رایگان و فعال بمانند.')
        new = dict(item_id=key, kind=kind, title=title.strip(), price=0 if data['free'] else price,
                   free=int(data['free']), enabled=int(data['enabled']), for_sale=int(data['for_sale']),
                   sort_order=order, filename=data.get('filename') or None,
                   mask_filename=data.get('mask_filename') or None, geometry=geometry, color=color,
                   revision=(old['revision'] + 1) if old else 1)
        if new['geometry'] == 'custom' and not new['mask_filename']:
            raise ValueError('برای قاب با شکل دلخواه، ماسک شفاف بارگذاری کن.')
        conn.execute('''INSERT INTO avatar_cosmetics VALUES(:item_id,:kind,:title,:price,:free,
            :enabled,:for_sale,:sort_order,:filename,:mask_filename,:geometry,:color,:revision)
            ON CONFLICT(item_id) DO UPDATE SET title=excluded.title,price=excluded.price,
            free=excluded.free,enabled=excluded.enabled,for_sale=excluded.for_sale,
            sort_order=excluded.sort_order,filename=excluded.filename,mask_filename=excluded.mask_filename,
            geometry=excluded.geometry,color=excluded.color,revision=excluded.revision''', new)
        if new['free']:
            conn.execute('''INSERT OR IGNORE INTO player_avatar_items(user_id,item_id,source)
                SELECT user_id,?,'free' FROM players''', (key,))
        audit_in(conn, actor, {'action': 'item', 'before': old, 'after': new})
        return new


def set_defaults(db, actor, data):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN IMMEDIATE')
        for kind in DEFAULTS:
            item = item_in(conn, data.get(kind))
            if not item or item['kind'] != kind or not item['enabled'] or not item['free'] or not ready(db, item):
                raise ValueError('پیش‌فرض باید رایگان، فعال و دارای تصویر باشد.')
            conn.execute('UPDATE avatar_settings SET value=? WHERE key=?', (item['item_id'], kind))
        audit_in(conn, actor, {'action': 'defaults', 'value': data})


def validate_purchase_in(db, conn, user, key):
    item = item_in(conn, key)
    if not item or not item['enabled'] or not item['for_sale'] or item['free'] or not ready(db, item):
        raise ValueError('item_unavailable')
    if conn.execute('SELECT 1 FROM player_avatar_items WHERE user_id=? AND item_id=?', (user, key)).fetchone():
        raise ValueError('already_owned')
    return item


def geometric_mask(geometry, size):
    image = Image.new('L', (size, size), 0)
    draw, m = ImageDraw.Draw(image), size * .07
    if geometry == 'circle':
        draw.ellipse((m, m, size-m, size-m), fill=255)
    elif geometry == 'diamond':
        draw.polygon([(size/2, m), (size-m, size/2), (size/2, size-m), (m, size/2)], fill=255)
    elif geometry == 'ruby':
        draw.polygon([(size*.3,m),(size*.7,m),(size-m,size*.3),(size-m,size*.7),
                      (size*.7,size-m),(size*.3,size-m),(m,size*.7),(m,size*.3)], fill=255)
    else:
        draw.rounded_rectangle((m,m,size-m,size-m), radius=size*.05, fill=255)
    return image


def generic_portrait(size):
    image = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(image)
    draw.ellipse((size*.34,size*.18,size*.66,size*.5), fill='#c6d0e2')
    draw.ellipse((size*.18,size*.53,size*.82,size*1.1), fill='#a0acc5')
    return image


def item_art(db, item, mask=False, size=512):
    if mask:
        if item['mask_filename']:
            return file_image(db, item['mask_filename'], size).getchannel('A')
        return geometric_mask(item['geometry'], size)
    if item['filename']:
        return file_image(db, item['filename'], size)
    if item['kind'] == 'background':
        return Image.new('RGBA', (size, size), item['color'])
    image = Image.new('RGBA', (size, size))
    # Neutral temporary Silver border until the owner's artwork is uploaded.
    ImageDraw.Draw(image).ellipse((size*.055,size*.055,size*.945,size*.945), outline='#bdc9dc', width=max(1,round(size*.025)))
    return image


def face_meta_in(conn, card, rarity):
    row = conn.execute('SELECT * FROM avatar_face_metadata WHERE card_id=? AND rarity=?', (card, rarity)).fetchone()
    return {k: row[k] for k in ('kind','enabled','scale','offset_x','offset_y')} if row else dict(kind='legacy', enabled=1, scale=1, offset_x=0, offset_y=0)


def configure_face(db, actor, card, rarity, data):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN IMMEDIATE')
        if not faces._valid_card_in(conn, card, rarity) or not faces.path_for(db, card, rarity):
            raise ValueError('آواتار این کارت هنوز ثبت نشده است.')
        values = {k: data.get(k) for k in ('kind','enabled','scale','offset_x','offset_y')}
        if values['kind'] not in ('portrait','legacy') or type(values['enabled']) is not bool:
            raise ValueError('نوع یا وضعیت چهره معتبر نیست.')
        for key, lo, hi in (('scale',.4,2),('offset_x',-.4,.4),('offset_y',-.4,.4)):
            val = values[key]
            if type(val) not in (int,float) or not math.isfinite(val) or not lo <= val <= hi:
                raise ValueError('اندازه یا محل چهره معتبر نیست.')
        if values['kind'] == 'portrait':
            with Image.open(faces.path_for(db,card,rarity)) as image:
                if image.convert('RGBA').getchannel('A').getextrema() == (255,255):
                    raise ValueError('سر شخصیت باید پس‌زمینهٔ شفاف داشته باشد.')
        conn.execute('''INSERT INTO avatar_face_metadata VALUES(?,?,?,?,?,?,?) ON CONFLICT(card_id,rarity)
            DO UPDATE SET kind=excluded.kind,enabled=excluded.enabled,scale=excluded.scale,
            offset_x=excluded.offset_x,offset_y=excluded.offset_y''', (card,rarity,*values.values()))
        audit_in(conn, actor, {'action':'face','card_id':card,'rarity':rarity,**values})


def _face(db, conn, user, slot):
    row = conn.execute('SELECT card_id,rarity FROM player_avatar_choices WHERE user_id=? AND slot=?', (user,slot)).fetchone()
    if row:
        meta = face_meta_in(conn,*row)
        card = faces._owned_card_in(db,conn,user,*row) if meta['enabled'] else None
        path = faces.path_for(db,*row) if card else None
        if path:
            return dict(card_id=row[0],rarity=row[1],name=card.name,filename=path.name,**meta)
    return dict(card_id=None,rarity=None,name='چهرهٔ عمومی',filename=None,kind='portrait',
                enabled=1,scale=1,offset_x=0,offset_y=0)


def appearance_in(db, conn, user, slot='profile'):
    if slot not in faces.SLOTS:
        raise ValueError('جایگاه آواتار معتبر نیست.')
    defaults = dict(conn.execute('SELECT key,value FROM avatar_settings'))
    style = conn.execute('SELECT * FROM player_avatar_styles WHERE user_id=? AND slot=?', (user,slot)).fetchone()
    existing = conn.execute('SELECT 1 FROM player_avatar_choices WHERE user_id=? AND slot=?', (user,slot)).fetchone()
    inherit = slot != 'profile' and (bool(style['inherit_profile']) if style else not existing)
    if inherit:
        result = appearance_in(db,conn,user,'profile')
        return {**result,'slot':slot,'inherit_profile':True}
    result = dict(slot=slot,inherit_profile=False,face=_face(db,conn,user,slot))
    for kind in DEFAULTS:
        key = style[kind+'_id'] if style else defaults[kind]
        item = item_in(conn,key)
        allowed = conn.execute('SELECT 1 FROM player_avatar_items WHERE user_id=? AND item_id=?',(user,key)).fetchone()
        if not item or not item['enabled'] or not ready(db,item) or not (allowed or item['free']):
            item = item_in(conn,defaults[kind])
            if not item or not ready(db,item):
                item = item_in(conn,DEFAULTS[kind])
        result[kind] = item
    return result


def compose(db, appearance, size=512):
    # Replaced assets use new content filenames, so cached renders cannot go stale.
    key = (str(Path(db.db_path).resolve()), json.dumps(appearance,sort_keys=True), size)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    face, frame, bg = (appearance[k] for k in ('face','frame','background'))
    try:
        path = faces.media_root(db) / face['filename'] if face['filename'] else None
        if path:
            with Image.open(path) as source:
                head = source.convert('RGBA')
        else:
            head = generic_portrait(size)
    except (OSError,ValueError):
        head = generic_portrait(size)
        face = dict(kind='portrait',scale=1,offset_x=0,offset_y=0)
    if face['kind'] == 'legacy':
        image = ImageOps.contain(head,(size,size),Image.Resampling.LANCZOS)
    else:
        try:
            image = item_art(db,bg,size=size)
            mask = item_art(db,frame,mask=True,size=size)
            overlay = item_art(db,frame,size=size)
        except (OSError,ValueError):
            image = Image.new('RGBA',(size,size),'#8c3045')
            mask = geometric_mask('circle',size)
            overlay = Image.new('RGBA',(size,size))
        width = max(1,round(size*face['scale']))
        head = ImageOps.contain(head,(width,width),Image.Resampling.LANCZOS)
        image.alpha_composite(head, (round((size-head.width)/2+face['offset_x']*size),
                                     round((size-head.height)/2+face['offset_y']*size)))
        image.putalpha(ImageChops.multiply(image.getchannel('A'),mask))
        image.alpha_composite(overlay)
    output=BytesIO()
    image.save(output,'PNG',optimize=True)
    raw=output.getvalue()
    with _lock:
        _cache[key]=raw
        while len(_cache)>96 or sum(map(len,_cache.values())) > 16*1024*1024:
            _cache.popitem(last=False)
    return raw


def render(db,user,slot='profile'):
    with closing(sqlite3.connect(db.db_path)) as conn:
        conn.row_factory=sqlite3.Row
        return compose(db,appearance_in(db,conn,user,slot))


def asset_url(item,mask=False):
    return '/api/v1/avatar/item/'+quote(item['item_id'],safe='')+('/mask' if mask else '/image')+'?v='+str(item['revision'])


def face_payload(face):
    result={**face,'image_url': '/api/v1/avatar/generic'}
    if face['card_id']:
        result['image_url']='/api/v1/avatar/face/'+quote(face['card_id'],safe='')+'/'+face['rarity']+'?v='+face['filename']
    return result


def item_payload(db,item,owned=False):
    return {**item,'image_url':asset_url(item),'mask':{'image_url':asset_url(item,True)} if item['kind']=='frame' else None,
            'owned':bool(owned or item['free']),'ready':ready(db,item)}


def appearance_payload(db,value):
    return {**value,'face':face_payload(value['face']),
            **{kind:item_payload(db,value[kind],True) for kind in DEFAULTS}}


def catalog(db,user):
    with closing(sqlite3.connect(db.db_path)) as conn:
        conn.row_factory=sqlite3.Row
        owned={r[0] for r in conn.execute('SELECT item_id FROM player_avatar_items WHERE user_id=?',(user,))}
        items=[item_payload(db,dict(row),row['item_id'] in owned) for row in conn.execute('SELECT * FROM avatar_cosmetics WHERE enabled=1 ORDER BY sort_order,item_id')]
        portraits=[face_payload(dict(card_id=None,rarity=None,name='چهرهٔ عمومی',filename=None,kind='portrait',enabled=1,scale=1,offset_x=0,offset_y=0,owned=True))]
        for entry in faces.choices(db,user):
            meta=face_meta_in(conn,entry['card_id'],entry['rarity'])
            if meta['enabled']:
                portraits.append(face_payload(dict(entry,**meta,filename=faces.path_for(db,entry['card_id'],entry['rarity']).name,owned=True)))
        return dict(ok=True,items=items,faces=portraits,selections={slot:appearance_payload(db,appearance_in(db,conn,user,slot)) for slot in faces.SLOTS})


def save_style(db,user,data):
    if not isinstance(data,dict) or data.get('slot') not in faces.SLOTS or type(data.get('inherit_profile')) is not bool:
        raise ValueError('انتخاب آواتار معتبر نیست.')
    if any(not isinstance(data.get(k),str) or not 1 <= len(data[k]) <= 64 for k in ('frame_id','background_id')):
        raise ValueError('قاب و پس‌زمینهٔ معتبر انتخاب کن.')
    if data.get('card_id') is not None and (not isinstance(data['card_id'],str) or len(data['card_id'])>256):
        raise ValueError('چهرهٔ معتبر انتخاب کن.')
    if data.get('card_id') and data.get('rarity') not in faces.RARITIES:
        raise ValueError('فرم چهره معتبر نیست.')
    slot=data['slot']
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.row_factory=sqlite3.Row
        conn.execute('BEGIN IMMEDIATE')
        grant_free_in(conn,user)
        for kind in DEFAULTS:
            item=item_in(conn,data.get(kind+'_id'))
            if not item or item['kind']!=kind or not item['enabled'] or not ready(db,item) or not conn.execute(
                    'SELECT 1 FROM player_avatar_items WHERE user_id=? AND item_id=?',(user,item['item_id'])).fetchone():
                raise ValueError('این قاب یا پس‌زمینه را در اختیار نداری.')
        card,rarity=data.get('card_id'),data.get('rarity')
        if card:
            if not faces._owned_card_in(db,conn,user,card,rarity) or not faces.path_for(db,card,rarity) or not face_meta_in(conn,card,rarity)['enabled']:
                raise ValueError('این چهره برایت آزاد نیست.')
            conn.execute('''INSERT INTO player_avatar_choices VALUES(?,?,?,?) ON CONFLICT(user_id,slot)
                DO UPDATE SET card_id=excluded.card_id,rarity=excluded.rarity''',(user,slot,card,rarity))
        else:
            conn.execute('DELETE FROM player_avatar_choices WHERE user_id=? AND slot=?',(user,slot))
        conn.execute('''INSERT INTO player_avatar_styles VALUES(?,?,?,?,?) ON CONFLICT(user_id,slot)
            DO UPDATE SET frame_id=excluded.frame_id,background_id=excluded.background_id,
            inherit_profile=excluded.inherit_profile''',(user,slot,data['frame_id'],data['background_id'],int(slot!='profile' and data['inherit_profile'])))
    return catalog(db,user)
