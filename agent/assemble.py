"""Assemble a company profile with facts, sources and dates.

Every fact carries the real retrieval time and content hash of the source
response, provided via source_meta: {source_url: {"retrieved": iso, "content_sha256": hex}}.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .brreg_client import CompanyRecord, REGNSKAP_BASE


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fact(
    field: str,
    value: Any,
    source: str,
    retrieved: str,
    content_sha256: str | None = None,
    confidence: str = "high",
    note: str = "",
) -> dict:
    return {
        "field": field,
        "value": value,
        "source": source,
        "retrieved": retrieved,
        "content_sha256": content_sha256,
        "confidence": confidence,
        "note": note,
    }


def _meta_for(source_meta: dict[str, dict] | None, source_url: str) -> tuple[str, str | None]:
    if not source_meta:
        return _now_iso(), None
    m = source_meta.get(source_url) or {}
    return (m.get("retrieved") or _now_iso()), m.get("content_sha256")


def financial_facts(
    orgnr: str,
    accounts: list[dict] | None,
    source_meta: dict[str, dict] | None = None,
) -> list[dict]:
    if not accounts:
        return []
    src = f"{REGNSKAP_BASE}/{orgnr}"
    retrieved, sha = _meta_for(source_meta, src)
    a = accounts[0]
    valuta = a.get("valuta") or "NOK"
    period = a.get("regnskapsperiode") or {}
    fiscal = f"{period.get('fraDato', '?')}..{period.get('tilDato', '?')}"

    def money(value: Any) -> dict | None:
        if value is None:
            return None
        return {"value": value, "currency": valuta, "period": fiscal}

    facts: list[dict] = []
    facts.append(_fact("fiscal_year", fiscal, src, retrieved, sha,
                       note=f"Reporting period of the most recent filed annual account. Currency: {valuta}."))
    facts.append(_fact("accounting_currency", valuta, src, retrieved, sha,
                       note="Reporting currency of the filed annual accounts. All monetary facts below are in this currency."))
    facts.append(_fact("financials_filing_count", len(accounts), src, retrieved, sha,
                       note="Number of annual-account filings available in Regnskapsregisteret for this company."))

    def add(field: str, value: Any, note: str) -> None:
        wrapped = money(value)
        if wrapped is None:
            return
        facts.append(_fact(field, wrapped, src, retrieved, sha, confidence="high", note=note))

    r = a.get("resultatregnskapResultat") or {}
    d = r.get("driftsresultat") or {}
    di = d.get("driftsinntekter") or {}
    add("revenue", di.get("sumDriftsinntekter"),
        "Operating revenue (sum of operating income) from the most recent annual accounts.")
    add("operating_result", d.get("driftsresultat"),
        "Operating result (EBIT-equivalent) from the most recent annual accounts.")
    add("net_result", r.get("aarsresultat"),
        "Net result for the year (aarsresultat) from the most recent annual accounts.")

    e = a.get("eiendeler") or {}
    add("total_assets", e.get("sumEiendeler"),
        "Total assets at end of the fiscal year.")

    eg = a.get("egenkapitalGjeld") or {}
    ek = eg.get("egenkapital") or {}
    add("equity", ek.get("sumEgenkapital"),
        "Total equity at end of the fiscal year.")
    gj = eg.get("gjeldOversikt") or {}
    add("total_liabilities", gj.get("sumGjeld"),
        "Total liabilities (current + non-current) at end of the fiscal year.")

    return facts


def assemble_profile(
    company: CompanyRecord,
    roles: list[dict],
    source_meta: dict[str, dict] | None = None,
    extra_facts: list[dict] | None = None,
    financials: list[dict] | None = None,
) -> dict:
    orgnr = company.orgnr
    src = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
    roles_src = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller"
    entity_retrieved, entity_sha = _meta_for(source_meta, src)
    roles_retrieved, roles_sha = _meta_for(source_meta, roles_src)

    facts: list[dict] = []

    facts.append(_fact("name", company.navn, src, entity_retrieved, entity_sha,
                       note="Official name in Enhetsregisteret."))
    facts.append(_fact("orgnr", orgnr, src, entity_retrieved, entity_sha,
                       note="Norwegian organisation number (MOD11-validated)."))

    def add(field: str, value: Any, confidence: str = "high", note: str = "") -> None:
        facts.append(_fact(field, value, src, entity_retrieved, entity_sha,
                           confidence=confidence, note=note))

    if company.organisasjonsform:
        add("legal_form", company.organisasjonsform.get("beskrivelse"),
            note="Registered legal form (organisasjonsform).")
    if company.registreringsdatoEnhetsregisteret:
        add("registered_date", company.registreringsdatoEnhetsregisteret,
            note="Date of registration in Enhetsregisteret.")
    if company.stiftelsesdato:
        add("founded_date", company.stiftelsesdato,
            note="Founding date as recorded in Enhetsregisteret.")
    if company.forretningsadresse:
        add("business_address", company.forretningsadresse,
            note="Registered business address.")
    if company.postadresse:
        add("postal_address", company.postadresse,
            note="Registered postal address.")
    if company.naeringskode1:
        add("nace_code", company.naeringskode1,
            note="Primary industry code (NACE / SN2007).")
    if company.naeringskode2:
        add("nace_code_secondary", company.naeringskode2,
            note="Secondary industry code.")
    if company.antallAnsatte is not None:
        add("employees", company.antallAnsatte,
            note="Headcount as reported to Enhetsregisteret. Brreg hides counts below 5.")
    if company.registrertIMvaregisteret is not None:
        add("vat_registered", company.registrertIMvaregisteret,
            note="Whether the company is registered in the Norwegian VAT register (MVA).")
    if company.registrertIForetaksregisteret is not None:
        add("foretaksregisteret", company.registrertIForetaksregisteret,
            note="Whether the company is registered in Foretaksregisteret.")
    if company.konkurs is not None:
        add("bankrupt", company.konkurs,
            note="Bankruptcy flag. false means no open bankruptcy at retrieval time.")
    if company.underAvvikling is not None:
        add("under_liquidation", company.underAvvikling,
            note="Liquidation flag.")
    if company.hjemmeside:
        add("website", company.hjemmeside, confidence="medium",
            note="Website as self-reported to Enhetsregisteret.")
    if company.epostadresse:
        add("email", company.epostadresse, confidence="medium",
            note="Email as self-reported to Enhetsregisteret.")
    if company.telefon:
        add("phone", company.telefon, confidence="medium",
            note="Phone as self-reported to Enhetsregisteret.")
    if company.mobil:
        add("mobile", company.mobil, confidence="medium",
            note="Mobile as self-reported to Enhetsregisteret.")
    if company.sisteInnsendteAarsregnskap:
        add("last_annual_account", company.sisteInnsendteAarsregnskap,
            note="Date of most recently submitted annual accounts per Enhetsregisteret.")

    for r in roles:
        role_label = r.get("role") or r.get("role_group") or "role"
        facts.append(_fact(
            f"role:{role_label}",
            {"name": r.get("name"), "orgnr": r.get("orgnr"),
             "since": r.get("valgtDato"), "until": r.get("fratredelsesdato")},
            roles_src, roles_retrieved, roles_sha, confidence="high",
            note=f"Registered role from Enhetsregisteret. Role group: {r.get('role_group')}.",
        ))

    facts.extend(financial_facts(orgnr, financials, source_meta))

    if extra_facts:
        facts.extend(extra_facts)

    return {
        "orgnr": orgnr,
        "name": company.navn,
        "facts": facts,
        "sources_used": ["brreg", "regnskapsregisteret"] if financials else ["brreg"],
        "last_updated": _now_iso(),
    }