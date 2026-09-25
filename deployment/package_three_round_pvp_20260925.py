"""Package the audited Mini App PvP files and hashes for the VPS release."""
import hashlib
import json
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'frontend/game/dist'
INDEX = (DIST / 'index.html').read_text(encoding='utf-8')
asset_names = re.findall(r'/miniapp-assets/(assets/[^"\s]+)', INDEX)
paths = [
    'systems/mini_three_round_system.py',
    'web/miniapp_api.py',
    'frontend/game/src/api.ts',
    'frontend/game/src/main.ts',
    'tests/test_mini_three_round_api.py',
    'deployment/deploy_three_round_pvp_20260925.py',
    'deployment/smoke_three_round_pvp_20260925.py',
    'frontend/game/dist/index.html',
]
paths += ['frontend/game/dist/' + name for name in asset_names]
paths = list(dict.fromkeys(paths))
manifest = {
    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for name in paths
}
manifest_path = ROOT / 'deployment/THREE_ROUND_PVP_20260925_MANIFEST.json'
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
artifact = ROOT / 'deployment/artifacts/telbattle-three-round-pvp-20260925.tar.gz'
artifact.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(artifact, 'w:gz') as archive:
    for name in paths:
        archive.add(ROOT / name, arcname=name)
print(artifact.relative_to(ROOT))
print(manifest_path.relative_to(ROOT))
