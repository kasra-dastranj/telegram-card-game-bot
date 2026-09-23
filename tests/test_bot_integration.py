"""Small, side-effect-free checks for the Telegram bot composition."""

from bot.handlers.battle import BattleHandlersMixin
from bot.handlers.shop import ShopHandlersMixin
from bot.main import TelegramCardBot


def test_bot_composes_primary_handler_mixins():
    assert issubclass(TelegramCardBot, BattleHandlersMixin)
    assert issubclass(TelegramCardBot, ShopHandlersMixin)


def test_bot_exposes_current_phase_two_handlers():
    for handler in ("mission_claim_handler", "skins_menu_handler", "arena_pick_handler"):
        assert callable(getattr(TelegramCardBot, handler, None)), handler
