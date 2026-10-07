"""One-time owner/root installation. Does not deploy code or change production data."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from package_release import REPOSITORY, allowed_path

ROOT = Path("/opt/telbattle")
INSTALL = Path("/usr/local/lib/telbattle-deploy")
CONFIG = Path("/etc/telbattle/deploy.json")


def installation_plan(expected):
    current = ROOT / "current"
    if not current.is_symlink() or current.resolve() != expected.resolve() or expected.parent != ROOT / "releases":
        raise RuntimeError("active release differs from owner-reviewed baseline")
    if not (ROOT / "shared/game_bot.db").is_file():
        raise RuntimeError("shared SQLite database missing")
    for service in ("telbattle-bot", "telbattle-api", "telbattle-admin"):
        properties = subprocess.check_output(["systemctl", "show", service, "-p", "User", "-p", "WorkingDirectory"], text=True)
        values = dict(line.split("=", 1) for line in properties.splitlines() if "=" in line)
        if values.get("User") != "telbattle" or values.get("WorkingDirectory") != str(ROOT / "current"):
            raise RuntimeError("owner must review service User/WorkingDirectory: " + service)
    links = {"game_bot.db": str(ROOT / "shared/game_bot.db")}
    # Preserve existing configuration and all static/media paths by reference, without copying their contents.
    for name in (".env", "config.json", "game_config.json", "assets", "card_images", "stickers", "media"):
        path = expected / name
        if path.exists():
            links[name] = str(path.resolve())
    dist = expected / "frontend/game/dist"
    for path in dist.iterdir():
        if path.name not in {"index.html", "assets"}:
            links[path.relative_to(expected).as_posix()] = str(path.resolve())
    files = {}
    for path in expected.rglob("*"):
        name = path.relative_to(expected).as_posix()
        if allowed_path(name) and path.is_file() and not path.is_symlink():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    python = str(ROOT / "venv/bin/python")
    version = subprocess.check_output([python, "--version"], text=True).strip().split()[-1]
    if version != "3.9.25":
        raise RuntimeError("server runtime differs from the tested 3.9.25 baseline")
    return links, files, python, version


def install(args):
    if CONFIG.exists() or (ROOT / "deploy-state/state.json").exists():
        raise RuntimeError("deployment already bootstrapped; upgrade helpers through owner review instead")
    links, files, python, version = installation_plan(args.expected_current)
    public_key = args.public_key.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?", public_key):
        raise RuntimeError("a dedicated Ed25519 public key is required")
    subprocess.run(["ssh-keygen", "-l", "-f", str(args.public_key)], check=True, stdout=subprocess.DEVNULL)
    import pwd
    try:
        pwd.getpwnam("telbattle-deploy")
        raise RuntimeError("telbattle-deploy already exists; owner must inspect it before using this installer")
    except KeyError:
        pass
    # Root-owned parent paths prevent the app/deploy accounts from replacing current or helper state.
    for path, mode in ((ROOT, 0o755), (ROOT / "releases", 0o755), (ROOT / "backups", 0o700),
                       (ROOT / ".deploy", 0o711), (ROOT / "deploy-state", 0o700), (INSTALL, 0o755), (CONFIG.parent, 0o755)):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(str(path), 0, 0)
        path.chmod(mode)
    source = Path(__file__).resolve().parent
    for name in ("server.py", "package_release.py", "preflight.py"):
        destination = INSTALL / name
        shutil.copyfile(str(source / name), str(destination))
        os.chown(str(destination), 0, 0)
        destination.chmod(0o644)
    launcher = Path("/usr/local/sbin/telbattle-deploy")
    launcher.write_text("#!/bin/sh\nexec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin /usr/bin/python3 -E -s /usr/local/lib/telbattle-deploy/server.py\n", encoding="ascii")
    launcher.chmod(0o755)
    os.chown(str(launcher), 0, 0)
    requirements = CONFIG.parent / "deploy-requirements.txt"
    shutil.copyfile(str(args.expected_current / "requirements.txt"), str(requirements))
    requirements.chmod(0o644)
    subprocess.run(["useradd", "--system", "--create-home", "--home-dir", "/home/telbattle-deploy", "--shell", "/bin/sh", "telbattle-deploy"], check=True)
    subprocess.run(["passwd", "-l", "telbattle-deploy"], check=True, stdout=subprocess.DEVNULL)
    home = Path("/home/telbattle-deploy")
    ssh = home / ".ssh"
    ssh.mkdir(exist_ok=True)
    for path in (home, ssh):
        os.chown(str(path), 0, 0)
        path.chmod(0o755)
    authorized = ssh / "authorized_keys"
    authorized.write_text('restrict,command="/usr/bin/sudo -n /usr/local/sbin/telbattle-deploy" ' + public_key + "\n", encoding="ascii")
    authorized.chmod(0o644)
    os.chown(str(authorized), 0, 0)
    sudoers = Path("/etc/sudoers.d/telbattle-deploy")
    sudoers.write_text('telbattle-deploy ALL=(root) NOPASSWD: /usr/local/sbin/telbattle-deploy ""\n', encoding="ascii")
    sudoers.chmod(0o440)
    subprocess.run(["visudo", "-cf", str(sudoers)], check=True)
    sshd = Path("/etc/ssh/sshd_config.d/90-telbattle-deploy.conf")
    sshd.parent.mkdir(parents=True, exist_ok=True)
    sshd.write_text("Match User telbattle-deploy\n    AuthenticationMethods publickey\n    PasswordAuthentication no\n    KbdInteractiveAuthentication no\n    PermitTTY no\n    AllowTcpForwarding no\n    AllowAgentForwarding no\n    X11Forwarding no\n    PermitTunnel no\n    PermitUserRC no\n    ForceCommand /usr/bin/sudo -n /usr/local/sbin/telbattle-deploy\n", encoding="ascii")
    sshd.chmod(0o644)
    subprocess.run(["sshd", "-t"], check=True)
    effective = subprocess.check_output(["sshd", "-T", "-C", "user=telbattle-deploy,host=localhost,addr=127.0.0.1"], text=True)
    if "forcecommand /usr/bin/sudo -n /usr/local/sbin/telbattle-deploy" not in effective:
        raise RuntimeError("sshd_config must include sshd_config.d; owner must review it")
    config = {"enabled": False, "repository": REPOSITORY, "python": python, "server_python": version,
              "requirements_file": str(requirements), "shared_links": links}
    CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    CONFIG.chmod(0o600)
    state = {"active": {"path": str(args.expected_current), "source_sha": args.baseline_sha, "files": files}, "previous": None}
    state_path = ROOT / "deploy-state/state.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    state_path.chmod(0o600)
    lock = ROOT / "deploy.lock"
    if lock.is_symlink():
        raise RuntimeError("lock path must not be a symlink")
    lock.touch(exist_ok=True)
    lock.chmod(0o600)
    os.chown(str(lock), 0, 0)
    print("Installed disabled entrypoint. Owner must review shared_links, reload SSH and configure the GitHub environment before --enable.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--expected-current", type=Path)
    parser.add_argument("--baseline-sha")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Only the server owner/root may bootstrap this entrypoint")
    if sum((args.install, args.enable, args.reconcile)) > 1:
        raise SystemExit("install, enable and reconcile are separate reviewed steps")
    if args.enable:
        if args.install:
            raise SystemExit("enable is a separate reviewed step")
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        data["enabled"] = True
        CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Deployment entrypoint enabled")
    else:
        if not args.expected_current or not re.fullmatch(r"[0-9a-f]{40}", args.baseline_sha or ""):
            raise SystemExit("expected-current and full reviewed baseline-sha are required")
        if args.reconcile:
            from server import deployment_lock, atomic_json, STATE
            with deployment_lock(ROOT / "deploy.lock"):
                links, files, python, version = installation_plan(args.expected_current)
                old = json.loads(STATE.read_text(encoding="utf-8"))
                if old["active"]["path"] == str(args.expected_current):
                    raise RuntimeError("manual releases must use a new release directory")
                config = json.loads(CONFIG.read_text(encoding="utf-8"))
                config.update(enabled=False, shared_links=links, python=python, server_python=version)
                atomic_json(CONFIG, config)
                shutil.copyfile(str(args.expected_current / "requirements.txt"), config["requirements_file"])
                atomic_json(STATE, {"active": {"path": str(args.expected_current), "source_sha": args.baseline_sha, "files": files},
                                    "previous": old["active"]})
            print("Manual baseline recorded; entrypoint remains disabled until owner reviews and enables it")
        elif args.install:
            if not args.public_key:
                raise SystemExit("public-key is required")
            install(args)
        else:
            links, files, python, version = installation_plan(args.expected_current)
            print(json.dumps({"shared_links": links, "runtime_file_count": len(files), "python": python, "version": version}, indent=2))


if __name__ == "__main__":
    main()
