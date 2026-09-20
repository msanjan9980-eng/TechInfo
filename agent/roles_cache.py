"""Disk cache for Enhetsregisteret roles responses."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_DIR = Path("data/roles")
MAX_AGE_DAYS = 14


def _path(orgnr: str) -> Path:
    return CACHE_DIR / f"{orgnr}.json"


def load(orgnr: str) -> list[dict] | None:
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
    if datetime.now(timezone.utc) - when > timedelta(days=MAX_AGE_DAYS):
        return None
    return payload.get("roles")


def save(orgnr: str, roles: list[dict] | None) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": roles or [],
    }
    _path(orgnr).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
