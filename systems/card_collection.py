"""Private collection display; viewing a grant does not authorize game entry."""
import json
import sqlite3
from contextlib import closing

from core.models import Card
from systems.custom_cards import media_root
from systems.shared_foundation import settings_in


def custom_collection(db, user_id):
    """Only active grants/definitions, even while custom gameplay is disabled."""
    with closing(sqlite3.connect(db.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT c.*, d.payload_json, m.filename AS private_filename
            FROM custom_grants g
            JOIN custom_definitions d USING(card_id)
            JOIN cards c USING(card_id)
            LEFT JOIN custom_media m ON m.media_id=d.media_id AND m.removed=0
            WHERE g.user_id=? AND g.active=1 AND d.status='active' AND c.origin='custom'
            ORDER BY g.updated_at DESC, c.card_id
        """, (user_id,)).fetchall()
    cards = []
    for row in rows:
        values = dict(row)
        values['name'] = json.loads(row['payload_json'])['name']
        values['image_path'] = str(media_root(db) / row['private_filename']) if row['private_filename'] else ''
        cards.append(Card.from_dict(values))
    return cards


def custom_owned_card(db, user_id, card_id):
    return next((card for card in custom_collection(db, user_id) if card.card_id == card_id), None)


def collection_cards(db, user_id):
    return [card for card in db.get_player_cards(user_id) if card.origin == 'official'] + custom_collection(db, user_id)


def collection_page(db, user_id, category, page=1, per_page=6):
    if category == 'favorite':
        return db.get_favorite_cards(user_id, page=page, per_page=per_page)
    cards = (custom_collection(db, user_id) if category == 'custom' else
             [card for card in db.get_player_cards(user_id)
              if card.origin == 'official' and card.rarity.value == category])
    return cards[(page-1)*per_page:page*per_page], len(cards)


def custom_gameplay_notice(db):
    with closing(sqlite3.connect(db.db_path)) as conn:
        flags = settings_in(conn)
    if not flags['custom_cards_enabled'] or not flags['progression_v2_enabled']:
        return 'استفاده از کارت شخصی‌سازی‌شده در بازی فعلاً از تنظیمات مدیریت غیرفعاله؛ کارتت توی موجودیت محفوظ می‌مونه.'
    modes = []
    if flags['quick_friendly_enabled']:
        modes.append('Quick دوستانه')
    if flags['easy_custom_cards_enabled']:
        modes.append('Easy با انتخاب «بله»')
    modes.append('تمرین با ASO')
    return '🎮 قابل استفاده در: ' + '، '.join(modes) + '\nدر Quick اصلی، Deck و بازی‌های رقابتی قابل استفاده نیست.'
