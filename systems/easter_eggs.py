"""Admin-authored secret phrases with transactional, account-scoped rewards."""
import json
import random
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(value):
    return ' '.join(value.translate(str.maketrans({'ي': 'ی', 'ك': 'ک', '\u200c': ' '})).casefold().split())


def ensure_in(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS easter_rules(
        rule_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload_json TEXT NOT NULL,
        deleted INTEGER NOT NULL DEFAULT 0,actor TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    conn.execute('CREATE TABLE IF NOT EXISTS easter_aliases(phrase TEXT PRIMARY KEY,rule_id TEXT NOT NULL)')
    conn.execute('''CREATE TABLE IF NOT EXISTS easter_events(
        event_id TEXT PRIMARY KEY,rule_id TEXT NOT NULL,user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,message_id INTEGER NOT NULL,receipt_json TEXT NOT NULL,
        created_at TEXT NOT NULL,delivery_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(chat_id,message_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_easter_uses ON easter_events(rule_id,user_id)')
    conn.execute('''CREATE TABLE IF NOT EXISTS easter_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,
        rule_id TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)''')


def integer(value, minimum=1, maximum=1_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('عدد واردشده در محدودهٔ مجاز نیست.')
    return value


def text(value, maximum, *, empty=True):
    if not isinstance(value, str) or len(value) > maximum or not empty and not value.strip():
        raise ValueError('طول یا نوع متن معتبر نیست.')
    return value.strip()


def _date(value):
    if value is None or value == '':
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise ValueError('زمان شروع و پایان باید تاریخ معتبر با منطقهٔ زمانی باشد.')


def card_in(conn, card_id, rarity):
    row = conn.execute('SELECT origin,rarity FROM cards WHERE card_id=?', (card_id,)).fetchone()
    if not row or rarity not in ('normal', 'epic', 'legend', 'rare'):
        raise ValueError('کارت و فرم معتبر انتخاب کن.')
    if row[0] == 'custom':
        if row[1] != rarity or not conn.execute("SELECT 1 FROM custom_definitions WHERE card_id=? AND status='active'", (card_id,)).fetchone():
            raise ValueError('کارت سفارشی باید فعال باشد و فرم خودش انتخاب شود.')
    elif row[0] != 'official' or (row[1] == 'rare') != (rarity == 'rare'):
        raise ValueError('فرم انتخاب‌شده متعلق به این کارت نیست.')
    elif rarity != row[1] and not conn.execute('SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?', (card_id, rarity)).fetchone():
        raise ValueError('این فرم کارت هنوز آماده نشده است.')
    return row[0]


def validate_in(conn, value):
    if not isinstance(value, dict):
        raise ValueError('فرم ایستراگ معتبر نیست.')
    title = text(value.get('title'), 100, empty=False)
    phrases = value.get('phrases')
    if not isinstance(phrases, list) or not 1 <= len(phrases) <= 20:
        raise ValueError('بین یک تا بیست عبارت برای همین ایستراگ بنویس.')
    phrases = [text(item, 300, empty=False) for item in phrases]
    normalized = [normalize(item) for item in phrases]
    from bot.game_help import COMMANDS
    reserved = {normalize(item[0]) for item in COMMANDS} | {'بتل کوئیک', 'بتل کوییک مود', 'بتل کلیم'}
    if len(set(normalized)) != len(normalized) or any(item in reserved or item.startswith('/') for item in normalized):
        raise ValueError('عبارت تکراری یا دستور اصلی بازی قابل استفاده برای ایستراگ نیست.')
    scope = value.get('scope', 'all')
    if scope not in ('all', 'private', 'group'):
        raise ValueError('محل اجرای معتبر انتخاب کن.')
    enabled = value.get('enabled', False)
    if type(enabled) is not bool:
        raise ValueError('وضعیت فعال‌بودن معتبر نیست.')
    limit = value.get('per_user_limit', 1)
    total = value.get('total_limit')
    if limit is not None:
        integer(limit)
    if total is not None:
        integer(total)
    cooldown = integer(value.get('cooldown_seconds', 2), 0, 86400)
    start, end = _date(value.get('starts_at')), _date(value.get('ends_at'))
    if start and end and start >= end:
        raise ValueError('پایان باید بعد از شروع باشد.')
    groups = value.get('chat_ids', [])
    if not isinstance(groups, list) or len(groups) > 100 or any(type(item) is not int or not -(2**63) < item < 0 for item in groups):
        raise ValueError('شناسه‌های گروه باید عدد منفی باشند.')
    users = value.get('user_ids', [])
    if not isinstance(users, list) or len(users) > 100 or any(type(item) is not int or not 0 < item < 2**63 for item in users):
        raise ValueError('شناسه‌های حساب باید عدد مثبت باشند.')
    rewards = value.get('rewards', [])
    if not isinstance(rewards, list) or len(rewards) > 8:
        raise ValueError('حداکثر هشت نوع جایزه برای یک اجرا مجاز است.')
    if rewards and limit is None:
        raise ValueError('ایستراگ جایزه‌دار باید سقف هر حساب داشته باشد.')
    cleaned = []
    from systems.game_mode_system import ABILITY_DEFINITIONS
    for reward in rewards:
        if not isinstance(reward, dict):
            raise ValueError('جایزه معتبر نیست.')
        kind = reward.get('kind')
        if kind not in ('card', 'ability', 'refill_hearts', 'silver_claim', 'daily_claim'):
            raise ValueError('نوع جایزه معتبر نیست.')
        item = {'kind': kind, 'quantity': integer(reward.get('quantity', 1), 1, 100)}
        if kind in ('refill_hearts', 'daily_claim') and item['quantity'] != 1:
            raise ValueError('پرکردن جان و کلیم روزانهٔ اضافه در هر اجرا یک بار انجام می‌شوند.')
        if kind == 'card':
            item.update(card_id=text(reward.get('card_id'), 128, empty=False), rarity=reward.get('rarity'))
            origin = card_in(conn, item['card_id'], item['rarity'])
            if origin == 'custom' and item['quantity'] != 1:
                raise ValueError('کارت سفارشی دسترسی است؛ تعداد باید یک باشد.')
        if kind == 'ability':
            if not isinstance(reward.get('ability_key'), str) or reward['ability_key'] not in ABILITY_DEFINITIONS:
                raise ValueError('ابیلیتی معتبر انتخاب کن.')
            item['ability_key'] = reward['ability_key']
        if item in cleaned:
            raise ValueError('یک جایزهٔ یکسان را دو بار در فرم وارد نکن.')
        cleaned.append(item)
    responses = value.get('responses', [])
    if not isinstance(responses, list) or len(responses) > 20:
        raise ValueError('حداکثر بیست پاسخ تصادفی مجاز است.')
    answers = []
    for response in responses:
        if not isinstance(response, dict):
            raise ValueError('پاسخ معتبر نیست.')
        answer = {'text': text(response.get('text', ''), 1800), 'media_id': response.get('media_id') or None}
        if answer['media_id']:
            from systems.easter_media import metadata_in
            if not metadata_in(conn, answer['media_id']):
                raise ValueError('رسانه در دسترس نیست؛ دوباره بارگذاری کن.')
        if answer['text'] or answer['media_id']:
            answers.append(answer)
    if not answers and not cleaned:
        raise ValueError('حداقل یک پاسخ یا جایزه لازم است.')
    receipt = value.get('show_reward_receipt', True)
    if type(receipt) is not bool:
        raise ValueError('تنظیم نمایش جایزه معتبر نیست.')
    return dict(title=title, phrases=phrases, scope=scope, enabled=enabled, per_user_limit=limit,
                total_limit=total, cooldown_seconds=cooldown, starts_at=start, ends_at=end,
                chat_ids=list(set(groups)), user_ids=list(set(users)), rewards=cleaned, responses=answers,
                exhausted_text=text(value.get('exhausted_text', 'سهمیهٔ این ایستراگ برای تو تمام شده است.'), 500),
                show_reward_receipt=receipt)


def save(db, actor, rule_id, expected, value):
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_in(conn)
        value = validate_in(conn, value)
        old = conn.execute('SELECT revision,deleted FROM easter_rules WHERE rule_id=?', (rule_id,)).fetchone() if rule_id else None
        if rule_id and not old:
            raise ValueError('ایستراگ پیدا نشد؛ فهرست را تازه کن.')
        if old and (old[0] != expected or old[1]):
            raise ValueError('ایستراگ تغییر کرده یا حذف شده؛ دوباره بازش کن.')
        rule_id = rule_id or uuid.uuid4().hex
        for phrase in value['phrases']:
            owner = conn.execute('SELECT rule_id FROM easter_aliases WHERE phrase=?', (normalize(phrase),)).fetchone()
            if owner and owner[0] != rule_id:
                raise ValueError('این عبارت قبلاً برای ایستراگ دیگری ثبت شده است.')
        revision = old[0] + 1 if old else 1
        stamp = now()
        encoded = json.dumps(value, ensure_ascii=False)
        conn.execute('''INSERT INTO easter_rules VALUES(?,?,?,0,?,?,?) ON CONFLICT(rule_id)
            DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json,actor=excluded.actor,updated_at=excluded.updated_at''',
                     (rule_id, revision, encoded, actor, stamp, stamp))
        conn.execute('DELETE FROM easter_aliases WHERE rule_id=?', (rule_id,))
        conn.executemany('INSERT INTO easter_aliases VALUES(?,?)', [(normalize(item), rule_id) for item in value['phrases']])
        conn.execute('INSERT INTO easter_audit(actor,action,rule_id,payload_json,created_at) VALUES(?,?,?,?,?)',
                     (actor, 'save', rule_id, encoded, stamp))
        return dict(rule_id=rule_id, revision=revision, **value)


def delete(db, actor, rule_id, expected):
    integer(expected)
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_in(conn)
        changed = conn.execute('UPDATE easter_rules SET deleted=1,revision=revision+1,updated_at=? WHERE rule_id=? AND revision=? AND deleted=0',
                               (now(), rule_id, expected))
        if not changed.rowcount:
            raise ValueError('ایستراگ تغییر کرده یا حذف شده؛ فهرست را تازه کن.')
        conn.execute('DELETE FROM easter_aliases WHERE rule_id=?', (rule_id,))
        conn.execute('INSERT INTO easter_audit(actor,action,rule_id,payload_json,created_at) VALUES(?,?,?,?,?)', (actor, 'delete', rule_id, '{}', now()))


def _award_in(db, conn, user_id, rewards, event_id, rule_id, actor):
    from systems.card_inventory_system import CardInventorySystem as Inventory
    from systems.reward_ledger import items_in, capacities_in
    from systems.progression_config import config_in, enabled_in
    from systems.game_mode_system import ABILITY_DEFINITIONS
    version, config = config_in(conn)
    lines, inventory, hearts_delta = [], {}, 0
    for reward_index, item in enumerate(rewards):
        kind, qty = item['kind'], item['quantity']
        if kind == 'card':
            card_id, rarity = item['card_id'], item['rarity']
            origin = card_in(conn, card_id, rarity)
            name = conn.execute('SELECT name FROM cards WHERE card_id=?', (card_id,)).fetchone()[0]
            if origin == 'custom':
                existing = conn.execute('SELECT active FROM custom_grants WHERE card_id=? AND user_id=?', (card_id, user_id)).fetchone()
                if existing and existing[0]:
                    continue
                from systems.custom_cards import CustomCards
                CustomCards(db)._admin_fulfillment(conn, 'easter:' + rule_id + ':' + actor, 'deliver_existing',
                    {'card_id': card_id, 'users': [user_id], 'review_confirmed': True}, None)
                name = json.loads(conn.execute('SELECT payload_json FROM custom_definitions WHERE card_id=?', (card_id,)).fetchone()[0])['name']
            elif rarity == 'rare':
                from systems.rare_delivery import issue_in
                for index in range(qty):
                    issue_in(conn, user_id, card_id, f'easter:{event_id}:{reward_index}:{index}', 'easter_egg')
            else:
                Inventory.grant_in(conn, user_id, card_id, rarity, qty)
            inventory[card_id + ':' + rarity] = inventory.get(card_id + ':' + rarity, 0) + qty
            lines.append(f'🎴 {name} · {rarity.title()} ×{qty}')
        elif kind == 'ability':
            key = item['ability_key']
            conn.execute('INSERT INTO player_ability_inventory VALUES(?,?,?) ON CONFLICT(user_id,ability_key) DO UPDATE SET quantity=quantity+excluded.quantity', (user_id, key, qty))
            inventory['ability:' + key] = inventory.get('ability:' + key, 0) + qty
            lines.append('⚡ ' + ABILITY_DEFINITIONS[key]['title'] + f' ×{qty}')
        elif kind == 'silver_claim':
            if not enabled_in(conn):
                raise ValueError('سیلور کلیم در این نسخهٔ اقتصاد هنوز فعال نیست؛ سهمیه مصرف نشد.')
            items_in(conn, user_id, 'free_silver_claim', qty)
            inventory['free_silver_claim'] = inventory.get('free_silver_claim', 0) + qty
            lines.append(f'🎟 سیلور کلیم ×{qty}')
        elif kind == 'refill_hearts':
            if enabled_in(conn):
                maximum = capacities_in(conn, user_id, config)['max_hearts']
            else:
                maximum = conn.execute('SELECT max_hearts FROM players WHERE user_id=?', (user_id,)).fetchone()[0]
            old = conn.execute('SELECT hearts FROM players WHERE user_id=?', (user_id,)).fetchone()[0]
            delta = max(0, int(maximum) - int(old))
            if delta:
                conn.execute('UPDATE players SET hearts=?,max_hearts=? WHERE user_id=?', (maximum, maximum, user_id))
                hearts_delta += delta
                lines.append('❤️ جون‌هات پر شد')
        elif kind == 'daily_claim':
            from systems.progression_economy import ProgressionEconomy
            if enabled_in(conn):
                if not ProgressionEconomy.pool(conn, config, 'daily'):
                    raise ValueError('کارت روزانه‌ای در فهرست دریافت نیست؛ سهمیه مصرف نشد.')
                ticket = random.random() * 100 < config['claim']['daily_ticket_percent']
                card = None if ticket else ProgressionEconomy.select_claim(conn, user_id, config, 'daily')
            else:
                pool = [row[0] for row in conn.execute("SELECT card_id FROM cards WHERE origin='official' AND rarity='normal'")]
                if not pool:
                    raise ValueError('کارت روزانه‌ای موجود نیست؛ سهمیه مصرف نشد.')
                ticket, card = False, random.choice(pool)
            if ticket:
                items_in(conn, user_id, 'silver_ticket', 1)
                inventory['silver_ticket'] = inventory.get('silver_ticket', 0) + 1
                lines.append('🎟 کلیم اضافه: یک سیلور تیکت')
            else:
                Inventory.grant_in(conn, user_id, card, 'normal')
                inventory[card + ':normal'] = inventory.get(card + ':normal', 0) + 1
                conn.execute("INSERT INTO claim_receipts VALUES(?,'daily',?,1) ON CONFLICT(user_id,claim_type,card_id) DO UPDATE SET received=received+1", (user_id, card))
                name = conn.execute('SELECT name FROM cards WHERE card_id=?', (card,)).fetchone()[0]
                lines.append('🎁 کلیم روزانهٔ اضافه: ' + name + ' · Normal')
            ability = random.choice(tuple(ABILITY_DEFINITIONS))
            conn.execute('INSERT INTO player_ability_inventory VALUES(?,?,1) ON CONFLICT(user_id,ability_key) DO UPDATE SET quantity=quantity+1', (user_id, ability))
            inventory['ability:' + ability] = inventory.get('ability:' + ability, 0) + 1
            lines.append('⚡ ' + ABILITY_DEFINITIONS[ability]['title'])
    return lines, inventory, hearts_delta, version


def execute(db, user_id, chat_id, message_id, phrase, chat_type):
    """UID comes from Telegram, never from an admin phrase or a display name."""
    if type(user_id) is not int or user_id <= 0 or type(message_id) is not int or message_id <= 0 or chat_type not in ('private', 'group', 'supergroup'):
        return {'matched': False}
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_in(conn)
        duplicate = conn.execute('SELECT event_id,receipt_json FROM easter_events WHERE chat_id=? AND message_id=?', (chat_id, message_id)).fetchone()
        if duplicate:
            return {'matched': True, 'event_id': duplicate[0], 'receipt': json.loads(duplicate[1]), 'replayed': True}
        row = conn.execute('''SELECT r.rule_id,r.revision,r.payload_json,r.actor FROM easter_aliases a
            JOIN easter_rules r USING(rule_id) WHERE a.phrase=? AND r.deleted=0''', (normalize(phrase),)).fetchone()
        if not row:
            return {'matched': False}
        rule_id, revision, encoded, actor = row
        rule = json.loads(encoded)
        stamp = now()
        group = chat_type in ('group', 'supergroup')
        if (not rule['enabled'] or rule['scope'] == 'private' and group or rule['scope'] == 'group' and not group
                or rule['chat_ids'] and group and chat_id not in rule['chat_ids']
                or rule['user_ids'] and user_id not in rule['user_ids']
                or rule['starts_at'] and stamp < rule['starts_at'] or rule['ends_at'] and stamp >= rule['ends_at']):
            return {'matched': True, 'silent': True}
        uses = conn.execute('SELECT COUNT(*),MAX(created_at) FROM easter_events WHERE rule_id=? AND user_id=?', (rule_id, user_id)).fetchone()
        total = conn.execute('SELECT COUNT(*) FROM easter_events WHERE rule_id=?', (rule_id,)).fetchone()[0]
        if (rule['per_user_limit'] is not None and uses[0] >= rule['per_user_limit']
                or rule['total_limit'] is not None and total >= rule['total_limit']):
            return {'matched': True, 'notice': rule['exhausted_text']}
        if uses[1] and (datetime.now(timezone.utc) - datetime.fromisoformat(uses[1])).total_seconds() < rule['cooldown_seconds']:
            return {'matched': True, 'silent': True}
        if rule['rewards']:
            if not conn.execute('SELECT 1 FROM players WHERE user_id=?', (user_id,)).fetchone():
                return {'matched': True, 'notice': 'برای گرفتن جایزه اول پیوی ربات را /start کن؛ سهمیه‌ات مصرف نشد.'}
            from systems.match_activity import require_free_in
            require_free_in(conn, user_id)
        event_id = uuid.uuid4().hex
        lines, inventory, hearts, version = _award_in(db, conn, user_id, rule['rewards'], event_id, rule_id, actor) if rule['rewards'] else ([], {}, 0, None)
        if rule['rewards'] and not inventory and not hearts:
            return {'matched': True, 'notice': 'این مورد را از قبل داری یا جون‌هات پر است؛ سهمیه‌ات مصرف نشد.'}
        answer = random.choice(rule['responses']) if rule['responses'] else {'text': '', 'media_id': None}
        receipt = {'rule_id': rule_id, 'revision': revision, 'response': answer, 'rewards': lines,
                   'show_reward_receipt': rule['show_reward_receipt'], 'uses': uses[0] + 1,
                   'remaining': None if rule['per_user_limit'] is None else rule['per_user_limit'] - uses[0] - 1}
        conn.execute('INSERT INTO easter_events(event_id,rule_id,user_id,chat_id,message_id,receipt_json,created_at) VALUES(?,?,?,?,?,?,?)',
                     (event_id, rule_id, user_id, chat_id, message_id, json.dumps(receipt, ensure_ascii=False), stamp))
        if rule['rewards']:
            from systems.reward_ledger import record_in
            record_in(conn, 'easter:' + event_id, user_id, 'easter_egg', 'secret_reward',
                      {'rule_id': rule_id, 'revision': revision}, receipt, version, inventory=inventory, hearts=hearts)
        return {'matched': True, 'event_id': event_id, 'receipt': receipt}


def catalog(db):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        ensure_in(conn)
        rules = [dict(rule_id=row[0], revision=row[1], **json.loads(row[2]), used=row[3]) for row in conn.execute('''
            SELECT r.rule_id,r.revision,r.payload_json,(SELECT COUNT(*) FROM easter_events e WHERE e.rule_id=r.rule_id)
            FROM easter_rules r WHERE r.deleted=0 ORDER BY r.updated_at DESC''')]
        cards = []
        for cid, name, rarity, origin, payload, status in conn.execute('''SELECT c.card_id,c.name,c.rarity,c.origin,d.payload_json,d.status
            FROM cards c LEFT JOIN custom_definitions d USING(card_id) ORDER BY c.name'''):
            if origin == 'custom':
                if status != 'active':
                    continue
                name = json.loads(payload)['name']
                forms = [rarity]
            elif rarity == 'rare':
                forms = ['rare']
            else:
                available = {rarity} | {row[0] for row in conn.execute('SELECT rarity FROM card_variants WHERE card_id=?', (cid,))}
                forms = [form for form in ('normal', 'epic', 'legend') if form in available]
            cards.append(dict(card_id=cid, name=name, rarities=forms, origin=origin))
        from systems.game_mode_system import ABILITY_DEFINITIONS
        return dict(rules=rules, cards=cards, abilities=[dict(key=key, title=item['title']) for key, item in ABILITY_DEFINITIONS.items()])


def history(db, rule_id, user_id=None):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        ensure_in(conn)
        params = [rule_id]
        where = 'e.rule_id=?'
        if user_id is not None:
            where += ' AND e.user_id=?'
            params.append(user_id)
        rows = conn.execute(f'''SELECT e.user_id,p.username,p.first_name,COUNT(*),MAX(e.created_at)
            FROM easter_events e LEFT JOIN players p USING(user_id) WHERE {where}
            GROUP BY e.user_id ORDER BY MAX(e.created_at) DESC LIMIT 100''', params).fetchall()
        return [dict(user_id=r[0], username=r[1], name=r[2], uses=r[3], last_used_at=r[4]) for r in rows]


def claim_delivery(db, event_id=None):
    import time
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_in(conn)
        rows = conn.execute('''SELECT event_id,user_id,chat_id,message_id,receipt_json,delivery_json
            FROM easter_events WHERE COALESCE(json_extract(delivery_json,'$.done'),0)=0
            AND COALESCE(json_extract(delivery_json,'$.next_attempt'),0)<=?
            AND COALESCE(json_extract(delivery_json,'$.lease_until'),0)<=?
            AND (? IS NULL OR event_id=?) ORDER BY created_at LIMIT 1''', (time.time(), time.time(), event_id, event_id)).fetchall()
        if not rows:
            return None
        row = rows[0]
        state = json.loads(row[5])
        state.update(lease=uuid.uuid4().hex, lease_until=time.time() + 90, attempts=state.get('attempts', 0) + 1)
        conn.execute('UPDATE easter_events SET delivery_json=? WHERE event_id=?', (json.dumps(state), row[0]))
        name = conn.execute('SELECT first_name FROM players WHERE user_id=?', (row[1],)).fetchone()
        return dict(event_id=row[0], user_id=row[1], chat_id=row[2], message_id=row[3],
                    receipt=json.loads(row[4]), delivery=state, name=name[0] if name else 'بازیکن')


def delivery_checkpoint(db, event, **changes):
    with closing(sqlite3.connect(db.db_path, timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT delivery_json FROM easter_events WHERE event_id=?', (event['event_id'],)).fetchone()
        if not row:
            return False
        state = json.loads(row[0])
        if state.get('lease') != event['delivery']['lease'] or state.get('done'):
            return False
        state.update(changes)
        conn.execute('UPDATE easter_events SET delivery_json=? WHERE event_id=?', (json.dumps(state), event['event_id']))
        event['delivery'] = state
        return True
