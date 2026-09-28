"""Bot and Mini App mission claims share one atomic card/XP transition."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from core.database import DatabaseManager
from core.models import Card, CardRarity
from systems.card_inventory_system import CardInventorySystem
from systems.card_missions_system import CardMissionsSystem
from systems.level_rewards_system import LevelRewardsSystem


def test_legacy_mission_claim_grants_legend_xp_and_level_coins_once(tmp_path):
    db = DatabaseManager(str(tmp_path / "mission.db"))
    db.get_or_create_player(101)
    assert db.add_card(Card("hero", "Hero", CardRarity.NORMAL, 40, 40, 40, 40, []))
    assert db.add_card_to_player(101, "hero")
    assert db.set_player_card_rarity_override(101, "hero", "epic")
    missions = CardMissionsSystem(db)
    assert missions.create_mission("hero", "total_wins", 1)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("""INSERT INTO player_card_missions(user_id,card_id,current_progress,completed)
                        VALUES(101,'hero',1,1)""")
        conn.execute("UPDATE player_progression SET total_xp=90 WHERE user_id=101")
    LevelRewardsSystem(db).set_coin_rule(2, 11)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: missions.claim_mission_reward(101, "hero"), range(2)))
    assert sum(result["success"] for result in results) == 1
    assert CardInventorySystem(db).counts(101, "hero") == {"legend": 1}
    assert db.get_or_create_progression(101)["total_xp"] == 120
    assert db.get_or_create_player(101).coins == 11
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT reward_claimed FROM player_card_missions WHERE user_id=101 AND card_id='hero'").fetchone()[0] == 1
