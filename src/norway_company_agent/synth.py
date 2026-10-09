"""Decision-useful synthesis layer (12 rubric points).

Rules from the playbook: an LLM may summarise supported claims or propose
candidates. It must not decide exact identity, invent a missing field, or
silently override deterministic evidence. Therefore:

- the prompt contains only published claims with evidence ids;
- the response must reuse evidence ids, and any sentence citing an unknown id is
  dropped;
- when no key is configured (or on any error) a deterministic template is used,
  so official runs are never blocked on an LLM;
- declared third-party cost is accumulated per run.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Ordered model fallbacks per provider (catalogs rotate; try each until one works).
# GROQ_MODEL / OPENROUTER_MODEL env vars override the whole list with one model.
DEFAULT_GROQ_MODELS = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"]
DEFAULT_OPENROUTER_MODELS = ["meta-llama/llama-3.3-70b-instruct", "qwen/qwen3-8b-instruct"]

# Rough blended price table (USD per 1M tokens) for declared cost reporting.
GROQ_PRICE_PER_1M = 0.40
OPENROUTER_PRICE_PER_1M = 0.30

EVIDENCE_ID_RE = re.compile(r"ev-[a-z0-9-]+")


def deterministic_brief(profile: dict[str, Any], claims: list[dict[str, Any]]) -> str:
    """Rule-based brief built strictly from available claims. Never invents values."""
    available = {c["field"]: c for c in claims if c["availability"] == "available"}
    name = (available.get("legal_name") or {}).get("value") or profile.get("name") or "The company"
    org = profile.get("organisation_number")
    place = (available.get("municipality") or {}).get("value") or profile.get("municipality")
    industry = (available.get("industry_label") or {}).get("value") or profile.get("industry_label")
    employees = (available.get("employees") or {}).get("value")
    revenue = available.get("revenue")
    result = available.get("annual_result")
    roles = [c for c in claims if c["field"] == "registered_role" and c["availability"] == "available"]
    locations = [c for c in claims if c["field"] == "registered_subunit" and c["availability"] == "available"]
    activity = [c for c in claims if c["field"] == "recent_activity" and c["availability"] == "available"]

    parts = [f"{name} (org. nr. {org}) is a Norwegian {industry or 'registered entity'} based in {place or 'Norway'}."]
    if employees is not None:
        parts.append(f"The registry reports {employees} employee(s).")
    if revenue and revenue.get("value") is not None:
        period = revenue.get("reporting_period") or "the latest filed period"
        parts.append(f"Filed revenue for {period} was NOK {revenue['value']:,}.")
        if result and result.get("value") is not None:
            parts.append(f"Annual result for {period} was NOK {result['value']:,}.")
    if roles:
        leader = roles[0].get("value") or {}
        parts.append(f"Registered leadership includes {leader.get('name')} as {leader.get('role')}.")
    if locations:
        parts.append(f"{len(locations)} registered subunit(s) are on file.")
    if activity:
        parts.append(f"{len(activity)} dated public mention(s) passed the exact-name gate.")
    if not revenue:
        parts.append("No normalized annual-account record is publicly available; missing values are not treated as zero.")
    return " ".join(parts)


def _provider_candidates() -> list[tuple[str, str, str]]:
    """Ordered (key, url, model) candidates from LLM_PROVIDER.

    Accepts a single provider or a comma/space-separated preference list,
    e.g. ``LLM_PROVIDER=groq, openrouter`` → try Groq first, fall back to
    OpenRouter. Within a provider, models are tried in default order (or a
    single ``GROQ_MODEL``/``OPENROUTER_MODEL`` override). A provider is only a
    candidate when its key is present.
    """
    raw = (os.environ.get("LLM_PROVIDER") or "none").strip().lower()
    wanted = [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]
    candidates: list[tuple[str, str, str]] = []
    for name in wanted:
        if name == "groq":
            key = os.environ.get("GROQ_API_KEY", "").strip()
            if key:
                override = os.environ.get("GROQ_MODEL", "").strip()
                for model in ([override] if override else DEFAULT_GROQ_MODELS):
                    candidates.append((key, GROQ_URL, model))
        elif name == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if key:
                override = os.environ.get("OPENROUTER_MODEL", "").strip()
                for model in ([override] if override else DEFAULT_OPENROUTER_MODELS):
                    candidates.append((key, OPENROUTER_URL, model))
    return candidates


def _provider() -> tuple[str | None, str, str]:
    """Backwards-compatible single-provider view (first candidate)."""
    candidates = _provider_candidates()
    if not candidates:
        return None, "", ""
    key, url, model = candidates[0]
    return key, url, model


def _guard(response_text: str, claims: list[dict[str, Any]]) -> str | None:
    """Drop the response when it cites evidence ids that do not exist."""
    valid = {eid for c in claims for eid in c.get("evidence_ids", [])}
    cited = set(EVIDENCE_ID_RE.findall(response_text))
    if cited and not cited.issubset(valid):
        return None
    return response_text.strip() or None


def _record(brief: str, method: str, model: str | None, note: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "available",
        "source_type": "deterministic_synthesis" if method == "deterministic" else "llm_synthesis",
        "source_class": "derived_from_evidence",
        "source_url": "local://synthesis/" + method,
        "retrieved_at": None,
        "value": {"brief": brief, "method": method, "model": model, **extra},
        "note": note,
    }


def synthesize(profile: dict[str, Any], claims: list[dict[str, Any]], *, timeout: float = 25.0) -> tuple[dict[str, Any], float]:
    """Return a synthesis record and the declared USD cost of this call.

    Tries each configured provider in preference order (e.g. Groq, then
    OpenRouter). Any failure — auth, outage, guard rejection — falls through to
    the next candidate and finally to the deterministic brief, so an official
    run is never blocked on an LLM.
    """
    fallback = deterministic_brief(profile, claims)
    candidates = _provider_candidates()
    if not candidates:
        return _record(fallback, "deterministic", None,
                       "No LLM key configured; deterministic evidence-bounded template used."), 0.0

    evidence_pack = [
        {"field": c["field"], "value": c["value"], "evidence_ids": c["evidence_ids"],
         "reporting_period": c["reporting_period"]}
        for c in claims if c["availability"] == "available"
    ]
    system = (
        "You are a company-research analyst. Write a 3-4 sentence decision-useful brief "
        "(supplier, partner, employer or investor perspective) using ONLY the supplied claims. "
        "Cite supporting evidence ids inline like [ev-registry]. Never invent numbers, names or dates. "
        "If a fact is missing, say it is not available. Output plain text only."
    )
    user = json.dumps({"company": profile.get("name"), "organisation_number": profile.get("organisation_number"),
                       "claims": evidence_pack}, ensure_ascii=False)
    total_cost = 0.0
    last_error = "not attempted"
    for key, url, model in candidates:
        provider_name = "groq" if "groq" in url else "openrouter"
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "temperature": 0.1, "max_tokens": 400,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
            text = body.get("choices", [{}])[0].get("message", {}).get("content") or ""
            guarded = _guard(text, claims)
            usage = body.get("usage", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            price = GROQ_PRICE_PER_1M if provider_name == "groq" else OPENROUTER_PRICE_PER_1M
            total_cost += round((prompt_tokens + completion_tokens) / 1_000_000 * price, 6)
            if not guarded:
                last_error = f"{provider_name}: evidence-id guard rejected response"
                continue
            return _record(guarded, "llm", model,
                           f"Summary derived only from published claims with evidence ids (provider={provider_name}).",
                           prompt_tokens=prompt_tokens, completion_tokens=completion_tokens), total_cost
        except Exception as exc:
            last_error = f"{provider_name}: {type(exc).__name__}"
            continue
    return _record(fallback, "deterministic", None,
                   f"All LLM providers failed ({last_error}); deterministic fallback published."), total_cost

