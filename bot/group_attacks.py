"""Telegram presentation of owner-authored encounters; all mutations live in SQLite."""
import logging
import asyncio
import random
import sqlite3
import time
from contextlib import closing
from datetime import timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as Button,InlineKeyboardMarkup as Markup
from telegram.error import BadRequest
from core.display_text import isolate,ratio,signed
from core.models import Card,CardRarity
from systems.attack_catalog import read,write,remove,records
from systems.group_attacks import GroupAttacks,now_utc,date,effective,STATS

logger=logging.getLogger(__name__)
LABELS={'power':'💪 قدرت','speed':'⚡ سرعت','iq':'🧠 هوش','popularity':'❤️ محبوبیت'}
ERRORS={'attack_closed':'این حمله تموم شده؛ منتظر حملهٔ بعدی باش.',
        'attack_not_found':'این حمله پیدا نشد.', 'attack_slot_taken':'یکی زودتر این دشمن رو انتخاب کرده!',
        'attack_already_joined':'تو سهمت رو از این حمله بازی کردی.',
        'attack_daily_limit':'سهم حمله‌های امروزت تموم شده؛ فردا دوباره بیا.',
        'attack_stake_shortage':'سکه یا قلبت برای جریمهٔ احتمالی کافی نیست؛ چیزی کم نشد.',
        'attack_no_cards':'اول کارت‌های اولیه‌ت رو از /start بگیر.',
        'attack_choice_locked':'این انتخاب قبلاً ثبت شده؛ از آخرین دکمه‌ها ادامه بده.',
        'attack_choice_expired':'وقت این انتخاب تموم شده؛ نتیجه از پنل گروه مشخص می‌شه.',
        'no_alternative_arena':'زمین جایگزین آماده نیست؛ ابیلیتی مصرف نشد.',
        'ability_not_owned':'از این ابیلیتی موجودی نداری.', 'stat_not_allowed':'این ویژگی قابل انتخاب نیست.'}


def engine(bot):return GroupAttacks(bot.db,bot.modes)


async def chat_id_command(update,context):
    chat=update.effective_chat
    if not chat or not update.effective_message:return
    if chat.type not in ('group','supergroup'):
        await update.effective_message.reply_text('دستور /chatid رو داخل همون گروه بفرست.')
        return
    await update.effective_message.reply_text('شناسهٔ این گروه:\n'+isolate(chat.id))


def reward_text(reward):
    parts=[]
    if reward['coins']:parts.append('💰 '+isolate(reward['coins'])+' سکه')
    if reward['xp']:parts.append('⭐ '+signed(reward['xp'],'XP'))
    for card in reward['cards']:
        parts.append('🎴 '+isolate(card.get('name',card['card_id']))+' '+isolate(card['rarity'].title())+' × '+isolate(card['quantity']))
    return ' · '.join(parts) or 'بدون پاداش'


def rules(event):
    attack=event['attack'];loss=attack['loss']
    text=('⚔️ '+isolate(attack['title'])+'\nQuick یک‌راوندی؛ امتیاز = جمع ویژگی تو و دشمن بعد از اثرها.\n\n'
          '🏆 برد: '+reward_text(attack['win'])+'\n')
    text+=('باخت: 💰 '+isolate(loss['coins'])+' سکه · ❤️ '+isolate(loss['hearts'])+' قلب' if loss['coins'] or loss['hearts'] else 'باخت: چیزی ازت کم نمی‌شه.')
    if loss['coins'] or loss['hearts']:text+='\nاین مقدار با تأییدت رزرو می‌شه؛ فقط در باخت نهایی مصرف می‌شه.'
    if len(event['slots'])>1:
        text+='\n\nسهم همهٔ شرکت‌کننده‌ها یکسانه. برد فقط با تکمیل همهٔ نبردها؛ باختِ قطعی حتی قبل از تکمیل حساب می‌شه. حملهٔ ناتمامِ نامشخص بدون پاداش و جریمه بسته می‌شه.'
    if attack['death_after']:
        text+='\n\n☠️ شکست‌های این دشمن در گروه: '+ratio(event['progress']['wins'],attack['death_after'])
        text+='\nجایزهٔ شکست آخر: '+reward_text(attack['death_reward'])
    text+='\n\nهر نفر یک نبرد؛ بعد از تأیید، بی‌پاسخ‌گذاشتن انتخاب‌ها باخت حساب می‌شه.'
    return text


