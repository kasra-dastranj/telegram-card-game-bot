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
    if mode not in ('menu', 'text', 'voice', 'preview'):
        await query.answer('متن یا ویس رو انتخاب کن.', show_alert=True)
        return
    try:
        value = voices.preference(bot.db, query.from_user.id, card_id, mode if mode in ('text', 'voice') else None)
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await query.answer()
    if mode == 'preview':
        choices = voices.card_choices(bot.db, query.from_user.id, card_id, 'legend')
        if choices:
            from bot.victory_voices import send
            if await send(bot.db, context, query.from_user.id, choices[0], 'card:' + card_id, owner_id=query.from_user.id):
                return
        card = bot.db.get_card_by_id_for_rarity(card_id, 'legend') or bot.db.get_card_by_id(card_id)
        dialogs = getattr(card, 'dialogs', []) or ['برد مبارک!']
        await query.message.reply_text('🔎 پیش‌نمایش متن؛ ویس انتخاب نشده یا در دسترس نیست:\n' + dialogs[0])
        return
    text = ('🟡 شعار کارت Legendت چطوری بیاد؟\n\n'
            'تنظیم فعلی: ' + ('🎙 ویس' if value == 'voice' else '📝 متن')
            + '\nبرای بردهای Quick؛ دک‌مود و شعار ایزی جدا هستن.'
            + '\nاگر ویسی ثبت نشده باشه یا ارسال نشه، متن شعار میاد.')
    await query.edit_message_text(text, parse_mode=None, reply_markup=Markup([
        [Button('📝 متن', callback_data='lv:' + parts[1] + ':text'),
         Button('🎙 ویس', callback_data='lv:' + parts[1] + ':voice')],
        [Button('👁 پیش‌نمایش انتخاب فعلی', callback_data='lv:' + parts[1] + ':preview')],
        [Button('🎭 ظاهر و برد', callback_data='style_menu')],
        [Button('🔙 مشخصات کارت', callback_data='cardinfo_' + card_id)]]))
