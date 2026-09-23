"""Opt-in live Telegram connectivity check.

The default suite is offline. Set RUN_LIVE_TELEGRAM_TESTS=1 explicitly to
contact Telegram and verify the configured bot plus command scopes.
"""

import asyncio
import json
import os

import pytest
from telegram import Bot, BotCommandScopeAllGroupChats


async def _check_live_bot():
    with open("game_config.json", "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    token = os.getenv("BOT_TOKEN") or config["bot_settings"]["token"]
    bot = Bot(token=token)
    me = await bot.get_me()
    default_commands = await bot.get_my_commands()
    group_commands = await bot.get_my_commands(scope=BotCommandScopeAllGroupChats())
    return me, default_commands, group_commands


def test_live_bot_permissions():
    if os.getenv("RUN_LIVE_TELEGRAM_TESTS") != "1":
        pytest.skip("live Telegram check; set RUN_LIVE_TELEGRAM_TESTS=1 to enable")

    me, default_commands, group_commands = asyncio.run(_check_live_bot())
    assert me.id > 0
    assert me.username
    assert isinstance(default_commands, tuple)
    assert isinstance(group_commands, tuple)
