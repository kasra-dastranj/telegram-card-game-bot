"""Package the reviewed local progression release without local secrets or data."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(tempfile.gettempdir()) / "telbattle-progression-20260928-v1.tar.gz"
ALLOWED = ("bot/", "core/", "systems/", "web/", "frontend/game/src/",
           "scripts/", "tests/", "docs/", "deployment/")
TEST_IMAGES = ("assets/card_images/shrek.png", "assets/card_images/john_wick.png")


def git_paths(*args: str) -> set[str]:
    output = subprocess.check_output(["git", *args, "-z"], cwd=ROOT)
    return {item.decode("utf-8") for item in output.split(b"\0") if item}


def main() -> None:
    paths = git_paths("diff", "--name-only") | git_paths("ls-files", "--others", "--exclude-standard")
    paths = {path for path in paths if path.startswith(ALLOWED)}
    paths |= git_paths("ls-files", "tests")
    paths.update(TEST_IMAGES)
    paths |= {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "frontend/game/dist").rglob("*") if path.is_file()
    }
    manifest = {}
    with tarfile.open(OUTPUT, "w:gz") as archive:
        for relative in sorted(paths):
            source = ROOT / relative
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"unexpected release path: {relative}")
            data = source.read_bytes()
            manifest[relative] = hashlib.sha256(data).hexdigest()
            info = tarfile.TarInfo(relative)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
        data = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        info = tarfile.TarInfo("deployment/PROGRESSION_20260928_MANIFEST.json")
        info.size = len(data)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(data))
    print(json.dumps({"output": str(OUTPUT), "files": len(manifest),
                      "size_bytes": OUTPUT.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
