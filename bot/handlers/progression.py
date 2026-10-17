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
    if section=='shop':
        from bot.shop_presentation import show_catalog
        return await show_catalog(bot,update,context)
    user=update.effective_user.id
    economy=ProgressionEconomy(bot.db)
    inventory=economy.inventory(user)
    if not inventory.get('ok'):
        await update.effective_message.reply_text(inventory.get('error','خطا'));return
    keyboard=[]
    if section=='cards':
        cards=[card for card in bot.db.get_player_cards(user) if card.origin=='official']
        page=max(0,page);text='کارت را برای ارتقا یا فروش انتخاب کن. فرم‌ها و تعداد نسخه‌ها محفوظ‌اند.'
        for card in cards[page*15:(page+1)*15]:keyboard.append([action_button(context,card.name,{'kind':'card_menu','card_id':card.card_id})])
        navigation=[]
        if page:navigation.append(Button('قبلی',callback_data='v2_cards_'+str(page-1)))
        if (page+1)*15<len(cards):navigation.append(Button('بعدی',callback_data='v2_cards_'+str(page+1)))
        if navigation:keyboard.append(navigation)
    elif section=='missions':
        missions=PlayerRewardsSystem(bot.db).missions(user)
        text='مأموریت‌ها\n'+('\n'.join(item['name']+': '+str(item['current_progress'])+'/'+str(item['target'])+'؛ '+str(item.get('xp_reward',0))+' XP و '+str(item.get('coin_reward',0))+' سکه' for item in missions[:20]) or 'مأموریتی فعال نیست.')
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
            from bot.shop_presentation import show_quote
            return await show_quote(bot,update,context,quote)
        from bot.shop_presentation import show_purchase
        return await show_purchase(bot,update,context,quote)
    elif data.startswith('v2_buy_'):
        from bot.shop_presentation import show_purchase
        return await show_purchase(bot,update,context,economy.purchase(user,data[7:]))
    elif data=='v2_silver_claim':
        from bot.handlers import silver_claim
        if not silver_claim.private_panel(update):return
        return await silver_claim.show_menu(bot,update,context)
    elif data.startswith('v2_action_'):
        action=context.user_data.get('economy_actions',{}).get(data[10:])
        if not action:
            await query.edit_message_text('پیش‌نمایش منقضی شده؛ دوباره منو را باز کن.');return
        kind=action['kind'];card=action.get('card_id')
        if kind in ('silver_craft','silver_use'):
            from bot.handlers import silver_claim
            if not silver_claim.private_panel(update):return
            return await silver_claim.handle_action(bot,update,context,action)
        if kind=='card_menu':
            counts=__import__('systems.card_inventory_system',fromlist=['CardInventorySystem']).CardInventorySystem(bot.db).counts(user,card)
            keyboard=[]
            details=[]
            for target in ('epic','legend'):
                preview=economy.preview_upgrade(user,card,target)
                details.append(target+': '+str(preview.get('error') or (str(preview['required'])+' نسخه + '+str(preview['upgrade_cards_required'])+' کارت ارتقا')))
                if preview.get('ok'):
                    keyboard.append([action_button(context,'ارتقا به '+target+': '+str(preview['required'])+' نسخه + '+str(preview['upgrade_cards_required'])+' کارت ارتقا؛ '+str(preview['xp'])+' XP',{'kind':'upgrade','card_id':card,'target':target,'config_version':preview['config_version'],'request_key':'tg-upgrade:'+uuid.uuid4().hex})])
            for rarity,count in counts.items():
                preview=economy.sell_preview(user,card,rarity)
                if preview.get('ok'):keyboard.append([action_button(context,'فروش یک '+rarity+' از '+str(count)+' نسخه: '+str(preview['price'])+' سکه',{'kind':'sell','card_id':card,'rarity':rarity,'config_version':preview['config_version'],'request_key':'tg-sell:'+uuid.uuid4().hex})])
            keyboard.append([Button('🔙 کارت‌ها',callback_data='v2_cards_0')])
            await query.edit_message_text('تأیید ارتقا یا فروش؛ عملیات نسخه‌های انتخاب‌شده را مصرف می‌کند.\n'+'\n'.join(details),reply_markup=InlineKeyboardMarkup(keyboard));return
        if kind=='upgrade':
            result=economy.upgrade(user,card,action['target'],action['request_key'],action['config_version'])
            if result.get('ok'):
                from bot.card_reward_presentation import send_upgrade_cards
                from bot.deck_reports import isolate
                target=result.get('target', action['target'])
                source='normal' if target=='epic' else 'epic'
                if not result.get('replayed'):
                    await send_upgrade_cards(bot,update,context,card,source,target)
                definition=bot.db.get_card_by_id_for_rarity(card,target)
                text=('✨ '+isolate(definition.name if definition else card)+' ارتقا پیدا کرد!\n'
                      +isolate(source.title()+' → '+target.title())+'\n⭐ '
                      +isolate('+'+str(result.get('xp',0))+' XP'))
                if result.get('new_level',1)>result.get('old_level',1):
                    text+='\n⬆️ '+isolate('Level '+str(result['new_level']))
                await query.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[Button('🔙 کارت‌ها',callback_data='v2_cards_0')]]))
                return
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
