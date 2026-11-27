"""Choose an already-owned form from the private collection; never upgrade copies."""
import uuid

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

from core.display_text import isolate
from systems.card_inventory_system import CardInventorySystem


FORMS = {'normal': '🟢 نورمال', 'epic': '🟣 اپیک', 'legend': '🟡 لجند'}
NAMES = {'normal': 'نورمال', 'epic': 'اپیک', 'legend': 'لجند'}


def button(bot, context, user_id, card):
    if card.origin != 'official' or card.rarity.value not in FORMS:
        return None
    counts = CardInventorySystem(bot.db).counts(user_id, card.card_id)
    if sum(counts.get(form, 0) > 0 for form in FORMS) < 2:
        return None
    choices = context.user_data.setdefault('card_form_choices', {})
    while len(choices) >= 40:
        choices.pop(next(iter(choices)))
    token = uuid.uuid4().hex
    choices[token] = card.card_id
    return Button('🔄 انتخاب نوع کارت', callback_data='cf:' + token + ':menu')


def back():
    return Markup([[Button('🔙 بازگشت به کارت‌های من', callback_data='mycards_menu_1')]])


async def handle(bot, update, context):
    query = update.callback_query
    if (not query.message or query.message.chat_id != query.from_user.id
            or update.effective_chat.type != 'private'):
        await query.answer('انتخاب نوع کارت فقط در پیوی ربات انجام می‌شود.', show_alert=True)
        return
    parts = (query.data or '').split(':')
    choices = context.user_data.get('card_form_choices', {})
    card_id = choices.get(parts[1]) if len(parts) == 3 else None
    if not card_id or parts[2] not in (*FORMS, 'menu'):
        await query.answer('این دکمه قدیمی است؛ کارتت را دوباره باز کن.', show_alert=True)
        return
    user_id = query.from_user.id
    card = bot.db.get_card_by_id_for_player(card_id, user_id)
    if not card or card.origin != 'official' or card.rarity.value not in FORMS:
        await query.answer('این کارت در موجودی‌ات نیست.', show_alert=True)
        return
    inventory = CardInventorySystem(bot.db)
    if parts[2] == 'menu':
        counts = inventory.counts(user_id, card_id)
        rows = [[Button(title + ' ×' + str(counts[form])
                        + (' · فعال ✓' if form == card.rarity.value else ''),
                        callback_data='cf:' + parts[1] + ':' + form)]
                for form, title in FORMS.items() if counts.get(form, 0) > 0]
        rows.extend(back().inline_keyboard)
        await query.answer()
        await query.edit_message_text(
            '🎴 ' + isolate(card.name) + '\nفرم فعلی: ' + NAMES[card.rarity.value]
            + '\n\nنوع کارتت را انتخاب کن:', parse_mode=None, reply_markup=Markup(rows))
        return
    target = parts[2]
    if target == card.rarity.value:
        await query.answer('این فرم همین حالا فعال است.')
        return
    result = inventory.activate(user_id, card_id, target)
    if not result['ok']:
        await query.answer(result['error'], show_alert=True)
        return
    choices.pop(parts[1], None)
    text = ('🎴 ' + isolate(card.name) + '\n\n✅ فرم کارتت از '
            + NAMES[card.rarity.value] + ' به ' + NAMES[target] + ' تغییر پیدا کرد.')
    await query.answer()
    await query.edit_message_text(text, parse_mode=None, reply_markup=back())
    selected = bot.db.get_card_by_id_for_rarity(card_id, target)
    from bot.card_reward_presentation import send_card_sticker
    if not await send_card_sticker(bot, context, selected, query.message.reply_sticker):
        await query.edit_message_text(text + '\nاستیکر این فرم فعلاً در دسترس نیست.',
                                      parse_mode=None, reply_markup=back())
