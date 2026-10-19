"""Owner-authored group attacks. Stored in the existing versioned JSON namespace."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone

STATS=('power','speed','iq','popularity')
PREFIX='group-attacks:'
NUMBER_LABELS={'gap_minutes':'فاصلهٔ حمله‌ها به دقیقه','start_hour':'ساعت شروع','end_hour':'ساعت پایان',
               'user_daily_limit':'سقف ورود روزانهٔ هر حساب','choice_seconds':'مهلت انتخاب به ثانیه',
               'weight':'وزن انتخاب تصادفی','min_active':'حداقل بازیکنان فعال امروز گروه',
               'max_active':'حداکثر بازیکنان فعال امروز گروه','duration_minutes':'مدت حمله به دقیقه',
               'death_after':'تعداد برد برای خروج دائمی دشمن'}


def read(conn,key,default=None):
    row=conn.execute('SELECT value_json FROM foundation_settings WHERE key=?',(PREFIX+key,)).fetchone()
    return json.loads(row[0]) if row else copy.deepcopy(default)


def write(conn,key,value):
    conn.execute('INSERT INTO foundation_settings(key,value_json) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',
                 (PREFIX+key,json.dumps(value,ensure_ascii=False,separators=(',',':'))))


def remove(conn,key):
    conn.execute('DELETE FROM foundation_settings WHERE key=?',(PREFIX+key,))


def records(conn,prefix):
    prefix=PREFIX+prefix
    return [(key[len(PREFIX):],json.loads(value)) for key,value in conn.execute(
        'SELECT key,value_json FROM foundation_settings WHERE key>=? AND key<? ORDER BY key',(prefix,prefix+'\uffff'))]


def defaults():
    return {'revision':0,'enabled':True,'gap_minutes':180,'start_hour':9,'end_hour':24,
            'user_daily_limit':4,'choice_seconds':60,
            'test_schedule':{'chat_id':0,'until':''},
            'frequency':[{'min_active':4,'max_events':2},{'min_active':12,'max_events':4}],
            'attacks':[]}


def example():
    return {'id':'big-masoud','title':'حملهٔ بیگ مسعود','enabled':False,'weight':1,
            'min_active':4,'max_active':0,'duration_minutes':180,'death_after':3,
            'enemies':[{'card_id':'','rarity':'normal','name':'بیگ مسعود',
                        'stats':dict.fromkeys(STATS,50),'card_type':'POWER_TYPE','sticker_file_id':'','use_custom_stats':False}],
            'win':{'coins':20,'xp':10,'cards':[]},'loss':{'coins':10,'hearts':0},
            'death_reward':{'coins':50,'xp':20,'cards':[]},
            'dialogues':{'intro':['بیگ مسعود ریخته تو محله! کی جلوش درمیاد؟'],
                         'win':['دفعهٔ بعد جیباتونو پر کنین! 😏'],
                         'loss':['فعلاً می‌رم محله‌های دیگه، ولی بازم برمی‌گردم!'],
                         'death':['بیگ مسعود رو از محله بیرون کردین!'],
                         'tie':['این بار حسابمون صاف شد؛ بازم می‌بینمتون.'],
                         'expired':['کسی جلو نیومد؛ فعلاً می‌رم!']}}


def integer(value,low,high,label):
    if type(value) is not int or not low<=value<=high:
        raise ValueError(f'{label} باید عدد صحیح بین {low} و {high} باشد.')


def text(value,limit,label,empty=False):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()):
        raise ValueError('متن نامعتبر: '+label)


def validate_reward(conn,reward):
    if not isinstance(reward,dict) or set(reward)!={'coins','xp','cards'}:raise ValueError('ساختار پاداش نامعتبره.')
    integer(reward['coins'],0,10000,'سکهٔ پاداش');integer(reward['xp'],0,1000,'XP پاداش')
    if not isinstance(reward['cards'],list) or len(reward['cards'])>5:raise ValueError('حداکثر پنج نوع کارت پاداش مجازه.')
    seen=set()
    for card in reward['cards']:
        if not isinstance(card,dict) or set(card)!={'card_id','rarity','quantity'}:raise ValueError('ساختار کارت پاداش نامعتبره.')
        text(card['card_id'],100,'کارت پاداش');integer(card['quantity'],1,10,'تعداد کارت')
        if card['rarity'] not in ('normal','epic','legend','rare'):raise ValueError('فرم کارت پاداش نامعتبره.')
        identity=(card['card_id'],card['rarity'])
        if identity in seen:raise ValueError('کارت پاداش تکراریه.')
        seen.add(identity)
        row=conn.execute("SELECT rarity FROM cards WHERE card_id=? AND origin='official'",(card['card_id'],)).fetchone()
        if not row:raise ValueError('پاداش باید کارت رسمیِ موجود باشه.')
        if row[0]!=card['rarity'] and not conn.execute('SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?',(card['card_id'],card['rarity'])).fetchone():
            raise ValueError('فرم کارت پاداش آماده نیست.')
        has_rare=bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='rare_cards_info'").fetchone())
        if card['rarity']=='rare' and (row[0]!='rare' or not has_rare or not conn.execute('SELECT 1 FROM rare_cards_info WHERE card_id=?',(card['card_id'],)).fetchone()):
            raise ValueError('Rare باید عرضهٔ محدود رسمی داشته باشه.')


def validate(conn,value):
    value=copy.deepcopy(value)
    if not isinstance(value,dict) or set(value)!=set(defaults()):raise ValueError('ساختار تنظیمات حمله نامعتبره.')
    integer(value['revision'],0,2**31,'نسخه')
    if type(value['enabled']) is not bool:raise ValueError('فعال‌بودن باید بله/خیر باشه.')
    test=value['test_schedule']
    if not isinstance(test,dict) or set(test)!={'chat_id','until'}:raise ValueError('تنظیم گروه تست نامعتبره.')
    integer(test['chat_id'],-(2**52),0,'شناسهٔ گروه تست؛ صفر یعنی خاموش')
    if test['chat_id']==0:
        if test['until']!='':raise ValueError('برای خاموش‌کردن تست، زمان پایان را هم خالی کن.')
    else:
        try:
            until=datetime.fromisoformat(test['until'])
            if until.tzinfo is None or until.utcoffset() is None:raise ValueError()
            if (until-datetime.now(timezone.utc)).total_seconds()>24*3600:raise ValueError()
        except (TypeError,ValueError):raise ValueError('پایان تست باید زمان دارای منطقهٔ زمانی و حداکثر ۲۴ ساعت بعد باشد.') from None
    for field,low,high in [('gap_minutes',30,1440),('start_hour',0,23),('end_hour',1,24),('user_daily_limit',1,10),('choice_seconds',30,120)]:
        integer(value[field],low,high,NUMBER_LABELS[field])
    if value['start_hour']>=value['end_hour']:raise ValueError('بازهٔ ساعت باید در یک روز و رو به جلو باشه.')
    if not isinstance(value['frequency'],list) or not 1<=len(value['frequency'])<=5:raise ValueError('بازه‌های فعالیت نامعتبرند.')
    last=3
    for tier in value['frequency']:
        if not isinstance(tier,dict) or set(tier)!={'min_active','max_events'}:raise ValueError('بازهٔ فعالیت نامعتبره.')
        integer(tier['min_active'],4,10000,'حداقل بازیکنان فعال امروز گروه در بازهٔ فعالیت');integer(tier['max_events'],1,8,'تعداد حمله')
        if tier['min_active']<=last:raise ValueError('بازه‌های فعالیت باید صعودی باشند.')
        last=tier['min_active']
    if not isinstance(value['attacks'],list) or len(value['attacks'])>100:raise ValueError('حداکثر صد نوع حمله مجازه.')
    ids=set()
    for attack in value['attacks']:
        if not isinstance(attack,dict) or set(attack)!=set(example()):raise ValueError('ساختار حمله نامعتبره.')
        text(attack['id'],40,'شناسه')
        if not re.fullmatch('[a-z][a-z0-9_-]{0,39}',attack['id']) or attack['id'] in ids:raise ValueError('شناسهٔ حمله تکراری یا نامعتبره.')
        ids.add(attack['id']);text(attack['title'],100,'عنوان')
        if type(attack['enabled']) is not bool:raise ValueError('وضعیت حمله نامعتبره.')
        for field,low,high in [('weight',1,100),('min_active',4,10000),('max_active',0,10000),('duration_minutes',5,480),('death_after',0,100)]:
            integer(attack[field],low,high,f'حملهٔ «{attack["title"]}»: {NUMBER_LABELS[field]}')
        if attack['max_active'] and attack['max_active']<attack['min_active']:raise ValueError('سقف فعالیت از حداقل کمتره.')
        enemies=attack['enemies']
        if not isinstance(enemies,list) or not 1<=len(enemies)<=8:raise ValueError('حمله باید یک تا هشت دشمن داشته باشه.')
        if len(enemies)>attack['min_active']:raise ValueError('تعداد دشمن‌ها از حداقل بازیکن‌ها بیشتره.')
        for enemy in enemies:
            if not isinstance(enemy,dict) or set(enemy)!=set(example()['enemies'][0]):raise ValueError('ساختار دشمن نامعتبره.')
            text(enemy['name'],80,'نام دشمن',empty=bool(enemy['card_id']))
            text(enemy['card_id'],100,'شناسهٔ کارت دشمن',empty=True)
            text(enemy['sticker_file_id'],250,'استیکر',empty=True)
            if type(enemy['use_custom_stats']) is not bool:raise ValueError('وضعیت آمار اختصاصی نامعتبره.')
            if enemy['sticker_file_id'] and not re.fullmatch('[A-Za-z0-9_-]+',enemy['sticker_file_id']):raise ValueError('فقط file_id استیکر تلگرام مجازه.')
            if enemy['rarity'] not in ('normal','epic','legend','rare'):raise ValueError('فرم دشمن نامعتبره.')
            if enemy['card_type'] not in ('POWER_TYPE','SPEED_TYPE','IQ_TYPE','POPULARITY_TYPE'):raise ValueError('تایپ دشمن نامعتبره.')
            if not isinstance(enemy['stats'],dict) or set(enemy['stats'])!=set(STATS):raise ValueError('چهار ویژگی دشمن لازمه.')
            for amount in enemy['stats'].values():integer(amount,1,100,'ویژگی دشمن')
            if enemy['card_id']:
                row=conn.execute("SELECT rarity FROM cards WHERE card_id=? AND origin='official'",(enemy['card_id'],)).fetchone()
                if not row or (row[0]!=enemy['rarity'] and not conn.execute('SELECT 1 FROM card_variants WHERE card_id=? AND rarity=?',(enemy['card_id'],enemy['rarity'])).fetchone()):
                    raise ValueError('کارت یا فرم دشمن آماده نیست.')
        validate_reward(conn,attack['win']);validate_reward(conn,attack['death_reward'])
        loss=attack['loss']
        if not isinstance(loss,dict) or set(loss)!={'coins','hearts'}:raise ValueError('ساختار جریمه نامعتبره.')
        integer(loss['coins'],0,500,'سکهٔ جریمه');integer(loss['hearts'],0,5,'قلب جریمه')
        dialogues=attack['dialogues']
        if not isinstance(dialogues,dict) or set(dialogues)!=set(example()['dialogues']):raise ValueError('دیالوگ‌های حمله ناقص‌اند.')
        for lines in dialogues.values():
            if not isinstance(lines,list) or not 1<=len(lines)<=10:raise ValueError('برای هر حالت یک تا ده دیالوگ لازمه.')
            for line in lines:text(line,350,'دیالوگ')
    if len(json.dumps(value,ensure_ascii=False).encode('utf8'))>512000:raise ValueError('فهرست بیش از حد بزرگه.')
    return value


def catalog_in(conn):
    value=read(conn,'catalog',defaults())
    # Catalogs written before test scheduling remain valid without a migration.
    value.setdefault('test_schedule',{'chat_id':0,'until':''})
    return value


class CatalogConflict(ValueError):pass


def save_in(conn,value,actor):
    if not isinstance(actor,str) or not actor.strip():raise ValueError('شناسهٔ مدیر لازمه.')
    value=validate(conn,value)
    if value['revision']!=catalog_in(conn)['revision']:raise CatalogConflict('فهرست عوض شده؛ دوباره بارگذاری کن.')
    value['revision']+=1
    write(conn,'catalog',value)
    write(conn,'audit:'+str(value['revision']),{'actor':actor,'at':datetime.now(timezone.utc).isoformat(),'catalog':value})
    return value
