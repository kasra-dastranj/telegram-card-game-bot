"""Package the daily Quick reward and Telegram card Ability fixes."""

import hashlib
import json
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend/game/dist"
asset_names = re.findall(r'/miniapp-assets/(assets/[^"\s]+)', (DIST / "index.html").read_text(encoding="utf-8"))
paths = [
    "bot/handlers/basic.py",
    "bot/handlers/battle.py",
    "bot/handlers/pvp.py",
    "core/database.py",
    "core/game_logic.py",
    "systems/player_hub_system.py",
    "systems/player_rewards_system.py",
    "web/miniapp_api.py",
    "frontend/game/src/api.ts",
    "frontend/game/src/main.ts",
    "deployment/deploy_ability_fixes_20260925.py",
    "deployment/smoke_ability_fixes_20260925.py",
    "frontend/game/dist/index.html",
]
paths += ["frontend/game/dist/" + name for name in asset_names]
paths = list(dict.fromkeys(paths))
manifest = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
manifest_path = ROOT / "deployment/ABILITY_FIXES_20260925_MANIFEST.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
artifact = ROOT / "deployment/artifacts/telbattle-ability-fixes-20260925.tar.gz"
artifact.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(artifact, "w:gz") as archive:
    for name in paths:
        archive.add(ROOT / name, arcname=name)
print(artifact.relative_to(ROOT))
print(manifest_path.relative_to(ROOT))
