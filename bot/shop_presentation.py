"""Shop boards stay above text controls, preserving all existing menu callbacks."""
from io import BytesIO
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup, InputMediaPhoto

from bot.battle_visual_delivery import ROOT, limited_cache, read_bitmap, work
from bot.battle_visuals import resources
from bot.deck_reports import isolate
from bot import shop_visuals

logger = logging.getLogger(__name__)


def number(value):
    return isolate(format(value, ','))


def title(item):
    emoji, name, _, _ = shop_visuals.product(item)
    return emoji + ' ' + isolate(name)


def display_name(bot, item):
    if item.startswith('skin:'):
        getter = getattr(getattr(bot,'skins',None),'get_skin',None)
        if callable(getter):
            skin = getter(item[5:])
            if skin:
                return str(skin['name'])
    return shop_visuals.product(item)[1]


def back_buttons():
    return InlineKeyboardMarkup([[Button('🛍 بازم خرید دارم', callback_data='v2_shop')],
                                 [Button('🔙 منوی اصلی', callback_data='back_to_main')]])


def catalog_text(catalog):
    items = catalog['items']
    text = ('🛒 چی برای نبرد بعدیت لازم داری؟\n'
            '💰 سکه‌هات: ' + number(catalog['coins']) + '\n'
            '🧪 کارت ارتقا: ' + number(items.get('upgrade_card',0)) +
            ' · 🎟 Silver Ticket: ' + number(items.get('silver_ticket',0)))
    if not catalog['products']:
        text += '\nفعلاً کالایی برای خرید نداریم؛ بعداً سر بزن.'
    return text


def catalog_buttons(catalog):
    rows = []
    for entry in catalog['products']:
        price = number(entry['price'])+' سکه' if entry['price'] is not None else 'فعلاً بسته‌ست'
        if not entry['available']:
            price = shop_visuals.STATUSES.get(entry['error_code'], 'فعلاً بسته‌ست')
        rows.append([Button(title(entry['item'])+' · '+price, callback_data='v2_quote_'+entry['item'])])
    rows.extend([[Button('🎴 ارتقا و فروش کارت',callback_data='v2_cards_0')],
                 [Button('🎴 Ability cards · خرید و موجودی',callback_data='v2_abilities')],
                 [Button('🔙 منوی اصلی',callback_data='back_to_main')]])
    return InlineKeyboardMarkup(rows)


def background():
    root = Path(os.environ.get('TELBATTLE_BATTLE_MEDIA_DIR', ROOT/'assets/battle_visuals/overrides'))
    for extension in ('.webp','.png','.jpg','.jpeg'):
        try:
            return read_bitmap(root/('shop-template'+extension))
        except (OSError, ValueError):
            pass
    return resources()['shop/template']


async def text_panel(update, text, markup):
    query = update.callback_query
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=None)
    except Exception:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=None)


async def show(update, context, model, text, markup):
    query = update.callback_query
    message = getattr(query, 'message', None)
    chat_id, control_id = getattr(message,'chat_id',None), getattr(message,'message_id',None)
    telegram_bot = getattr(context,'bot',None)
    # Test doubles / clients without media support keep the full text interface.
    capable = (type(chat_id) is int and type(control_id) is int
               and callable(getattr(telegram_bot,'edit_message_media',None))
               and callable(getattr(message,'reply_photo',None))
               and callable(getattr(message,'reply_text',None)))
    if capable:
        key = (chat_id, control_id, query.from_user.id)
        boards = limited_cache(context,'_shop_boards',128)
        try:
            raw = await work(context,background)
            image = await work(context,shop_visuals.render,model,raw)
            if key in boards:
                await telegram_bot.edit_message_media(chat_id=chat_id, message_id=boards[key],
                    media=InputMediaPhoto(BytesIO(image)))
                await text_panel(update,text,markup)
            else:
                picture = await message.reply_photo(BytesIO(image))
                controls = await message.reply_text(text,reply_markup=markup,parse_mode=None)
                if type(picture.message_id) is int and type(controls.message_id) is int:
                    boards[(chat_id,controls.message_id,query.from_user.id)] = picture.message_id
                # Keep all callbacks on text messages: main/card/mission navigation
                # needs no changes to support shop photos.
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    logger.warning('Could not retire previous shop controls')
            return
        except Exception:
            boards.pop(key,None)
            logger.warning('Shop image unavailable; keeping text controls')
    await text_panel(update,text,markup)


async def show_catalog(bot,update,context):
    from bot.shop_access import require_private
    if not await require_private(update):return
    from systems.progression_economy import ProgressionEconomy
    catalog = ProgressionEconomy(bot.db).shop_catalog(update.effective_user.id)
    if not catalog.get('ok'):
        return await text_panel(update,'فعلاً فروشگاه باز نمی‌شه؛ یه کم دیگه امتحان کن.',back_buttons())
    return await show(update,context,dict(catalog,screen='catalog'),catalog_text(catalog),catalog_buttons(catalog))


