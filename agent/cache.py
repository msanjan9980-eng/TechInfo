"""Disk cache for annual-account responses from Regnskapsregisteret.

Stores both the payload and the fetch meta (retrieval time, content SHA-256),
so a cache hit still carries the original retrieval timestamp into the facts.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .brreg_client import REGNSKAP_BASE

CACHE_DIR = Path("data/financials")
MAX_AGE_DAYS = 7


def _path(orgnr: str) -> Path:
    return CACHE_DIR / f"{orgnr}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(orgnr: str) -> tuple[list[dict] | None, dict | None]:
    p = _path(orgnr)
    if not p.exists():
        return None, None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    fetched = payload.get("fetched_at")
    if not fetched:
        return None, None
    try:
        when = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    except Exception:
        return None, None
    if datetime.now(timezone.utc) - when > timedelta(days=MAX_AGE_DAYS):
        return None, None
    meta = payload.get("meta") or {
        "source_url": f"{REGNSKAP_BASE}/{orgnr}",
        "retrieved": fetched,
        "content_sha256": None,
    }
    return payload.get("accounts"), meta


def save(orgnr: str, accounts: list[dict] | None, meta: dict | None) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": (meta or {}).get("retrieved") or _now_iso(),
        "accounts": accounts or [],
        "meta": meta,
    }
    _path(orgnr).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )