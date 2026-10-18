"""Private Telegram Silver Claim menu and receipt presentation."""
import logging
import uuid
from html import escape

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
from telegram.error import TelegramError

from bot.silver_claim_art import silver_claim_picture
from bot.card_reward_presentation import send_claim_card
from systems.progression_economy import ProgressionEconomy
from core.display_text import isolate
from bot.player_messages import error_text

logger = logging.getLogger(__name__)


def private_panel(update):
    # These callbacks only belong to the main menu in the user's bot chat.
    return update.effective_message.chat.type == 'private'


async def show_menu(bot, update, context, notice=None, receipt_action=None):
    from bot.handlers.progression import action_button

    inventory = ProgressionEconomy(bot.db).inventory(update.effective_user.id)
    if not inventory.get('ok'):
        await update.effective_message.reply_text(inventory['error'])
        return
    items = inventory['items']
    number = lambda value: str(value).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
    text = ('🎟 سیلور کلیم\n\n'
            f"{number(items.get('free_silver_claim', 0))} تا سیلور کلیم داری\n"
            f"{number(items.get('silver_ticket', 0))} تا سیلور تیکت داری\n\n"
            f"با {number(inventory['silver_claim_tickets'])} تا سیلور تیکت، یه سیلور کلیم بساز.\n"
            'هر سیلور کلیم یه کارت Epic داره!')
    if notice:
        text += '\n\n' + (error_text(notice, inventory) if isinstance(notice, dict) else notice)
    keyboard = []
    for kind, title in [('silver_craft', 'ساخت سیلور کلیم'), ('silver_use', 'استفاده از سیلور کلیم')]:
        action = {'kind': kind, 'config_version': inventory['config_version'],
                  'request_key': 'tg-' + kind + ':' + uuid.uuid4().hex}
        keyboard.append([action_button(context, title, action)])
    if receipt_action:
        keyboard.append([action_button(context, 'مشاهده کارت دریافتی', dict(receipt_action, view_receipt=True))])
    keyboard.append([Button('🔙 منوی اصلی', callback_data='back_to_main')])
    markup = InlineKeyboardMarkup(keyboard)
    try:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    except TelegramError:
        # A deleted/old panel must not hide an already committed receipt.
        await update.effective_message.reply_text(text, reply_markup=markup)


def card_text(card, replayed=False):
    title = 'این کارت رو قبلاً از همین سیلور کلیم گرفتی:' if replayed else '✨ ببین کی به تیمت اضافه شد!'
    text = (f'{title}\n\n🟣 <b>{isolate(escape(card.name))}</b> {isolate("(Epic)")}\n\n'
            f'📊 آمار کارت:\n💪 قدرت: {card.power}\n⚡️ سرعت: {card.speed}\n'
            f'🧠 آی‌کیو: {card.iq}\n❤️ محبوبیت: {card.popularity}\n'
            f'🎯 مجموع: {card.get_total_stats()}')
    if card.abilities:
        text += '\n\n✨ ابیلیتی‌ها:\n' + '\n'.join('• ' + escape(str(ability)) for ability in card.abilities)
    return text


async def handle_action(bot, update, context, action):
    economy = ProgressionEconomy(bot.db)
    user = update.effective_user.id
    crafting = action['kind'] == 'silver_craft'
    result = (economy.craft_silver_claim(user, action['request_key'], action['config_version'])
              if crafting else economy.use_silver_claim(user, action['request_key']))
    if not result.get('ok'):
        return await show_menu(bot, update, context, result)
    replayed = result.get('replayed', False)
    notice = ('این ساخت قبلاً ثبت شده؛ دوباره تیکت کم نکردیم.' if crafting else
              'این سیلور کلیم قبلاً باز شده؛ دوباره از موجودیت کم نکردیم.') if replayed else None
    message = update.effective_message
    # Delivery errors never undo a committed reward or reuse the spend with a new key.
    try:
        await show_menu(bot, update, context, notice, None if crafting else action)
    except TelegramError:
        logger.warning('Could not refresh Silver Claim panel')
    if crafting:
        if replayed:
            return
        caption = '🎟 یه سیلور کلیم به موجودیت اضافه شد!\nهر وقت آماده بودی، بازش کن ببین چه کارتی منتظرته.'
        try:
            with silver_claim_picture() as picture:
                await message.reply_photo(picture, caption=caption)
        except (TelegramError, OSError):
            logger.warning('Could not send Silver Claim illustration')
            await message.reply_text(caption)
        return
    if not replayed:
        try:
            # Telegram clients can animate a single interactive emoji in private chats.
            await message.reply_text('🎉')
        except TelegramError:
            logger.warning('Could not send Silver Claim celebration')
    card = bot.db.get_card_by_id_for_rarity(result['card_id'], result['rarity'])
    if card is None:
        await message.reply_text('کارت Epic به موجودیت اضافه شد؛ مشخصاتش فعلاً در دسترس نیست.')
        return
    if not replayed or action.get('view_receipt'):
        await send_claim_card(message, card, bot.config, bot.db)
    try:
        await message.reply_text(card_text(card, replayed), parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[Button('🎟 سیلور کلیم', callback_data='v2_silver_claim')],
                                              [Button('🔙 منوی اصلی', callback_data='back_to_main')]]))
    except TelegramError:
        logger.warning('Could not send Silver Claim card details')
        await show_menu(bot, update, context,
                        'کارتت به موجودیت اضافه شده! برای دیدنش «مشاهده کارت دریافتی» رو بزن.', action)
