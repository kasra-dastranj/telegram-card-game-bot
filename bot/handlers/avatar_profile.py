"""Private picker for owned, uploaded profile and victory avatars."""
import uuid

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

from systems import card_avatars

PAGE_SIZE = 8
LABELS = {'profile': 'پروفایل', 'easy': 'برد Easy', 'deck': 'برد Deck'}


async def handle(bot, update, context):
    query = update.callback_query
    if update.effective_chat.type != 'private':
        await query.answer('انتخاب آواتار فقط در پیوی ربات انجام می‌شود.', show_alert=True)
        return
    await query.answer()
    data = query.data
    if data.startswith('avatar_clear_'):
        slot = data.removeprefix('avatar_clear_')
        if slot not in LABELS:
            return
        card_avatars.clear_choice(bot.db, query.from_user.id, slot)
        await query.edit_message_text('آواتار انتخاب‌شده برداشته شد.', reply_markup=Markup([[Button('🔙 ظاهر و برد', callback_data='style_menu')]]))
        return
    if data.startswith('avatar_pick_'):
        token = data.removeprefix('avatar_pick_')
        item = context.user_data.get('avatar_choices', {}).get(token)
        if item:
            try:
                card_avatars.save_choice(bot.db, query.from_user.id, item['slot'], item['card_id'], item['rarity'])
            except ValueError as error:
                await query.edit_message_text(str(error), reply_markup=Markup([[Button('🎭 بازکردن ظاهر و برد', callback_data='style_menu')]]))
                return
            await query.edit_message_text('✅ آواتار ' + LABELS[item['slot']] + ' ذخیره شد.',
                                          reply_markup=Markup([[Button('🔙 ظاهر و برد', callback_data='style_menu')]]))
            return
        await query.edit_message_text('این انتخاب قدیمی شده؛ دوباره از ظاهر و برد بازش کن.',
                                     reply_markup=Markup([[Button('🎭 ظاهر و برد', callback_data='style_menu')]]))
        return
    if not data.startswith('avatar_page_'):
        return
    try:
        _, _, slot, raw_page = data.split('_', 3)
        page = max(0, int(raw_page))
    except (ValueError, TypeError):
        return
    if slot not in LABELS:
        return
    items = card_avatars.choices(bot.db, query.from_user.id)
    page = min(page, max(0, (len(items) - 1) // PAGE_SIZE))
    rows, tokens = [], {}
    selected = card_avatars.selected(bot.db, query.from_user.id, slot)
    for item in items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        token = uuid.uuid4().hex[:16]
        tokens[token] = dict(item, slot=slot)
        marker = '✓ ' if selected and selected['card_id'] == item['card_id'] and selected['rarity'] == item['rarity'] else ''
        rows.append([Button(marker + item['name'][:55] + ' · ' + item['rarity'].title(),
                            callback_data='avatar_pick_' + token)])
    context.user_data['avatar_choices'] = tokens
    nav = []
    if page:
        nav.append(Button('قبلی', callback_data=f'avatar_page_{slot}_{page-1}'))
    if (page + 1) * PAGE_SIZE < len(items):
        nav.append(Button('بعدی', callback_data=f'avatar_page_{slot}_{page+1}'))
    if nav:
        rows.append(nav)
    if selected:
        rows.append([Button('برداشتن آواتار', callback_data=f'avatar_clear_{slot}')])
    rows.append([Button('🔙 ظاهر و برد', callback_data='style_menu')])
    await query.edit_message_text('🎭 آواتار ' + LABELS[slot] + ' را انتخاب کن:\n\n'
                                  + ('از آواتار کارت‌هایی که داری انتخاب کن.' if items else 'هنوز آواتار قابل انتخابی نداری.'),
                                  reply_markup=Markup(rows))
