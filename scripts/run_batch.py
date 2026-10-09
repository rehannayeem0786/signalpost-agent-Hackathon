#!/usr/bin/env python3
"""The single evaluator command.

Example (100-company smoke test)::

    python scripts/run_batch.py \\
        --organisations data/smoke-companies.jsonl \\
        --universe data/signalpost-company-universe-2025.jsonl.gz \\
        --profiles-output out/smoke-profiles.jsonl \\
        --output out/smoke-envelopes.jsonl \\
        --report reports/smoke-100/report.json \\
        --run-id smoke-001 --expected-count 100
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.runner import DEFAULT_MODULES, run_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost batch runner (one terminal envelope per input company)")
    parser.add_argument("--organisations", required=True, help="JSON/JSONL/text list of organisation numbers")
    parser.add_argument("--universe", required=True, help="Frozen Builderr universe JSONL(.gz) used for identity anchoring")
    parser.add_argument("--output", required=True, help="Terminal envelope JSONL (one row per input)")
    parser.add_argument("--profiles-output", required=True, help="Enriched profile JSONL")
    parser.add_argument("--report", required=True, help="Machine-readable run report (JSON)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--modules", default=DEFAULT_MODULES)
    parser.add_argument("--offline", action="store_true", help="No network: registry-anchored envelopes only")
    parser.add_argument("--no-llm", action="store_true", help="Force deterministic synthesis even if keys exist")
    parser.add_argument("--budget-seconds", type=float, default=3600.0)
    parser.add_argument("--previous", default=None, help="Prior profiles JSONL to diff for changes")
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    report = run_batch(
        args.organisations,
        args.universe,
        output_path=args.output,
        profiles_output=args.profiles_output,
        report_path=args.report,
        run_id=args.run_id,
        expected_count=args.expected_count,
        workers=args.workers,
        modules=[m.strip() for m in args.modules.split(",") if m.strip()],
        offline=args.offline,
        use_llm=not args.no_llm,
        budget_seconds=args.budget_seconds,
        previous_profiles_path=args.previous,
        checkpoint_every=args.checkpoint_every,
        resume=args.resume,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["validation"]["passed"] else 1)


if __name__ == "__main__":
    main()