async def show_quote(bot,update,context,quote,back_callback='v2_shop'):
    player = bot.db.get_or_create_player(update.effective_user.id)
    item = quote['item']
    name = display_name(bot,item)
    description = shop_visuals.product(item)[2]
    balance = int(getattr(player,'coins',0))
    text = (shop_visuals.product(item)[0]+' '+isolate(name)+'\n'+description+'\n\n💰 هزینه: '+number(quote['price'])+' سکه\n'
            '🪙 سکه‌هات: '+number(balance))
    if balance < quote['price']:
        text += '\n'+number(quote['price']-balance)+' سکه دیگه لازم داری.'
    else:
        text += '\nبردارمش برات؟'
    text += '\n⏳ این قیمت تا ۵ دقیقه معتبره.'
    rows = [[Button('✅ آره، می‌خرم',callback_data='v2_buy_'+quote['quote_id'])]] if balance>=quote['price'] else []
    rows.append([Button('🔙 نه، برگردیم',callback_data=back_callback)])
    markup = InlineKeyboardMarkup(rows)
    model = {'screen':'quote','item':item,'name':name,'coins':balance,'price':quote['price'],'note':description}
    return await show(update,context,model,text,markup)


async def show_purchase(bot,update,context,result):
    from systems.progression_economy import ProgressionEconomy
    if not result.get('ok'):
        from bot.player_messages import error_text
        return await text_panel(update,'⚠️ '+error_text(result),back_buttons())
    player = bot.db.get_or_create_player(update.effective_user.id)
    item = result['item']
    name = display_name(bot,item)
    amount = result['coins_spent']
    text = ('این خرید قبلاً ثبت شده؛ دوباره سکه کم نشد.' if result.get('replayed') else '✨ مبارکه، مال تو شد!')
    text += '\n'+shop_visuals.product(item)[0]+' '+isolate(name)+'\n💰 هزینهٔ این خرید: '+number(amount)+' سکه\n🪙 سکه‌های باقی‌مونده: '+number(player.coins)
    inventory = ProgressionEconomy(bot.db).inventory(update.effective_user.id)
    note = ''
    if item.startswith('ability:'):
        abilities = ProgressionEconomy(bot.db).ability_catalog(update.effective_user.id)
        if abilities.get('ok'):
            entry = next(p for p in abilities['products'] if p['key']==item[8:])
            note = 'حالا '+str(entry['quantity'])+' تا داری'
    if inventory.get('ok'):
        if item in ('silver_ticket','upgrade_card'):
            note = 'حالا '+str(inventory['items'].get(item,0))+' تا داری'
        elif item=='deck_slot':
            note = 'ظرفیت دک‌هات: '+str(inventory['capacity']['slots'])
        elif item in ('refill','permanent_heart'):
            note = 'قلب‌هات: '+str(player.hearts)+' / '+str(inventory['capacity']['max_hearts'])
    if note:
        text += '\n'+isolate(note)
    model = {'screen':'receipt','item':item,'name':name,'coins':player.coins,'price':amount,'note':note}
    markup = (InlineKeyboardMarkup([[Button('🎴 ابیلیتی‌ها و موجودی',callback_data='v2_abilities')],
                                   [Button('🔙 فروشگاه',callback_data='v2_shop')]])
              if item.startswith('ability:') else back_buttons())
    return await show(update,context,model,text,markup)


async def show_abilities(bot,update,context):
    from systems.progression_economy import ProgressionEconomy
    from systems.game_mode_system import ABILITY_DEFINITIONS
    catalog=ProgressionEconomy(bot.db).ability_catalog(update.effective_user.id)
    if not catalog.get('ok'):
        from bot.player_messages import error_text
        return await text_panel(update,error_text(catalog),back_buttons())
    text=('🎴 ابیلیتی‌هات\n💰 سکه‌هات: '+number(catalog['coins'])+
          '\nموجودی Quick و مینی‌اپ مشترکه؛ قفل ویژگی فقط توی Quick کار می‌کنه.\n')
    rows=[]
    for entry in catalog['products']:
        name=ABILITY_DEFINITIONS[entry['key']]['title']
        text+='\n'+isolate(name)+' · موجودی: '+number(entry['quantity'])
        if entry['enabled']:
            rows.append([Button(name+' · '+number(entry['price'])+' سکه',callback_data='v2_quote_ability:'+entry['key'])])
        else:text+=' · فروش فعلاً بسته‌ست'
    rows.append([Button('🔙 فروشگاه',callback_data='v2_shop')])
    return await text_panel(update,text,InlineKeyboardMarkup(rows))
