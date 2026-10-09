"""Pick the first N universe rows that carry a registry website (dev helper)."""
from __future__ import annotations

import gzip
import json
import sys

universe = sys.argv[1] if len(sys.argv) > 1 else "data/signalpost-company-universe-2025.jsonl.gz"
count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
out = sys.argv[3] if len(sys.argv) > 3 else "data/test-orgs-web.txt"

picked: list[str] = []
with gzip.open(universe, "rt", encoding="utf-8") as handle:
    for line in handle:
        row = json.loads(line)
        if row.get("website"):
            picked.append(row["organisation_number"])
            if len(picked) >= count:
                break
with open(out, "w", encoding="ascii") as handle:
    handle.write("\n".join(picked) + "\n")
print(picked)
