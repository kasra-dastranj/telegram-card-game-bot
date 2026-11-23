"""Private Mini App entry points, using the already configured application URL."""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from telegram import InlineKeyboardButton, WebAppInfo


def button(bot, title='🎨 چهره، قاب و پس‌زمینه', category=None):
    config=getattr(bot,'config',None) or {}
    url=os.getenv('MINIAPP_URL') or config.get('miniapp_url','')
    if not url:return None
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.netloc:return None
    params=dict(parse_qsl(parts.query));params['avatar']='1'
    if category in ('frame','background'):params['avatar_shop']=category
    url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params),parts.fragment))
    return InlineKeyboardButton(title,web_app=WebAppInfo(url=url))
