"""Post-commit card presentation. Never spends inventory, coins or XP."""
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


def sticker_bytes(raw):
    from PIL import Image, ImageOps
    from bot.battle_visuals import safe_bitmap
    bitmap = safe_bitmap(raw).convert('RGBA')
    bitmap = ImageOps.contain(bitmap, (512, 512), Image.Resampling.LANCZOS)
    stream = BytesIO()
    bitmap.save(stream, 'WEBP', quality=85, method=4)
    if len(stream.getvalue()) > 512 * 1024:
        raise ValueError('sticker_size_limit')
    return stream.getvalue()


async def send_card_sticker(bot, context, card, send_sticker):
    """Deliver one explicit form; never fall back to another form's artwork."""
    from bot.battle_visual_delivery import card_art, work
    try:
        cached = bot.db.get_card_variant_media_file_id(card.card_id, card.rarity.value, 'sticker')
        if cached:
            await send_sticker(cached)
            return True
    except Exception:
        logger.warning('Card sticker cache delivery failed')
    try:
        from core.card_media import sticker_path
        from pathlib import Path
        path = sticker_path(card, include_legacy=False)
        raw = await work(context, Path(path).read_bytes) if path else await card_art(bot, context, card)
        if not raw:
            path = sticker_path(card)
            raw = await work(context, Path(path).read_bytes) if path else None
        if raw:
            image = await work(context, sticker_bytes, raw)
            sticker = BytesIO(image)
            sticker.name = 'card-' + card.rarity.value + '.webp'
            await send_sticker(sticker)
            return True
    except Exception:
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
