"""Private profile editor for Deck victory text and its avatar picker."""
import time
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from core.display_text import isolate
from systems import deck_victory as settings


def back_buttons():
    return Markup([[Button('🔙 شعار برد دک مود', callback_data='deck_victory_menu')]])


def menu(bot, user_id):
    slogan = settings.read(bot.db, user_id)
    return ('🃏 وقتی دک‌مود رو بردی چی بگیم؟\n\n💬 ' + isolate(slogan or 'هنوز شعاری ننوشتی')
            + '\n\nاین شعار زیر عکس نتیجهٔ بردت میاد و برای همهٔ دک‌هات استفاده می‌شه.'), Markup([
        [Button('🎭 انتخاب آواتار برد', callback_data='avatar_page_deck_0')],
        [Button('💬 نوشتن / تغییر شعار', callback_data='deck_victory_slogan')],
        [Button('🗑 پاک‌کردن شعار پروفایل', callback_data='deck_victory_clear')],
        [Button('🔙 ظاهر و برد', callback_data='style_menu')]])


async def handle(bot, update, context):
    query = update.callback_query
    if update.effective_chat.type != 'private':
        await query.answer('این تنظیم رو توی پیوی ربات باز کن.', show_alert=True)
        return
    await query.answer()
    context.user_data.pop('deck_victory_draft', None)
    context.user_data.pop('easy_victory_draft', None)
    if query.data == 'deck_victory_slogan':
        build = context.user_data.get('deck_build', {})
        if build.get('waiting_name') or build.get('waiting_slogan'):
            await query.edit_message_text('اول ساخت یا ویرایش دکت رو کامل کن؛ بعد بیا شعارت رو بنویس.',
                                          reply_markup=back_buttons())
            return
        context.user_data['deck_victory_draft'] = {'expires_at': time.time() + 600}
        await query.edit_message_text('💬 شعار برد دک‌مودت رو بنویس؛ از ۱ تا ۱۲۰ کاراکتر.',
                                      reply_markup=Markup([[Button('❌ لغو', callback_data='deck_victory_menu')]]))
        return
    if query.data == 'deck_victory_clear':
        settings.clear(bot.db, query.from_user.id)
    elif query.data != 'deck_victory_menu':
        return
    text, markup = menu(bot, query.from_user.id)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=None)


async def receive_slogan(bot, update, context):
    draft = context.user_data.get('deck_victory_draft')
    if not draft or update.effective_chat.type != 'private':
        return
    if draft.get('expires_at', 0) < time.time():
        context.user_data.pop('deck_victory_draft', None)
        await update.effective_message.reply_text('مهلت نوشتن شعار تموم شد؛ دوباره بازش کن.', reply_markup=back_buttons())
        return
    try:
        settings.save(bot.db, update.effective_user.id, update.effective_message.text)
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc), reply_markup=back_buttons())
        return
    context.user_data.pop('deck_victory_draft', None)
    text, markup = menu(bot, update.effective_user.id)
    await update.effective_message.reply_text('✅ شعارت ذخیره شد!\n\n' + text, reply_markup=markup, parse_mode=None)
