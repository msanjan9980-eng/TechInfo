"""Disk cache for Enhetsregisteret roles responses.

Stores fetch meta alongside the payload so a cache hit carries its original
retrieval timestamp into the facts.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_DIR = Path("data/roles")
MAX_AGE_DAYS = 14


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
        "source_url": None,
        "retrieved": fetched,
        "content_sha256": None,
    }
    return payload.get("roles"), meta


def save(orgnr: str, roles: list[dict] | None, meta: dict | None) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": (meta or {}).get("retrieved") or _now_iso(),
        "roles": roles or [],
        "meta": meta,
    }
    _path(orgnr).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )