"""Deterministic arena and result images. No game rules, network calls or player writes."""
from functools import lru_cache
from io import BytesIO
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bot.battle_visual_assets import resources
from bot._vendor.arabic_reshaper import ArabicReshaper
from bot._vendor.bidi.algorithm import get_display

RESHAPER = ArabicReshaper(configuration={'language': 'Farsi'})
COLORS = {'normal': '#63d6a3', 'epic': '#c589fa', 'legend': '#ffdc7b', 'rare': '#69c8ff'}
STATS = {'power': 'قدرت', 'speed': 'سرعت', 'iq': 'هوش', 'popularity': 'محبوبیت'}
TYPES = {'power': 'قدرتی', 'speed': 'سرعتی', 'iq': 'هوشی', 'popularity': 'محبوبیتی'}
TRAITS = {'god': 'خدا', 'monster': 'هیولا', 'hero': 'قهرمان', 'warrior': 'جنگجو',
          'villain': 'شرور', 'assassin': 'آدمکش', 'funny': 'کمدی', 'detective': 'کارآگاه',
          'mage': 'جادوگر', 'leader': 'رهبر'}


def clean(value, limit=300):
    # Telegram isolates/overrides and emoji have no place in the bitmap text shaper.
    return ''.join(c for c in str(value)[:limit] if unicodedata.category(c) not in ('Cc', 'Cf', 'So')
                   or c in '\u200c\u200d').strip()


def display(value):
    text = clean(value)
    # Give signed numbers an LTR anchor while the Persian sentence stays RTL.
    text = re.sub(r'(?<!\w)[+-]\d+(?:\.\d+)?', lambda match: '\u200e' + match[0] + '\u200e', text)
    return get_display(RESHAPER.reshape(text))


@lru_cache(maxsize=24)
def font(size):
    return ImageFont.truetype(BytesIO(resources()['font.ttf']), size, layout_engine=ImageFont.Layout.BASIC)


def label(image, text, box, size=34, color='#f4f7fc', minimum=18):
    x, y, width, height = box
    text = clean(text)
    draw = ImageDraw.Draw(image)
    for current in range(size, minimum - 1, -2):
        face = font(current)
        shaped = display(text)
        bounds = draw.textbbox((0, 0), shaped, font=face)
        if bounds[2] - bounds[0] <= width and bounds[3] - bounds[1] <= height:
            break
    else:
        while len(text) > 1 and draw.textlength(display(text + '…'), font=face) > width:
            text = text[:-1]
        shaped = display(text + '…')
        bounds = draw.textbbox((0, 0), shaped, font=face)
    draw.text((x + (width - bounds[2] + bounds[0]) / 2, y + (height - bounds[3] + bounds[1]) / 2 - bounds[1]),
              shaped, font=face, fill=color)


def wrapped(text, width, size):
    lines = []
    for paragraph in str(text).splitlines():
        words = clean(paragraph, 2000).split()
        current = ''
        for word in words:
            candidate = (current + ' ' + word).strip()
            if current and font(size).getlength(display(candidate)) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def safe_bitmap(raw):
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError('bitmap_size_limit')
    with Image.open(BytesIO(raw)) as original:
        if original.width * original.height > 16_000_000:
            raise ValueError('bitmap_pixel_limit')
        return ImageOps.exif_transpose(original).convert('RGB')


def background(arena_id):
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,40}', str(arena_id)):
        arena_id = 'default'
    return resources().get('arena/' + arena_id, resources()['arena/default'])


def canvas(raw, size):
    image = ImageOps.fit(safe_bitmap(raw), size, method=Image.Resampling.LANCZOS).convert('RGBA')
    image = Image.alpha_composite(image, Image.new('RGBA', size, (4, 10, 21, 82)))
    return image.convert('RGB')


def panel(image, box, outline='#41546e'):
    layer = Image.new('RGBA', image.size)
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=24, fill=(9, 18, 32, 220), outline=outline, width=2)
    image.paste(layer, mask=layer.getchannel('A'))


def encode(image):
    stream = BytesIO()
    image.save(stream, 'JPEG', quality=87, optimize=True)
    return stream.getvalue()


def rule_lines(arena, mode):
    rules = arena.get('rules') or arena
    if mode == 'quick':
        lines = []
        for effect in arena.get('effects', []):
            lines.append(f"کارت‌های {TYPES.get(effect.get('card_type'), effect.get('card_type', ''))}: "
                         f"{STATS.get(effect['stat'], effect['stat'])} {int(effect['delta']):+d}")
        disabled = arena.get('disabled_stats', rules.get('disabled_stats', []))
        if disabled:
            lines.append('ویژگی غیرفعال: ' + '، '.join(STATS.get(s, s) for s in disabled))
        if not arena.get('abilities_enabled', rules.get('abilities_enabled', True)):
            lines.append('Ability غیرفعاله')
        if not arena.get('passives_enabled', rules.get('passives_enabled', True)):
            lines.append('Passive غیرفعاله')
        return lines or ['این زمین تغییری روی ویژگی‌ها نداره']
    lines = ['اولویت تریت‌ها:']
    for index, tier in enumerate(arena.get('trait_ranks', rules.get('trait_ranks', [])), 1):
        lines.append(f"T{index}: " + ' / '.join(TRAITS.get(str(trait), str(trait)) for trait in tier))
    if mode == 'deck':
        if arena.get('stat_tiebreak_enabled', rules.get('stat_tiebreak_enabled', True)):
            stat = arena.get('compare_stat', rules.get('compare_stat', 'popularity'))
            lines.append('معیار دوم: ' + STATS.get(stat, stat) + ' بیشتر')
        else:
            lines.append('معیار عددی دوم غیرفعاله')
    else:
        lines.append(f"بونس {STATS.get(arena.get('boost_stat'), arena.get('boost_stat', ''))}: +{arena.get('boost_amount', 0)}")
    return lines


