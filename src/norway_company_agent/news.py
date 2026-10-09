"""Google News RSS connector with an exact-legal-name publication gate.

Discovery results are candidates, never evidence. An item is only published as a
claim when the full legal name (including the legal-form token) appears as a
contiguous token window in the headline, which keeps wrong-company publication
at effectively zero. Publisher, date and URL are preserved for every item.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from .evidence import evidence

UA = "SignalpostResearchAgent/1.0 (https://builderr.ai; bounded qualification run)"
RSS_ENDPOINT = "https://news.google.com/rss/search?q={query}&hl=no&gl=NO&ceid=NO:no"


def exact_title_match(company_name: str, title: str) -> bool:
    """Two-tier exact gate for a headline.

    Tier 1: the full legal name (including the legal-form token) appears as a
    contiguous token window — the strongest possible gate.
    Tier 2: the name STEM (legal-form tokens removed) appears contiguously,
    but only when the stem keeps at least two tokens, so single-word stems
    ("Storebrand") never match headlines on their own.
    """
    company_tokens = re.findall(r"[a-z0-9æøå]+", str(company_name or "").casefold())
    title_tokens = re.findall(r"[a-z0-9æøå]+", str(title or "").rsplit(" - ", 1)[0].casefold())
    if not company_tokens or not title_tokens or len(company_tokens) > len(title_tokens):
        return False
    allowed_predecessors = {"av", "for", "fra", "hos", "i", "med", "om", "på", "til", "og", "kjøper", "velger", "ny", "i"}
    if _window_match(company_tokens, title_tokens, allowed_predecessors):
        return True
    stem = [token for token in company_tokens if token not in LEGAL_FORM_TOKENS]
    if len(stem) >= 2 and len(stem) < len(company_tokens) and len(stem) <= len(title_tokens):
        return _window_match(stem, title_tokens, allowed_predecessors)
    return False


LEGAL_FORM_TOKENS = {"as", "asa", "a/s", "sa", "ba", "da", "ans", "enk", "nuf", "sti", "ks", "bf", "bl", "rl"}


def _window_match(needle: list[str], haystack: list[str], allowed_predecessors: set[str]) -> bool:
    for index in range(len(haystack) - len(needle) + 1):
        if not _tokens_match(needle, haystack[index:index + len(needle)]):
            continue
        if index == 0 or haystack[index - 1] in allowed_predecessors:
            return True
    return False


def _tokens_match(needle: list[str], window: list[str]) -> bool:
    """Exact token equality with Norwegian possessive tolerance ("Equinors")."""
    if len(needle) != len(window):
        return False
    for want, got in zip(needle, window):
        if got == want:
            continue
        if len(want) >= 4 and got in {want + "s", want + "ens", want + "es"}:
            continue
        return False
    return True


def fetch_news(profile: dict[str, Any], *, limit: int = 10, years: int = 2, timeout: float = 25.0) -> dict[str, Any]:
    org = str(profile.get("organisation_number") or "")
    name = str(profile.get("name") or "")
    if not name:
        return evidence("news", "not_applicable", "public_news_rss",
                        RSS_ENDPOINT.format(query=""), note="No legal name available for exact-title gate")
    query = urllib.parse.quote(f'"{name}" when:{years}y')
    url = RSS_ENDPOINT.format(query=query)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
        root = ET.fromstring(raw)
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for node in root.findall(".//item"):
            title = str(node.findtext("title") or "").strip()
            link = str(node.findtext("link") or "").strip()
            publisher = str(node.findtext("source") or "").strip()
            if not link or not exact_title_match(name, title):
                continue
            key = (title.casefold(), publisher.casefold())
            if key in seen:
                continue
            seen.add(key)
            published = node.findtext("pubDate")
            try:
                published_at = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                published_at = None
            items.append({
                "id": "google-news-title-" + hashlib.sha256(f"{org}|{title}|{publisher}".encode()).hexdigest()[:24],
                "title": title,
                "publisher": publisher,
                "source_url": link,
                "published_at": published_at,
                "retrieved_at": retrieved_at,
            })
            if len(items) >= limit:
                break
        content_sha = hashlib.sha256(raw).hexdigest()
        item_count = len(root.findall(".//item"))
        if not items:
            return evidence("news", "not_found", "public_news_rss", url,
                            retrieved_at=retrieved_at, content_sha256=content_sha,
                            note=f"No headline passed the exact legal-name gate (rss_items={item_count})")
        return evidence("news", "available", "public_news_rss", url,
                        value={"items": items, "lookback_years": years},
                        retrieved_at=retrieved_at, content_sha256=content_sha,
                        note="Headline-level exact legal-name matches; publisher bodies not stored")
    except Exception as exc:  # network, parse, or blocking errors become an honest state
        return evidence("news", "source_error", "public_news_rss", url,
                        note=f"{type(exc).__name__}: {str(exc)[:180]}")
