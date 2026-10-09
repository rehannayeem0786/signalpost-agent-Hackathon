"""Batch orchestrator: organisation numbers in, one terminal envelope out.

Hard guarantees (official-run checks):
- exactly one terminal envelope per input company, always (errors are isolated
  per company and mapped to honest states, never to dropped rows);
- both state vocabularies are emitted: the starter ``state`` (validated by
  ``batch.validate_envelopes``) and the harness ``status``
  (``available | not_available | blocked | not_applicable | ambiguous | failed``);
- every claim carries evidence ids, retrieval time and reporting period;
- a wall-clock budget is enforced: companies that cannot be fully researched in
  time still return a registry-anchored envelope instead of disappearing.
"""

from __future__ import annotations

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from .batch import TERMINAL_STATES, read_organisation_inputs, terminal_envelope, validate_envelopes
from .claims import build_claims
from .evidence import evidence, utc_now
from .identity import apply_website_identity_gate
from .news import fetch_news
from .official import fetch_official_modules
from .refresh import diff_profile
from .synth import synthesize
from .universe import profiles_from_universe
from .website import fetch_website, guess_website_candidates

DEFAULT_MODULES = "registry,accounting_obligation,registry_live,financials,financial_history,roles,group,locations,website,news"
HARNESS_STATES = {"available", "not_available", "blocked", "not_applicable", "ambiguous", "failed"}


def harness_status(profile: dict[str, Any], module_states: dict[str, dict[str, str]]) -> str:
    """Map internal module states to the six contract states of the envelope."""
    if profile.get("_identity_unresolved"):
        return "ambiguous"
    states = [item.get("state") for item in module_states.values()]
    if any(state == "submission_error" for state in states):
        return "failed"
    records = profile.get("evidence", {})
    statuses = [record.get("status") for record in records.values() if isinstance(record, dict)]
    if statuses and all(status in {"blocked"} for status in statuses):
        return "blocked"
    has_content = any(
        isinstance(record, dict) and record.get("status") == "available"
        for record in records.values()
    )
    registry_ok = isinstance(records.get("registry"), dict) and records["registry"].get("status") == "available"
    if has_content and registry_ok:
        return "available"
    if any(status == "blocked" for status in statuses):
        return "blocked"
    if registry_ok or has_content:
        return "available"
    return "not_available"


def _module_record(status: str, note: str) -> dict[str, Any]:
    return evidence("deferred", status, "not_requested", "", note=note)


def build_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    modules: list[str],
    started_at: str,
    completed_at: str,
    requests: int,
    runtime_ms: int,
    third_party_cost_usd: float,
    errors: list[dict[str, Any]],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = terminal_envelope(profile, run_id=run_id, modules=modules,
                                 started_at=started_at, completed_at=completed_at)
    claims, evidence_rows = build_claims(profile)
    synthesis = profile.get("evidence", {}).get("synthesis")
    if synthesis and synthesis.get("status") == "available":
        claims.append({
            "field": "company_brief",
            "value": (synthesis.get("value") or {}).get("brief"),
            "availability": "available",
            "confidence": 0.9,
            "evidence_ids": ["ev-synthesis"],
            "reporting_period": None,
        })
        evidence_rows.append({
            "id": "ev-synthesis",
            "source_url": synthesis.get("source_url"),
            "source_class": synthesis.get("source_class"),
            "retrieved_at": synthesis.get("retrieved_at"),
            "content_sha256": None,
            "reporting_period": None,
            "claim_span": str((synthesis.get("value") or {}).get("brief") or "")[:300],
        })
    status = harness_status(profile, envelope["modules"])
    changes: list[dict[str, Any]] = []
    if previous and previous.get("organisation_number") == profile.get("organisation_number"):
        changes = diff_profile(previous, profile)
    errors = list(errors)
    for module, record in profile.get("evidence", {}).items():
        if isinstance(record, dict) and record.get("status") == "source_error":
            errors.append({"module": module, "error": str(record.get("note") or "source_error")[:300]})
        if isinstance(record, dict) and module == "website":
            for crawl_error in (record.get("value") or {}).get("crawl_errors") or []:
                errors.append({"module": "website", "url": crawl_error.get("url"),
                               "error": str(crawl_error.get("error"))[:300]})
    envelope["status"] = status
    envelope["run"] = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "terminal_status": status,
    }
    envelope["identity"] = {
        "organisation_number": profile.get("organisation_number"),
        "legal_name": profile.get("name"),
        "legal_form": profile.get("legal_form"),
        "municipality": profile.get("municipality"),
        "anchor": "brreg_universe_2025_frozen_snapshot",
    }
    envelope["claims"] = claims
    envelope["evidence"] = evidence_rows
    envelope["changes"] = changes
    envelope["errors"] = errors
    envelope["operations"] = {
        "requests": int(requests),
        "runtime_ms": int(runtime_ms),
        "third_party_cost_usd": round(float(third_party_cost_usd), 6),
    }
    if status not in HARNESS_STATES:  # defensive: never emit an unknown state
        envelope["status"] = "failed"
    return envelope


