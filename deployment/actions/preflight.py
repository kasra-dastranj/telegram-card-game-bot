"""Run as telbattle in a disposable directory, without production configuration."""
import hashlib
import os
import sqlite3
import socket
import sys
from pathlib import Path


def database_digest(path):
    with sqlite3.connect(str(path)) as conn:
        assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()


def main():
    release, database = map(Path, sys.argv[1:])
    assert release.is_absolute() and database.is_absolute()
    before = database_digest(database)
    original_connect = sqlite3.connect
    def only_copy(name, *args, **kwargs):
        if str(name) != ":memory:" and Path(name).resolve() != database.resolve():
            raise RuntimeError("preflight may access only its SQLite copy")
        return original_connect(name, *args, **kwargs)
    def offline(*args, **kwargs):
        raise RuntimeError("preflight network access disabled")
    sqlite3.connect = only_copy
    socket.socket.connect = offline
    socket.create_connection = offline
    sys.path.insert(0, str(release))
    os.environ["DATABASE_PATH"] = os.environ["DB_PATH"] = str(database)
    from core.database import DatabaseManager
    from web.web_api import WebAPI
    from web import miniapp_api
    client = WebAPI(DatabaseManager(str(database))).app.test_client()
    for url in ("/", "/api/cards", "/api/card-editor/options"):
        response = client.get(url)
        assert response.status_code == 200
        response.close()
    api = miniapp_api.app.test_client()
    assert api.get("/api/v1/health").get_json() == {"status": "ok"}
    response = api.get("/miniapp")
    assert response.status_code == 200
    response.close()
    # This first automation intentionally excludes every schema or data migration.
    assert before == database_digest(database), "startup changed the SQLite copy; explicit owner migration review required"


if __name__ == "__main__":
    main()
