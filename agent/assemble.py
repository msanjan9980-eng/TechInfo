"""Assemble a company profile with facts, sources and dates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .brreg_client import CompanyRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fact(
    field: str,
    value: Any,
    source: str,
    confidence: str = "high",
    note: str = "",
) -> dict:
    return {
        "field": field,
        "value": value,
        "source": source,
        "retrieved": _now_iso(),
        "confidence": confidence,
        "note": note,
    }


def assemble_profile(
    company: CompanyRecord,
    roles: list[dict],
    extra_facts: list[dict] | None = None,
) -> dict:
    orgnr = company.orgnr
    src = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
    roles_src = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller"

    facts: list[dict] = []

    facts.append(_fact("name", company.navn, src))
    facts.append(_fact("orgnr", orgnr, src))

    if company.organisasjonsform:
        facts.append(_fact("legal_form", company.organisasjonsform.get("beskrivelse"), src))
    if company.registreringsdatoEnhetsregisteret:
        facts.append(_fact("registered_date", company.registreringsdatoEnhetsregisteret, src))
    if company.stiftelsesdato:
        facts.append(_fact("founded_date", company.stiftelsesdato, src))
    if company.forretningsadresse:
        facts.append(_fact("business_address", company.forretningsadresse, src))
    if company.postadresse:
        facts.append(_fact("postal_address", company.postadresse, src))
    if company.naeringskode1:
        facts.append(_fact("nace_code", company.naeringskode1, src))
    if company.naeringskode2:
        facts.append(_fact("nace_code_secondary", company.naeringskode2, src))
    if company.antallAnsatte is not None:
        facts.append(_fact("employees", company.antallAnsatte, src, note="Official registry employee count"))
    if company.registrertIMvaregisteret is not None:
        facts.append(_fact("vat_registered", company.registrertIMvaregisteret, src))
    if company.registrertIForetaksregisteret is not None:
        facts.append(_fact("foretaksregisteret", company.registrertIForetaksregisteret, src))
    if company.konkurs is not None:
        facts.append(_fact("bankrupt", company.konkurs, src))
    if company.underAvvikling is not None:
        facts.append(_fact("under_liquidation", company.underAvvikling, src))
    if company.hjemmeside:
        facts.append(_fact("website", company.hjemmeside, src, confidence="medium"))
    if company.epostadresse:
        facts.append(_fact("email", company.epostadresse, src, confidence="medium"))
    if company.telefon:
        facts.append(_fact("phone", company.telefon, src, confidence="medium"))
    if company.mobil:
        facts.append(_fact("mobile", company.mobil, src, confidence="medium"))
    if company.sisteInnsendteAarsregnskap:
        facts.append(_fact("last_annual_account", company.sisteInnsendteAarsregnskap, src, note="Date of most recent submitted annual accounts"))

    for r in roles:
        role_label = r.get("role") or r.get("role_group") or "role"
        facts.append(
            _fact(
                f"role:{role_label}",
                {
                    "name": r.get("name"),
                    "orgnr": r.get("orgnr"),
                    "since": r.get("valgtDato"),
                    "until": r.get("fratredelsesdato"),
                },
                roles_src,
                confidence="high",
                note=f"Role group: {r.get('role_group')}",
            )
        )

    if extra_facts:
        facts.extend(extra_facts)

    return {
        "orgnr": orgnr,
        "name": company.navn,
        "facts": facts,
        "sources_used": ["brreg"],
        "last_updated": _now_iso(),
    }