def enrich_company(
    profile: dict[str, Any],
    modules: list[str],
    *,
    offline: bool = False,
    news_limit: int = 10,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch live sources for one company. Errors are captured, never raised."""
    org = profile["organisation_number"]
    fetch_modules = {m for m in modules if m in
                     {"registry_live", "financials", "financial_history", "roles", "group", "locations"}}
    requests = 0
    latencies: list[int] = []
    if offline:
        for module in modules:
            profile["evidence"].setdefault(module, _module_record("not_applicable", "offline mode: not fetched"))
        return profile, {"requests": 0, "latencies_ms": [], "third_party_cost_usd": 0.0}

    if fetch_modules:
        try:
            records, metrics = fetch_official_modules(org, fetch_modules)
            profile["evidence"].update(records)
            requests += len(metrics)
            latencies.extend(item.elapsed_ms for item in metrics)
        except Exception:
            profile["evidence"]["registry_live"] = evidence(
                "registry_live", "source_error", "official_registry_live",
                f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}",
                note=f"fetch_official_modules: {traceback.format_exc(limit=1)}"[:300])

    if "website" in modules:
        website_url = profile.get("website")
        try:
            if website_url:
                website_record, website_metrics = fetch_website(website_url)
                profile["evidence"]["website"] = apply_website_identity_gate(profile, website_record)["website"]
                requests += int(website_metrics.get("requests") or 0)
                latencies.extend(int(x) for x in website_metrics.get("latencies_ms") or [])
            else:
                # Bounded candidate discovery: deterministic slug guesses from the
                # legal name. Every candidate must pass the exact-entity gate
                # before any of its content can be published.
                discovered = None
                for candidate in guess_website_candidates(profile.get("name")):
                    record, metrics = fetch_website(candidate)
                    requests += int(metrics.get("requests") or 0)
                    latencies.extend(int(x) for x in metrics.get("latencies_ms") or [])
                    gated = apply_website_identity_gate(profile, record)["website"]
                    if gated.get("status") == "available" and \
                            ((gated.get("value") or {}).get("identity_assessment") or {}).get("publishable"):
                        discovered = gated
                        break
                if discovered:
                    profile["evidence"]["website"] = discovered
                else:
                    profile["evidence"]["website"] = evidence(
                        "website", "not_found", "registry_linked_company_website", "",
                        note="No registry website; bounded slug discovery found no exact-entity match")
        except Exception:
            profile["evidence"]["website"] = evidence(
                "website", "source_error", "registry_linked_company_website",
                str(website_url or ""), note=f"website: {traceback.format_exc(limit=1)}"[:300])

    if "news" in modules:
        try:
            profile["evidence"]["news"] = fetch_news(profile, limit=news_limit)
            requests += 1
        except Exception:
            profile["evidence"]["news"] = evidence(
                "news", "source_error", "public_news_rss", "",
                note=f"news: {traceback.format_exc(limit=1)}"[:300])

    for module in modules:
        profile["evidence"].setdefault(module, _module_record("not_applicable", "module produced no record"))
    return profile, {"requests": requests, "latencies_ms": latencies, "third_party_cost_usd": 0.0}


def unresolved_profile(organisation_number: str, note: str) -> dict[str, Any]:
    """Identity could not be confirmed in the frozen snapshot -> honest ambiguous row."""
    profile: dict[str, Any] = {
        "organisation_number": organisation_number,
        "name": None, "legal_form": None, "employees": None, "bankrupt": False,
        "liquidating": False, "municipality": None, "municipality_number": None,
        "industry_code": None, "industry_label": None, "website": None,
        "latest_submitted_accounts": None,
        "evidence": {},
        "_identity_unresolved": True,
    }
    profile["evidence"]["registry"] = evidence(
        "registry", "not_found", "official_registry_bulk",
        "https://builderr.ai/signalpost-company-universe-2025.jsonl.gz",
        note=note, source_row_key=organisation_number)
    return profile


def research_company(
    profile: dict[str, Any],
    modules: list[str],
    *,
    run_id: str,
    started_at: str,
    offline: bool = False,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Research one company end to end and return its terminal envelope."""
    company_started = time.monotonic()
    errors: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {"requests": 0, "latencies_ms": [], "third_party_cost_usd": 0.0}
    try:
        profile, metrics = enrich_company(profile, modules, offline=offline)
        claims, _ = build_claims(profile)
        if use_llm and not profile.get("_identity_unresolved"):
            synthesis, cost = synthesize(profile, claims)
            synthesis["retrieved_at"] = utc_now()
            profile["evidence"]["synthesis"] = synthesis
            metrics["third_party_cost_usd"] = cost
    except Exception:
        errors.append({"module": "research", "error": traceback.format_exc(limit=2)[:500]})
        metrics = {"requests": 0, "latencies_ms": [], "third_party_cost_usd": 0.0}
        for module in modules:
            profile["evidence"].setdefault(module, _module_record("source_error", "research step failed"))
    completed_at = utc_now()
    runtime_ms = int((time.monotonic() - company_started) * 1000)
    return build_envelope(
        profile,
        run_id=run_id,
        modules=modules,
        started_at=started_at,
        completed_at=completed_at,
        requests=int(metrics.get("requests") or 0),
        runtime_ms=runtime_ms,
        third_party_cost_usd=float(metrics.get("third_party_cost_usd") or 0.0),
        errors=errors,
    )

def run_batch(
    organisations_path: str | Path,
    universe_path: str | Path,
    *,
    output_path: str | Path,
    profiles_output: str | Path,
    report_path: str | Path,
    run_id: str,
    expected_count: int | None = None,
    workers: int = 8,
    modules: Iterable[str] = DEFAULT_MODULES.split(","),
    offline: bool = False,
    use_llm: bool = True,
    budget_seconds: float = 3600.0,
    previous_profiles_path: str | Path | None = None,
    checkpoint_every: int = 25,
    resume: bool = False,
) -> dict[str, Any]:
    """Run the full batch and write envelopes, profiles and a machine-readable report."""
    modules_list = [m.strip() for m in modules if m.strip()]
    started_at = utc_now()
    wall_start = time.monotonic()
    deadline = wall_start + max(1.0, float(budget_seconds))

    organisation_inputs = read_organisation_inputs(organisations_path)
    orgs = [item["organisation_number"] for item in organisation_inputs]
    if expected_count is not None and len(orgs) != expected_count:
        raise SystemExit(f"Expected {expected_count} organisations, received {len(orgs)}")

    profiles, registry_metadata = profiles_from_universe(universe_path, orgs)
    by_org = {profile["organisation_number"]: profile for profile in profiles}
    missing = registry_metadata.get("missing_organisation_numbers") or []

    previous: dict[str, dict[str, Any]] = {}
    if previous_profiles_path and Path(previous_profiles_path).exists():
        rows = [json.loads(line) for line in Path(previous_profiles_path).read_text(encoding="utf-8").splitlines() if line.strip()]
        previous = {row.get("organisation_number"): row for row in rows if row.get("organisation_number")}

    state: dict[str, dict[str, Any]] = {}
    envelopes_by_org: dict[str, dict[str, Any]] = {}
    if resume and Path(profiles_output).exists():
        prior = [json.loads(line) for line in Path(profiles_output).read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in prior:
            org = row.get("organisation_number")
            if org in set(orgs) and all(m in row.get("evidence", {}) for m in modules_list):
                state[org] = row

    def research(org: str) -> dict[str, Any]:
        profile = by_org.get(org) or unresolved_profile(org, "Organisation number absent from the frozen 2025 universe snapshot")
        return research_company(
            dict(profile), modules_list, run_id=run_id, started_at=started_at,
            offline=offline, use_llm=use_llm,
        )

    pending = [org for org in orgs if org not in state]
    timed_out: set[str] = set()
    if pending and time.monotonic() >= deadline:
        timed_out = set(pending)
        pending = []

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
            futures = {pool.submit(research, org): org for org in pending}
            done = 0
            for future in as_completed(futures):
                org = futures[future]
                try:
                    envelope = future.result()
                except Exception:
                    profile = by_org.get(org) or unresolved_profile(org, "envelope construction failed")
                    envelope = build_envelope(
                        profile, run_id=run_id, modules=modules_list,
                        started_at=started_at, completed_at=utc_now(),
                        requests=0, runtime_ms=0, third_party_cost_usd=0.0,
                        errors=[{"module": "runner", "error": traceback.format_exc(limit=2)[:500]}])
                state[org] = envelope["profile"]
                envelopes_by_org[org] = envelope
                done += 1
                if done % checkpoint_every == 0:
                    _write_jsonl(profiles_output, [state[o] for o in orgs if o in state])
                if time.monotonic() >= deadline:
                    timed_out = set(orgs) - set(state)
                    break

    envelopes: list[dict[str, Any]] = []
    for org in orgs:
        if org in envelopes_by_org and org not in timed_out:
            envelope = envelopes_by_org[org]
            if previous.get(org):
                try:
                    envelope["changes"] = diff_profile(previous[org], envelope["profile"])
                except ValueError:
                    envelope["changes"] = []
            envelopes.append(envelope)
        elif org in state and org not in timed_out:
            profile = state[org]
            envelopes.append(build_envelope(
                profile, run_id=run_id, modules=modules_list,
                started_at=started_at, completed_at=utc_now(),
                requests=0, runtime_ms=0, third_party_cost_usd=0.0,
                errors=[], previous=previous.get(org)))
        else:
            # Budget exhausted: still emit a terminal, registry-anchored envelope.
            profile = by_org.get(org) or unresolved_profile(org, "not present in frozen snapshot")
            for module in modules_list:
                if module in ("registry", "accounting_obligation"):
                    continue
                profile["evidence"].setdefault(module, _module_record("not_applicable", "time budget exhausted before fetch"))
            envelopes.append(build_envelope(
                profile, run_id=run_id, modules=modules_list,
                started_at=started_at, completed_at=utc_now(),
                requests=0, runtime_ms=0, third_party_cost_usd=0.0,
                errors=[{"module": "budget", "error": "time budget exhausted; registry-anchored envelope emitted"}]))

    completed_at = utc_now()
    validation = validate_envelopes(envelopes, len(orgs))
    harness_checks = {
        "one_envelope_per_input": len(envelopes) == len(orgs),
        "all_harness_states_legal": all(item.get("status") in HARNESS_STATES for item in envelopes),
        "every_claim_has_evidence": all(
            claim.get("evidence_ids") for item in envelopes for claim in item.get("claims", [])
            if claim.get("availability") == "available"),
        "no_zero_for_missing": all(
            not (claim.get("value") == 0 and claim.get("availability") != "available")
            for item in envelopes for claim in item.get("claims", [])),
        "identity_present_everywhere": all(item.get("identity", {}).get("organisation_number") for item in envelopes),
    }
    _write_jsonl(profiles_output, [state[org] for org in orgs if org in state])
    _write_jsonl(output_path, envelopes)

    latencies = sorted(
        ms for item in envelopes
        for ms in [item.get("operations", {}).get("runtime_ms")]
        if isinstance(ms, int) and ms
    )
    claim_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for item in envelopes:
        key = item.get("status", "failed")
        status_counts[key] = status_counts.get(key, 0) + 1
        for claim in item.get("claims", []):
            if claim.get("availability") == "available":
                claim_counts[claim["field"]] = claim_counts.get(claim["field"], 0) + 1
    report = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "expected_count": len(orgs),
        "emitted_envelopes": len(envelopes),
        "resolved_profiles": len(state),
        "unresolved_organisation_numbers": missing,
        "timed_out_organisation_numbers": sorted(timed_out),
        "modules": modules_list,
        "offline": offline,
        "llm_enabled": use_llm,
        "registry": registry_metadata,
        "status_counts": status_counts,
        "available_claim_counts": dict(sorted(claim_counts.items(), key=lambda kv: -kv[1])),
        "operations": {
            "wall_seconds": round(time.monotonic() - wall_start, 3),
            "requests_total": sum(int(item.get("operations", {}).get("requests") or 0) for item in envelopes),
            "p50_ms": latencies[len(latencies) // 2] if latencies else None,
            "p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
            "third_party_cost_usd": round(sum(
                item.get("operations", {}).get("third_party_cost_usd", 0.0) for item in envelopes), 6),
        },
        "validation": {
            "passed": all(validation["checks"].values()) and all(harness_checks.values()),
            "starter": validation,
            "harness": harness_checks,
        },
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(target)




