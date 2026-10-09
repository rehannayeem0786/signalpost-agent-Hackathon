"""Output-contract regression tests (offline; no network required).

Verifies the official-run checks: exactly one terminal envelope per input,
legal harness states, evidence on every published claim, no zero-for-missing,
honest identity resolution, refresh idempotency, and the dual state vocabulary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import validate_envelopes  # noqa: E402
from norway_company_agent.claims import build_claims  # noqa: E402
from norway_company_agent.runner import HARNESS_STATES, run_batch, unresolved_profile  # noqa: E402
from norway_company_agent.universe import profiles_from_universe  # noqa: E402

UNIVERSE = ROOT / "data" / "signalpost-company-universe-2025.jsonl.gz"
ORGS = ["810034882", "810059672", "810094532"]


@pytest.fixture(scope="module")
def offline_run(tmp_path_factory):
    if not UNIVERSE.exists():
        pytest.skip("universe file not downloaded")
    tmp = tmp_path_factory.mktemp("contract")
    inputs = tmp / "orgs.txt"
    inputs.write_text("\n".join(ORGS), encoding="ascii")
    report = run_batch(
        inputs, UNIVERSE,
        output_path=tmp / "envelopes.jsonl",
        profiles_output=tmp / "profiles.jsonl",
        report_path=tmp / "report.json",
        run_id="contract-test", expected_count=3,
        workers=2, offline=True, use_llm=False, budget_seconds=60,
    )
    envelopes = [json.loads(line) for line in (tmp / "envelopes.jsonl").read_text(encoding="utf-8").splitlines()]
    return report, envelopes, tmp


def test_one_envelope_per_input_no_drops(offline_run):
    report, envelopes, _ = offline_run
    assert len(envelopes) == len(ORGS)
    assert [e["organisation_number"] for e in envelopes] == ORGS
    assert report["validation"]["passed"] is True


def test_states_legal_in_both_vocabularies(offline_run):
    _, envelopes, _ = offline_run
    starter_states = {"complete", "not_applicable", "not_found", "blocked_policy",
                      "blocked_robots", "source_error", "budget_exhausted", "submission_error"}
    for envelope in envelopes:
        assert envelope["status"] in HARNESS_STATES
        assert envelope["state"] in starter_states
        for module in envelope["modules"].values():
            assert module["state"] in starter_states


def test_every_available_claim_has_evidence_and_timestamp(offline_run):
    _, envelopes, _ = offline_run
    for envelope in envelopes:
        evidence_ids = {row["id"] for row in envelope["evidence"]}
        for claim in envelope["claims"]:
            if claim["availability"] == "available":
                assert claim["evidence_ids"], f"claim {claim['field']} lacks evidence"
                assert set(claim["evidence_ids"]).issubset(evidence_ids)
                assert claim["value"] is not None
        for row in envelope["evidence"]:
            assert row["retrieved_at"] or row["source_class"] == "derived_from_evidence"
            assert row["source_class"]


def test_missing_values_never_zero(offline_run):
    _, envelopes, _ = offline_run
    for envelope in envelopes:
        for claim in envelope["claims"]:
            if claim["availability"] != "available":
                assert claim["value"] is None
            if claim["value"] == 0:
                assert claim["availability"] == "available"  # a real zero must be sourced


def test_identity_blocker_produces_ambiguous_not_crash():
    profile = unresolved_profile("999999999", "absent from snapshot")
    claims, rows = build_claims(profile)
    assert claims and rows
    assert all(c["availability"] != "available" for c in claims if c["field"] == "legal_name")
    from norway_company_agent.runner import build_envelope
    envelope = build_envelope(profile, run_id="x", modules=["registry", "website"],
                              started_at="t0", completed_at="t1", requests=0,
                              runtime_ms=0, third_party_cost_usd=0.0, errors=[])
    assert envelope["status"] == "ambiguous"
    assert envelope["state"] in {"not_found", "submission_error", "complete"}


def test_refresh_idempotency_no_duplicate_changes():
    from norway_company_agent.store import Store
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "s.db")
        store.ensure_tenant("t1")
        changes = [{"field": "registry.employees", "old_value": 1, "new_value": 2}]
        first = store.record_changes("t1", "810034882", changes)
        second = store.record_changes("t1", "810034882", changes)  # same snapshot replay
        assert first == 1
        assert second == 0  # idempotent: no false change on re-run


def test_validate_envelopes_rejects_duplicates(offline_run):
    _, envelopes, _ = offline_run
    duplicated = envelopes + [envelopes[0]]
    result = validate_envelopes(duplicated, len(ORGS))
    assert result["passed"] is False
    assert result["checks"]["exact_expected_count"] is False
