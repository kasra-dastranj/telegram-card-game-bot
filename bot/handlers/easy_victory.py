"""Private profile controls and post-settlement Easy winner presentation."""
import logging
import time
import uuid

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

from bot.deck_reports import isolate
from systems import easy_presentation as settings

logger = logging.getLogger(__name__)
PAGE_SIZE = 8
DRAFT_TTL = 600


def back_buttons():
    return Markup([[Button('🔙 شعار برد ایزی مود', callback_data='easy_victory_menu')]])


def menu(bot, user_id):
    value = settings.read(bot.db, user_id)
    card = settings.owned_card(bot.db, user_id, value['card_id'], value['rarity']) if value.get('card_id') else None
    character = isolate(f'{card.name} ({card.rarity.value.title()})') if card else 'هنوز انتخاب نکردی'
    text = ('🏆 بردِ ایزی مودت چه شکلی باشه؟\n\n🎴 شخصیت: ' + character
            + '\n💬 شعار: ' + isolate(value.get('slogan', 'هنوز ننوشتی')))
    if value.get('card_id') and not card:
        text += '\nکارت قبلی دیگه در دسترست نیست؛ یه شخصیت دیگه انتخاب کن.'
    return text, Markup([
        [Button('🎴 انتخاب شخصیت', callback_data='easy_victory_cards_0')],
        [Button('💬 نوشتن شعار', callback_data='easy_victory_slogan')],
        [Button('🗑 پاک‌کردن تنظیم برد', callback_data='easy_victory_clear')],
        [Button('🔙 پروفایل', callback_data='easy_profile')]])


async def handle(bot, update, context):
    query = update.callback_query
    if update.effective_chat.type != 'private':
        await query.answer('این تنظیم رو توی پیوی ربات باز کن.', show_alert=True)
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    # Navigating away invalidates text drafts; old card panels have scoped tokens.
    context.user_data.pop('easy_victory_draft', None)
    if data == 'easy_victory_slogan':
        build = context.user_data.get('deck_build', {})
        if build.get('waiting_name') or build.get('waiting_slogan'):
            await query.edit_message_text('اول اسم یا شعار دکت رو کامل کن؛ بعد بیا شعار ایزی رو بنویس.',
                                          reply_markup=back_buttons())
            return
        context.user_data['easy_victory_draft'] = {'expires_at': time.time() + DRAFT_TTL}
        await query.edit_message_text('💬 وقتی اول شدی چی بگیم؟\nشعارت رو بنویس؛ از ۱ تا ۱۲۰ کاراکتر.',
                                      reply_markup=Markup([[Button('❌ لغو', callback_data='easy_victory_menu')]]))
        return
    if data.startswith('easy_victory_cards_'):
        try:
            page = max(0, int(data.removeprefix('easy_victory_cards_')))
        except ValueError:
            page = 0
        items = settings.choices(bot.db, user_id)
        page = min(page, max(0, (len(items) - 1) // PAGE_SIZE))
        actions, rows = {}, []
        for item in items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            # Do not offer a form without an actual card definition.
            if not settings.owned_card(bot.db, user_id, item['card_id'], item['rarity']):
                continue
            token = uuid.uuid4().hex
            actions[token] = item
            label = f"{item['name']} ({item['rarity'].title()})"
            rows.append([Button(label[:90], callback_data='easy_victory_pick_' + token)])
        context.user_data['easy_victory_choices'] = actions
        nav = []
        if page:
            nav.append(Button('قبلی', callback_data=f'easy_victory_cards_{page - 1}'))
        if (page + 1) * PAGE_SIZE < len(items):
            nav.append(Button('بعدی', callback_data=f'easy_victory_cards_{page + 1}'))
        if nav:
            rows.append(nav)
        rows.extend(back_buttons().inline_keyboard)
        await query.edit_message_text('🎴 استیکر کدوم شخصیتت رو برای برد بفرستیم؟' if actions else
                                      'فعلاً کارتی برای انتخاب نداری.', reply_markup=Markup(rows))
        return
    if data.startswith('easy_victory_pick_'):
        token = data.removeprefix('easy_victory_pick_')
        item = context.user_data.get('easy_victory_choices', {}).pop(token, None)
        if not item:
            await query.edit_message_text('این انتخاب قدیمیه؛ دوباره شخصیتت رو انتخاب کن.', reply_markup=back_buttons())
            return
        try:
            settings.save(bot.db, user_id, card_id=item['card_id'], rarity=item['rarity'])
        except ValueError as exc:
            await query.edit_message_text(str(exc), reply_markup=back_buttons())
            return
        context.user_data.pop('easy_victory_choices', None)
    elif data == 'easy_victory_clear':
        settings.clear(bot.db, user_id)
    elif data != 'easy_victory_menu':
        return
    text, markup = menu(bot, user_id)
    await query.edit_message_text(text, reply_markup=markup)


async def receive_slogan(bot, update, context):
    draft = context.user_data.get('easy_victory_draft')
    if not draft or update.effective_chat.type != 'private':
        return
    if draft.get('expires_at', 0) < time.time():
        context.user_data.pop('easy_victory_draft', None)
        await update.effective_message.reply_text('مهلت نوشتن شعار تموم شد؛ دوباره بازش کن.', reply_markup=back_buttons())
        return
    try:
        settings.save(bot.db, update.effective_user.id, slogan=update.effective_message.text)
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc), reply_markup=back_buttons())
        return
    context.user_data.pop('easy_victory_draft', None)
    text, markup = menu(bot, update.effective_user.id)
    await update.effective_message.reply_text('✅ شعارت ذخیره شد!\n\n' + text, reply_markup=markup)


async def announce(bot, context, request, report):
    """Called only after settlement. Tied first place gets the table alone."""
    winners = report.get('winner_ids', [])
    if len(winners) != 1:
        return
    user_id = int(winners[0])
    try:
        value = settings.read(bot.db, user_id)
        card = settings.owned_card(bot.db, user_id, value['card_id'], value['rarity']) if value.get('card_id') else None
        if card:
            from bot.card_reward_presentation import send_card_sticker
            async def send_sticker(sticker):
                return await context.bot.send_sticker(chat_id=request['origin_chat_id'], sticker=sticker)
            await send_card_sticker(bot, context, card, send_sticker)
        name = bot.db.get_or_create_player(user_id).first_name
        text = '🏆 ' + isolate(name) + ' برنده شد!'
        if value.get('slogan'):
            text += '\n\n💬 ' + isolate(value['slogan'])
        await context.bot.send_message(chat_id=request['origin_chat_id'], text=text)
    except Exception:
        # Cosmetic transport errors must not retry settlement or block later games.
        logger.warning('Could not deliver Easy victory presentation')
