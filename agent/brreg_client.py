"""Client for the Norwegian Enhetsregisteret (Bronnoysundregistrene) open API."""
from __future__ import annotations

from typing import Any

import logging
from pathlib import Path as _Path

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

BRREG_BASE = "https://data.brreg.no/enhetsregisteret/api"

_LOG_DIR = _Path("logs")
_LOG_DIR.mkdir(exist_ok=True)
logger = logging.getLogger("brreg")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(_LOG_DIR / "fetch_errors.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)



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
    """Validate a Norwegian organisation number using the MOD11 checksum."""
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
    """Brreg returns names as a dict {fornavn, etternavn} or as a plain string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        parts = [value.get("fornavn"), value.get("etternavn")]
        joined = " ".join(p for p in parts if p).strip()
        return joined or None
    return None


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict | None = None
) -> dict | None:
    resp = await client.get(url, params=params)
    if resp.status_code == 404:
        logger.info(f"404 for {url}")
        return None
    if resp.status_code >= 400:
        logger.warning(f"HTTP {resp.status_code} for {url}")
    resp.raise_for_status()
    return resp.json()


async def fetch_company(
    orgnr: str, client: httpx.AsyncClient
) -> CompanyRecord | None:
    data = await _get_json(client, f"{BRREG_BASE}/enheter/{orgnr}")
    if data is None:
        return None
    return CompanyRecord(**data)


async def fetch_roles(
    orgnr: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    data = await _get_json(client, f"{BRREG_BASE}/enheter/{orgnr}/roller")
    if data is None:
        return []
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
    return out


REGNSKAP_BASE = "https://data.brreg.no/regnskapsregisteret/regnskap"


async def fetch_financials(
    orgnr: str, client: httpx.AsyncClient
) -> list[dict] | None:
    """Return the list of filed annual accounts for a company, or None.

    The Regnskapsregisteret endpoint returns a JSON array with one element
    per filed accounting period, most recent first.
    """
    try:
        data = await _get_json(client, f"{REGNSKAP_BASE}/{orgnr}")
    except httpx.HTTPStatusError:
        return None
    except httpx.HTTPError:
        return None
    if not data:
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return None


async def fetch_updates(
    since_date: str, client: httpx.AsyncClient
) -> list[str]:
    """Return orgnrs updated since `since_date` (YYYY-MM-DD)."""
    data = await _get_json(
        client,
        f"{BRREG_BASE}/oppdateringer/enheter",
        params={"dato": since_date},
    )
    if not data:
        return []
    return [
        e.get("organisasjonsnummer")
        for e in data.get("_embedded", {}).get("enheter", [])
        if e.get("organisasjonsnummer")
    ]
