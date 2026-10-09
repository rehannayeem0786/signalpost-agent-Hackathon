"""Generate strong secrets for .env (run once, paste the output into .env)."""

from __future__ import annotations

import secrets

NAMES = ("JWT_SECRET", "CSRF_PEPPER", "SESSION_SECRET", "WEBHOOK_SECRET")

if __name__ == "__main__":
    for name in NAMES:
        print(f"{name}={secrets.token_urlsafe(48)}")
