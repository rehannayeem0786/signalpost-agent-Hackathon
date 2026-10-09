"""Dev diagnostic: summarize news-module outcomes from an envelope file."""
from __future__ import annotations

import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "out/smoke-envelopes.jsonl"
statuses: Counter[str] = Counter()
notes: Counter[str] = Counter()
samples: list[str] = []
for line in open(path, encoding="utf-8"):
    if not line.strip():
        continue
    envelope = json.loads(line)
    news = (envelope.get("profile", {}).get("evidence", {}) or {}).get("news", {}) or {}
    status = str(news.get("status"))
    statuses[status] += 1
    note = str(news.get("note") or "")[:120]
    notes[f"{status}: {note}"] += 1
    if len(samples) < 5 and news.get("value"):
        samples.append(json.dumps(news.get("value"), ensure_ascii=False)[:400])
print("STATUSES:", dict(statuses))
print("NOTES:")
for key, count in notes.most_common(8):
    print(f"  {count:3d}  {key}")
for sample in samples:
    print("SAMPLE:", sample)
