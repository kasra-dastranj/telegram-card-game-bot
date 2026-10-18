"""Fresh deck previews using the same bounded worker and form-safe artwork."""
from io import BytesIO
import logging
import os
from pathlib import Path

from bot import battle_visuals as visual
from bot.battle_visual_delivery import ROOT, card_art, read_bitmap, work
from bot.deck_reports import isolate
from systems.deck_system import DeckSystem

logger = logging.getLogger(__name__)


def template():
    root = Path(os.environ.get('TELBATTLE_BATTLE_MEDIA_DIR', ROOT / 'assets/battle_visuals/overrides'))
    for extension in ('.webp', '.png', '.jpg', '.jpeg'):
        try:
            return read_bitmap(root / ('deck-template' + extension))
        except (OSError, ValueError):
            pass
    return visual.resources().get('deck/template', visual.background('default'))


async def send_deck(handler, context, user_id, deck_id, markup):
    deck = handler.db.get_deck_by_id(deck_id)
    if not deck or deck['player_id'] != user_id:
        return False
    cards = DeckSystem(handler.db).get_deck_cards(deck_id, user_id)
    synergy = handler.modes.calculate_deck_synergy(cards)
    lines = [f"🃏 {isolate(deck['deck_name'])}", '', f"🧩 بونس ساخت دک: {isolate('+' + str(synergy['score']))}"]
    lines.extend('• ' + reason for reason in synergy['reasons'])
    if not synergy['reasons']:
        lines.append('فعلاً بدون بونس')
    if deck.get('victory_slogan'):
        lines.extend(['', '💬 ' + isolate(deck['victory_slogan'])])
    caption = '\n'.join(lines)
    try:
        if not callable(getattr(context.bot, 'send_photo', None)):
            raise ValueError('photo_unavailable')
        items = [{'name': card.name, 'rarity': str(getattr(card.rarity, 'value', card.rarity)),
                  'image': await card_art(handler, context, card)} for card in cards]
        raw = await work(context, template)
        image = await work(context, visual.render_deck, items, raw)
        await context.bot.send_photo(chat_id=user_id, photo=BytesIO(image), caption=caption, reply_markup=markup)
        return True
    except Exception:
        logger.warning('Deck preview unavailable; using text preview')
    # Keep a complete useful preview if images or Telegram media fail.
    text = caption + '\n\n' + '\n'.join(isolate(f'{card.name} ({str(getattr(card.rarity, "value", card.rarity)).title()})') for card in cards)
    await context.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
    return False
