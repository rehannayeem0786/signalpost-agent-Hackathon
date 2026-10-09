"""Synthesis layer tests: provider preference parsing, evidence guard, determinism.

No network calls — these cover the configuration and safety logic only; the
live provider path is verified manually via the smoke runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.synth import (  # noqa: E402
    DEFAULT_GROQ_MODELS,
    DEFAULT_OPENROUTER_MODELS,
    GROQ_URL,
    OPENROUTER_URL,
    _guard,
    _provider_candidates,
    deterministic_brief,
)


def test_provider_preference_list_parsing(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq, openrouter")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    candidates = _provider_candidates()
    urls = [url for _key, url, _model in candidates]
    assert set(urls) == {GROQ_URL, OPENROUTER_URL}
    # All Groq models come first, then OpenRouter models (preference order).
    assert urls[0] == GROQ_URL
    assert urls.index(OPENROUTER_URL) == len(DEFAULT_GROQ_MODELS)
    models = [model for _key, _url, model in candidates]
    assert len(models) == len(set(models)), "no duplicate model candidates"


def test_provider_single_value(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    candidates = _provider_candidates()
    assert candidates
    assert all(url == OPENROUTER_URL for _key, url, _model in candidates)
    assert len(candidates) == len(DEFAULT_OPENROUTER_MODELS)


def test_provider_skips_missing_keys(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq, openrouter")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert _provider_candidates() == []
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    candidates = _provider_candidates()
    assert len(candidates) == len(DEFAULT_GROQ_MODELS)
    assert all(url == GROQ_URL for _key, url, _model in candidates)


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GROQ_MODEL", "my-custom-model")
    candidates = _provider_candidates()
    assert [model for _k, _u, model in candidates] == ["my-custom-model"]


def test_provider_none_disables(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert _provider_candidates() == []


def test_guard_rejects_unknown_evidence_ids():
    claims = [{"evidence_ids": ["ev-registry"]}]
    assert _guard("Facts from [ev-financials] here.", claims) is None


def test_guard_accepts_valid_or_absent_citations():
    claims = [{"evidence_ids": ["ev-registry"]}]
    assert _guard("Based on [ev-registry] only.", claims) == "Based on [ev-registry] only."
    assert _guard("No citations at all.", claims) == "No citations at all."


def test_deterministic_brief_uses_available_claims_only():
    profile = {"name": "ACME AS", "organisation_number": "810034882"}
    claims = [
        {"field": "legal_name", "value": "ACME AS", "availability": "available"},
        {"field": "municipality", "value": "OSLO", "availability": "available"},
        {"field": "revenue", "value": None, "availability": "not_available"},
        {"field": "registered_role", "value": {"name": "Ada Nordmann", "role": "daglig leder"},
         "availability": "available"},
    ]
    brief = deterministic_brief(profile, claims)
    assert "ACME AS" in brief and "OSLO" in brief and "Ada Nordmann" in brief
    # Missing revenue is stated honestly, never invented or zeroed.
    assert "No normalized annual-account record is publicly available" in brief
    assert "not treated as zero" in brief
