"""Build and verify a bounded release archive; no configuration or database files."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

REPOSITORY = "kasra-dastranj/telegram-card-game-bot"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
ROOT_FILES = {"telegram_bot.py", "game_core.py", "config_loader.py", "requirements.txt", "card_dialogs.json"}
CODE_DIRS = {"bot", "core", "systems", "web", "migrations"}


def allowed_path(name):
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or str(path) != name or ".." in path.parts:
        return False
    if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
        return False
    if name in ROOT_FILES or name in {"data/card_dialogs.json", "data/generated_card_content.json"}:
        return True
    if path.parts[0] in CODE_DIRS:
        return path.suffix == ".py" or (path.parts[0] == "web" and len(path.parts) == 2 and path.suffix == ".html")
    return name == "frontend/game/dist/index.html" or (
        name.startswith("frontend/game/dist/assets/") and path.suffix in {".js", ".css", ".woff", ".woff2", ".ttf"}
    )


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(archive, sha, run_id=None):
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("invalid source SHA or archive size")
    with tarfile.open(str(archive), "r:gz") as tar:
        members, expanded = [], 0
        for item in tar:
            expanded += item.size
            members.append(item)
            if len(members) > 10000 or expanded > MAX_EXPANDED:
                raise ValueError("archive limits exceeded")
        names = [item.name for item in members]
        if len(names) != len(set(names)) or any(not item.isfile() or item.size < 0 for item in members):
            raise ValueError("duplicate or non-regular archive member")
        if "RELEASE.json" not in names or tar.getmember("RELEASE.json").size > 2 * 1024 * 1024:
            raise ValueError("missing or oversized release manifest")
        manifest = json.load(tar.extractfile("RELEASE.json"))
        if (manifest.get("schema") != 1 or manifest.get("repository") != REPOSITORY
                or manifest.get("source_sha") != sha or manifest.get("database_policy") != "no-change"):
            raise ValueError("release identity or database policy mismatch")
        if run_id is not None and str(manifest.get("run_id")) != str(run_id):
            raise ValueError("release belongs to another Actions run")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(names) != set(files) | {"RELEASE.json"}:
            raise ValueError("archive and manifest file sets differ")
        required = {"telegram_bot.py", "game_core.py", "requirements.txt", "core/database.py",
                    "bot/main.py",
                    "web/admin_wsgi.py", "web/miniapp_api.py", "web/card_management.html", "frontend/game/dist/index.html"}
        if not required <= set(files):
            raise ValueError("required runtime files missing")
        for member in members:
            if member.name == "RELEASE.json":
                continue
            if not allowed_path(member.name) or digest(tar.extractfile(member).read()) != files[member.name]:
                raise ValueError("file policy or hash mismatch: " + member.name)
    return manifest


def build(root, output, sha, run_id, attempt):
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    if actual != sha:
        raise ValueError("checkout SHA differs from requested source")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=str(root)).decode("utf-8").split("\0")
    files = {name: (root / name).read_bytes() for name in tracked if name and allowed_path(name)
             and not name.startswith("frontend/game/dist/")}
    # Refuse changed tracked runtime files, even when called from a dirty checkout.
    for name, content in files.items():
        original = subprocess.check_output(["git", "show", sha + ":" + name], cwd=str(root))
        if content != original or (root / name).is_symlink():
            raise ValueError("runtime file differs from Git: " + name)
    dist = root / "frontend/game/dist"
    for path in dist.rglob("*"):
        name = path.relative_to(root).as_posix()
        if allowed_path(name) and path.is_file():
            if path.is_symlink():
                raise ValueError("frontend symlink refused")
            files[name] = path.read_bytes()
    manifest = {"schema": 1, "repository": REPOSITORY, "source_sha": sha, "run_id": str(run_id),
                "run_attempt": str(attempt), "database_policy": "no-change",
                "python": (root / ".python-version").read_text().strip(),
                "server_python": (root / ".server-python-version").read_text().strip(),
                "node": (root / ".node-version").read_text().strip(),
                "files": {name: digest(content) for name, content in sorted(files.items())}}
    files["RELEASE.json"] = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "telbattle-release.tar.gz"
    with tarfile.open(str(archive), "w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name, content in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(content), 0o644, 0
            tar.addfile(info, io.BytesIO(content))
    verify(archive, sha, run_id)
    (output / "telbattle-release.sha256").write_text(digest(archive.read_bytes()) + "\n", encoding="ascii")
    (output / "RELEASE.json").write_bytes(files["RELEASE.json"])
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["build", "verify"])
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", default="1")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("release-artifact"))
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    result = build(args.root, args.output, args.sha, args.run_id, args.attempt) if args.operation == "build" else verify(args.archive, args.sha, args.run_id)
    print(json.dumps({"source_sha": result["source_sha"], "files": len(result["files"]), "database_policy": result["database_policy"]}))


if __name__ == "__main__":
    main()
