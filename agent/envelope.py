"""Terminal envelope layer for Signalpost.

One envelope per input organisation number, with a valid availability state.
Semantic shape per the Signalpost evaluation contract:

    legal identity, claims, evidence references, availability states,
    source snapshots, refresh metadata and errors.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

STATE_AVAILABLE = "available"
STATE_NOT_AVAILABLE = "not_available"
STATE_BLOCKED = "blocked"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_AMBIGUOUS = "ambiguous"
STATE_FAILED = "failed"

VALID_STATES = (
    STATE_AVAILABLE,
    STATE_NOT_AVAILABLE,
    STATE_BLOCKED,
    STATE_NOT_APPLICABLE,
    STATE_AMBIGUOUS,
    STATE_FAILED,
)

_IDENTITY_FIELDS = {
    "name",
    "orgnr",
    "legal_form",
    "registered_date",
    "founded_date",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base(orgnr: str, state: str, errors: list[str]) -> dict:
    return {
        "orgnr": orgnr,
        "state": state,
        "legal_identity": None,
        "claims": [],
        "evidence_refs": [],
        "source_snapshots": [],
        "refresh": {"previous_envelope_at": None, "changes": []},
        "errors": list(errors),
    }


def error_envelope(orgnr: str, state: str, errors: list[str]) -> dict:
    if state not in VALID_STATES:
        state = STATE_FAILED
    return _base(orgnr, state, errors)


def _evidence_ref_id(source_url: str) -> str:
    return "e" + hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]


def _claim_id(orgnr: str, index: int) -> str:
    return f"{orgnr}-c{index:04d}"


def _identity_from_facts(facts: list[dict]) -> dict:
    ident: dict[str, Any] = {}
    for f in facts:
        name = f.get("field")
        if name in _IDENTITY_FIELDS:
            ident[name] = f.get("value")
    return ident


def _reporting_period(field: str | None, value: Any) -> str | None:
    if isinstance(value, dict):
        p = value.get("period")
        if isinstance(p, str):
            return p
    if field == "fiscal_year" and isinstance(value, str):
        return value
    return None


def envelope_from_profile(
    orgnr: str,
    profile: dict,
    state: str = STATE_AVAILABLE,
    errors: list[str] | None = None,
) -> dict:
    if state not in VALID_STATES:
        state = STATE_FAILED
    errors = list(errors or [])

    facts = profile.get("facts") or []
    identity = _identity_from_facts(facts)

    claims: list[dict] = []
    evidence_by_url: dict[str, dict] = {}
    source_snapshots: list[str] = []

    for i, f in enumerate(facts):
        field = f.get("field")
        if field in _IDENTITY_FIELDS:
            continue
        url = f.get("source")
        if not url:
            continue
        if url not in evidence_by_url:
            ref_id = _evidence_ref_id(url)
            evidence_by_url[url] = {
                "ref_id": ref_id,
                "source_url": url,
                "retrieved": f.get("retrieved"),
                "content_sha256": f.get("content_sha256"),
                "extraction_method": "api_json",
            }
            source_snapshots.append(url)

        value = f.get("value")
        claims.append(
            {
                "claim_id": _claim_id(orgnr, i),
                "field": field,
                "value": value,
                "reporting_period": _reporting_period(field, value),
                "confidence": f.get("confidence", "high"),
                "evidence_ref": evidence_by_url[url]["ref_id"],
            }
        )

    env = _base(orgnr, state, errors)
    env["legal_identity"] = identity or None
    env["claims"] = claims
    env["evidence_refs"] = list(evidence_by_url.values())
    env["source_snapshots"] = source_snapshots
    return env