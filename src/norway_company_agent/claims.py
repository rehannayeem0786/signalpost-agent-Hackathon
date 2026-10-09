"""Flatten an enriched profile into contract-level claims and evidence rows.

Guarantees enforced here:
- every published claim references at least one evidence id;
- missing values are emitted as ``not_available`` with ``value: null`` (never 0);
- evidence rows carry source url, retrieval time, content hash and a span;
- only identity-gated website content can be published (see ``identity.py``).
"""

from __future__ import annotations

import re
from typing import Any

AVAILABILITY_BY_STATUS = {
    "available": "available",
    "not_found": "not_available",
    "not_applicable": "not_applicable",
    "blocked": "blocked",
    "source_error": "failed",
    "not_fetched": "not_applicable",
}

PHONE_RE = re.compile(r"(?:\+47)?\s?(?:\d[\d\s-]{7,12}\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _evidence_row(record: dict[str, Any], evidence_id: str, *, claim_span: str | None = None) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "source_url": record.get("source_url"),
        "source_class": record.get("source_class") or record.get("source_type"),
        "retrieved_at": record.get("retrieved_at"),
        "content_sha256": record.get("content_sha256"),
        "reporting_period": record.get("as_of") or record.get("effective_at"),
        "claim_span": claim_span,
    }


def _claim(
    field: str,
    value: Any,
    availability: str,
    evidence_id: str,
    *,
    confidence: float = 1.0,
    reporting_period: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "field": field,
        "value": value if availability == "available" else None,
        "availability": availability,
        "confidence": round(float(confidence), 3),
        "evidence_ids": [evidence_id] if evidence_id else [],
        "reporting_period": reporting_period,
    }
    if note:
        row["note"] = note
    return row


def _availability(record: dict[str, Any] | None) -> str:
    if not record:
        return "not_applicable"
    return AVAILABILITY_BY_STATUS.get(str(record.get("status")), "failed")


