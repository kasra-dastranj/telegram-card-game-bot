import sqlite3
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.database import DatabaseManager
from systems.game_mode_system import GameModeSystem
from systems.mode_access_system import ModeAccessSystem
from systems.risk_mode_system import RiskModeSystem, RiskTable


def test_mode_rules_apply_to_creation_and_join_on_server(tmp_path):
    db = DatabaseManager(str(tmp_path / "modes.sqlite"))
    for uid in (1, 2):
        db.get_or_create_player(uid)
    access = ModeAccessSystem(db)
    modes = GameModeSystem(db)

    assert access.min_level("easy") == 1
    assert access.min_level("risk") == 7
    access.set_min_level("easy", 5)
    with pytest.raises(ValueError, match="Level 5"):
        modes.create_easy_lobby(1, -100, 1)

    db.update_progression(1, level=5)
    request = modes.create_easy_lobby(1, -100, 1)
    allowed, reason, state = modes.join_easy_lobby(request["request_id"], 2)
    assert not allowed and "Level 5" in reason
    assert state["players"] == [1]
    db.update_progression(2, level=5)
    assert modes.join_easy_lobby(request["request_id"], 2)[0]


def test_risk_uses_same_configured_level_rule(tmp_path):
    db = DatabaseManager(str(tmp_path / "risk.sqlite"))
    db.get_or_create_player(1)
    db.update_progression(1, level=7)
    access = ModeAccessSystem(db)
    access.set_min_level("risk", 8)
    allowed, reason = RiskModeSystem(db).can_enter_risk(1, RiskTable.TABLE_50)
    assert not allowed and "Level 8" in reason
    db.update_progression(1, level=8)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE players SET coins=300 WHERE user_id=1")
    assert RiskModeSystem(db).can_enter_risk(1, RiskTable.TABLE_50)[0]


def test_quick_and_deck_invites_obey_trial_level(tmp_path):
    db = DatabaseManager(str(tmp_path / "invites.sqlite"))
    for uid in (1, 2):
        db.get_or_create_player(uid)
    access = ModeAccessSystem(db)
    access.set_min_level("quick", 2)
    modes = GameModeSystem(db)
    with pytest.raises(ValueError, match="Level 2"):
        modes.create_invite(1, "quick", "normal")
    db.update_progression(1, level=2)
    request = modes.create_group_challenge(1, "quick", "normal", -100)
    allowed, reason, _ = modes.accept_request(request["request_id"], 2)
    assert not allowed and "Level 2" in reason
    db.update_progression(2, level=2)
    assert modes.accept_request(request["request_id"], 2)[0]


def test_trial_rule_cli_previews_then_applies_both_rules(tmp_path):
    db = DatabaseManager(str(tmp_path / "rules.sqlite"))
    script = Path(__file__).resolve().parents[1] / "scripts" / "configure_trial_progression.py"
    command = [sys.executable, str(script), "--db", db.db_path,
               "--level-coins", "2:9", "--mode-level", "easy:4"]
    preview = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(preview.stdout)["applied"] is False
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT coins FROM level_coin_rules WHERE level=2").fetchone() is None
    applied = subprocess.run([*command, "--apply"], capture_output=True, text=True, check=True)
    assert json.loads(applied.stdout)["applied"] is True
    assert ModeAccessSystem(db).min_level("easy") == 4
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT coins FROM level_coin_rules WHERE level=2").fetchone()[0] == 9
