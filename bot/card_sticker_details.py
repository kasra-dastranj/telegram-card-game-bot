"""Read-only card-form details on sticker messages; no battle or inventory actions."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.display_text import clean, isolate

PREFIX = 'card_stats:'
FORMS = {'normal': 'Normal', 'epic': 'Epic', 'legend': 'Legend', 'rare': 'Rare'}


def _short_name(value):
    name = ' '.join(clean(value).split())
    return name[:24] + '…' if len(name) > 24 else name


def button(card):
    """Keep the displayed form in a restart-safe, Telegram-sized callback."""
    if card is None:
        return None
    rarity = getattr(getattr(card, 'rarity', None), 'value', '')
    card_id = str(getattr(card, 'card_id', '') or '')
    data = PREFIX + rarity + ':' + card_id
    if rarity not in FORMS or not card_id or len(data.encode('utf-8')) > 64:
        return None
    label = '🎴 مشخصات ' + isolate(_short_name(card.name)) + ' · ' + FORMS[rarity]
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data)]])


def details(card):
    """Only the four public stats, not hidden Easy values or battle choices."""
    return (
        f'🎴 {isolate(_short_name(card.name))} · {FORMS[card.rarity.value]}\n'
        f'💪 قدرت: {card.power}\n'
        f'⚡ سرعت: {card.speed}\n'
        f'🧠 هوش: {card.iq}\n'
        f'❤️ محبوبیت: {card.popularity}\n'
        'اعداد پایهٔ فعلی؛ پیش از اثر زمین و ابیلیتی.'
    )


async def handle(bot, update, context):
    query = update.callback_query
    unavailable = 'مشخصات این کارت در دسترس نیست.'
    data = query.data or ''
    parts = data.split(':', 2)
    if (len(parts) != 3 or parts[0] != 'card_stats' or parts[1] not in FORMS
            or not parts[2] or len(data.encode('utf-8')) > 64):
        await query.answer(unavailable, show_alert=True)
        return
    rarity, card_id = parts[1:]
    base = bot.db.get_card_by_id(card_id)
    card = None
    if base and base.origin == 'official':
        card = bot.db.get_card_by_id_for_rarity(card_id, rarity)
    elif base and base.origin == 'custom':
        # A forwarded/private custom sticker does not grant access to its record.
        message = getattr(query, 'message', None)
        if message and message.chat_id == query.from_user.id:
            from systems.card_collection import custom_owned_card
            owned = custom_owned_card(bot.db, query.from_user.id, card_id)
            if owned and owned.rarity.value == rarity:
                card = owned
    await query.answer(details(card) if card else unavailable, show_alert=True)