def build_claims(profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claims: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    evidence_index: dict[str, dict[str, Any]] = {}

    def register(evidence_id: str, record: dict[str, Any], *, claim_span: str | None = None) -> str:
        if evidence_id not in evidence_index:
            evidence_index[evidence_id] = _evidence_row(record, evidence_id, claim_span=claim_span)
            evidence_rows.append(evidence_index[evidence_id])
        elif claim_span and not evidence_index[evidence_id].get("claim_span"):
            evidence_index[evidence_id]["claim_span"] = claim_span
        return evidence_id

    ev = profile.get("evidence", {})

    # --- Official registry identity (always anchored by organisation number) ---
    registry = ev.get("registry") or {}
    registry_value = registry.get("value") or {}
    live_value = (ev.get("registry_live") or {}).get("value") or {}
    registry_id = register("ev-registry", registry, claim_span=f"organisation_number={profile.get('organisation_number')}")
    reg_availability = _availability(registry)

    def _identity_value(key: str):
        """Prefer the frozen snapshot, fall back to the live registry module."""
        value = profile.get(key)
        if value in (None, ""):
            value = live_value.get(key)
        if value in (None, "") and key == "website":
            value = live_value.get("website") or registry_value.get(key)
        return value

    for field, key in (
        ("legal_name", "name"),
        ("organisation_number", "organisation_number"),
        ("legal_form", "legal_form"),
        ("municipality", "municipality"),
        ("municipality_number", "municipality_number"),
        ("industry_code", "industry_code"),
        ("industry_label", "industry_label"),
        ("employees", "employees"),
        ("registry_website", "website"),
        ("latest_submitted_accounts", "latest_submitted_accounts"),
    ):
        value = _identity_value(key)
        if reg_availability == "available" and value not in (None, ""):
            claims.append(_claim(field, value, "available", registry_id, confidence=1.0,
                                 reporting_period=registry.get("as_of")))
        else:
            claims.append(_claim(field, None, "not_available" if reg_availability == "available" else reg_availability,
                                 registry_id, confidence=0.0))
    for field, key in (("is_bankrupt", "bankrupt"), ("is_liquidating", "liquidating")):
        value = profile.get(key)
        if reg_availability == "available" and isinstance(value, bool):
            claims.append(_claim(field, value, "available", registry_id, confidence=1.0))
    business_address = registry_value.get("forretningsadresse") or profile.get("business_address")
    claims.append(_claim(
        "business_address",
        business_address,
        "available" if business_address else "not_available",
        registry_id,
        confidence=1.0,
    ))

    # --- Accounting obligation rule path ---
    obligation = ev.get("accounting_obligation") or {}
    if obligation.get("status") == "available":
        obligation_id = register("ev-accounting-obligation", obligation)
        claims.append(_claim("accounting_obligation", (obligation.get("value") or {}).get("classification"),
                             "available", obligation_id, confidence=0.9,
                             reporting_period=obligation.get("as_of")))

    # --- Official annual accounts (financials) ---
    financials = ev.get("financials") or {}
    fin_availability = _availability(financials)
    financial_id = register("ev-financials", financials)
    records = (financials.get("value") or {}).get("records") or []
    if fin_availability == "available" and records:
        latest = records[0]
        period = str(latest.get("period") or "") or None
        for field, key in (
            ("revenue", "revenue"),
            ("operating_result", "operating_result"),
            ("annual_result", "annual_result"),
            ("total_assets", "assets"),
            ("total_debt", "debt"),
            ("equity", "equity"),
        ):
            value = latest.get(key)
            if value is None:
                claims.append(_claim(field, None, "not_available", financial_id, confidence=0.0,
                                     reporting_period=period))
            else:
                claims.append(_claim(field, value, "available", financial_id, confidence=1.0,
                                     reporting_period=period))
        claims.append(_claim("reporting_period", period, "available" if period else "not_available",
                             financial_id, confidence=1.0, reporting_period=period))
    else:
        for field in ("revenue", "operating_result", "annual_result", "total_assets", "total_debt", "equity", "reporting_period"):
            claims.append(_claim(field, None, fin_availability if fin_availability != "available" else "not_available",
                                 financial_id, confidence=0.0))

    history = ev.get("financial_history") or {}
    if history.get("status") == "available":
        history_id = register("ev-financial-history", history)
        years = (history.get("value") or {}).get("years") or []
        claims.append(_claim("available_filing_years", years or None,
                             "available" if years else "not_available", history_id, confidence=0.95))

    # --- Official roles (board / management) ---
    roles = ev.get("roles") or {}
    roles_availability = _availability(roles)
    roles_id = register("ev-roles", roles)
    role_items = [item for item in ((roles.get("value") or {}).get("roles") or []) if not item.get("inactive")]
    if roles_availability == "available" and role_items:
        for index, person in enumerate(role_items[:20]):
            span = f"{person.get('role') or ''} {person.get('name') or ''}".strip()
            span_id = register(f"ev-roles-{index + 1}", roles, claim_span=span)
            claims.append(_claim(
                "registered_role",
                {"role": person.get("role"), "name": person.get("name"), "group": person.get("group"),
                 "from_date": person.get("from_date")},
                "available", span_id, confidence=0.98,
            ))
    else:
        claims.append(_claim("registered_role", None,
                             roles_availability if roles_availability != "available" else "not_available",
                             roles_id, confidence=0.0))

    # --- Registered subunits (locations) ---
    locations = ev.get("locations") or {}
    locations_availability = _availability(locations)
    locations_id = register("ev-locations", locations)
    location_items = (locations.get("value") or {}).get("locations") or []
    if locations_availability == "available" and location_items:
        for index, item in enumerate(location_items[:50]):
            span = f"{item.get('name')} {item.get('address')}".strip()
            span_id = register(f"ev-locations-{index + 1}", locations, claim_span=span)
            claims.append(_claim("registered_subunit", item, "available", span_id, confidence=0.98))
    else:
        claims.append(_claim("registered_subunit", None,
                             locations_availability if locations_availability != "available" else "not_available",
                             locations_id, confidence=0.0))

    group = ev.get("group") or {}
    if group.get("status") == "available":
        group_id = register("ev-group", group)
        claims.append(_claim("group_structure", group.get("value"), "available", group_id, confidence=0.95))

    # --- Company website (identity-gated) ---
    website = ev.get("website") or {}
    website_availability = _availability(website)
    website_id = register("ev-website", website)
    value = website.get("value") or {}
    assessment = value.get("identity_assessment") or {}
    publishable = bool(assessment.get("publishable", website_availability == "available"))
    if website_availability == "available" and publishable:
        claims.append(_claim("official_website", value.get("final_url") or profile.get("website"),
                             "available", website_id, confidence=0.97))
        claims.append(_claim("website_title", value.get("title") or None,
                             "available" if value.get("title") else "not_available",
                             register("ev-website-title", website, claim_span=str(value.get("title") or "")[:200]),
                             confidence=0.9))
        description = value.get("description") or None
        claims.append(_claim("company_description", description,
                             "available" if description else "not_available",
                             register("ev-website-description", website, claim_span=str(description or "")[:300]),
                             confidence=0.85))
        for link in value.get("social_links") or []:
            if not link.get("publishable", True):
                continue
            claims.append(_claim(f"social_profile_{link.get('platform')}", link.get("url"), "available",
                                 register(f"ev-social-{link.get('platform')}", website, claim_span=link.get("url")),
                                 confidence=0.9))
        for org in (value.get("structured_organisations") or [])[:3]:
            for field, raw in (("contact_phone", org.get("telephone")), ("contact_email", org.get("email")),
                               ("registered_address", org.get("address"))):
                if raw:
                    claims.append(_claim(field, raw, "available",
                                         register(f"ev-jsonld-{field}", website, claim_span=str(raw)[:200]),
                                         confidence=0.85))
            if org.get("foundingDate"):
                claims.append(_claim("founding_date", org["foundingDate"], "available",
                                     register("ev-jsonld-founding", website, claim_span=str(org["foundingDate"])),
                                     confidence=0.8))
        pages = value.get("pages") or []
        careers = [p for p in pages if re.search(r"career|job|karriere|stilling", str(p.get("url") or ""), re.I)]
        news_pages = [p for p in pages if re.search(r"news|nyheter|aktuelt|press", str(p.get("url") or ""), re.I)]
        claims.append(_claim("careers_page", careers[0]["url"] if careers else None,
                             "available" if careers else "not_available",
                             register("ev-website-careers", website), confidence=0.8))
        claims.append(_claim("news_page", news_pages[0]["url"] if news_pages else None,
                             "available" if news_pages else "not_available",
                             register("ev-website-news", website), confidence=0.8))
        text = " ".join(str(p.get("main_text_excerpt") or "") for p in pages)[:20000]
        phone = PHONE_RE.search(text)
        email = EMAIL_RE.search(text)
        if not any(c["field"] == "contact_phone" for c in claims):
            claims.append(_claim("contact_phone", phone.group(0).strip() if phone else None,
                                 "available" if phone else "not_available",
                                 register("ev-website-phone", website), confidence=0.7))
        if not any(c["field"] == "contact_email" for c in claims):
            claims.append(_claim("contact_email", email.group(0) if email else None,
                                 "available" if email else "not_available",
                                 register("ev-website-email", website), confidence=0.7))
    else:
        state = "ambiguous" if website_availability == "available" else website_availability
        claims.append(_claim("official_website", None, state, website_id, confidence=0.0,
                             note="Website content withheld: exact-entity gate did not pass."))
        for field in ("website_title", "company_description", "careers_page", "news_page",
                      "contact_phone", "contact_email", "registered_address"):
            claims.append(_claim(field, None, state, website_id, confidence=0.0))

    # --- Dated public activity (news RSS, exact legal-name gate) ---
    news = ev.get("news") or {}
    news_availability = _availability(news)
    news_id = register("ev-news", news)
    news_items = (news.get("value") or {}).get("items") or []
    if news_availability == "available" and news_items:
        for index, item in enumerate(news_items[:10]):
            span_id = register(f"ev-news-{index + 1}", news, claim_span=str(item.get("title") or "")[:300])
            claims.append(_claim(
                "recent_activity",
                {"title": item.get("title"), "publisher": item.get("publisher"),
                 "published_at": item.get("published_at"), "url": item.get("source_url")},
                "available", span_id, confidence=0.9,
                reporting_period=str(item.get("published_at") or "")[:10] or None,
            ))
    else:
        claims.append(_claim("recent_activity", None,
                             news_availability if news_availability != "available" else "not_available",
                             news_id, confidence=0.0))

    return claims, evidence_rows


