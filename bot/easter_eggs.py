"""Trusted Telegram identities, durable response delivery and fixed reward types."""
import asyncio
import logging
import time
from io import BytesIO

from systems import easter_eggs as eggs, easter_media

logger = logging.getLogger(__name__)


async def deliver(bot, context, event):
    receipt, state = event['receipt'], event['delivery']
    response = receipt['response']
    text = response['text'].replace('{name}', event['name'] or 'بازیکن')
    text = text.replace('{remaining}', str(receipt['remaining']) if receipt['remaining'] is not None else 'نامحدود')
    if receipt['show_reward_receipt'] and receipt['rewards']:
        text += ('\n\n' if text else '') + '\n'.join(receipt['rewards'])
    from bot.card_reward_presentation import text_chunks
    parts = text_chunks(text) if text else []
    kwargs = dict(chat_id=event['chat_id'], reply_to_message_id=event['message_id'], allow_sending_without_reply=True)
    try:
        for index, part in enumerate(parts):
            if index < state.get('text_next', 0):
                continue
            await asyncio.wait_for(context.bot.send_message(text=part, **kwargs), 10)
            if not eggs.delivery_checkpoint(bot.db, event, text_next=index + 1):
                return
        if response['media_id'] and not state.get('media_done'):
            item, raw = await asyncio.to_thread(easter_media.read, bot.db, response['media_id'])
            media = BytesIO(raw)
            media.name = item['filename']
            method = {'photo': 'send_photo', 'voice': 'send_voice', 'video': 'send_video', 'sticker': 'send_sticker'}[item['kind']]
            await asyncio.wait_for(getattr(context.bot, method)(**{item['kind']: media}, **kwargs), 15)
            if not eggs.delivery_checkpoint(bot.db, event, media_done=True):
                return
        eggs.delivery_checkpoint(bot.db, event, done=True, lease_until=0)
    except Exception:
        attempts = state.get('attempts', 1)
        eggs.delivery_checkpoint(bot.db, event, lease_until=0, next_attempt=time.time() + min(3600, 30 * 2**min(attempts, 7)),
                                 done=attempts >= 10, failed=attempts >= 10)
        logger.warning('Easter response delivery failed; committed rewards will not repeat', exc_info=True)


async def handle(bot, update, context):
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    if not message or not user or getattr(user, 'is_bot', False) or getattr(message, 'sender_chat', None):
        return False
    if not isinstance(getattr(message, 'message_id', None), int):
        return False
    try:
        result = eggs.execute(bot.db, user.id, update.effective_chat.id, message.message_id, message.text or '', update.effective_chat.type)
    except ValueError as error:
        code = str(error)
        notice = {'rare_supply_empty': 'نسخهٔ آزاد این کارت ریر تمام شده؛ سهمیهٔ تو مصرف نشد.'}.get(code, code)
        await message.reply_text(notice)
        return True
    if not result['matched']:
        return False
    if result.get('event_id'):
        event = eggs.claim_delivery(bot.db, result['event_id'])
        if event:
            await deliver(bot, context, event)
    elif result.get('notice'):
        # Repeated exhausted attempts must not turn a busy group into a bot echo.
        cache = context.user_data.setdefault('easter_notices', {})
        key = result['notice']
        if time.time() - cache.get(key, 0) >= 10:
            if len(cache) >= 30:
                cache.clear()
            cache[key] = time.time()
            await message.reply_text(key)
    return True


async def drain(bot, context):
    for _ in range(5):
        event = eggs.claim_delivery(bot.db)
        if not event:
            return
        await deliver(bot, context, event)
