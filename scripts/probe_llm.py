"""Probe LLM providers directly: status codes + error messages only (no keys)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

MINIMAL = {
    "temperature": 0.1,
    "max_tokens": 40,
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
}

PROBES = [
    ("groq", "https://api.groq.com/openai/v1/chat/completions",
     os.environ.get("GROQ_API_KEY", ""), os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile"),
    ("groq-list-models", "https://api.groq.com/openai/v1/models",
     os.environ.get("GROQ_API_KEY", ""), None),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions",
     os.environ.get("OPENROUTER_API_KEY", ""), os.environ.get("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct:free"),
]

for name, url, key, model in PROBES:
    if not key:
        print(f"{name}: no key configured")
        continue
    if model:
        payload = dict(MINIMAL, model=model)
        body: bytes | None = json.dumps(payload).encode()
    else:
        body = None
    try:
        response = httpx.post(url if body else url.replace("/chat/completions", "/models"),
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              content=body, timeout=30)
        detail = ""
        if response.status_code != 200:
            try:
                err = response.json().get("error", {})
                detail = str(err.get("message", ""))[:160] + f" type={err.get('type','')}"
            except Exception:
                detail = response.text[:160]
        else:
            if body:
                data = response.json()
                detail = f"reply={data['choices'][0]['message']['content']!r} model={data.get('model')}"
            else:
                ids = [m.get("id") for m in response.json().get("data", [])]
                sample = [i for i in ids if "llama" in i or "mixtral" in i or "qwen" in i][:8]
                detail = f"{len(ids)} models; sample={sample}"
        print(f"{name}: HTTP {response.status_code} — {detail}")
    except Exception as exc:
        print(f"{name}: {type(exc).__name__}: {str(exc)[:140]}")
