"""Private card-ready messages. Delivery never grants cards or game rewards."""
import asyncio
from io import BytesIO
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, RetryAfter

from bot.card_reward_presentation import text_chunks
from bot.battle_visual_delivery import read_bitmap, work
from core.display_text import isolate
from systems.card_collection import custom_owned_card
from systems.custom_card_notices import claim, checkpoint, rare_owned_card

logger = logging.getLogger(__name__)


def text(payload):
    rare = payload.get('delivery_kind') == 'rare'
    lines = ['🎉 مبارکت باشه! یه کارت Rare به موجودیت اضافه شد.' if rare else '🎉 مبارکت باشه! کارت شخصی‌سازی‌شده‌ت آماده‌ست.', '',
             '🎴 '+isolate(payload['name'])+' '+isolate('('+payload['rarity'].title()+')'), '',
             '📊 آمار کارت:']
    for key, label in (('power','💪 قدرت'),('speed','⚡ سرعت'),('iq','🧠 هوش'),('popularity','❤️ محبوبیت')):
        lines.append(label+': '+isolate(payload[key]))
    lines.append('🎯 مجموع: '+isolate(sum(payload[key] for key in ('power','speed','iq','popularity'))))
    if payload.get('traits'):
        lines += ['', '🧬 تریت‌ها: '+'، '.join(isolate(value) for value in payload['traits'])]
    if payload.get('abilities'):
        lines += ['', '✨ ابیلیتی‌ها:'] + ['• '+str(value) for value in payload['abilities']]
    biography = str(payload.get('biography') or '').strip()
    if biography:
        lines += ['', '📖 بیوگرافی', biography]
    if rare:
        lines += ['', '🌟 شمارهٔ نسخه: ' + isolate(payload['serial'])]
    lines += ['', 'کارتت توی «کارت‌های من ← ' + ('Rare' if rare else 'شخصی‌سازی‌شده') + '» منتظرته!']
    return '\n'.join(lines)


def markup(card_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎴 مشخصات کارتم', callback_data='cardinfo_'+card_id)]])


def current(bot, key, notice):
    if not checkpoint(bot.db, key, notice):
        return None
    card = (rare_owned_card(bot.db, notice) if notice.get('kind') == 'rare' else
            custom_owned_card(bot.db, notice['user_id'], notice['card_id']))
    if not card:
        checkpoint(bot.db, key, notice, state='cancelled')
    return card


async def send_one(bot, context, key, notice):
    parts = text_chunks(text(notice['payload']))  # Fits photo captions, counts UTF-16.
    buttons = markup(notice['card_id'])
    card = current(bot, key, notice)
    if not card:
        return
    if not notice['photo_done']:
        image = None
        if notice.get('kind') == 'rare':
            from bot.battle_visual_delivery import card_art
            image = await card_art(bot, context, card)
        elif card.image_path:
            try:
                image = await work(context, read_bitmap, card.image_path)
            except asyncio.TimeoutError:
                raise  # A busy worker is temporary; keep the photo for retry.
            except (OSError, ValueError):
                logger.warning('Custom card receipt artwork unavailable')
        if image and current(bot, key, notice):
            try:
                await asyncio.wait_for(context.bot.send_photo(chat_id=notice['user_id'],photo=BytesIO(image),
                    caption=parts[0],parse_mode=None,reply_markup=buttons if len(parts)==1 else None),timeout=30)
            except BadRequest:
                # A rejected image must not hide the card-ready message.
                if not checkpoint(bot.db,key,notice,photo_done=True):return
            else:
                if not checkpoint(bot.db,key,notice,photo_done=True,text_next=1):return
        elif not checkpoint(bot.db,key,notice,photo_done=True):
            return
    while notice['text_next'] < len(parts):
        if not current(bot,key,notice):return
        index=notice['text_next']
        await asyncio.wait_for(context.bot.send_message(chat_id=notice['user_id'],text=parts[index],
            parse_mode=None,reply_markup=buttons if index==len(parts)-1 else None),timeout=30)
        if not checkpoint(bot.db,key,notice,text_next=index+1):return
    checkpoint(bot.db,key,notice,state='sent')


async def deliver(bot, context):
    if context.bot_data.get('_custom_card_notices_pause_until',0)>time.time():return
    if context.bot_data.get('_custom_card_notices_busy'):return
    context.bot_data['_custom_card_notices_busy']=True
    try:
        for _ in range(5):
            item=claim(bot.db)
            if not item:break
            key,notice=item
            try:
                await send_one(bot,context,key,notice)
            except (Forbidden,BadRequest):
                checkpoint(bot.db,key,notice,state='blocked')
                logger.warning('Custom card receipt could not reach private chat')
            except Exception as error:
                delay=min(1800,30*2**min(notice['attempts']-1,6))
                if isinstance(error,RetryAfter):
                    value=error.retry_after
                    delay=max(delay,value.total_seconds() if hasattr(value,'total_seconds') else value)
                    context.bot_data['_custom_card_notices_pause_until']=time.time()+delay
                checkpoint(bot.db,key,notice,state='retry' if notice['attempts']<6 else 'failed',
                           next_attempt=time.time()+delay)
                logger.warning('Custom card receipt deferred (%s)',type(error).__name__)
                if isinstance(error,RetryAfter):break
    finally:
        context.bot_data.pop('_custom_card_notices_busy',None)
