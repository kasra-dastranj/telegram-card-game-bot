"""Release integrity and failure recovery using disposable data and fake services."""
import io
import json
import os
import sqlite3
import subprocess
import shutil
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "deployment/actions"
sys.path.insert(0, str(TOOLS))
import package_release as package
import server as deploy


@pytest.fixture()
def bundle(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    names = ["telegram_bot.py", "game_core.py", "requirements.txt", "core/database.py",
             "bot/main.py", "web/admin_wsgi.py", "web/miniapp_api.py", "web/card_management.html", "data/card_dialogs.json"]
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime", encoding="utf-8")
    for name, value in ((".python-version", "3.11"), (".server-python-version", "3.9.25"), (".node-version", "24.19.0")):
        (root / name).write_text(value, encoding="ascii")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=str(root), check=True)
    subprocess.run(["git", "-c", "user.name=QA", "-c", "user.email=qa@example.invalid", "commit", "-qm", "fixture"], cwd=str(root), check=True)
    dist = root / "frontend/game/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>build</html>")
    (dist / "assets/app.js").write_text("const built = true;")
    (root / ".env").write_text("NEVER_SHIP=test")
    (root / "game_bot.db").write_bytes(b"NEVER_SHIP")
    (dist / "onboarding").mkdir()
    (dist / "onboarding/private.webp").write_bytes(b"NEVER_SHIP")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    output = tmp_path / "artifact"
    package.build(root, output, sha, "42", "1")
    return root, output / "telbattle-release.tar.gz", sha


def rewrite(archive, transform):
    with tarfile.open(str(archive), "r:gz") as tar:
        entries = [(item, tar.extractfile(item).read()) for item in tar.getmembers()]
    with tarfile.open(str(archive), "w:gz") as tar:
        for item, data in transform(entries):
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))


def test_bundle_is_exact_and_excludes_data_and_settings(bundle):
    _, archive, sha = bundle
    manifest = package.verify(archive, sha, "42")
    assert manifest["source_sha"] == sha
    assert "frontend/game/dist/assets/app.js" in manifest["files"]
    assert not any("NEVER_SHIP" in name or name.endswith(".db") or name.startswith(".env") for name in manifest["files"])
    assert "frontend/game/dist/onboarding/private.webp" not in manifest["files"]
    with pytest.raises(ValueError, match="identity"):
        package.verify(archive, "0" * 40, "42")
    with pytest.raises(ValueError, match="another Actions"):
        package.verify(archive, sha, "43")


@pytest.mark.parametrize("attack", ["hash", "duplicate", "symlink", "traversal", "secret"])
def test_archive_tampering_cannot_pass_verification(bundle, attack):
    _, archive, sha = bundle
    def transform(entries):
        if attack == "hash":
            item, _ = next(pair for pair in entries if pair[0].name == "game_core.py")
            return [(member, b"changed" if member is item else content) for member, content in entries]
        if attack == "duplicate":
            return entries + [entries[-1]]
        name = {"symlink": "core/link.py", "traversal": "../escape.py", "secret": ".env"}[attack]
        item = tarfile.TarInfo(name)
        if attack == "symlink":
            item.type, item.linkname = tarfile.SYMTYPE, "/etc/passwd"
        manifest_item, raw = next(pair for pair in entries if pair[0].name == "RELEASE.json")
        manifest = json.loads(raw)
        manifest["files"][name] = package.digest(b"attack")
        return [(member, json.dumps(manifest).encode() if member is manifest_item else content) for member, content in entries] + [(item, b"attack")]
    rewrite(archive, transform)
    with pytest.raises(ValueError):
        package.verify(archive, sha, "42")


def test_dirty_runtime_cannot_be_packaged(bundle, tmp_path):
    root, _, sha = bundle
    (root / "game_core.py").write_text("edited after tests")
    with pytest.raises(ValueError, match="differs from Git"):
        package.build(root, tmp_path / "new", sha, "42", "1")


