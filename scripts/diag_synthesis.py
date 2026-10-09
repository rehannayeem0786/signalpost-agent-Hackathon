"""Dev diagnostic: synthesis method/cost/brief per envelope."""
from __future__ import annotations

import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "out/llm-envelopes.jsonl"
for line in open(path, encoding="utf-8"):
    if not line.strip():
        continue
    envelope = json.loads(line)
    syn = (envelope.get("profile", {}).get("evidence", {}) or {}).get("synthesis", {}) or {}
    value = syn.get("value") or {}
    ops = envelope.get("operations", {})
    print(json.dumps({
        "org": envelope.get("organisation_number"),
        "method": value.get("method"),
        "model": value.get("model"),
        "cost_usd": ops.get("third_party_cost_usd"),
        "requests": ops.get("requests"),
        "brief_head": str(value.get("brief") or "")[:150],
    }, ensure_ascii=False))
