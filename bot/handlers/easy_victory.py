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


def details_button(request_id):
    return Markup([[Button('مشاهده جزئیات', callback_data=f'easy_details_{request_id}')]])


def details_parts(report, db, limit=4000):
    """Keep the report readable within Telegram's UTF-16 text limit."""
    from bot.card_reward_presentation import text_chunks
    def units(value):
        return sum(2 if ord(character) > 0xFFFF else 1 for character in value)
    parts = []
    current = '📋 جزئیات Easy Mode'
    players = [int(user_id) for user_id in report.get('scores', {})]
    rank_names = {1: '🥇 اول', 2: '🥈 دوم', 3: '🥉 سوم'}
    for played in report.get('round_history', []):
        question = played.get('question', {}).get('text', '')
        heading = f"🎯 راند {played['round']}: {question}"
        if units(current) + units(heading) + 2 > limit:
            parts.append(current)
            current = '📋 ادامهٔ جزئیات Easy Mode'
        current += '\n\n' + heading
        entries = played.get('entries', [])
        ranked_values = sorted({(item.get('eligible', True), item['hidden_value']) for item in entries}, reverse=True)
        choices = {int(item['user_id']): item for item in entries}
        ordered_players = [int(item['user_id']) for item in entries]
        ordered_players.extend(user_id for user_id in players if user_id not in choices)
        for user_id in ordered_players:
            name = isolate(db.get_or_create_player(user_id).first_name)
            item = choices.get(user_id)
            if item is None:
                line = f'• {name}: انتخاب نکرد'
            else:
                rank = ranked_values.index((item.get('eligible', True), item['hidden_value'])) + 1
                place = rank_names.get(rank, f'رتبهٔ {rank}')
                line = f"{place} · {name}: {isolate(item['card_name'])}"
            if units(current) + units(line) + 1 > limit:
                parts.append(current)
                current = '📋 ادامهٔ جزئیات Easy Mode\n\n' + heading
            current += '\n' + line
    parts.append(current)
    # A single authored heading/card name can itself exceed the limit.
    return [chunk for part in parts for chunk in text_chunks(part, limit)]


async def show_details(bot, update, context):
    query = update.callback_query
    request_id = query.data.removeprefix('easy_details_')
    request = bot.modes.get_request(request_id)
    chat = update.effective_chat
    if not request or chat.type not in ('group', 'supergroup') or chat.id != request.get('origin_chat_id'):
        await query.answer('جزئیات این بازی فقط در گروه خودش نمایش داده می‌شود.', show_alert=True)
        return
    report = bot.modes.claim_easy_details(request_id)
    if not report:
        await query.answer('جزئیات قبلاً نمایش داده شده یا بازی در دسترس نیست.')
        return
    try:
        for part in details_parts(report, bot.db):
            await context.bot.send_message(chat_id=chat.id, text=part,
                                           reply_to_message_id=query.message.message_id)
    except Exception:
        bot.modes.release_easy_details(request_id)
        logger.warning('Could not deliver Easy round details', exc_info=True)
        await query.answer('ارسال جزئیات نشد؛ دوباره تلاش کن.', show_alert=True)
        return
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.debug('Could not remove Easy details button', exc_info=True)


def menu(bot, user_id):
    from systems import card_avatars
    value = settings.read(bot.db, user_id)
    avatar = card_avatars.selected(bot.db, user_id, 'easy')
    character = isolate(f"{avatar['card'].name} ({avatar['rarity'].title()})") if avatar else 'هنوز انتخاب نکردی'
    text = ('🏆 بردِ ایزی مودت چه شکلی باشه؟\n\n🎭 آواتار: ' + character
            + '\n💬 شعار: ' + isolate(value.get('slogan', 'هنوز ننوشتی')))
    return text, Markup([
        [Button('🎭 انتخاب آواتار برد', callback_data='avatar_page_easy_0')],
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
    context.user_data.pop('deck_victory_draft', None)
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
        from systems.card_avatars import clear_choice
        clear_choice(bot.db, user_id, 'easy')
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
        from systems import card_avatars
        value = settings.read(bot.db, user_id)
        avatar_sent = await card_avatars.send_sticker(bot, context, request['origin_chat_id'], user_id, 'easy')
        card = settings.owned_card(bot.db, user_id, value['card_id'], value['rarity']) if value.get('card_id') else None
        if card and not avatar_sent:
            from bot.card_reward_presentation import send_card_sticker
            async def send_sticker(sticker):
                return await context.bot.send_sticker(chat_id=request['origin_chat_id'], sticker=sticker)
            await send_card_sticker(bot, context, card, send_sticker)
        name = bot.db.get_or_create_player(user_id).first_name
        text = '🏆 ' + isolate(name)
        if value.get('slogan'):
            text += ': "' + isolate(value['slogan']) + '"'
        request_id = report.get('request_id')
        await context.bot.send_message(chat_id=request['origin_chat_id'], text=text,
                                       reply_markup=details_button(request_id) if request_id else None)
    except Exception:
        # Cosmetic transport errors must not retry settlement or block later games.
        logger.warning('Could not deliver Easy victory presentation')