def test_package_uses_commit_bytes_with_windows_eol_filters(bundle, tmp_path):
    root, _, _ = bundle
    subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=str(root), check=True)
    (root / "web/card_management.html").write_bytes(b"<html>\r\n</html>\r\n")
    subprocess.run(["git", "add", "web/card_management.html"], cwd=str(root), check=True)
    subprocess.run(["git", "-c", "user.name=QA", "-c", "user.email=qa@example.invalid", "commit", "-qm", "eol"], cwd=str(root), check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    output = tmp_path / "canonical"
    package.build(root, output, sha, "42", "1")
    with tarfile.open(str(output / "telbattle-release.tar.gz")) as tar:
        assert tar.extractfile("web/card_management.html").read() == b"<html>\n</html>\n"


def test_backup_includes_committed_wal_and_passes_quick_check(tmp_path):
    database, backup = tmp_path / "wal.db", tmp_path / "backup.db"
    with sqlite3.connect(str(database)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE scores(value INTEGER)")
        conn.execute("INSERT INTO scores VALUES(7)")
        conn.commit()
        deploy.backup_sqlite(database, backup)
        with sqlite3.connect(str(backup)) as saved:
            assert saved.execute("SELECT value FROM scores").fetchone() == (7,)
            assert saved.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_failed_activation_rolls_code_back_without_restoring_new_player_data(tmp_path, monkeypatch):
    database, backup = tmp_path / "live-fixture.db", tmp_path / "before.db"
    with sqlite3.connect(str(database)) as conn:
        conn.execute("CREATE TABLE scores(value INTEGER)")
        conn.execute("INSERT INTO scores VALUES(7)")
    current, events = {"path": "old"}, []
    def switch(target):
        current["path"] = target
        events.append(("switch", target))
    monkeypatch.setattr(deploy, "switch_current", switch)
    monkeypatch.setattr(deploy.time, "sleep", lambda _: None)
    class Services:
        def stop(self):
            events.append(("stop", current["path"]))
        def start(self):
            events.append(("start", current["path"]))
            if current["path"] == "new":
                with sqlite3.connect(str(database)) as conn:
                    conn.execute("UPDATE scores SET value=8")
        def health(self):
            if current["path"] == "new":
                raise RuntimeError("broken API")
    with pytest.raises(RuntimeError, match="previous code restored"):
        deploy.activate_release("new", "old", database, backup, Services())
    assert current["path"] == "old"
    assert events == [("stop", "old"), ("switch", "new"), ("start", "new"), ("stop", "new"), ("switch", "old"), ("start", "old")]
    with sqlite3.connect(str(database)) as conn:
        assert conn.execute("SELECT value FROM scores").fetchone() == (8,)
    with sqlite3.connect(str(backup)) as conn:
        assert conn.execute("SELECT value FROM scores").fetchone() == (7,)


@pytest.mark.skipif(os.name != "posix", reason="Linux flock")
def test_shared_lock_serializes_two_deployers(tmp_path):
    path, events = tmp_path / "deploy.lock", []
    def work(number):
        with deploy.deployment_lock(path):
            events.append((number, "start"))
            time.sleep(0.02)
            events.append((number, "end"))
    threads = [threading.Thread(target=work, args=(number,)) for number in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(events) == 4
    assert events[0][0] == events[1][0] and events[2][0] == events[3][0]


def test_fixed_entrypoint_rejects_shell_commands_and_bad_identifiers():
    with pytest.raises(ValueError):
        deploy.validate_envelope({"operation": "sh", "run_id": "1", "run_attempt": "1"})
    with pytest.raises(ValueError):
        deploy.validate_envelope({"operation": "rollback", "run_id": "1;id", "run_attempt": "1", "expected_current_sha": "a" * 40})


def test_overlapping_shared_paths_are_rejected_before_any_write(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    with pytest.raises(RuntimeError, match="overlapping"):
        deploy.attach_shared(release, {"assets": str(shared), "assets/card_images": str(shared)})
    assert list(release.iterdir()) == []


def test_backup_failure_recovers_old_services_without_activating_candidate(tmp_path, monkeypatch):
    events = []
    class Services:
        def stop(self):
            events.append("stop")
        def start(self):
            events.append("start")
        def health(self):
            events.append("healthy")
    def backup(*args):
        raise RuntimeError("disk full")
    monkeypatch.setattr(deploy, "backup_sqlite", backup)
    monkeypatch.setattr(deploy, "switch_current", lambda target: events.append(target))
    with pytest.raises(RuntimeError, match="previous code restored"):
        deploy.activate_release("candidate", "old", tmp_path / "db", tmp_path / "backup", Services())
    assert events == ["stop", "stop", "old", "start", "healthy"]


def test_isolated_preflight_accepts_current_startup_and_rejects_migration_on_copy(tmp_path):
    root = TOOLS.parents[1]
    release = tmp_path / "candidate"
    for directory in package.CODE_DIRS:
        for path in (root / directory).rglob("*"):
            if path.is_file() and package.allowed_path(path.relative_to(root).as_posix()):
                destination = release / path.relative_to(root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(path), str(destination))
    for name in package.ROOT_FILES:
        if (root / name).is_file():
            shutil.copyfile(str(root / name), str(release / name))
    index = release / "frontend/game/dist/index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<html>synthetic build</html>")
    source, copy = tmp_path / "source.db", tmp_path / "copy.db"
    env = {k: v for k, v in os.environ.items() if k not in {"BOT_TOKEN", "ADMIN_API_TOKEN", "ARENA_ADMIN_TOKEN"}}
    env.update(DATABASE_PATH=str(source), DB_PATH=str(source), PYTHONUTF8="1")
    seed = "import sys; sys.path.insert(0, sys.argv[1]); from web import miniapp_api; from web.admin_wsgi import app"
    subprocess.run([sys.executable, "-c", seed, str(release)], cwd=str(tmp_path), env=env,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deploy.backup_sqlite(source, copy)
    command = [sys.executable, str(TOOLS / "preflight.py"), str(release), str(copy)]
    passed = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert passed.returncode == 0, passed.stderr.decode("utf-8", errors="replace")
    # The new vocabulary must be prepared explicitly; deployment keeps its no-change guard.
    with sqlite3.connect(str(copy)) as legacy:
        legacy.execute('DROP TABLE card_trait_registry')
    requires_owner_migration = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert requires_owner_migration.returncode != 0
    with sqlite3.connect(str(copy)) as legacy:
        legacy.execute('DROP TABLE card_trait_registry')
    from migrations.migrate_card_trait_registry import apply_migration
    apply_migration(copy)
    prepared = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert prepared.returncode == 0, prepared.stderr.decode('utf-8', errors='replace')
    # Phase 1 likewise requires owner preparation; deploy must not auto-migrate.
    for attempt in range(2):
        with sqlite3.connect(str(copy)) as legacy:
            legacy.execute('DROP TABLE foundation_settings')
            legacy.execute('DROP TABLE match_contexts')
        if attempt == 0:
            rejected = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
            assert rejected.returncode != 0
    from migrations.migrate_shared_foundation import apply_migration as prepare_foundation
    prepare_foundation(copy)
    prepared = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert prepared.returncode == 0, prepared.stderr.decode('utf-8', errors='replace')
    # Phase 2 schema must also be prepared on an owner-reviewed copy first.
    with sqlite3.connect(str(copy)) as legacy:
        legacy.execute('DROP TABLE reward_ledger')
    rejected = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert rejected.returncode != 0
    with sqlite3.connect(str(copy)) as legacy:
        legacy.execute('DROP TABLE reward_ledger')
    from migrations.migrate_progression_v2 import apply_migration as prepare_economy
    prepare_economy(copy)
    prepared = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert prepared.returncode == 0, prepared.stderr.decode('utf-8', errors='replace')
    with (release / "core/database.py").open("a", encoding="utf-8") as changed:
        changed.write("\nimport os\nwith sqlite3.connect(os.environ['DATABASE_PATH']) as c:\n    c.execute('CREATE TABLE unreviewed_migration (value INTEGER)')\n")
    failed = subprocess.run(command, cwd=str(tmp_path), env=env, capture_output=True)
    assert failed.returncode != 0
    with sqlite3.connect(str(source)) as original:
        assert not original.execute("SELECT name FROM sqlite_master WHERE name='unreviewed_migration'").fetchall()
