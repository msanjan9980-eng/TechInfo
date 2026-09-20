"""Assemble a company profile with facts, sources and dates."""
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


def financial_facts(orgnr: str, accounts: list[dict] | None) -> list[dict]:
    """Turn a Regnskapsregisteret response into structured facts."""
    if not accounts:
        return []
    src = f"{REGNSKAP_BASE}/{orgnr}"
    a = accounts[0]
    valuta = a.get("valuta") or "NOK"
    period = a.get("regnskapsperiode") or {}
    fiscal = f"{period.get('fraDato', '?')}..{period.get('tilDato', '?')}"

    def money(value: Any) -> dict | None:
        if value is None:
            return None
        return {"value": value, "currency": valuta, "period": fiscal}

    facts: list[dict] = []

    facts.append(
        _fact(
            "fiscal_year",
            fiscal,
            src,
            note=f"Reporting period of the most recent filed annual account. Currency: {valuta}.",
        )
    )
    facts.append(
        _fact(
            "accounting_currency",
            valuta,
            src,
            note="Reporting currency of the filed annual accounts. All monetary facts below are in this currency.",
        )
    )
    facts.append(
        _fact(
            "financials_filing_count",
            len(accounts),
            src,
            note="Number of annual-account filings available in Regnskapsregisteret for this company.",
        )
    )

    def add(field: str, value: Any, note: str) -> None:
        wrapped = money(value)
        if wrapped is None:
            return
        facts.append(_fact(field, wrapped, src, confidence="high", note=note))

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
    extra_facts: list[dict] | None = None,
    financials: list[dict] | None = None,
) -> dict:
    orgnr = company.orgnr
    src = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
    roles_src = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller"

    facts: list[dict] = []

    facts.append(_fact("name", company.navn, src, note="Official name in Enhetsregisteret."))
    facts.append(_fact("orgnr", orgnr, src, note="Norwegian organisation number (MOD11-validated)."))

    if company.organisasjonsform:
        facts.append(_fact("legal_form", company.organisasjonsform.get("beskrivelse"), src,
                           note="Registered legal form (organisasjonsform)."))
    if company.registreringsdatoEnhetsregisteret:
        facts.append(_fact("registered_date", company.registreringsdatoEnhetsregisteret, src,
                           note="Date of registration in Enhetsregisteret."))
    if company.stiftelsesdato:
        facts.append(_fact("founded_date", company.stiftelsesdato, src,
                           note="Founding date as recorded in Enhetsregisteret."))
    if company.forretningsadresse:
        facts.append(_fact("business_address", company.forretningsadresse, src,
                           note="Registered business address."))
    if company.postadresse:
        facts.append(_fact("postal_address", company.postadresse, src,
                           note="Registered postal address."))
    if company.naeringskode1:
        facts.append(_fact("nace_code", company.naeringskode1, src,
                           note="Primary industry code (NACE / SN2007)."))
    if company.naeringskode2:
        facts.append(_fact("nace_code_secondary", company.naeringskode2, src,
                           note="Secondary industry code."))
    if company.antallAnsatte is not None:
        facts.append(_fact("employees", company.antallAnsatte, src,
                           note="Headcount as reported to Enhetsregisteret. Brreg hides counts below 5."))
    if company.registrertIMvaregisteret is not None:
        facts.append(_fact("vat_registered", company.registrertIMvaregisteret, src,
                           note="Whether the company is registered in the Norwegian VAT register (MVA)."))
    if company.registrertIForetaksregisteret is not None:
        facts.append(_fact("foretaksregisteret", company.registrertIForetaksregisteret, src,
                           note="Whether the company is registered in Foretaksregisteret."))
    if company.konkurs is not None:
        facts.append(_fact("bankrupt", company.konkurs, src,
                           note="Bankruptcy flag. false means no open bankruptcy at retrieval time."))
    if company.underAvvikling is not None:
        facts.append(_fact("under_liquidation", company.underAvvikling, src,
                           note="Liquidation flag."))
    if company.hjemmeside:
        facts.append(_fact("website", company.hjemmeside, src, confidence="medium",
                           note="Website as self-reported to Enhetsregisteret."))
    if company.epostadresse:
        facts.append(_fact("email", company.epostadresse, src, confidence="medium",
                           note="Email as self-reported to Enhetsregisteret."))
    if company.telefon:
        facts.append(_fact("phone", company.telefon, src, confidence="medium",
                           note="Phone as self-reported to Enhetsregisteret."))
    if company.mobil:
        facts.append(_fact("mobile", company.mobil, src, confidence="medium",
                           note="Mobile as self-reported to Enhetsregisteret."))
    if company.sisteInnsendteAarsregnskap:
        facts.append(_fact("last_annual_account", company.sisteInnsendteAarsregnskap, src,
                           note="Date of most recently submitted annual accounts per Enhetsregisteret."))

    for r in roles:
        role_label = r.get("role") or r.get("role_group") or "role"
        facts.append(_fact(
            f"role:{role_label}",
            {"name": r.get("name"), "orgnr": r.get("orgnr"),
             "since": r.get("valgtDato"), "until": r.get("fratredelsesdato")},
            roles_src, confidence="high",
            note=f"Registered role from Enhetsregisteret. Role group: {r.get('role_group')}.",
        ))

    facts.extend(financial_facts(orgnr, financials))

    if extra_facts:
        facts.extend(extra_facts)

    return {
        "orgnr": orgnr,
        "name": company.navn,
        "facts": facts,
        "sources_used": ["brreg", "regnskapsregisteret"] if financials else ["brreg"],
        "last_updated": _now_iso(),
    }
