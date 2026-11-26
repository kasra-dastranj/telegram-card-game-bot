"""Post-commit card presentation. Never spends inventory, coins or XP."""
import asyncio
from io import BytesIO
import logging

from bot.utils import send_card_image_safely

logger = logging.getLogger(__name__)


def biography_text(card):
    bio = str(getattr(card, 'biography', '') or '').strip()
    if not bio or bio == 'Biography not available.':
        bio = 'بیوگرافی این کارت هنوز نوشته نشده.'
    return f'🎴 {card.name}\n\n{bio}'


def text_chunks(text, limit=1000):
    """Telegram limits use UTF-16 units; keep emoji and the entire biography."""
    parts, current, length = [], [], 0
    for character in text:
        units = 2 if ord(character) > 0xFFFF else 1
        if current and length + units > limit:
            parts.append(''.join(current))
            current, length = [], 0
        current.append(character)
        length += units
    if current:
        parts.append(''.join(current))
    return parts


async def send_claim_card(message, card, config, db):
    parts = text_chunks(biography_text(card))
    sent = await send_card_image_safely(message, card.name, config, parts[0],
                                      card=card, db=db, caption_parse_mode=None, sticker_caption=True)
    remaining = parts[1:] if sent else parts
    for part in remaining:
        await message.reply_text(part)
    return sent


def black_background_photo(raw, filename):
    from PIL import Image
    from bot.battle_visuals import safe_bitmap

    artwork = safe_bitmap(raw, preserve_alpha=True)
    background = Image.new('RGBA', artwork.size, 'black')
    background.alpha_composite(artwork)
    photo = BytesIO()
    photo.name = filename
    background.convert('RGB').save(photo, 'JPEG', quality=95)
    photo.seek(0)
    return photo


async def send_silver_claim_card(bot, context, message, card):
    from bot.battle_visual_delivery import card_art, work
    from telegram.error import TelegramError

    if bot.config.get('image_settings', {}).get('enable_images', False):
        parts = text_chunks(biography_text(card))
        try:
            raw = await card_art(bot, context, card, preserve_alpha=True)
            if raw:
                with await work(context, black_background_photo, raw, 'silver-card.jpg') as photo:
                    await message.reply_photo(photo, caption=parts[0], parse_mode=None)
        except (OSError, ValueError, asyncio.TimeoutError, TelegramError):
            logger.warning('Could not deliver Silver Claim card photo', exc_info=True)
        else:
            if raw:
                for part in parts[1:]:
                    await message.reply_text(part, parse_mode=None)
                return
    await send_claim_card(message, card, bot.config, bot.db)


async def send_daily_claim_card(message, card, ability, config, db):
    from core.display_text import isolate

    await send_card_image_safely(message, card.name, config, card=card, db=db)
    title = ability.get('title') if ability else None
    footer = f'\n\n🎁 ابیلیتی دریافتی: {isolate(title)} ×۱' if title else ''
    biography = biography_text(card)
    limit = 4096 - len(footer.encode('utf-16-le')) // 2
    parts = text_chunks(biography, limit=limit)
    if len(parts) > 1:
        biography = text_chunks(biography, limit=limit - 1)[0].rstrip() + '…'
    await message.reply_text(biography + footer, parse_mode=None)


def sticker_bytes(raw):
    from PIL import Image, ImageOps
    from bot.battle_visuals import safe_bitmap
    bitmap = safe_bitmap(raw, preserve_alpha=True)
    bitmap = ImageOps.contain(bitmap, (512, 512), Image.Resampling.LANCZOS)
    stream = BytesIO()
    bitmap.save(stream, 'WEBP', quality=85, method=4)
    if len(stream.getvalue()) > 512 * 1024:
        raise ValueError('sticker_size_limit')
    return stream.getvalue()


async def send_card_sticker(bot, context, card, send_sticker, *, show_details=True, strict=False):
    """Deliver one explicit form; never fall back to another form's artwork."""
    from bot.battle_visual_delivery import card_art, work
    from bot.card_sticker_details import button
    from telegram.error import BadRequest, TelegramError
    if not card:
        return False
    rarity = str(getattr(getattr(card, 'rarity', ''), 'value', getattr(card, 'rarity', '')))
    markup = button(card) if show_details else None
    kwargs = {'reply_markup': markup} if markup else {}
    try:
        cached = (bot.db.get_card_variant_media_file_id(card.card_id, rarity, 'sticker')
                  if getattr(card, 'origin', 'official') != 'custom' else None)
        if cached:
            await send_sticker(cached, **kwargs)
            return True
    except Exception as error:
        if strict and isinstance(error, (TelegramError, asyncio.TimeoutError)) and not isinstance(error, BadRequest):
            raise
        logger.warning('Card sticker cache delivery failed')
    try:
        from core.card_media import sticker_path
        from pathlib import Path
        path = sticker_path(card, include_legacy=False, db=bot.db)
        image = None
        if path:
            try:
                raw = await work(context, Path(path).read_bytes)
                image = await work(context, sticker_bytes, raw)
            except (OSError, ValueError):
                logger.warning('Uploaded sticker unavailable; trying this card portrait')
        if image is None:
            raw = await card_art(bot, context, card, preserve_alpha=True)
            if raw:
                image = await work(context, sticker_bytes, raw)
        if image:
            sticker = BytesIO(image)
            sticker.name = 'card-' + rarity + '.webp'
            await send_sticker(sticker, **kwargs)
            return True
    except Exception as error:
        if strict and isinstance(error, (TelegramError, asyncio.TimeoutError)) and not isinstance(error, BadRequest):
            raise
        logger.warning('Card sticker delivery failed')
    return False


async def send_upgrade_cards(bot, update, context, card_id, source, target):
    """Always resolve explicit transaction forms, even if another form is active."""
    from bot.deck_reports import isolate
    message = update.effective_message
    for rarity in (source, target):
        card = bot.db.get_card_by_id_for_rarity(card_id, rarity)
        delivered = await send_card_sticker(bot, context, card, message.reply_sticker) if card else False
        if not delivered:
            # Preserve sequence/context even when a form has no usable media.
            label = f'{card.name if card else card_id} ({rarity.title()})'
            try:
                await message.reply_text('🎴 ' + isolate(label) + '\nاستیکر این فرم فعلاً در دسترس نیست.')
            except Exception:
                logger.warning('Upgrade media fallback delivery failed')
