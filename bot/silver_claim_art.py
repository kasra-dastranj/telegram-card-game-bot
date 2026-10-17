"""A small native Silver Claim illustration, without external assets or fonts."""
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def _label(image, text, center, scale, color):
    font = ImageFont.load_default(size=scale * 10)
    bounds = font.getbbox(text)
    layer = Image.new('RGBA', (bounds[2] + 2, bounds[3] - bounds[1] + 2))
    ImageDraw.Draw(layer).text((1, 1 - bounds[1]), text, fill=color, font=font)
    image.paste(layer, (center[0] - layer.width // 2, center[1] - layer.height // 2), layer)


@lru_cache(maxsize=1)
def _png():
    image = Image.new('RGB', (800, 500), '#101a2d')
    draw = ImageDraw.Draw(image)
    for y in range(500):
        glow = max(0, 1 - abs(y - 245) / 260)
        draw.line((0, y, 799, y), fill=(16 + int(9 * glow), 26 + int(13 * glow), 45 + int(20 * glow)))
    draw.rounded_rectangle((101, 115, 719, 401), radius=28, fill='#090f1e')
    # Silver foil gradient inside a rounded ticket silhouette.
    foil = Image.new('RGB', image.size)
    foil_draw = ImageDraw.Draw(foil)
    for y in range(98, 385):
        shine = max(0, 1 - abs(y - 164) / 220)
        tone = 145 + int(105 * shine)
        foil_draw.line((90, y, 710, y), fill=(tone - 8, tone - 3, tone))
    mask = Image.new('L', image.size)
    ImageDraw.Draw(mask).rounded_rectangle((90, 98, 710, 385), radius=26, fill=255)
    image.paste(foil, mask=mask)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((105, 113, 695, 370), radius=18, outline='#f3f7ff', width=2)
    for x in (90, 710):
        draw.ellipse((x - 20, 222, x + 20, 262), fill='#18263d')
    for y in range(128, 355, 18):
        draw.line((560, y, 560, y + 8), fill='#7e8a9b', width=2)
    draw.polygon([(610, 197), (645, 232), (610, 277), (575, 232)], fill='#465870', outline='#f5f8ff')
    draw.line((575, 232, 645, 232), fill='#b5c6de', width=2)
    draw.line((610, 197, 599, 232, 610, 277, 621, 232, 610, 197), fill='#dbe6f5', width=2)
    _label(image, 'TELBATTLE', (320, 163), 2, '#52637b')
    _label(image, 'SILVER', (320, 230), 6, '#192940')
    _label(image, 'CLAIM', (320, 294), 4, '#3e5068')
    _label(image, 'YOUR NEXT EPIC', (400, 441), 2, '#9baecb')
    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def silver_claim_picture():
    picture = BytesIO(_png())
    picture.name = 'silver-claim.png'
    return picture
