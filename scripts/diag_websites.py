"""Dev diagnostic: summarize website identity-gate outcomes from an envelope file."""
from __future__ import annotations

import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "out/web-envelopes.jsonl"
for line in open(path, encoding="utf-8"):
    if not line.strip():
        continue
    envelope = json.loads(line)
    website = (envelope.get("profile", {}).get("evidence", {}) or {}).get("website", {}) or {}
    value = website.get("value") or {}
    identity = value.get("identity_assessment") or {}
    print(json.dumps({
        "org": envelope.get("organisation_number"),
        "name": envelope.get("identity", {}).get("legal_name"),
        "status": website.get("status"),
        "note": website.get("note"),
        "source_url": website.get("source_url"),
        "final_url": value.get("final_url"),
        "score": identity.get("score"),
        "status_identity": identity.get("status"),
        "publishable": identity.get("publishable"),
        "reason": identity.get("reason"),
    }, ensure_ascii=False))
