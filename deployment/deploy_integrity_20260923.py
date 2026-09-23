"""One-time release switch, run on the TelBattle VPS after staging tests pass."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request


ROOT = Path('/opt/telbattle')
CURRENT = ROOT / 'current'
PREVIOUS = ROOT / 'releases/20260922-tabletop-ui-v1'
RELEASE = ROOT / 'releases/20260923-game-integrity-v1'
SERVICES = ['telbattle-api', 'telbattle-bot', 'telbattle-admin']


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def switch(target):
    temporary = ROOT / 'current-integrity-20260923.tmp'
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError('Unexpected temporary release link')
    temporary.symlink_to(target)
    os.replace(temporary, CURRENT)


def verify_services():
    for service in SERVICES:
        if run('systemctl', 'is-active', service) != 'active':
            raise RuntimeError('Service not active: ' + service)
    with urllib.request.urlopen('http://127.0.0.1:5001/api/v1/health', timeout=10) as response:
        if json.load(response).get('status') != 'ok':
            raise RuntimeError('API health failed')


def main():
    if CURRENT.resolve() != PREVIOUS:
        raise RuntimeError('Live release changed; refusing to overwrite it')
    manifest = json.loads(Path('/tmp/telbattle-integrity-20260923-manifest.json').read_text())
    for name, digest in manifest.items():
        if hashlib.sha256((RELEASE / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Staged file hash mismatch: ' + name)
    database = ROOT / 'shared/game_bot.db'
    backup = ROOT / 'backups/game_bot-before-integrity-20260923.db'
    if backup.exists():
        raise RuntimeError('Backup already exists')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(backup) as destination:
            source.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database backup failed integrity check')
    backup.chmod(0o600)
    print('Verified database backup:', backup, flush=True)
    subprocess.run(['chown', '-hR', 'telbattle:telbattle', str(RELEASE)], check=True)
    try:
        subprocess.run(['systemctl', 'stop', *SERVICES], check=True)
        switch(RELEASE)
        subprocess.run(['systemctl', 'start', *SERVICES], check=True)
        for attempt in range(12):
            time.sleep(2)
            try:
                verify_services()
                break
            except Exception:
                if attempt == 11:
                    raise
        time.sleep(8)
        verify_services()
    except Exception:
        switch(PREVIOUS)
        subprocess.run(['systemctl', 'restart', *SERVICES], check=True)
        print('Rolled back to previous release', flush=True)
        raise
    print('Active release:', CURRENT.resolve(), flush=True)
    print(run('systemctl', 'show', *SERVICES, '-p', 'Id', '-p', 'ActiveState', '-p', 'MainPID'), flush=True)


if __name__ == '__main__':
    main()
