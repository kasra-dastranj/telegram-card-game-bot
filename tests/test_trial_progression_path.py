"""A fresh tester can earn the first coin upgrade through ordinary wins."""

import sqlite3

from core.database import DatabaseManager
from core.models import Card, CardRarity
from scripts.configure_trial_progression import TRIAL_PRESETS
from systems.card_missions_system import CardMissionsSystem
from systems.card_upgrade_system import CardUpgradeSystem
from systems.level_rewards_system import LevelRewardsSystem
from systems.match_rewards_system import MatchRewardsSystem
from systems.mode_access_system import ModeAccessSystem


def test_trial_first_upgrade_without_manual_coin_grant(tmp_path):
    db = DatabaseManager(str(tmp_path / "trial.db"))
    db.get_or_create_player(101)
    db.add_card(Card("hero", "Hero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    db.add_card_to_player(101, "hero")
    assert CardMissionsSystem(db).create_mission("hero", "total_wins", 3)
    for level, coins in TRIAL_PRESETS["tester-v1"]["level_coins"]:
        LevelRewardsSystem(db).set_coin_rule(level, coins)
    for mode, level in TRIAL_PRESETS["tester-v1"]["mode_levels"]:
        ModeAccessSystem(db).set_min_level(mode, level)
    gates = ModeAccessSystem(db)
    assert gates.check(101, "quick")[0]
    assert not gates.check(101, "mini_three_round")[0]
    assert not gates.check(101, "easy")[0]
    for match_number in range(10):
        with sqlite3.connect(db.db_path) as conn:
            MatchRewardsSystem.award(conn, f"trial-win-{match_number}", "quick", {
                101: {"result": "win", "xp": 10, "score": 10, "card_id": "hero"},
            })
    assert db.get_or_create_progression(101)["level"] == 2
    assert db.get_or_create_player(101).coins == 100
    assert gates.check(101, "mini_three_round")[0]
    upgrade = CardUpgradeSystem(db).upgrade(101, "hero", "normal_to_epic")
    assert upgrade["ok"] and upgrade["coins"] == 0
    assert db.get_or_create_progression(101)["total_xp"] == 115
    claim = CardMissionsSystem(db).claim_mission_reward(101, "hero")
    assert claim["success"] and claim["xp_gained"] == 30
    assert db.get_card_by_id_for_player("hero", 101).rarity == CardRarity.LEGEND
