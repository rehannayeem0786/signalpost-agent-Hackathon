"""SQLite persistence with row-level security enforced in the data layer.

Every read/write is scoped by ``tenant_id``; no function in this module can
return or mutate another tenant's rows. All SQL uses bound parameters (no
string interpolation), which eliminates SQL injection by construction.

Refresh semantics: snapshots are immutable and content-addressed, so replaying
the same source snapshot is idempotent (no duplicate rows, no false changes).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .evidence import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    tenant_id TEXT NOT NULL,
    organisation_number TEXT NOT NULL,
    payload TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, organisation_number)
);
CREATE TABLE IF NOT EXISTS snapshots (
    tenant_id TEXT NOT NULL,
    organisation_number TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    payload TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, organisation_number, content_sha256)
);
CREATE TABLE IF NOT EXISTS changes (
    tenant_id TEXT NOT NULL,
    organisation_number TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    detected_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS jobs (
    tenant_id TEXT NOT NULL,
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_tenant ON profiles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_changes_tenant_org ON changes (tenant_id, organisation_number);
"""


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        with self._lock:
            conn = _connect(self.db_path)
            try:
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def ensure_tenant(self, tenant_id: str, name: str = "default") -> None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO tenants (tenant_id, name, created_at) VALUES (?, ?, ?)",
                    (tenant_id, name, utc_now()),
                )
                conn.commit()
            finally:
                conn.close()

    def upsert_profile(self, tenant_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        org = str(profile.get("organisation_number") or "")
        if not org:
            raise ValueError("profile requires an organisation_number")
        payload = json.dumps(profile, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = utc_now()
        with self._lock:
            conn = _connect(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO profiles (tenant_id, organisation_number, payload, content_sha256, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, organisation_number) DO UPDATE SET "
                    "payload = excluded.payload, content_sha256 = excluded.content_sha256, updated_at = excluded.updated_at",
                    (tenant_id, org, payload, digest, now),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO snapshots (tenant_id, organisation_number, content_sha256, payload, retrieved_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tenant_id, org, digest, payload, now),
                )
                conn.commit()
            finally:
                conn.close()
        return {"organisation_number": org, "content_sha256": digest, "updated_at": now}

    def get_profile(self, tenant_id: str, organisation_number: str) -> dict[str, Any] | None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT payload FROM profiles WHERE tenant_id = ? AND organisation_number = ?",
                    (tenant_id, organisation_number),
                ).fetchone()
            finally:
                conn.close()
        return json.loads(row["payload"]) if row else None

    def list_profiles(self, tenant_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT organisation_number, content_sha256, updated_at FROM profiles "
                    "WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (tenant_id, int(limit), int(offset)),
                ).fetchall()
            finally:
                conn.close()
        return [dict(row) for row in rows]

    def record_changes(self, tenant_id: str, organisation_number: str, changes: list[dict[str, Any]]) -> int:
        recorded = 0
        now = utc_now()
        with self._lock:
            conn = _connect(self.db_path)
            try:
                for change in changes:
                    field = str(change.get("field") or "")
                    old_digest = hashlib.sha256(json.dumps(change.get("old_value"), sort_keys=True, default=str).encode()).hexdigest()[:16]
                    new_digest = hashlib.sha256(json.dumps(change.get("new_value"), sort_keys=True, default=str).encode()).hexdigest()[:16]
                    key = hashlib.sha256(f"{tenant_id}|{organisation_number}|{field}|{old_digest}|{new_digest}".encode()).hexdigest()
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO changes "
                        "(tenant_id, organisation_number, field, old_value, new_value, detected_at, idempotency_key) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (tenant_id, organisation_number, field,
                         json.dumps(change.get("old_value"), ensure_ascii=False, default=str),
                         json.dumps(change.get("new_value"), ensure_ascii=False, default=str),
                         now, key),
                    )
                    recorded += cursor.rowcount
                conn.commit()
            finally:
                conn.close()
        return recorded

    def list_changes(self, tenant_id: str, organisation_number: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT field, old_value, new_value, detected_at FROM changes "
                    "WHERE tenant_id = ? AND organisation_number = ? ORDER BY detected_at DESC LIMIT ?",
                    (tenant_id, organisation_number, int(limit)),
                ).fetchall()
            finally:
                conn.close()
        return [dict(row) for row in rows]

    def create_job(self, tenant_id: str, job_id: str, kind: str) -> None:
        now = utc_now()
        with self._lock:
            conn = _connect(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO jobs (tenant_id, job_id, kind, status, detail, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'queued', NULL, ?, ?)",
                    (tenant_id, job_id, kind, now, now),
                )
                conn.commit()
            finally:
                conn.close()

    def update_job(self, tenant_id: str, job_id: str, status: str, detail: str | None = None) -> None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                conn.execute(
                    "UPDATE jobs SET status = ?, detail = ?, updated_at = ? WHERE tenant_id = ? AND job_id = ?",
                    (status, detail, utc_now(), tenant_id, job_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_job(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT job_id, kind, status, detail, created_at, updated_at FROM jobs "
                    "WHERE tenant_id = ? AND job_id = ?",
                    (tenant_id, job_id),
                ).fetchone()
            finally:
                conn.close()
        return dict(row) if row else None

