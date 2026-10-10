"""Owner-installed fixed SSH receiver. Linux only; never execute bundle code as root."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

from package_release import MAX_ARCHIVE, REPOSITORY, verify

ROOT = Path("/opt/telbattle")
CONFIG = Path("/etc/telbattle/deploy.json")
STATE = ROOT / "deploy-state/state.json"
SERVICES = ("telbattle-bot", "telbattle-api", "telbattle-admin")


def service_account():
    import pwd
    return pwd.getpwnam("telbattle")


@contextlib.contextmanager
def deployment_lock(path):
    import fcntl
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def atomic_json(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(data, output, sort_keys=True, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temporary.chmod(0o600)
    os.replace(str(temporary), str(path))


def current_release():
    link = ROOT / "current"
    if not link.is_symlink():
        raise RuntimeError("current must be a symlink")
    target = link.resolve(strict=True)
    if target.parent != ROOT / "releases":
        raise RuntimeError("current target is outside releases")
    return target


def switch_current(target):
    temporary = ROOT / ".current-actions.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("unexpected temporary current link")
    temporary.symlink_to(target)
    os.replace(str(temporary), str(ROOT / "current"))


def backup_sqlite(source, destination):
    if destination.exists():
        raise RuntimeError("backup already exists")
    # SQLite backup API includes committed WAL content; raw file copies are unsafe.
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30) as src:
        with sqlite3.connect(str(destination)) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("SQLite backup failed integrity check")
    destination.chmod(0o600)


class SystemServices:
    def stop(self):
        subprocess.run(["systemctl", "stop", *SERVICES], check=True, timeout=90,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start(self):
        subprocess.run(["systemctl", "start", *SERVICES], check=True, timeout=90,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def health(self):
        for service in SERVICES:
            output = subprocess.check_output(["systemctl", "show", service, "--property=ActiveState",
                                              "--property=ExecMainStatus", "--property=NRestarts"], text=True, timeout=10)
            status = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
            if status != {"ActiveState": "active", "ExecMainStatus": "0", "NRestarts": "0"}:
                raise RuntimeError("service health failed: " + service)
        checks = (("http://127.0.0.1:5001/api/v1/health", "health"),
                  ("http://127.0.0.1:5000/", "html"),
                  ("http://127.0.0.1:5000/api/cards", "cards"),
                  ("http://127.0.0.1:5000/api/card-editor/options", "options"),
                  ("http://127.0.0.1:5001/miniapp", "html"))
        for url, kind in checks:
            with urllib.request.urlopen(url, timeout=10) as response:
                body = response.read(8 * 1024 * 1024)
                if response.status != 200:
                    raise RuntimeError("internal HTTP check failed")
                if kind == "html":
                    if b"<html" not in body.lower():
                        raise RuntimeError("internal HTML check failed")
                else:
                    data = json.loads(body)
                    if kind == "health" and data.get("status") != "ok":
                        raise RuntimeError("internal API health failed")
                    if kind == "cards" and (data.get("success") is not True or not isinstance(data.get("cards"), list)):
                        raise RuntimeError("card catalog check failed")
                    if kind == "options" and (data.get("success") is not True or not isinstance(data.get("traits"), list)):
                        raise RuntimeError("card editor options check failed")


def wait_health(services, attempts=12):
    for attempt in range(attempts):
        try:
            services.health()
            return
        except Exception:
            if attempt == attempts - 1:
                raise RuntimeError("internal service checks failed") from None
            time.sleep(2)


def activate_release(target, previous, database, backup, services):
    # This transaction restores only the code pointer. Never restore SQLite here.
    try:
        services.stop()
        backup_sqlite(database, backup)
        switch_current(target)
        services.start()
        wait_health(services)
    except Exception:
        try:
            restore_code(previous, services)
        except Exception:
            raise RuntimeError("activation and code rollback failed; owner intervention required") from None
        raise RuntimeError("activation failed; previous code restored; database was not restored") from None


def restore_code(previous, services):
    services.stop()
    switch_current(previous)
    services.start()
    wait_health(services)


def verify_runtime_files(release, files):
    for relative, expected in files.items():
        path = release / relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("recorded release file changed")


def preflight(release, database, python):
    account = service_account()
    with tempfile.TemporaryDirectory(prefix="preflight-", dir=str(ROOT / ".deploy")) as directory:
        working = Path(directory)
        copy = working / "snapshot.db"
        backup_sqlite(database, copy)
        os.chown(str(working), account.pw_uid, account.pw_gid)
        os.chown(str(copy), account.pw_uid, account.pw_gid)
        env = {"PATH": "/usr/bin:/bin", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "DATABASE_PATH": str(copy), "DB_PATH": str(copy), "RUN_LIVE_TELEGRAM_TESTS": "0"}
        # No shared config links, application secrets, or production DB path exist in this process.
        result = subprocess.run(["/usr/sbin/runuser", "-u", "telbattle", "--", python,
                                 "/usr/local/lib/telbattle-deploy/preflight.py", str(release), str(copy)],
                                cwd=str(working), env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=120)
        if result.returncode:
            raise RuntimeError("isolated SQLite/runtime preflight failed; no activation occurred")


def attach_shared(release, links):
    paths = [PurePosixPath(name) for name in links]
    if any(path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name
           for path, name in zip(paths, links)) or any(a in b.parents for a in paths for b in paths):
        raise RuntimeError("invalid or overlapping preserved server paths")
    for relative, raw_target in links.items():
        path = release / relative
        if path.exists() or path.is_symlink():
            raise RuntimeError("bundle overlaps a preserved server path")
        target = Path(raw_target)
        if not target.is_absolute() or not target.exists():
            raise RuntimeError("preserved server path missing")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target, target_is_directory=target.is_dir())


def validate_envelope(data):
    if not isinstance(data, dict) or data.get("operation") not in {"deploy", "rollback"}:
        raise ValueError("invalid operation")
    if set(data) - {"operation", "source_sha", "run_id", "run_attempt", "archive_sha256", "expected_current_sha"}:
        raise ValueError("unknown deployment field")
    for name in ("run_id", "run_attempt"):
        if not re.fullmatch(r"[0-9]{1,20}", str(data.get(name, ""))):
            raise ValueError("invalid Actions run identity")
    key = "source_sha" if data["operation"] == "deploy" else "expected_current_sha"
    if not re.fullmatch(r"[0-9a-f]{40}", str(data.get(key, ""))):
        raise ValueError("invalid source SHA")
    if data["operation"] == "deploy" and not re.fullmatch(r"[0-9a-f]{64}", str(data.get("archive_sha256", ""))):
        raise ValueError("invalid archive digest")


def receive_archive(stream, path, expected):
    total = 0
    hasher = hashlib.sha256()
    with path.open("xb") as out:
        while True:
            data = stream.read(1024 * 1024)
            if not data:
                break
            total += len(data)
            if total > MAX_ARCHIVE:
                raise ValueError("archive too large")
            out.write(data)
            hasher.update(data)
    if hasher.hexdigest() != expected:
        raise ValueError("transport checksum mismatch")


def dispatch(data, stream, config, state):
    validate_envelope(data)
    previous = current_release()
    if str(previous) != state["active"]["path"]:
        raise RuntimeError("current changed outside recorded deployment state; owner must reconcile it")
    suffix = data["run_id"] + "-" + data["run_attempt"]
    backup = ROOT / "backups" / ("before-actions-" + suffix + ".db")
    if data["operation"] == "rollback":
        if data["expected_current_sha"] != state["active"]["source_sha"] or not state.get("previous"):
            raise RuntimeError("rollback source mismatch or no recorded previous release")
        record = state["previous"]
        target = Path(record["path"])
        if target.parent != ROOT / "releases" or not target.is_dir():
            raise RuntimeError("previous release unavailable")
        verify_runtime_files(target, record["files"])
        # Rollback preflight must also exclude server secrets, so use a clean copy of runtime files.
        with tempfile.TemporaryDirectory(prefix="rollback-", dir=str(ROOT / ".deploy")) as directory:
            clean = Path(directory)
            clean.chmod(0o755)
            for name in record["files"]:
                destination = clean / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(target / name), str(destination))
                destination.chmod(0o644)
                for parent in destination.parents:
                    if parent == clean.parent:
                        break
                    parent.chmod(0o755)
            preflight(clean, ROOT / "shared/game_bot.db", config["python"])
    else:
        name = "actions-" + suffix + "-" + data["source_sha"][:12]
        target = ROOT / "releases" / name
        if target.exists():
            raise RuntimeError("release already exists; rerun with a new Actions attempt")
        with tempfile.TemporaryDirectory(prefix="receive-", dir=str(ROOT / ".deploy")) as directory:
            archive = Path(directory) / "release.tar.gz"
            receive_archive(stream, archive, data["archive_sha256"])
            manifest = verify(archive, data["source_sha"], data["run_id"])
            if manifest["run_attempt"] != data["run_attempt"]:
                raise ValueError("release attempt mismatch")
            if manifest["server_python"] != config["server_python"]:
                raise RuntimeError("server Python differs from tested runtime")
            expected_requirements = Path(config["requirements_file"]).read_bytes()
            if manifest["files"]["requirements.txt"] != hashlib.sha256(expected_requirements).hexdigest():
                raise RuntimeError("dependencies changed; owner must prepare the server venv first")
            target.mkdir(mode=0o755)
            with tarfile.open(str(archive), "r:gz") as tar:
                for member in tar.getmembers():
                    destination = target / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(tar.extractfile(member).read())
                    destination.chmod(0o644)
                    for parent in destination.parents:
                        if parent == target.parent:
                            break
                        parent.chmod(0o755)
        preflight(target, ROOT / "shared/game_bot.db", config["python"])
        attach_shared(target, config["shared_links"])
        account = service_account()
        os.chown(str(target), account.pw_uid, account.pw_gid)
        record = {"path": str(target), "source_sha": manifest["source_sha"], "files": manifest["files"]}
    activate_release(target, previous, ROOT / "shared/game_bot.db", backup, SystemServices())
    new_state = {"active": record, "previous": state["active"]}
    receipt = {"status": "ok", "operation": data["operation"], "source_sha": record["source_sha"],
               "previous_sha": state["active"]["source_sha"], "release": target.name,
               "backup": backup.name, "run_id": data["run_id"], "internal_health": "ok"}
    receipt_path = STATE.parent / ("run-" + suffix + ".json")
    try:
        atomic_json(receipt_path, receipt)
        atomic_json(STATE, new_state)
    except Exception:
        # The verified pre-activation backup already exists; recording failure must not require a second backup.
        restore_code(previous, SystemServices())
        if receipt_path.exists():
            receipt_path.unlink()
        raise RuntimeError("state recording failed; previous code restored") from None
    return receipt


def main():
    if os.geteuid() != 0 or sys.argv[1:]:
        raise SystemExit("fixed deployment entrypoint requires root and no arguments")
    os.umask(0o077)
    def timed_out(*args):
        raise RuntimeError("deployment receiver timed out")
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(600)
    try:
        raw = sys.stdin.buffer.readline(4097)
        if len(raw) > 4096 or not raw.endswith(b"\n"):
            raise ValueError("invalid request header")
        data = json.loads(raw)
        validate_envelope(data)
        with deployment_lock(ROOT / "deploy.lock"):
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            if config.get("repository") != REPOSITORY or not config.get("enabled"):
                raise RuntimeError("deployment bootstrap is not enabled")
            state = json.loads(STATE.read_text(encoding="utf-8"))
            receipt = dispatch(data, sys.stdin.buffer, config, state)
        print(json.dumps(receipt), flush=True)
    except Exception as exc:
        # Fixed messages only; never print subprocess output, paths containing secret values, or HTTP bodies.
        safe = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__
        print(json.dumps({"status": "failed", "error": safe}), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
