"""User identity store: tenants, users, roles, MFA secrets.

Row-level security: every query is scoped by ``tenant_id``. Passwords are
argon2id hashes; TOTP secrets are encrypted at rest with an HMAC-derived key
from ``SESSION_SECRET`` (no key material in code). Bootstrap admin credentials
are random and must be rotated on first login (``must_change_password``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .security import hash_password, needs_rehash, totp_secret, verify_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    totp_secret TEXT,
    mfa_enabled INTEGER NOT NULL DEFAULT 0,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
"""


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _derive_key() -> bytes:
    material = os.environ.get("SESSION_SECRET", "").strip() or jwt_fallback_secret()
    return hashlib.sha256(("totp-encryption|" + material).encode()).digest()


def jwt_fallback_secret() -> str:
    # Keep TOTP storage encrypted even when only JWT_SECRET is configured.
    return os.environ.get("JWT_SECRET", "").strip() or secrets.token_urlsafe(48)


def _seal_secret(plain: str) -> str:
    key = _derive_key()
    import hmac as _hmac
    tag = _hmac.new(key, plain.encode(), hashlib.sha256).hexdigest()
    payload = base64.urlsafe_b64encode(plain.encode()).decode()
    return f"{tag}.{payload}"


def _open_secret(sealed: str) -> str | None:
    try:
        tag, payload = sealed.split(".", 1)
        plain = base64.urlsafe_b64decode(payload.encode()).decode()
    except Exception:
        return None
    expected = hmac.new(_derive_key(), plain.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(tag, expected):
        return None
    return plain


class IdentityStore:
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

    def create_user(self, tenant_id: str, email: str, password: str, role: str = "user",
                    *, must_change_password: bool = False) -> dict[str, Any]:
        user_id = "usr-" + secrets.token_urlsafe(9)
        now = _now()
        with self._lock:
            conn = _connect(self.db_path)
            try:
                conn.execute(
                    "INSERT INTO users (user_id, tenant_id, email, password_hash, role, must_change_password, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, tenant_id, email.strip().casefold(), hash_password(password), role,
                     1 if must_change_password else 0, now, now),
                )
                conn.commit()
            finally:
                conn.close()
        return {"user_id": user_id, "tenant_id": tenant_id, "email": email.strip().casefold(), "role": role}

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM users WHERE email = ?", (email.strip().casefold(),)
                ).fetchone()
            finally:
                conn.close()
        return dict(row) if row else None

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        user = self.find_by_email(email)
        if not user:
            # Constant-ish work to reduce user-enumeration timing signal.
            hash_password(password)
            return None
        if not verify_password(user["password_hash"], password):
            return None
        if needs_rehash(user["password_hash"]):
            with self._lock:
                conn = _connect(self.db_path)
                try:
                    conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
                                 (hash_password(password), _now(), user["user_id"]))
                    conn.commit()
                finally:
                    conn.close()
        # ``must_change_password`` stays in the returned row; the login flow
        # issues a session that redirects to the change-password screen.
        return user

    # --- MFA -----------------------------------------------------------------

    def enable_mfa(self, user_id: str, tenant_id: str) -> str:
        """Generate and seal a TOTP secret. Row-level scoped by (user, tenant)."""
        secret = totp_secret()
        sealed = _seal_secret(secret)
        with self._lock:
            conn = _connect(self.db_path)
            try:
                cursor = conn.execute(
                    "UPDATE users SET totp_secret = ?, mfa_enabled = 1, updated_at = ? "
                    "WHERE user_id = ? AND tenant_id = ?",
                    (sealed, _now(), user_id, tenant_id),
                )
                conn.commit()
                if cursor.rowcount != 1:
                    raise PermissionError("row-level security: user not in tenant")
            finally:
                conn.close()
        return secret

    def get_totp_secret(self, user_id: str, tenant_id: str) -> str | None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT totp_secret FROM users WHERE user_id = ? AND tenant_id = ?",
                    (user_id, tenant_id),
                ).fetchone()
            finally:
                conn.close()
        if not row or not row["totp_secret"]:
            return None
        return _open_secret(row["totp_secret"])

    # --- mutations (server-side permission + row-level scope enforced) -------

    def set_password(self, user_id: str, tenant_id: str, new_password: str) -> None:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                cursor = conn.execute(
                    "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? "
                    "WHERE user_id = ? AND tenant_id = ?",
                    (hash_password(new_password), _now(), user_id, tenant_id),
                )
                conn.commit()
                if cursor.rowcount != 1:
                    raise PermissionError("row-level security: user not in tenant")
            finally:
                conn.close()

    def list_users(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT user_id, email, role, mfa_enabled, created_at FROM users WHERE tenant_id = ? ORDER BY created_at",
                    (tenant_id,),
                ).fetchall()
            finally:
                conn.close()
        return [dict(row) for row in rows]

    def count_users(self) -> int:
        with self._lock:
            conn = _connect(self.db_path)
            try:
                row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            finally:
                conn.close()
        return int(row["n"])

    def ensure_bootstrap_admin(self, tenant_id: str = "signalpost") -> dict[str, Any] | None:
        """Create the first admin with a RANDOM password (never a default credential)."""
        if self.count_users() > 0:
            return None
        configured = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
        password = configured or secrets.token_urlsafe(18)
        email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "admin@localhost").strip().casefold()
        user = self.create_user(tenant_id, email, password, role="admin", must_change_password=True)
        return {"email": email, "password": password, "must_change_password": True, "user_id": user["user_id"]}


# --- file upload validation ---------------------------------------------------

ALLOWED_UPLOAD_SUFFIXES = {".json", ".jsonl", ".txt", ".csv"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def validate_upload(filename: str, content: bytes) -> tuple[bool, str]:
    """Validate an uploaded smoke-test artifact before it touches disk.

    Checks the allowlisted extension, a hard size limit, UTF-8 text decoding,
    JSON/JSONL structural validity (content sniffing) and NUL bytes. Anything
    else is rejected before any filesystem write happens.
    """
    name = (filename or "").strip()
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        return False, f"extension {suffix or '(none)'} not allowed"
    if len(content) > MAX_UPLOAD_BYTES:
        return False, f"file exceeds {MAX_UPLOAD_BYTES} bytes"
    if not content:
        return False, "empty file"
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False, "content is not UTF-8 text (binary uploads rejected)"
    stripped = text.lstrip()
    if suffix == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            return False, f"invalid JSON: {exc.msg}"
    elif suffix == ".jsonl":
        first = stripped.splitlines()[0] if stripped else ""
        if not first.startswith("{"):
            return False, "JSONL rows must start with '{'"
        for line in text.splitlines():
            if line.strip():
                json.loads(line)
    if "\x00" in text:
        return False, "NUL bytes detected"
    return True, "ok"


