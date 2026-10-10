"""Telegram entry points for the shared Phase 2 economy."""
import uuid
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
from systems.progression_config import enabled
from systems.progression_economy import ProgressionEconomy
from systems.player_rewards_system import PlayerRewardsSystem

LABELS={'upgrade_card':'کارت ارتقا','silver_ticket':'Silver Ticket','deck_slot':'ظرفیت دک','refill':'پرکردن قلب‌ها','permanent_heart':'قلب دائمی'}


def action_button(context,title,action):
    token=uuid.uuid4().hex
    actions=context.user_data.setdefault('economy_actions',{})
    if len(actions)>100:actions.clear()
    actions[token]=action
    return Button(title,callback_data='v2_action_'+token)


async def show_menu(bot,update,context,section='shop',page=0):
    user=update.effective_user.id
    economy=ProgressionEconomy(bot.db)
    inventory=economy.inventory(user)
    if not inventory.get('ok'):
        await update.effective_message.reply_text(inventory.get('error','خطا'));return
    keyboard=[]
    if section=='shop':
        text='🛒 فروشگاه\nقیمت هر خرید قبل از تأیید نمایش داده می‌شود.\n'
        text+=' · '.join(LABELS.get(key,key)+': '+str(value) for key,value in inventory['items'].items())
        for item in inventory['shop']:
            keyboard.append([Button(LABELS[item],callback_data='v2_quote_'+item)])
        keyboard.extend([[Button('🎟 Silver Claim',callback_data='v2_silver_claim')],[Button('ارتقا و فروش کارت',callback_data='v2_cards_0')],[Button('مأموریت‌ها',callback_data='v2_missions')]])
    elif section=='cards':
        cards=[card for card in bot.db.get_player_cards(user) if card.origin=='official']
        page=max(0,page);text='کارت را برای ارتقا یا فروش انتخاب کن. فرم‌ها و تعداد نسخه‌ها محفوظ‌اند.'
        for card in cards[page*15:(page+1)*15]:keyboard.append([action_button(context,card.name,{'kind':'card_menu','card_id':card.card_id})])
        navigation=[]
        if page:navigation.append(Button('قبلی',callback_data='v2_cards_'+str(page-1)))
        if (page+1)*15<len(cards):navigation.append(Button('بعدی',callback_data='v2_cards_'+str(page+1)))
        if navigation:keyboard.append(navigation)
    elif section=='missions':
        missions=PlayerRewardsSystem(bot.db).missions(user)
        text='مأموریت‌ها\n'+('\n'.join(item['name']+': '+str(item['current_progress'])+'/'+str(item['target']) for item in missions[:20]) or 'مأموریتی فعال نیست.')
        for item in missions[:20]:
            if item['can_claim']:keyboard.append([action_button(context,'دریافت '+item['name'],{'kind':'mission','mission_id':item['mission_id']})])
    keyboard.append([Button('🔙 منوی اصلی',callback_data='back_to_main')])
    await update.callback_query.edit_message_text(text,reply_markup=InlineKeyboardMarkup(keyboard))


async def handle(bot,update,context):
    query=update.callback_query
    await query.answer()
    if not enabled(bot.db):
        await query.edit_message_text('اقتصاد جدید فعال نیست.');return
    user=query.from_user.id;data=query.data;economy=ProgressionEconomy(bot.db)
    if data=='v2_shop':return await show_menu(bot,update,context)
    if data.startswith('v2_cards_'):return await show_menu(bot,update,context,'cards',int(data[9:]))
    if data=='v2_missions':return await show_menu(bot,update,context,'missions')
    if data.startswith('v2_quote_'):
        quote=economy.quote(user,data[9:])
        if quote.get('ok'):
            keyboard=[[Button('تأیید خرید',callback_data='v2_buy_'+quote['quote_id'])],[Button('انصراف',callback_data='v2_shop')]]
            await query.edit_message_text('قیمت: '+str(quote['price'])+' سکه؛ تأیید می‌کنی؟',reply_markup=InlineKeyboardMarkup(keyboard));return
        result=quote
    elif data.startswith('v2_buy_'):result=economy.purchase(user,data[7:])
    elif data=='v2_silver_claim':result=economy.claim(user,'silver','tg-silver:'+query.id)
    elif data.startswith('v2_action_'):
        action=context.user_data.get('economy_actions',{}).get(data[10:])
        if not action:
            await query.edit_message_text('پیش‌نمایش منقضی شده؛ دوباره منو را باز کن.');return
        kind=action['kind'];card=action.get('card_id')
        if kind=='card_menu':
            counts=__import__('systems.card_inventory_system',fromlist=['CardInventorySystem']).CardInventorySystem(bot.db).counts(user,card)
            keyboard=[]
            for target in ('epic','legend'):
                preview=economy.preview_upgrade(user,card,target)
                if preview.get('ok'):
                    keyboard.append([action_button(context,'ارتقا به '+target+': '+str(preview['required'])+' نسخه + '+str(preview['upgrade_cards_required'])+' کارت ارتقا؛ '+str(preview['xp'])+' XP',{'kind':'upgrade','card_id':card,'target':target,'config_version':preview['config_version'],'request_key':'tg-upgrade:'+uuid.uuid4().hex})])
            for rarity,count in counts.items():
                preview=economy.sell_preview(user,card,rarity)
                if preview.get('ok'):keyboard.append([action_button(context,'فروش یک '+rarity+' از '+str(count)+' نسخه: '+str(preview['price'])+' سکه',{'kind':'sell','card_id':card,'rarity':rarity,'config_version':preview['config_version'],'request_key':'tg-sell:'+uuid.uuid4().hex})])
            keyboard.append([Button('🔙 کارت‌ها',callback_data='v2_cards_0')])
            await query.edit_message_text('تأیید ارتقا یا فروش؛ عملیات نسخه‌های انتخاب‌شده را مصرف می‌کند.',reply_markup=InlineKeyboardMarkup(keyboard));return
        if kind=='upgrade':result=economy.upgrade(user,card,action['target'],action['request_key'],action['config_version'])
        elif kind=='sell':result=economy.sell(user,card,action['rarity'],action['request_key'],action['config_version'])
        elif kind=='mission':result=PlayerRewardsSystem(bot.db).claim_mission(user,action['mission_id'])
        else:result={'ok':False,'error':'عملیات نامعتبر'}
    else:return
    if result.get('ok'):
        text='✅ انجام شد.'
        if result.get('card_id'):
            card=bot.db.get_card_by_id(result['card_id']);text+='\n'+card.name
        text+='\nXP: '+str(result.get('xp',0))+' · سکه: '+str(result.get('coins',0))
    else:text='انجام نشد: '+result.get('error','خطا')
    await query.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[Button('🔙 فروشگاه',callback_data='v2_shop')]]))
