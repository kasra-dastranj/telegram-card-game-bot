"""Transactional idempotency receipts for card mutations."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Optional


_KEY = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")


def fingerprint(operation: str, payload: Any) -> str:
    encoded = json.dumps([operation, payload], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def lookup_in(conn: sqlite3.Connection, user_id: int, request_key: Optional[str],
              operation: str, payload: Any) -> Optional[dict]:
    if request_key is None:
        return None
    if not isinstance(request_key, str) or not _KEY.fullmatch(request_key):
        raise ValueError("شناسهٔ درخواست نامعتبر است")
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT operation,payload_hash,result_json FROM card_action_requests WHERE user_id=? AND request_key=?",
        (user_id, request_key),
    ).fetchone()
    if row is None:
        return None
    if row[0] != operation or row[1] != fingerprint(operation, payload):
        raise ValueError("این شناسهٔ درخواست قبلاً برای عملیات دیگری استفاده شده است")
    return json.loads(row[2])


def record_in(conn: sqlite3.Connection, user_id: int, request_key: Optional[str],
              operation: str, payload: Any, result: dict) -> None:
    if request_key is None:
        return
    conn.execute(
        """INSERT INTO card_action_requests
           (user_id,request_key,operation,payload_hash,result_json)
           VALUES(?,?,?,?,?)""",
        (user_id, request_key, operation, fingerprint(operation, payload),
         json.dumps(result, ensure_ascii=False, sort_keys=True)),
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS card_action_requests (
        user_id INTEGER NOT NULL,
        request_key TEXT NOT NULL,
        operation TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id,request_key)
    )""")
