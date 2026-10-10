"""Client for the NAV Arbeidsplassen job search API.

NAV returns job ads that identify their employer by trade name only, with no
organisation number. Matching to an Enhetsregisteret company is done by exact
normalized name comparison in this module. No fuzzy match: a wrong-company
job claim is a qualification risk, a missing job claim is only a recall loss.

NAV applies rate limits and returns HTTP 429 when called too fast. Calls are
serialized through a small global semaphore and retried with exponential
backoff on 429 and 5xx. After retries exhaust, the caller receives an empty
list plus meta with the final http_status, so the company still gets an
envelope. The rate limit is not silently treated as "no jobs" for scoring.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

NAV_SEARCH = "https://arbeidsplassen.nav.no/stillinger/api/search"
NAV_LISTING = "https://arbeidsplassen.nav.no/stillinger/stilling/{uuid}"

# Serialize NAV traffic globally. NAV rate-limits aggressively.
_NAV_SEMAPHORE: asyncio.Semaphore | None = None
_MAX_RETRIES = 4
_BASE_BACKOFF = 1.5

_PUNCT = re.compile(r"[^\w\s]|_", re.UNICODE)
_WS = re.compile(r"\s+", re.UNICODE)
_SUFFIXES = {
    "as", "asa", "ans", "da", "enk", "sa", "nuf", "kf", "ba", "iks",
    "stiftelse", "forening", "avd", "filial",
}


def _get_semaphore() -> asyncio.Semaphore:
    global _NAV_SEMAPHORE
    if _NAV_SEMAPHORE is None:
        _NAV_SEMAPHORE = asyncio.Semaphore(2)
    return _NAV_SEMAPHORE


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).lower().strip()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _strip_suffix(normalized: str) -> str:
    parts = normalized.split()
    while parts and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts).strip()


def names_match(a: str | None, b: str | None) -> bool:
    """Exact normalized match, with optional Norwegian company-suffix stripping.

    Two names match if their fully-normalized forms are equal, or if their
    suffix-stripped forms are equal and both suffix-stripped forms are non-empty.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    sa, sb = _strip_suffix(na), _strip_suffix(nb)
    return bool(sa) and sa == sb


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job_dict(hit: dict) -> dict | None:
    src = hit.get("_source") or {}
    uuid = src.get("uuid") or src.get("reference")
    if not uuid:
        return None
    employer = src.get("employer") or {}
    locations = src.get("locationList") or []
    loc = locations[0] if locations else {}
    props = src.get("properties") or {}
    return {
        "uuid": str(uuid),
        "title": src.get("title") or props.get("jobtitle"),
        "business_name": src.get("businessName"),
        "employer_name": employer.get("name"),
        "published": src.get("published"),
        "expires": src.get("expires"),
        "status": src.get("status"),
        "city": loc.get("city"),
        "municipal": loc.get("municipal"),
        "county": loc.get("county"),
        "url": NAV_LISTING.format(uuid=uuid),
    }


def exact_match(hits: list[dict], company_name: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for h in hits:
        j = _job_dict(h)
        if j is None:
            continue
        if not (names_match(j.get("business_name"), company_name)
                or names_match(j.get("employer_name"), company_name)):
            continue
        if j["uuid"] in seen:
            continue
        seen.add(j["uuid"])
        out.append(j)
    return out


async def _search_with_retry(
    client: httpx.AsyncClient, params: dict
) -> httpx.Response | None:
    sem = _get_semaphore()
    async with sem:
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.get(NAV_SEARCH, params=params, timeout=25.0)
            except httpx.HTTPError:
                resp = None
            if resp is not None and resp.status_code not in (429, 500, 502, 503, 504):
                return resp
            if attempt < _MAX_RETRIES - 1:
                # Exponential backoff with jitter, capped at 30s.
                delay = min(30.0, _BASE_BACKOFF * (2 ** attempt))
                delay += random.uniform(0, delay * 0.3)
                await asyncio.sleep(delay)
        return resp


async def fetch_jobs(
    company_name: str, client: httpx.AsyncClient
) -> tuple[list[dict], dict | None]:
    """Query NAV for the company name, return (matched_jobs, meta).

    meta carries the real retrieval timestamp and SHA-256 of the raw search
    response, so all job facts from this call share one evidence reference.
    On persistent rate limiting (429) or network failure, returns ([], meta)
    with meta['http_status'] reflecting the last status. Empty list means
    "no jobs" to the caller, but meta records whether it was a rate-limit.
    """
    if not company_name or not company_name.strip():
        return [], None
    params = {"q": company_name, "size": "100"}
    url = f"{NAV_SEARCH}?{urlencode(params)}"
    resp = await _search_with_retry(client, params)
    if resp is None:
        return [], {
            "source_url": url,
            "retrieved": _now_iso(),
            "content_sha256": None,
            "http_status": None,
        }
    meta = {
        "source_url": url,
        "retrieved": _now_iso(),
        "content_sha256": hashlib.sha256(resp.content).hexdigest(),
        "http_status": resp.status_code,
    }
    if resp.status_code >= 400:
        return [], meta
    try:
        data = resp.json()
    except Exception:
        return [], meta
    hits = ((data.get("hits") or {}).get("hits")) or []
    return exact_match(hits, company_name), meta