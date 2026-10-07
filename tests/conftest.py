"""Optional CI guard: offline tests can open SQLite only in disposable storage."""
import os
import socket
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname


def pytest_configure(config):
    if os.environ.get("TELBATTLE_OFFLINE_CI") != "1":
        return
    os.environ["RUN_LIVE_TELEGRAM_TESTS"] = "0"
    for key in ("BOT_TOKEN", "ADMIN_API_TOKEN", "ARENA_ADMIN_TOKEN", "DATABASE_PATH", "DB_PATH"):
        os.environ.pop(key, None)
    root = Path(os.environ["TELBATTLE_TEST_DB_ROOT"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_PATH"] = str(root / "default.db")
    os.environ["DB_PATH"] = str(root / "default.db")
    original = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        name = os.fsdecode(database)
        if name != ":memory:":
            if name.startswith("file:"):
                name = url2pathname(urlsplit(name).path)
            path = Path(name).resolve()
            if path != root and root not in path.parents:
                raise RuntimeError("CI SQLite access outside disposable directory")
        return original(database, *args, **kwargs)

    original_connect_socket = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def guarded_socket(original):
        def connect(sock, address):
            # asyncio uses local socket pairs even when no HTTP/network request is made.
            if sock.family == getattr(socket, "AF_UNIX", None) or (
                    isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}):
                return original(sock, address)
            raise RuntimeError("External network access is disabled in the offline test suite")
        return connect

    sqlite3.connect = guarded_connect
    socket.socket.connect = guarded_socket(original_connect_socket)
    socket.socket.connect_ex = guarded_socket(original_connect_ex)
