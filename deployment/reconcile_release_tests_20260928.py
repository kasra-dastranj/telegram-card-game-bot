"""Make the staged release's test files match this release manifest exactly."""

from __future__ import annotations

import json
from pathlib import Path


RELEASE = Path("/opt/telbattle/releases/20260928-progression-economy-v1")
MANIFEST = RELEASE / "deployment/PROGRESSION_20260928_MANIFEST.json"


def main() -> None:
    expected = {name for name in json.loads(MANIFEST.read_text(encoding="utf-8"))
                if name.startswith("tests/") and name.endswith(".py")}
    if not expected:
        raise RuntimeError("release has no packaged tests")
    removed = []
    for path in (RELEASE / "tests").rglob("*.py"):
        relative = path.relative_to(RELEASE).as_posix()
        if relative not in expected:
            path.unlink()
            removed.append(relative)
    print("Packaged tests:", len(expected), "Stale tests removed:", removed)


if __name__ == "__main__":
    main()
