"""Private home for existing profile/victory cosmetic settings and previews."""
from io import BytesIO

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from systems import card_avatars


async def handle(bot, update, context):
    query = update.callback_query
    if update.effective_chat.type != 'private':
        await query.answer('تنظیم ظاهر و برد در پیوی ربات است.', show_alert=True)
        return
    await query.answer()
    data = query.data
    if data.startswith('style_preview_'):
        slot = data.removeprefix('style_preview_')
        if slot not in card_avatars.SLOTS:
            return
        choice = card_avatars.selected(bot.db, query.from_user.id, slot)
        if choice:
            if slot == 'profile':
                await query.message.reply_photo(photo=BytesIO(choice['path'].read_bytes()), caption='👤 پیش‌نمایش آواتار پروفایل')
            else:
                await card_avatars.send_sticker(bot, context, query.from_user.id, query.from_user.id, slot)
        if slot == 'profile':
            message = 'هنوز آواتار پروفایل انتخاب نکرده‌ای.' if not choice else 'آمار و رتبه‌ها هنگام نمایش پروفایل زیر عکس می‌آیند.'
        elif slot == 'easy':
            from systems.easy_presentation import read
            slogan = read(bot.db, query.from_user.id).get('slogan')
            message = '🏆 ' + (query.from_user.first_name or 'بازیکن') + (': "' + slogan + '"' if slogan else '')
        else:
            from systems.deck_victory import read
            message = '🏆 ' + (read(bot.db, query.from_user.id) or 'شعار دک انتخاب‌شده در بازی؛ اگر نداشته باشد پیام پیش‌فرض برد.')
        await query.message.reply_text('🔎 پیش‌نمایش خصوصی\n' + message)
        return
    if data.startswith('style_voices'):
        from systems import victory_voices
        from bot.handlers.legend_voice import button
        try:
            page = max(0, int(data.removeprefix('style_voices_'))) if data.startswith('style_voices_') else 0
        except ValueError:
            return
        forms = [item for item in card_avatars.owned_forms(bot.db, query.from_user.id)
                 if item['rarity'] == 'legend' and victory_voices.owned(bot.db, query.from_user.id, item['card_id'])]
        page = min(page, max(0, (len(forms) - 1) // 8))
        rows = []
        for item in forms[page * 8:(page + 1) * 8]:
            control = button(context, item['card_id'])
            rows.append([Button(item['name'], callback_data=control.callback_data)])
        nav = []
        if page:
            nav.append(Button('قبلی', callback_data=f'style_voices_{page-1}'))
        if (page + 1) * 8 < len(forms):
            nav.append(Button('بعدی', callback_data=f'style_voices_{page+1}'))
        if nav:
            rows.append(nav)
        rows.append([Button('🔙 ظاهر و برد', callback_data='style_menu')])
        await query.edit_message_text('🎙 ویس شعار کارت‌های لجند\n\nکارتت را انتخاب کن تا متن یا ویس برد Quick را تنظیم کنی. '
            'ویس‌ها را ادمین برای کارت بارگذاری می‌کند. تنظیم ریر از قانون ویس همان کارت پیروی می‌کند. '
            'شعار ایزی و دک تنظیم جدا دارند.' + ('\n\nفعلاً کارت لجند قابل تنظیمی نداری.' if not forms else ''), reply_markup=Markup(rows))
        return
    context.user_data.pop('easy_victory_draft', None)
    context.user_data.pop('deck_victory_draft', None)
    rows = []
    for slot, name in (('profile', 'پروفایل'), ('easy', 'برد ایزی'), ('deck', 'برد دک')):
        choice = card_avatars.selected(bot.db, query.from_user.id, slot)
        title = choice['card'].name if choice else 'انتخاب نشده'
        rows.append([Button(f'🎭 آواتار {name}: {title}', callback_data=f'avatar_page_{slot}_0'),
                     Button('👁 پیش‌نمایش', callback_data=f'style_preview_{slot}')])
    rows.extend([[Button('💬 شعار برد ایزی', callback_data='easy_victory_menu'), Button('💬 شعار برد دک', callback_data='deck_victory_menu')],
                 [Button('🎙 ویس / متن شعار کارت', callback_data='style_voices')],
                 [Button('🔙 پروفایل', callback_data='easy_profile')]])
    await query.edit_message_text('🎭 ظاهر و برد\n\nآواتار پروفایل، برد ایزی و برد دک مستقل‌اند. '
                                 'انتخاب‌ها و پیش‌نمایش‌ها فقط برای خودت در پیوی‌اند.', reply_markup=Markup(rows))
