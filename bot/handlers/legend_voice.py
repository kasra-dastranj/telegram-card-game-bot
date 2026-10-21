"""Owner-scoped private text/voice controls, shared across owned Legend forms."""
import uuid
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from systems import victory_voices as voices


def button(context, card_id):
    choices = context.user_data.setdefault('legend_voice_choices', {})
    while len(choices) >= 40:
        choices.pop(next(iter(choices)))
    token = uuid.uuid4().hex
    choices[token] = card_id
    return Button('🎙 شعار کارت: ویس یا متن', callback_data='lv:' + token + ':menu')


async def handle(bot, update, context):
    query = update.callback_query
    if update.effective_chat.type != 'private':
        await query.answer('این تنظیم رو توی پیوی ربات باز کن.', show_alert=True)
        return
    parts = query.data.split(':')
    card_id = context.user_data.get('legend_voice_choices', {}).get(parts[1]) if len(parts) == 3 else None
    if not card_id:
        await query.answer('این دکمه قدیمیه؛ دوباره مشخصات کارتت رو باز کن.', show_alert=True)
        return
    mode = parts[2]
    if mode not in ('menu', 'text', 'voice'):
        await query.answer('متن یا ویس رو انتخاب کن.', show_alert=True)
        return
    try:
        value = voices.preference(bot.db, query.from_user.id, card_id, mode if mode != 'menu' else None)
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await query.answer()
    text = ('🟡 شعار کارت Legendت چطوری بیاد؟\n\n'
            'تنظیم فعلی: ' + ('🎙 ویس' if value == 'voice' else '📝 متن')
            + '\nبرای بردهای Quick؛ دک‌مود و شعار ایزی جدا هستن.'
            + '\nاگر ویسی ثبت نشده باشه یا ارسال نشه، متن شعار میاد.')
    await query.edit_message_text(text, parse_mode=None, reply_markup=Markup([
        [Button('📝 متن', callback_data='lv:' + parts[1] + ':text'),
         Button('🎙 ویس', callback_data='lv:' + parts[1] + ':voice')],
        [Button('🔙 مشخصات کارت', callback_data='cardinfo_' + card_id)]]))
