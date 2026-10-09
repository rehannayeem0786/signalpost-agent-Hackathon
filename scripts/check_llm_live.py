"""Live synthesis smoke check (uses keys from .env; never prints secrets)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from norway_company_agent.claims import build_claims  # noqa: E402
from norway_company_agent.synth import _provider_candidates, synthesize  # noqa: E402
from norway_company_agent.universe import iter_universe, normalize_universe_row  # noqa: E402

ORG = sys.argv[1] if len(sys.argv) > 1 else "810034882"

candidates = _provider_candidates()
print(f"configured providers in order: {[url.split('//')[1].split('.')[0] for _k, url, _m in candidates] or 'none'}")

row = None
for candidate in iter_universe(ROOT / "data" / "signalpost-company-universe-2025.jsonl.gz"):
    if str(candidate.get("organisation_number")) == ORG:
        row = candidate
        break
assert row, f"org {ORG} not in universe"
profile = normalize_universe_row(row)
profile["evidence"] = {"registry": {"status": "available", "source_url": "universe", "retrieved_at": "now"}}
claims, _rows = build_claims(profile)

record, cost = synthesize(profile, claims)
value = record.get("value") or {}
print(f"method={value.get('method')} model={value.get('model')} "
      f"tokens={value.get('prompt_tokens', '-')}/{value.get('completion_tokens', '-')} cost_usd={cost}")
print(f"note: {record.get('note')}")
print(f"brief: {value.get('brief')}")