def render_arena(arena, mode, raw):
    lines = wrapped('\n'.join(rule_lines(arena, mode)), 950, 34)
    height = max(800, 470 + len(lines) * 52)
    image = canvas(raw, (1200, height))
    panel(image, (65, 75, 1135, height - 60))
    label(image, mode.replace('_', ' ').upper() + ' / TELBATTLE', (110, 100, 980, 42), 26, '#a4b8d3')
    label(image, arena.get('name_fa') or arena.get('name') or 'زمین بازی', (100, 163, 1000, 88), 56)
    ImageDraw.Draw(image).line((230, 273, 970, 273), fill='#c8a86a', width=3)
    for index, line in enumerate(lines):
        label(image, line, (125, 303 + index * 52, 950, 48), 34)
    label(image, 'زمین مشخص شد؛ آماده‌ای؟', (150, height - 122, 900, 40), 26, '#b9c8db')
    return encode(image)


def card_tile(image, card, art, box):
    x, y, width, height = box
    color = COLORS.get(card.get('rarity'), '#a4b8d3')
    panel(image, (x, y, x + width, y + height), color)
    if art:
        try:
            bitmap = ImageOps.contain(safe_bitmap(art), (width - 16, height - 84), Image.Resampling.LANCZOS)
            image.paste(bitmap, (int(x + (width - bitmap.width) / 2), int(y + 8 + (height - 84 - bitmap.height) / 2)))
        except (OSError, ValueError):
            art = None
    if not art:
        label(image, 'TELBATTLE', (x + 12, y + 28, width - 24, height - 160), min(36, width // 7), '#687d98')
        label(image, 'تصویر کارت موجود نیست', (x + 12, y + height // 2 - 10, width - 24, 45), 23, '#a4b8d3')
    label(image, card.get('name') or 'انتخاب نشد', (x + 8, y + height - 79, width - 16, 42), 29)
    label(image, str(card.get('rarity') or '').title(), (x + 8, y + height - 39, width - 16, 32), 23, color)


def render_result(model, raw):
    deck = model['mode'] == 'deck'
    height = 1080 if deck else 1020
    image = canvas(raw, (1200, height))
    panel(image, (25, 25, 1175, 192))
    label(image, model['mode'].replace('_', ' ').upper() + ' / TELBATTLE', (90, 40, 1020, 40), 25, '#b0c4de')
    winner = model.get('winner_name')
    title = ('برنده: ' + winner) if winner else 'این دست مساوی شد!'
    if model.get('forfeit'):
        title = ('برد با پایان مهلت: ' + winner) if winner else 'مهلت انتخاب تموم شد'
    label(image, title, (75, 82, 1050, 65), 48, '#ffdd8b')
    label(image, model.get('arena_name', 'زمین بازی'), (75, 145, 1050, 35), 27, '#c2d2e8')
    for side, player in enumerate(model['players']):
        start = 35 + side * 600
        panel(image, (start, 203, start + 530, 263))
        label(image, player['name'], (start, 205, 530, 53), 38, '#8cc9ff' if side == 0 else '#ffb28c')
        cards = player.get('cards') or [{'name': 'انتخاب نشد', 'rarity': ''}]
        if deck:
            for index, card in enumerate(cards[:3]):
                card_tile(image, card, card.get('image'), (start + index * 181, 275, 169, 270))
        else:
            card = cards[0]
            card_tile(image, card, card.get('image'), (start + 95, 275, 340, 405))
        score_y = 564 if deck else 698
        panel(image, (start, score_y, start + 530, score_y + (178 if player.get('equation') else 128)))
        label(image, 'امتیاز نهایی', (start + 12, score_y + 5, 506, 38), 27, '#b8c8df')
        score = str(player['score']) if player.get('score') is not None else '—'
        label(image, score, (start + 12, score_y + 43, 506, 78), 63)
        if player.get('equation'):
            label(image, player['equation'], (start + 12, score_y + 130, 506, 43), 28)
        reward = player.get('reward') or {}
        if reward:
            reward_y = 903 if deck else 870
            panel(image, (start, reward_y - 8, start + 530, reward_y + 87))
            label(image, f"XP +{reward.get('xp', 0)}   |   Score +{reward.get('score', 0)}",
                  (start, reward_y, 530, 44), 26, '#c5dfb8')
            if reward.get('hearts_lost'):
                label(image, f"قلب از دست رفته: {reward['hearts_lost']}", (start, reward_y + 45, 530, 38), 27, '#ffb4b4')
    if deck:
        for index, line in enumerate(model.get('round_lines', [])[:3]):
            label(image, line, (100, 750 + index * 48, 1000, 45), 29)
    label(image, 'حساب‌وکتاب کامل توی «مشاهده جزئیات»', (90, height - 64, 1020, 38), 25, '#b5c6dd')
    return encode(image)


def render_deck(cards, raw):
    """A reusable three-slot frame; the deck name/bonuses stay in its caption."""
    image = canvas(raw, (1200, 760))
    label(image, 'TELBATTLE / DECK', (100, 26, 1000, 55), 34, '#e2cc99')
    for index in range(3):
        card = cards[index] if index < len(cards) else {'name': 'جای کارت', 'rarity': ''}
        x = 65 + index * 370
        card_tile(image, card, card.get('image'), (x, 100, 330, 560))
    label(image, 'سه مبارز، یه تیم', (100, 682, 1000, 47), 30, '#c3d0e4')
    return encode(image)
