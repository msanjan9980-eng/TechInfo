"""Simple disk cache for annual-account responses from Regnskapsregisteret."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_DIR = Path("data/financials")
MAX_AGE_DAYS = 7


def _path(orgnr: str) -> Path:
    return CACHE_DIR / f"{orgnr}.json"


def load(orgnr: str) -> list[dict] | None:
    """Return cached accounts if fresh, else None."""
    p = _path(orgnr)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    fetched = payload.get("fetched_at")
    if not fetched:
        return None
    try:
        when = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    except Exception:
        return None
    age = datetime.now(timezone.utc) - when
    if age > timedelta(days=MAX_AGE_DAYS):
        return None
    return payload.get("accounts")


def save(orgnr: str, accounts: list[dict] | None) -> None:
    """Store the raw accounts list (or empty list for "filed nothing")."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accounts": accounts or [],
    }
    _path(orgnr).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
