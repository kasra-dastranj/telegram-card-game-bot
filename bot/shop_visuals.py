"""Native store illustrations and live-data layouts, with bundled Persian font."""
from io import BytesIO

from PIL import Image, ImageDraw

from bot.battle_visuals import canvas, encode, label, panel, resources

PRODUCTS = {
    'upgrade_card': ('🧪', 'کارت ارتقا', 'برای ارتقای کارت‌هات استفاده می‌شه.', '#ba8dfa'),
    'silver_ticket': ('🎟', 'Silver Ticket', 'جمعش کن و از منوی اصلی سیلور کلیم بساز.', '#c7d6ee'),
    'deck_slot': ('🗂', 'جای دک', 'یه جای بیشتر برای ذخیرهٔ دک‌هات.', '#75bdff'),
    'refill': ('💗', 'پرکردن قلب‌ها', 'قلب‌هات تا ظرفیت فعلی پر می‌شن.', '#ff99bb'),
    'permanent_heart': ('❤️', 'قلب دائمی', 'ظرفیت قلب‌هات یکی بیشتر می‌شه.', '#ffca80'),
}
STATUSES = {'hearts_full': 'قلب‌هات پره', 'heart_cap': 'ظرفیتت به سقف رسیده',
            'stock_empty': 'فعلاً ناموجود', 'price_limit': 'فعلاً قابل خرید نیست',
            'heart_policy_unset': 'فعلاً قابل خرید نیست'}


def product(item):
    return PRODUCTS.get(item, ('🎨', 'اسکین کارت' if str(item).startswith('skin:') else str(item),
                               'ظاهر کارتت رو عوض کن.', '#8ad5c1'))


def template_png():
    """Blank replaceable backdrop; no player data or font dependencies."""
    image = Image.new('RGB', (1200, 1000), '#101a30')
    draw = ImageDraw.Draw(image)
    for y in range(1000):
        glow = max(0, 1 - abs(y - 200) / 1000)
        draw.line((0, y, 1199, y), fill=(12 + int(glow * 10), 20 + int(glow * 12), 36 + int(glow * 19)))
    draw.rounded_rectangle((18, 18, 1182, 982), radius=44, outline='#705e42', width=3)
    for x in range(90, 1200, 170):
        draw.line((x, 70, x + 150, 0), fill='#26364a', width=2)
        draw.line((x, 1000, x + 150, 930), fill='#26364a', width=2)
    draw.ellipse((930, -190, 1400, 210), outline='#66563d', width=18)
    draw.ellipse((-190, 800, 210, 1200), outline='#32465f', width=18)
    stream = BytesIO()
    image.save(stream, 'PNG', optimize=True)
    return stream.getvalue()


def icon(image, item, center, scale=1):
    """Geometric merchandise icons; no dependence on an OS emoji font."""
    draw = ImageDraw.Draw(image)
    x, y = center
    def box(a, b, c, d):
        return (int(x+a*scale), int(y+b*scale), int(x+c*scale), int(y+d*scale))
    color = product(item)[3]
    if item == 'silver_ticket':
        draw.rounded_rectangle(box(-88,-45,88,45), radius=int(14*scale), fill='#cbd7e6', outline='#f3f8ff', width=3)
        for offset in (-88, 88):
            draw.ellipse(box(offset-11,-11,offset+11,11), fill='#16243a')
        draw.polygon([(x,y-25*scale),(x+23*scale,y),(x,y+25*scale),(x-23*scale,y)], fill='#617696')
    elif item in ('refill', 'permanent_heart'):
        draw.ellipse(box(-65,-43,1,25), fill=color)
        draw.ellipse(box(-1,-43,65,25), fill=color)
        draw.polygon([(x-62*scale,y+4*scale),(x+62*scale,y+4*scale),(x,y+68*scale)], fill=color)
        draw.line((x-17*scale,y+8*scale,x+17*scale,y+8*scale), fill='#ffffff', width=max(3,int(9*scale)))
        draw.line((x,y-9*scale,x,y+25*scale), fill='#ffffff', width=max(3,int(9*scale)))
        if item == 'refill':
            draw.arc(box(-92,-67,92,90), 10, 290, fill='#fff0f7', width=max(3,int(5*scale)))
    else:
        for offset in (-20, 0, 20) if item == 'deck_slot' else (0,):
            draw.rounded_rectangle(box(-42+offset,-62,42+offset,62), radius=int(10*scale),
                                   fill='#22344e', outline=color, width=max(2,int(4*scale)))
        draw.line((x,y+30*scale,x,y-28*scale), fill=color, width=max(4,int(9*scale)))
        draw.line((x,y-28*scale,x-20*scale,y-6*scale), fill=color, width=max(4,int(9*scale)))
        draw.line((x,y-28*scale,x+20*scale,y-6*scale), fill=color, width=max(4,int(9*scale)))


def render(model, background):
    root = model['screen'] == 'catalog'
    image = canvas(background, (1200, 1000 if root else 820))
    label(image, 'TELBATTLE / SHOP', (70, 35, 1060, 42), 28, '#d1b276')
    title = 'یه چیزی برای نبرد بعدیت بردار!' if root else 'خریدت ثبت شد!' if model['screen'] == 'receipt' else 'این رو برمی‌داری؟'
    label(image, title, (70, 85, 1060, 62), 43)
    label(image, 'سکه‌هات: ' + format(model['coins'], ','), (70, 152, 1060, 48), 33, '#ffdb88')
    if root:
        entries = model['products']
        if not entries:
            label(image, 'فعلاً کالایی برای خرید نداریم؛ بعداً سر بزن.', (100, 400, 1000, 100), 38)
        for index, item in enumerate(entries[:5]):
            column, row = index % 3, index // 3
            x = 55 + column * 370 + (185 if row == 1 else 0)
            y = 235 + row * 335
            entry_id = item['item']
            panel(image, (x, y, x+350, y+312), product(entry_id)[3] if item['available'] else '#536174')
            icon(image, entry_id, (x+175, y+83), .74)
            label(image, product(entry_id)[1], (x+12,y+158,326,48), 34)
            price = format(item['price'], ',') + ' سکه' if item['price'] is not None else '—'
            label(image, price, (x+12,y+214,326,42), 29, '#f4d79d')
            state = STATUSES.get(item.get('error_code'), 'فعلاً قابل خرید نیست') if not item['available'] else (
                'موجودی فروشگاه: '+str(item['stock_remaining']) if item.get('stock_remaining') is not None else 'آمادهٔ خرید')
            label(image, state, (x+12,y+263,326,34), 23, '#a7bdd7')
        items = model.get('items', {})
        footer = 'کارت ارتقا: '+str(items.get('upgrade_card',0))+'   |   Silver Ticket: '+str(items.get('silver_ticket',0))
        label(image, footer, (70, 934, 1060, 40), 27, '#b3c5dc')
    else:
        item = model['item']
        panel(image, (110,235,1090,735), product(item)[3])
        icon(image,item,(600,365),1.25)
        label(image, model.get('name') or product(item)[1], (145,475,910,65), 47)
        label(image, ('هزینه: ' if model['screen']=='receipt' else 'قیمت این خرید: ') + format(model['price'], ',')+' سکه',
              (145,555,910,55), 36, '#ffdb88')
        label(image, model.get('note',''), (145,625,910,70), 29, '#b8cee4')
    return encode(image)
