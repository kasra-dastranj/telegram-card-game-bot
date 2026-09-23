"""Integration checks for the current Phase 2 progression contract."""

from core.database import DatabaseManager
from systems.economy_system import EconomySystem
from systems.fusion_system import FusionSystem
from systems.phase2_systems import LevelSystem, ProgressionDB, TierSystem


def test_phase2_systems_share_the_same_player_database(tmp_path):
    path = str(tmp_path / "phase2.db")
    db = DatabaseManager(path)
    db.get_or_create_player(777777, "integration", "Integration")
    progression = ProgressionDB(path)
    before = progression.get_progression(777777)
    assert before is not None
    success, old_level, new_level = progression.add_xp(777777, 30, "test")
    assert success and old_level == 1 and new_level >= old_level
    success, old_tier, new_tier = progression.add_tp(777777, 25)
    assert success and old_tier and new_tier
    assert LevelSystem.get_level_from_xp(30) >= 1
    assert TierSystem.get_tier_from_tp(progression.get_progression(777777).tier_points)
    assert FusionSystem(db).db is db
    assert EconomySystem(db).db is db