async def member(context,event,user):
    try:
        value=await context.bot.get_chat_member(event['chat_id'],user)
        return value.status in ('creator','administrator','member') or value.status=='restricted' and value.is_member
    except Exception:
        return False


async def offer(bot,update,context,event_id,index):
    event=engine(bot).get(event_id)
    query=update.callback_query;user=update.effective_user.id
    if not event or event['status']!='open' or not 0<=index<len(event['slots']):raise ValueError('attack_closed')
    if not await member(context,event,user):
        if query:await query.answer('برای شرکت باید عضو همین گروه باشی؛ بررسی عضویت انجام نشد.',show_alert=True)
        else:await update.effective_message.reply_text('عضویتت در گروه قابل تأیید نیست؛ از دکمهٔ همان گروه وارد شو.')
        return
    markup=Markup([[Button('⚔️ قبول، می‌جنگم',callback_data=f'ga_join:{event_id}:{index}')]])
    await context.bot.send_message(chat_id=user,text=rules(event),reply_markup=markup,parse_mode=None)
    if query:await query.answer('قوانین و دکمهٔ ورود رو توی پیوی ربات فرستادم.')


async def start(bot,update,context):
    payload=(getattr(context,'args',None) or [''])[0]
    if not payload.startswith('attack_'):return False
    try:
        _,event_id,index=payload.split('_')
        await offer(bot,update,context,event_id,int(index))
    except ValueError as exc:
        await update.effective_message.reply_text(ERRORS.get(str(exc),'این دعوت حمله معتبر نیست.'))
    return True


async def send_snapshot(bot,context,chat,snapshot):
    try:
        if snapshot.get('sticker_file_id'):
            await context.bot.send_sticker(chat_id=chat,sticker=snapshot['sticker_file_id'])
            return True
    except Exception:pass
    if not snapshot.get('card_id'):
        return False  # A standalone NPC must never borrow an unrelated catalog image.
    from bot.card_reward_presentation import send_card_sticker
    card=Card(snapshot.get('card_id') or 'attack-npc',snapshot['name'],CardRarity(snapshot['rarity']),
              *(snapshot['stats'][s] for s in STATS),[],image_path=snapshot.get('image_path',''),card_type=snapshot['card_type'])
    async def send(sticker):return await context.bot.send_sticker(chat_id=chat,sticker=sticker)
    return await send_card_sticker(bot,context,card,send)


