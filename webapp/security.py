"""Security primitives for the Signalpost web product.

Implements: JWT (env-secret, pinned HS256), argon2id password hashing, TOTP
MFA, double-submit CSRF, per-route rate limiting, webhook HMAC signatures,
security headers, and log redaction. No secret ever reaches a template.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
import pyotp

_MIN_SECRET_LEN = 32


def _secret(name: str, *, required: bool = True) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        if not required:
            return ""
        value = secrets.token_urlsafe(48)
        logging.getLogger("webapp.security").warning(
            "%s not set; using a per-process ephemeral secret (set it for production)", name)
    if len(value) < _MIN_SECRET_LEN and required:
        raise RuntimeError(f"{name} must be at least {_MIN_SECRET_LEN} characters")
    return value


def jwt_secret() -> str:
    return _secret("JWT_SECRET")


def csrf_pepper() -> str:
    return _secret("CSRF_PEPPER")


def webhook_secret() -> str:
    return _secret("WEBHOOK_SECRET")


def cors_allowlist() -> list[str]:
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- passwords ---------------------------------------------------------------

_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except Exception:
        return False


_PASSWORD_RULE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{12,}$")


def password_policy_ok(password: str) -> bool:
    return bool(_PASSWORD_RULE.match(password or ""))


# --- JWT (HS256 pinned; secret from environment only) ------------------------

ALGORITHM = "HS256"


def issue_token(subject: str, tenant_id: str, role: str, *, expires_seconds: int = 3600,
                email: str = "") -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "tenant": tenant_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + max(60, expires_seconds),
        "jti": secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


# --- MFA (TOTP) --------------------------------------------------------------

def totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, account: str, issuer: str = "Signalpost") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def totp_verify(secret: str, code: str) -> bool:
    try:
        return pyotp.TOTP(secret).verify(code.replace(" ", ""), valid_window=1)
    except Exception:
        return False


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_token_for(session_id: str) -> str:
    return hashlib.sha256(f"{csrf_pepper()}|{session_id}".encode()).hexdigest()


def csrf_validate(session_id: str, presented: str | None) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(csrf_token_for(session_id), presented)


# --- rate limiting -----------------------------------------------------------

class RateLimiter:
    """In-memory sliding-window limiter keyed by (bucket, identity)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, bucket: str, identity: str, limit: int, window_seconds: int) -> bool:
        key = f"{bucket}|{identity}"
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


# --- webhook signatures (HMAC-SHA256, constant-time compare) -----------------

def sign_payload(body: bytes) -> str:
    return "sha256=" + hmac.new(webhook_secret().encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_webhook_signature(body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    return hmac.compare_digest(sign_payload(body), header_value.strip())


# --- log redaction -----------------------------------------------------------

_REDACT_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I), lambda m: m.group(1) + "***"),
    (re.compile(r"(\"(?:password|token|secret|api_key|authorization)\"\s*[:=]\s*\")([^\"]+)(\")", re.I),
     lambda m: m.group(1) + "***" + m.group(3)),
    (re.compile(r"\b(password|passwd|pwd)\s*[:=]\s*\S+", re.I), lambda m: m.group(1) + "=***"),
    (re.compile(r"(GROQ_API_KEY|OPENROUTER_API_KEY|JWT_SECRET|CSRF_PEPPER|WEBHOOK_SECRET|SESSION_SECRET)"
                r"(\s*[:=]\s*)(\S+)", re.I), lambda m: m.group(1) + m.group(2) + "***"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        for pattern, replacer in _REDACT_PATTERNS:
            message = pattern.sub(replacer, message)
        record.msg = message
        record.args = ()
        return True


def install_log_redaction() -> None:
    redactor = RedactingFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)
    logging.getLogger("webapp").addFilter(redactor)
    logging.getLogger("norway_company_agent").addFilter(redactor)


# --- security headers --------------------------------------------------------

def security_headers() -> list[tuple[str, str]]:
    return [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy",
         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
         "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
        ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
        ("Cache-Control", "no-store"),
    ]

