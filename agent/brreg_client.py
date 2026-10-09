"""Client for the Norwegian Enhetsregisteret (Bronnoysundregistrene) open API.

Every fetcher returns (payload, meta) where meta carries the real retrieval
timestamp and a SHA-256 of the raw response body. Meta is threaded into facts
and caches so evidence timestamps are the actual fetch times.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

BRREG_BASE = "https://data.brreg.no/enhetsregisteret/api"
REGNSKAP_BASE = "https://data.brreg.no/regnskapsregisteret/regnskap"

_LOG_DIR = _Path("logs")
_LOG_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("brreg")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(_LOG_DIR / "fetch_errors.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CompanyRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    orgnr: str = Field(alias="organisasjonsnummer")
    navn: str
    organisasjonsform: dict | None = None
    registreringsdatoEnhetsregisteret: str | None = None
    stiftelsesdato: str | None = None
    forretningsadresse: dict | None = None
    postadresse: dict | None = None
    naeringskode1: dict | None = None
    naeringskode2: dict | None = None
    antallAnsatte: int | None = None
    konkurs: bool | None = None
    underAvvikling: bool | None = None
    registrertIMvaregisteret: bool | None = None
    registrertIForetaksregisteret: bool | None = None
    sisteInnsendteAarsregnskap: str | None = None
    hjemmeside: str | None = None
    epostadresse: str | None = None
    telefon: str | None = None
    mobil: str | None = None


def validate_orgnr(orgnr: str) -> bool:
    orgnr = orgnr.strip()
    if not orgnr.isdigit() or len(orgnr) != 9:
        return False
    weights = [3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(orgnr[:8], weights))
    remainder = total % 11
    check = 11 - remainder
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(orgnr[8])


def _flatten_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        parts = [value.get("fornavn"), value.get("etternavn")]
        joined = " ".join(p for p in parts if p).strip()
        return joined or None
    return None


def _meta_from_response(resp: httpx.Response) -> dict:
    return {
        "source_url": str(resp.url),
        "retrieved": now_iso(),
        "content_sha256": hashlib.sha256(resp.content).hexdigest(),
        "http_status": resp.status_code,
    }


def _empty_meta(url: str, status: int | None = None) -> dict:
    return {
        "source_url": url,
        "retrieved": now_iso(),
        "content_sha256": None,
        "http_status": status,
    }


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict | None = None
) -> tuple[Any | None, dict]:
    resp = await client.get(url, params=params)
    meta = _meta_from_response(resp)
    if resp.status_code == 404:
        logger.info(f"404 for {url}")
        return None, meta
    if resp.status_code >= 400:
        logger.warning(f"HTTP {resp.status_code} for {url}")
    resp.raise_for_status()
    return resp.json(), meta


async def fetch_company(
    orgnr: str, client: httpx.AsyncClient
) -> tuple[CompanyRecord | None, dict]:
    url = f"{BRREG_BASE}/enheter/{orgnr}"
    data, meta = await _get_json(client, url)
    if data is None:
        return None, meta
    return CompanyRecord(**data), meta


async def fetch_roles(
    orgnr: str, client: httpx.AsyncClient
) -> tuple[list[dict[str, Any]], dict]:
    url = f"{BRREG_BASE}/enheter/{orgnr}/roller"
    data, meta = await _get_json(client, url)
    if data is None:
        return [], meta
    groups = data.get("rollegrupper", []) or []
    out: list[dict[str, Any]] = []
    for group in groups:
        role_type = (group.get("type") or {}).get("kode") or (
            group.get("type") or {}
        ).get("beskrivelse")
        for role in group.get("roller", []) or []:
            person = role.get("person") or {}
            entity = role.get("enhet") or {}
            out.append(
                {
                    "role_group": role_type,
                    "role": (role.get("type") or {}).get("beskrivelse"),
                    "name": _flatten_name(person.get("navn")) or entity.get("navn"),
                    "birth_date": person.get("fodselsdato"),
                    "orgnr": entity.get("organisasjonsnummer"),
                    "fratredelsesdato": role.get("fratredelsesdato"),
                    "valgtDato": role.get("valgtDato"),
                }
            )
    return out, meta


async def fetch_financials(
    orgnr: str, client: httpx.AsyncClient
) -> tuple[list[dict] | None, dict]:
    url = f"{REGNSKAP_BASE}/{orgnr}"
    try:
        data, meta = await _get_json(client, url)
    except httpx.HTTPStatusError as e:
        return None, _empty_meta(url, e.response.status_code)
    except httpx.HTTPError:
        return None, _empty_meta(url, None)
    if not data:
        return None, meta
    if isinstance(data, list):
        return data, meta
    if isinstance(data, dict):
        return [data], meta
    return None, meta


async def fetch_updates(
    since_date: str, client: httpx.AsyncClient
) -> tuple[list[str], dict]:
    url = f"{BRREG_BASE}/oppdateringer/enheter"
    data, meta = await _get_json(client, url, params={"dato": since_date})
    if not data:
        return [], meta
    entries = data.get("_embedded", {}).get("oppdaterteEnheter", []) or []
    return [
        e.get("organisasjonsnummer")
        for e in entries
        if e.get("organisasjonsnummer")
    ], meta