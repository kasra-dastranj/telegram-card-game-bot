import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, ChatMemberLeft, ChatMemberMember, ChatMemberAdministrator, ChatMemberUpdated, Update, User
from telegram.error import Forbidden
from telegram.ext import ChatMemberHandler

from bot.group_welcome import WELCOME, handle
from tests.test_easy_presentation import scene


def arrival(old=None, new=None, chat_type='supergroup', chat_id=-100):
    user = User(99, 'Test bot', True, username='LocalTestBot')
    return Update(50, my_chat_member=ChatMemberUpdated(
        Chat(chat_id, chat_type), User(1, 'Owner', False), datetime.now(timezone.utc),
        old or ChatMemberLeft(user), new or ChatMemberMember(user)))


def test_real_my_chat_member_handler_welcomes_once_across_restart_and_readd(scene):
    bot, _, context, _ = scene
    context.bot.username = 'LocalTestBot'
    context.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=500))
    routes = []
    bot.setup_handlers(SimpleNamespace(add_handler=routes.append))
    handler = next(route for route in routes if isinstance(route, ChatMemberHandler))
    event = arrival()
    assert handler.check_update(event)
    assert handler.chat_member_types == ChatMemberHandler.MY_CHAT_MEMBER
    asyncio.run(handler.callback(event, context))
    sent = context.bot.send_message.await_args.kwargs
    assert sent['chat_id'] == -100 and sent['text'] == WELCOME
    assert sent['reply_markup'].inline_keyboard[0][0].url == 'https://t.me/LocalTestBot?start=group'
    # A fresh bot facade and context still see the persistent group receipt.
    asyncio.run(handle(SimpleNamespace(db=bot.db), arrival(), context))
    asyncio.run(handle(bot, arrival(chat_id=-200), context))
    assert context.bot.send_message.await_count == 2


@pytest.mark.parametrize('kind', ['promotion', 'departure', 'private', 'channel', 'other_member'])
def test_welcome_ignores_permission_changes_departures_and_non_group_events(scene, kind):
    bot, _, context, _ = scene
    user = User(99, 'Test bot', True)
    if kind == 'promotion':
        event = arrival(old=ChatMemberMember(user), new=ChatMemberAdministrator(
            user=user, can_be_edited=False, is_anonymous=False, can_manage_chat=True,
            can_delete_messages=True, can_manage_video_chats=True, can_restrict_members=True,
            can_promote_members=True, can_change_info=True, can_invite_users=True))
    elif kind == 'departure':
        event = arrival(old=ChatMemberMember(user), new=ChatMemberLeft(user))
    elif kind == 'other_member':
        event = Update(51, chat_member=arrival().my_chat_member)
    else:
        event = arrival(chat_type=kind)
    asyncio.run(handle(bot, event, context))
    context.bot.send_message.assert_not_awaited()


def test_failed_send_does_not_hide_first_welcome(scene):
    bot, _, context, _ = scene
    context.bot.username = 'LocalTestBot'
    context.bot.send_message = AsyncMock(side_effect=Forbidden('offline test'))
    with pytest.raises(Forbidden):
        asyncio.run(handle(bot, arrival(), context))
    context.bot.send_message.side_effect = None
    context.bot.send_message.return_value = SimpleNamespace(message_id=501)
    asyncio.run(handle(bot, arrival(), context))
    asyncio.run(handle(bot, arrival(), context))
    assert context.bot.send_message.await_count == 2
