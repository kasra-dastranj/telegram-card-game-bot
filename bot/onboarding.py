"""First private welcome and resumable sticker delivery; no automatic Daily Claim."""
import json
import logging
import sqlite3
from contextlib import closing

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

from bot.card_reward_presentation import send_card_sticker
from systems.starter_cards_system import starter_status, grant_starter_pack, offer_starter_pack

logger = logging.getLogger(__name__)
WELCOME = (
    '🎴 به TelBattle خوش اومدی!\n'
    'اینجا قهرمان‌ها و شرورهای فیلم‌ها، سریال‌ها و بازی‌ها روبه‌روی هم قرار می‌گیرن!\n\n'
    '🎁 کارت جمع کن و شخصیت‌هات رو ارتقا بده\n'
    '🃏 با سه تا کارت، دک خودت رو بچین\n'
    '⚔️ رفیقت رو به نبرد دعوت کن یا حریف تصادفی پیدا کن\n'
    '🏆 توی گروه بازی کن و با بقیه رقابت کن\n\n'
    '🎁 بستهٔ آغازینت: ۱۰ کارت نورمال تصادفی!'
)
PREFIX = 'starter_delivery:v2_10:'


def delivery_in(conn, user_id):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (PREFIX + str(user_id),)).fetchone()
    return json.loads(row[0]) if row else {'sent_ids': [], 'done': False}


def delivery(db, user_id):
    with closing(sqlite3.connect(db.db_path)) as conn:
        return delivery_in(conn, user_id)


def mark_delivery(db, user_id, *, card_id=None, done=False):
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = delivery_in(conn, user_id)
        if card_id and card_id not in state['sent_ids']:
            state['sent_ids'].append(card_id)
        state['done'] = state.get('done', False) or done
        conn.execute('INSERT OR REPLACE INTO foundation_settings(key,value_json) VALUES (?,?)',
                     (PREFIX + str(user_id), json.dumps(state)))


def needed(bot, user_id):
    offer_starter_pack(bot.db, user_id)
    return starter_status(bot.db, user_id).get('ok', False) and not delivery(bot.db, user_id).get('done')


def buttons(retry=False):
    rows = [[Button('🎁 دریافت کارت‌های اولیه', callback_data='starter_receive')]]
    if retry:
        rows.append([Button('🎮 منوی بازی', callback_data='back_to_main')])
    return Markup(rows)


async def show(bot, update, context):
    offer_starter_pack(bot.db, update.effective_user.id)
    if update.callback_query:
        await update.callback_query.edit_message_text(WELCOME)
    else:
        await update.effective_message.reply_text(WELCOME)
    await receive(bot, update, context, automatic=True)


async def resume_invite(bot, update, context):
    payload = context.user_data.pop('onboarding_invite', None)
    if not payload:
        return False
    old_args = getattr(context, 'args', None)
    try:
        context.args = [payload]
        if payload.startswith('attack_'):
            from bot.group_attacks import start
            return await start(bot,update,context)
        return await bot.handle_game_invite_start(update, context)
    finally:
        context.args = old_args


async def receive(bot, update, context, automatic=False):
    query = update.callback_query
    async def edit(text, **kwargs):
        if query:
            return await query.edit_message_text(text, **kwargs)
        return await update.effective_message.reply_text(text, **kwargs)
    if not update.effective_chat or update.effective_chat.type != 'private':
        if query:
            await query.answer('کارت‌های اولیه‌ت رو توی پیوی ربات بگیر.', show_alert=True)
        return
    user = update.effective_user if automatic else query.from_user
    if query and not automatic:
        await query.answer()
    if not await bot.is_user_in_channel(user.id, context):
        await bot.send_channel_join_message(update)
        return
    bot.db.get_or_create_player(user.id, user.username, user.first_name)
    active = context.bot_data.setdefault('_starter_deliveries', set())
    if user.id in active:
        return
    active.add(user.id)
    try:
        if delivery(bot.db, user.id).get('done'):
            await edit('🎴 کارت‌های اولیه‌ت رو قبلاً گرفتی!\nکارت روزانه‌ت رو با /claim بگیر.',
                reply_markup=Markup([[Button('🎮 منوی بازی', callback_data='back_to_main')]]))
            return
        result = grant_starter_pack(bot.db, user.id)
        if not result.get('ok'):
            text = ('کارت‌های اولیه فعلاً آماده نیستن؛ یه کم بعد دوباره بزن.'
                    if result.get('reason') == 'pool_unavailable' else
                    'این بسته شامل این حساب نمی‌شود؛ کارت روزانه‌ت رو با /claim بگیر.')
            await edit(text, reply_markup=buttons(retry=True) if result.get('reason') == 'pool_unavailable' else
                Markup([[Button('🎮 منوی بازی', callback_data='back_to_main')]]))
            return
        sent = set(delivery(bot.db, user.id)['sent_ids'])
        for card_id in result['card_ids']:
            if card_id in sent:
                continue
            card = bot.db.get_card_by_id_for_rarity(card_id, 'normal')
            if not card:
                # A later catalog edit can retire a committed reward; never redraw it.
                mark_delivery(bot.db, user.id, card_id=card_id)
                continue
            async def send_sticker(sticker, **kwargs):
                return await context.bot.send_sticker(chat_id=user.id, sticker=sticker, **kwargs)
            if not await send_card_sticker(bot, context, card, send_sticker):
                await edit('کارت‌هات توی موجودیت هستن؛ ارسال یکی از استیکرها نشد.\nدوباره بزن تا از همین‌جا ادامه بدیم.',
                                              reply_markup=buttons(retry=True))
                return
            mark_delivery(bot.db, user.id, card_id=card_id)
        await context.bot.send_message(chat_id=user.id,
            text='🎴 اینم ده کارت نورمالت!\nحالا می‌تونی کارت روزانه‌ت رو هم با دستور /claim بگیری.',
            reply_markup=Markup([[Button('🎮 منوی بازی', callback_data='back_to_main')]]))
        mark_delivery(bot.db, user.id, done=True)
        await resume_invite(bot, update, context)
    except Exception:
        logger.warning('Starter onboarding delivery interrupted; committed inventory is preserved')
        try:
            await edit('ارسال کارت‌ها کامل نشد؛ دوباره بزن تا ادامه بدیم.', reply_markup=buttons(retry=True))
        except Exception:
            pass
    finally:
        active.discard(user.id)
