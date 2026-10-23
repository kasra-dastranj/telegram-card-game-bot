"""Introduce the game on the bot's first successful group arrival."""
import json
import sqlite3
from contextlib import closing

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


WELCOME = (
    '🎴 TelBattle به گروهتون رسید!\n\n'
    'قهرمان‌های فیلم‌ها، سریال‌ها و بازی‌ها اینجا روبه‌روی هم قرار می‌گیرن؛ '
    'کارت جمع کنین، دک بچینین و رفیقاتون رو به نبرد دعوت کنین! ⚔️\n\n'
    '🚀 برای شروع، از دکمهٔ زیر ربات رو توی پیوی استارت کنین؛ '
    'بعد توی گروه بنویسین «بتل مبارزه».\n'
    '📖 راهنمای بازی: «بتل راهنما»\n\n'
    '🛡 برای اینکه همهٔ قابلیت‌های ربات درست کار کنن، بهتره ادمینش کنین.'
)


def present(member):
    return member.status in ('member', 'administrator', 'creator') or (
        member.status == 'restricted' and member.is_member)


async def handle(bot, update, context):
    change = update.my_chat_member
    if not change or change.chat.type not in ('group', 'supergroup'):
        return
    if present(change.old_chat_member) or not present(change.new_chat_member):
        return
    key = 'group_welcome:' + str(change.chat.id)
    with closing(sqlite3.connect(bot.db.db_path)) as conn:
        if conn.execute('SELECT 1 FROM foundation_settings WHERE key=?', (key,)).fetchone():
            return
    # Use the running bot's username so test/staging bots get their own link.
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(
        '🚀 استارت ربات و ورود به بازی', url=f'https://t.me/{context.bot.username}?start=group')]])
    sent = await context.bot.send_message(chat_id=change.chat.id, text=WELCOME,
                                          reply_markup=markup, parse_mode=None)
    # A rejected send must not mark the introduction as delivered. The normal
    # Application processes updates sequentially; no lock is held over network IO.
    with closing(sqlite3.connect(bot.db.db_path)) as conn, conn:
        conn.execute('INSERT OR IGNORE INTO foundation_settings(key,value_json) VALUES (?,?)',
                     (key, json.dumps({'message_id': sent.message_id})))
