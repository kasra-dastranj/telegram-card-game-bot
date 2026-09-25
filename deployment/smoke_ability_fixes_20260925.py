"""Exercise both fixed Ability flows on a staged release and isolated DB."""

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


class SmokeDirectory(tempfile.TemporaryDirectory):
    def cleanup(self):
        try:
            super().cleanup()
        except PermissionError:
            # Windows can retain a SQLite file handle until interpreter exit.
            pass


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with SmokeDirectory(prefix="telbattle-ability-smoke-") as scratch:
    os.environ["DATABASE_PATH"] = str(Path(scratch) / "game.db")
    from bot.handlers.battle import BattleHandlersMixin
    from core.database import DatabaseManager
    from core.game_logic import GameLogic
    from core.models import Card, CardRarity
    from systems.game_mode_system import GameModeSystem
    from systems.player_rewards_system import PlayerRewardsSystem

    db = DatabaseManager(os.environ["DATABASE_PATH"])
    for user_id, card_id, card_type in ((101, "speed-smoke", "SPEED_TYPE"),
                                        (202, "power-smoke", "POWER_TYPE")):
        db.get_or_create_player(user_id)
        assert db.add_card(Card(card_id=card_id, name=card_id, rarity=CardRarity.NORMAL,
                                power=80, speed=70, iq=60, popularity=50,
                                abilities=[], card_type=card_type))
    GameModeSystem(db)
    claimed = PlayerRewardsSystem(db).claim_daily(101)
    assert claimed["ok"] and claimed["ability"]["key"]
    assert not GameLogic(db).claim_daily_card_with_ability(101)[0]
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT SUM(quantity) FROM player_ability_inventory WHERE user_id=101").fetchone()[0] == 1
        conn.execute("INSERT OR IGNORE INTO player_cards(user_id,card_id,obtained_at) VALUES (101,'speed-smoke',CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO player_cards(user_id,card_id,obtained_at) VALUES (202,'power-smoke',CURRENT_TIMESTAMP)")
        conn.execute('''INSERT INTO battle_states (
            fight_id,challenger_id,opponent_id,challenger_card_id,opponent_card_id,
            arena,current_round,challenger_used_stats,opponent_used_stats,
            challenger_current_stats,opponent_current_stats,status,created_at
        ) VALUES ('abc12345',101,202,'speed-smoke','power-smoke',
                  'speed_track',1,'[]','[]',?,?,'round_1',CURRENT_TIMESTAMP)''',
                     (json.dumps({"power": 80, "speed": 70, "iq": 60, "popularity": 50}),
                      json.dumps({"power": 83, "speed": 73, "iq": 63, "popularity": 53})))
    handler = BattleHandlersMixin()
    handler.db = db
    assert handler._activate_r3_ability("abc12345", 101, "peek", {})["peek"]
    assert handler._r3_pending_abilities("abc12345", 1) == ("peek", None)
    print("Staged Python 3.9 Ability smoke passed")
