"""Import and wiring smoke tests for optional systems.

This used to be a script that called ``sys.exit`` during pytest collection.
Keeping it as normal pytest tests makes failures actionable and lets the suite
collect completely.
"""

from systems.card_missions_system import CardMissionsSystem
from systems.rare_cards_system import RareCardsSystem
from systems.risk_mode_system import RiskModeSystem
from systems.skins_system import SkinsSystem
from systems.tier_decay_system import TierDecaySystem
from telegram_bot import TelegramCardBot


def test_phase_two_systems_are_importable():
    assert all((TierDecaySystem, CardMissionsSystem, RareCardsSystem, SkinsSystem, RiskModeSystem))


def test_current_bot_handler_contract_is_present():
    for handler in ("mission_claim_handler", "skins_menu_handler"):
        assert hasattr(TelegramCardBot, handler), handler
