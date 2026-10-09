"""Publication-gate tests: news title matching and website candidate generation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.news import exact_title_match  # noqa: E402
from norway_company_agent.website import guess_website_candidates  # noqa: E402


def test_full_legal_name_matches_headline():
    assert exact_title_match("EQUINOR ASA", "Equinor ASA: eksutbytte første kvartal")


def test_possessive_stem_matches_two_token_company():
    # Tier 2 + Norwegian possessive tolerance ("Elektriskes")
    assert exact_title_match("SANDNES ELEKTRISKE AS", "Sandnes Elektriskes årsrapport er klar")


def test_single_token_stem_never_matches_alone():
    # Precision-first: a one-token stem must not match headlines on its own.
    assert not exact_title_match("EQUINOR ASA", "Equinors årsrapport for 2024")


def test_reversed_or_partial_words_do_not_match():
    assert not exact_title_match("SANDNES ELEKTRISKE AS", "Elektriske nyheter fra Sandnes")
    assert not exact_title_match("SANDNES ELEKTRISKE AS", "Sandnes")


def test_parent_brand_does_not_claim_subsidiary():
    # Storebrand subsidiary must not publish parent-brand headlines.
    assert not exact_title_match("STOREBRAND TILLERTORGET AS", "Storebrand kutter utbytte")


def test_generic_word_company_not_matched():
    assert not exact_title_match("EIENDOM AS", "Slik er eiendomsmarkedet i år")


def test_website_candidates_are_https_bounded_slugs():
    candidates = guess_website_candidates("SANDNES ELEKTRISKE AS")
    assert candidates
    assert len(candidates) <= 2
    assert all(c.startswith("https://") and c.endswith(".no") for c in candidates)
    assert not any("as" in c.split("//")[1].split(".")[0] and c.split("//")[1].split(".")[0] == "as" for c in candidates)


def test_website_candidates_empty_for_short_or_generic_names():
    assert guess_website_candidates("AS") == []
    assert guess_website_candidates(None) == []
