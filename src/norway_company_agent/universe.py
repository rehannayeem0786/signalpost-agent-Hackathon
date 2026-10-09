"""Frozen Builderr company-universe loader.

The public universe file (``signalpost-company-universe-2025.jsonl.gz``) is the
frozen 2025-filer identity snapshot published by Builderr. It carries the same
profile keys as the Brreg bulk CSV row normalizer, so profiles built from it are
drop-in compatible with ``batch.profiles_from_bulk``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from .evidence import evidence, utc_now
from .official import accounting_obligation_assessment

PROFILE_KEYS = (
    "organisation_number",
    "name",
    "legal_form",
    "employees",
    "bankrupt",
    "liquidating",
    "municipality",
    "municipality_number",
    "industry_code",
    "industry_label",
    "website",
    "latest_submitted_accounts",
)


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig")
    return path.open("r", encoding="utf-8-sig")


def iter_universe(path: str | Path) -> Iterator[dict[str, Any]]:
    source = Path(path)
    with _open_text(source) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if len(str(row.get("organisation_number") or "")) == 9:
                yield row


def normalize_universe_row(row: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {key: row.get(key) for key in PROFILE_KEYS if key != "organisation_number"}
    record["organisation_number"] = str(row.get("organisation_number") or "")
    employees = record.get("employees")
    record["employees"] = int(employees) if employees not in (None, "") else None
    for flag in ("bankrupt", "liquidating"):
        value = record.get(flag)
        if isinstance(value, str):
            record[flag] = value.casefold() == "true"
        else:
            record[flag] = bool(value)
    return record


def profiles_from_universe(path: str | Path, organisation_numbers: Iterable[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build starter-compatible profiles from the frozen Builderr universe file."""
    requested = list(organisation_numbers)
    wanted = set(requested)
    snapshot_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    retrieved_at = utc_now()
    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    for row in iter_universe(path):
        scanned += 1
        org = str(row["organisation_number"])
        if org not in wanted:
            continue
        profile = normalize_universe_row(row)
        profile["evidence"] = {
            "registry": evidence(
                "registry",
                "available",
                "official_registry_bulk",
                "https://builderr.ai/signalpost-company-universe-2025.jsonl.gz",
                value=dict(row),
                retrieved_at=retrieved_at,
                content_sha256=snapshot_sha256,
                source_row_key=org,
                as_of=str(row.get("latest_submitted_accounts") or "") or None,
            ),
            "accounting_obligation": accounting_obligation_assessment(profile),
        }
        found[org] = profile
        if len(found) == len(wanted):
            break
    missing = [org for org in requested if org not in found]
    selected = [found[org] for org in requested if org in found]
    return selected, {
        "registry_snapshot_sha256": snapshot_sha256,
        "registry_rows_scanned": scanned,
        "requested": len(requested),
        "selected": len(selected),
        "missing_organisation_numbers": missing,
    }