async def panel(bot,update,context,event,index,page=0):
    slot=event['slots'][index];query=update.callback_query;user=query.from_user.id
    if slot.get('user')!=user:raise ValueError('attack_choice_locked')
    rows=[]
    if slot['status']!='playing' or event['status']!='open':
        report=slot.get('report',{})
        text=('🏁 نبردت تموم شد!\n'+('🏆 بردی' if slot['status']=='win' else '🤝 مساوی شد' if slot['status']=='tie' else 'حمله بسته شد؛ نتیجهٔ تیم رو ببین.' if slot['status']=='cancelled' else 'دشمن این دست رو برد'))
        if report:text+='\nامتیاز تو: '+isolate(report['score'])+' · دشمن: '+isolate(report['npc_score'])
        if event['status']=='open':text+='\nنتیجهٔ تیم هنوز مشخص نیست؛ پاداش و جریمه در پایان حمله حساب می‌شن.'
        rows=[[Button('📋 نتیجه و حساب حمله',callback_data='ga_detail:'+event['id'])]]
    elif slot['phase']=='card':
        page=max(0,min(page,(len(slot['cards'])-1)//8))
        for number,card_id in enumerate(slot['cards'][page*8:page*8+8],page*8):
            card=bot.db.get_card_by_id_for_player(card_id,user)
            if card:rows.append([Button(card.name+' · '+card.rarity.value.title(),callback_data=f'ga_card:{event["id"]}:{index}:{number}')])
        nav=[]
        if page:nav.append(Button('قبلی',callback_data=f'ga_page:{event["id"]}:{index}:{page-1}'))
        if (page+1)*8<len(slot['cards']):nav.append(Button('بعدی',callback_data=f'ga_page:{event["id"]}:{index}:{page+1}'))
        if nav:rows.append(nav)
        text='🎴 مبارزت رو انتخاب کن'
    elif slot['phase']=='ability':
        for ability in bot.modes.list_player_abilities(user):
            rows.append([Button(ability['title']+' ×'+str(ability['quantity']),callback_data=f'ga_ability:{event["id"]}:{index}:{ability["ability_key"]}')])
        rows.append([Button('رد شو',callback_data=f'ga_ability:{event["id"]}:{index}:skip')])
        text='از کدوم Ability card استفاده می‌کنی؟'
    else:
        values=effective(slot['card'],event['attack']['enemies'][index],slot['arena'])
        for stat in STATS:
            if stat not in slot['arena'].get('disabled_stats',[]):
                rows.append([Button(LABELS[stat]+' · '+str(values[stat]),callback_data=f'ga_stat:{event["id"]}:{index}:{stat}')])
        text='یه ویژگی انتخاب کن ⏳\n(عددها با اثر زمین و Passive محاسبه شدن)'
    if slot['status']=='playing' and event['status']=='open':
        remaining=max(0,int((date(slot['deadline'])-now_utc()).total_seconds()))
        text+='\n⏳ '+isolate(remaining)+' ثانیه وقت داری!'
    await query.edit_message_text(text,reply_markup=Markup(rows),parse_mode=None)


def details_text(event,user):
    receipt=event.get('receipts',{}).get(str(user))
    text='📋 '+isolate(event['attack']['title'])+'\n'
    text+='وضعیت: '+{'open':'در جریان','win':'برد گروه','loss':'برد دشمن','tie':'مساوی','void':'ناتمام؛ بدون پاداش و جریمه'}.get(event['status'],event['status'])
    for enemy,slot in zip(event['attack']['enemies'],event['slots']):
        text+='\n'+isolate(enemy['name'])+': '+{'open':'منتظر مبارز','playing':'در حال نبرد','win':'شکست خورد','loss':'پیروز شد','tie':'مساوی','cancelled':'با پایان حمله بسته شد'}.get(slot['status'],'')
    if receipt:
        text+='\n\nحساب تو: 💰 '+signed(receipt['attack_coins'],'سکه')+' · ⭐ '+signed(receipt.get('xp',0),'XP')
        if receipt['attack_hearts_lost']:text+=' · ❤️ '+signed(-receipt['attack_hearts_lost'],'قلب')
        for card in receipt['cards']:text+='\n'+reward_text({'coins':0,'xp':0,'cards':[card]})
        if receipt['escrow_refunded']:text+='\nرزرو جریمه برگشت.'
        if receipt.get('ability_refunded'):text+='\nابیلیتی مصرف‌شده‌ت هم برگشت.'
    elif str(user) not in event['participants']:text+='\n\nتو در این حمله شرکت نکردی؛ موجودیت تغییری نکرده.'
    return text


async def handle(bot,update,context):
    query=update.callback_query;user=query.from_user.id
    from bot.battle_visual_delivery import limited_cache
    buckets=limited_cache(context,'_attack_clicks',256)
    recent=[t for t in buckets.get(user,[]) if time.monotonic()-t<10]
    if len(recent)>=10:
        await query.answer('یه لحظه صبر کن، بعد دوباره بزن.');return
    buckets[user]=recent+[time.monotonic()]
    try:
        parts=query.data.split(':');action,event_id=parts[:2]
        event=engine(bot).get(event_id)
        if not event:raise ValueError('attack_not_found')
        if action=='ga_offer':
            if query.message.chat_id!=event['chat_id']:raise ValueError('attack_not_found')
            try:return await offer(bot,update,context,event_id,int(parts[2]))
            except Exception as exc:
                if isinstance(exc,ValueError):raise
                username=(await context.bot.get_me()).username
                return await query.answer('اول پیوی ربات رو باز کن، بعد همین دکمه رو دوباره بزن.',url=f'https://t.me/{username}?start=attack_{event_id}_{int(parts[2])}')
        if action=='ga_status':return await query.answer('این نبرد قبلاً انتخاب شده یا تموم شده.',show_alert=True)
        if action=='ga_report':
            if query.message.chat_id!=event['chat_id'] or not await member(context,event,user):raise ValueError('attack_not_found')
            await context.bot.send_message(chat_id=user,text=details_text(event,user),parse_mode=None)
            return await query.answer('جزئیات حسابت رو توی پیوی فرستادم.')
        if query.message.chat_id!=user:raise ValueError('attack_choice_locked')
        if action=='ga_detail':
            await query.answer();return await query.edit_message_text(details_text(event,user),parse_mode=None)
        index=int(parts[2])
        if action=='ga_join':
            if not await member(context,event,user):return await query.answer('عضویتت در گروه تأیید نشد.',show_alert=True)
            if not await bot.is_user_in_channel(user,context):return await bot.send_channel_join_message(update)
            event=engine(bot).join(event_id,index,user,event['chat_id'])
        elif action=='ga_card':
            event=engine(bot).choose_card(event_id,index,user,int(parts[3]))
            await send_snapshot(bot,context,user,event['slots'][index]['card'])
            try:
                from bot.battle_visual_delivery import send_arena
                await send_arena(context,user,event_id,event['slots'][index]['arena'],'quick')
            except Exception:logger.warning('Attack arena media unavailable')
        elif action=='ga_ability':
            event=engine(bot).choose_ability(event_id,index,user,parts[3])
            if parts[3]=='reveal_opponent':
                enemy=event['attack']['enemies'][index]
                await send_snapshot(bot,context,user,enemy)
                await context.bot.send_message(chat_id=user,text=isolate(enemy['name'])+'\n'+' · '.join(LABELS[s]+': '+isolate(enemy['stats'][s]) for s in STATS))
        elif action=='ga_stat':event=engine(bot).choose_stat(event_id,index,user,parts[3])
        elif action!='ga_page':raise ValueError('attack_not_found')
        await query.answer()
        try:await panel(bot,update,context,event,index,int(parts[3]) if action=='ga_page' else 0)
        except BadRequest as exc:
            if 'message is not modified' not in str(exc).lower():raise
    except (ValueError,IndexError) as exc:
        from systems.match_activity import ActiveMatchError,BUSY_MESSAGE
        await query.answer(BUSY_MESSAGE if isinstance(exc,ActiveMatchError) else ERRORS.get(str(exc),'این انتخاب قابل انجام نیست؛ از آخرین پنل ادامه بده.'),show_alert=True)
    except Exception:
        if query.data.startswith(('ga_join:','ga_card:','ga_ability:','ga_stat:')):
            engine(bot).cancel(event_id)  # Never turn a failed private delivery into a paid loss.
        logger.warning('Attack private delivery failed; an unfinished encounter was cancelled safely')
        try:await query.answer('ارسال پیوی انجام نشد؛ ربات رو باز کن و دوباره از گروه وارد شو.',show_alert=True)
        except Exception:pass


def group_panel(event):
    attack=event['attack'];rows=[]
    if event['status']=='open':
        text=event.setdefault('intro',random.choice(attack['dialogues']['intro']))
        text+='\n⏳ فرصت دفاع تا '+isolate(date(event['deadline']).astimezone(ZoneInfo(event['settings']['timezone'])).strftime('%H:%M'))
        text+='\n🎁 سهم هر شرکت‌کننده در برد: '+reward_text(attack['win'])
        loss=attack['loss']
        if loss['coins'] or loss['hearts']:text+='\nباخت: '+isolate(loss['coins'])+' سکه و '+isolate(loss['hearts'])+' قلب؛ فقط شرکت‌کننده‌ها.'
        for index,(enemy,slot) in enumerate(zip(attack['enemies'],event['slots'])):
            label=('⚔️ مبارزه با ' if slot['status']=='open' else '⏳ در حال مبارزه با ' if slot['status']=='playing' else '✅ شکست خورد: ' if slot['status']=='win' else '🤝 مساوی: ' if slot['status']=='tie' else '❌ پیروز شد: ')+enemy['name']
            rows.append([Button(label,callback_data=f'ga_offer:{event["id"]}:{index}' if slot['status']=='open' else 'ga_status:'+event['id'])])
    else:
        key='death' if event.get('killed') else 'loss' if event['status']=='win' else 'win' if event['status']=='loss' else 'tie' if event['status']=='tie' else 'expired'
        text=random.choice(attack['dialogues'][key])
        text+='\n\n'+{'win':'🏆 دفاع موفق بود!','loss':'دشمن این بار برد!','tie':'🤝 حمله مساوی تموم شد.','void':'حمله کامل نشد؛ پاداش و جریمه‌ای حساب نشد.'}[event['status']]
        if event.get('killed'):text+='\n☠️ این دشمن دیگه به این گروه برنمی‌گرده.'
        if event['status']=='win':
            text+='\n🎁 سهم هر شرکت‌کننده: '+reward_text(attack['win'])
            if event.get('killed'):text+='\n🎉 جایزهٔ شکست آخر برای هر نفر: '+reward_text(attack['death_reward'])
        if event['status']=='loss':text+='\nسهم هر شرکت‌کننده: −'+isolate(attack['loss']['coins'])+' سکه · −'+isolate(attack['loss']['hearts'])+' قلب'
        if event['status'] in ('tie','void'):text+='\nرزرو جریمهٔ شرکت‌کننده‌ها برگشت.'
        rows=[[Button('📋 جزئیات و پاداش من',callback_data='ga_report:'+event['id'])]]
    return text,Markup(rows)


async def maintenance(bot,context):
    if context.bot_data.get('_attacks_busy'):return
    context.bot_data['_attacks_busy']=True
    try:
        system=engine(bot);system.tick()
        with closing(sqlite3.connect(bot.db.db_path)) as conn:
            queue=[pair for pair in records(conn,'notice:') if pair[1] is True or date(pair[1]['next_attempt'])<=now_utc()][:4]
        for key,_ in queue:
            event=system.get(key.split(':',1)[1])
            if not event:continue
            delivery=event['delivery'];text,markup=group_panel(event)
            try:
                stage='intro_sticker' if event['status']=='open' else 'final_sticker'
                if not delivery.get(stage):
                    await asyncio.wait_for(send_snapshot(bot,context,event['chat_id'],event['attack']['enemies'][0]),timeout=6);delivery[stage]=True
                    def save_media(conn):
                        current=read(conn,'event:'+event['id']);current['delivery']=delivery;write(conn,'event:'+event['id'],current)
                    system.run(save_media)
                if event['status']=='open' and delivery.get('message_id'):
                    try:await asyncio.wait_for(context.bot.edit_message_text(chat_id=event['chat_id'],message_id=delivery['message_id'],text=text,reply_markup=markup,parse_mode=None),timeout=6)
                    except BadRequest as exc:
                        if 'message is not modified' not in str(exc).lower():raise
                elif event['status']!='open' and delivery.get('final_id'):pass
                else:
                    result=await asyncio.wait_for(context.bot.send_message(chat_id=event['chat_id'],text=text,reply_markup=markup,parse_mode=None),timeout=6)
                    delivery['message_id' if event['status']=='open' else 'final_id']=result.message_id
                if event['status']!='open' and delivery.get('message_id'):
                    try:await asyncio.wait_for(context.bot.edit_message_reply_markup(chat_id=event['chat_id'],message_id=delivery['message_id'],reply_markup=None),timeout=6)
                    except Exception:pass
                def ack(conn):
                    current=read(conn,'event:'+event['id'])
                    current['delivery']=delivery
                    if event.get('intro'):current['intro']=event['intro']
                    write(conn,'event:'+event['id'],current)
                    if current['revision']==event['revision']:remove(conn,key)
                system.run(ack)
            except Exception:
                logger.warning('Attack notification deferred; encounter and receipts remain saved')
                from datetime import timedelta
                system.run(lambda conn:write(conn,key,{'next_attempt':(now_utc()+timedelta(minutes=10)).isoformat()}))
    finally:context.bot_data.pop('_attacks_busy',None)
