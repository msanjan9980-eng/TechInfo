"""Assemble a company profile with facts, sources and dates.

Every fact carries the real retrieval time and content hash of the source
response, provided via source_meta: {source_url: {"retrieved": iso, "content_sha256": hex}}.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .brreg_client import CompanyRecord, REGNSKAP_BASE
from .nav_client import NAV_SEARCH


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


def _join_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        if not parts:
            return None
        return " ".join(parts)
    return None


def _parent_parts(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, str):
        s = value.strip()
        return (s or None), None
    if isinstance(value, dict):
        orgnr = value.get("organisasjonsnummer") or value.get("orgnr")
        name = value.get("navn") or value.get("name")
        if orgnr is not None:
            orgnr = str(orgnr)
        if name is not None:
            name = str(name)
        return orgnr, name
    return None, None


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


def job_facts(
    jobs: list[dict] | None,
    jobs_meta: dict | None,
) -> list[dict]:
    """Emit one fact per exact-company-matched NAV job listing."""
    if not jobs:
        return []
    src = (jobs_meta or {}).get("source_url") or NAV_SEARCH
    retrieved = (jobs_meta or {}).get("retrieved") or _now_iso()
    sha = (jobs_meta or {}).get("content_sha256")

    facts: list[dict] = []
    for j in jobs:
        uuid = j.get("uuid")
        if not uuid:
            continue
        value = {
            "title": j.get("title"),
            "business_name": j.get("business_name"),
            "employer_name": j.get("employer_name"),
            "published": j.get("published"),
            "expires": j.get("expires"),
            "city": j.get("city"),
            "municipal": j.get("municipal"),
            "county": j.get("county"),
            "url": j.get("url"),
        }
        facts.append(_fact(
            f"job:{uuid}",
            value,
            src,
            retrieved,
            sha,
            confidence="high",
            note="Active NAV Arbeidsplassen job listing matched to this company by exact normalized name.",
        ))
    return facts


def assemble_profile(
    company: CompanyRecord,
    roles: list[dict],
    source_meta: dict[str, dict] | None = None,
    extra_facts: list[dict] | None = None,
    financials: list[dict] | None = None,
    jobs: list[dict] | None = None,
    jobs_meta: dict | None = None,
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

    activity = _join_text(getattr(company, "aktivitet", None))
    if activity:
        add("activity", activity,
            note="Registered business activity text from Enhetsregisteret.")

    purpose = _join_text(getattr(company, "vedtektsfestetFormaal", None))
    if purpose:
        add("purpose", purpose,
            note="Articles-of-association purpose from Enhetsregisteret.")

    sector = getattr(company, "institusjonellSektorkode", None)
    if isinstance(sector, dict) and (sector.get("kode") or sector.get("beskrivelse")):
        add("sector_code", {
            "kode": sector.get("kode"),
            "beskrivelse": sector.get("beskrivelse"),
        }, note="Institutional sector code (institusjonell sektorkode).")

    sole = getattr(company, "erEnkeltpersonforetak", None)
    if sole is not None:
        add("sole_proprietorship", bool(sole),
            note="Whether the entity is registered as a sole proprietorship (enkeltpersonforetak).")

    has_emp = getattr(company, "harRegistrertAntallAnsatte", None)
    if has_emp is not None:
        add("has_registered_employee_count", bool(has_emp),
            note="Whether an employee count is registered in Enhetsregisteret.")

    last_change = getattr(company, "sisteEndring", None)
    if last_change:
        add("last_registry_change", last_change,
            note="Date of the most recent change recorded in Enhetsregisteret.")

    parent_orgnr, parent_name = _parent_parts(getattr(company, "overordnetEnhet", None))
    if parent_orgnr or parent_name:
        add("parent", {"orgnr": parent_orgnr, "name": parent_name},
            note="Parent entity (overordnet enhet) as recorded in Enhetsregisteret.")

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
    facts.extend(job_facts(jobs, jobs_meta))

    if extra_facts:
        facts.extend(extra_facts)

    sources = ["brreg"]
    if financials:
        sources.append("regnskapsregisteret")
    if jobs:
        sources.append("nav-arbeidsplassen")

    return {
        "orgnr": orgnr,
        "name": company.navn,
        "facts": facts,
        "sources_used": sources,
        "last_updated": _now_iso(),
    }