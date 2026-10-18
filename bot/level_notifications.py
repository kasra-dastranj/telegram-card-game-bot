"""Private level celebrations for all XP writers, including Mini App matches."""
import logging
from core.display_text import isolate
from systems.level_notices import pending,finish

logger=logging.getLogger(__name__)
REWARDS={'coins':'💰 سکه','slots':'🗂 جای دک','hearts':'❤️ ظرفیت قلب',
         'silver_claims':'🎁 سیلور کلیم'}
MODES={'easy':'Easy Mode','deck':'Deck Mode','risk':'Risk Mode'}


def text(notice):
    lines=['🎉 لولت رفت بالا!','✨ '+isolate('Level '+str(notice['level']))]
    prizes=[REWARDS[key]+': '+isolate(amount) for key,amount in notice['rewards'].items()
            if key in REWARDS and amount>0]
    if prizes:lines+=['','این‌ها به حسابت اضافه شدن:']+prizes
    unlocks=[MODES[key] for key in notice.get('unlocks',[]) if key in MODES]
    if unlocks:lines+=['','🎮 باز شد: '+isolate(' · '.join(unlocks))]
    lines+=['','بریم برای لول بعدی! 💪']
    return '\n'.join(lines)


async def deliver(bot,context):
    if context.bot_data.get('_level_notices_busy'):return
    context.bot_data['_level_notices_busy']=True
    try:
        for key,notice in pending(bot.db):
            try:
                await context.bot.send_message(chat_id=notice['user_id'],text=text(notice),parse_mode=None)
            except Exception:
                logger.warning('Level notification delivery deferred')
                finish(bot.db,key,False)
            else:
                finish(bot.db,key,True)
    finally:
        context.bot_data.pop('_level_notices_busy',None)
