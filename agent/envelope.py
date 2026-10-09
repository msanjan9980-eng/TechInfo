"""Terminal envelope layer for Signalpost.

One envelope per input organisation number, with a valid availability state.
Semantic shape per the Signalpost evaluation contract: legal identity, claims,
evidence references, availability states, source snapshots, refresh metadata
and errors.
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
        "generated_at": _now_iso(),
        "legal_identity": None,
        "claims": [],
        "evidence_refs": [],
        "source_snapshots": [],
        "refresh": {
            "previous_envelope_at": None,
            "observed_at": _now_iso(),
            "changes": [],
        },
        "errors": list(errors),
    }


def error_envelope(orgnr: str, state: str, errors: list[str]) -> dict:
    if state not in VALID_STATES:
        state = STATE_FAILED
    return _base(orgnr, state, errors)


def _evidence_ref_id(source_url: str, content_sha256: str | None) -> str:
    """Stable evidence id. Same URL with different content hashes to different ids."""
    key = f"{source_url}|{content_sha256 or ''}"
    return "e" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


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
    evidence_by_key: dict[tuple[str, str], dict] = {}
    source_snapshots: list[str] = []

    for i, f in enumerate(facts):
        field = f.get("field")
        if field in _IDENTITY_FIELDS:
            continue
        url = f.get("source")
        if not url:
            continue
        sha = f.get("content_sha256")
        key = (url, sha or "")
        if key not in evidence_by_key:
            ref_id = _evidence_ref_id(url, sha)
            evidence_by_key[key] = {
                "ref_id": ref_id,
                "source_url": url,
                "retrieved": f.get("retrieved"),
                "content_sha256": sha,
                "extraction_method": "api_json",
            }
            if url not in source_snapshots:
                source_snapshots.append(url)

        value = f.get("value")
        claims.append(
            {
                "claim_id": _claim_id(orgnr, i),
                "field": field,
                "value": value,
                "reporting_period": _reporting_period(field, value),
                "confidence": f.get("confidence", "high"),
                "evidence_ref": evidence_by_key[key]["ref_id"],
            }
        )

    env = _base(orgnr, state, errors)
    env["legal_identity"] = identity or None
    env["claims"] = claims
    env["evidence_refs"] = list(evidence_by_key.values())
    env["source_snapshots"] = source_snapshots
    return env


def merge_evidence_refs(old_refs: list[dict] | None, new_refs: list[dict] | None) -> list[dict]:
    """Union of evidence refs, keyed by (source_url, content_sha256).

    When the same (url, sha) pair exists in both, the new entry wins, so ref_ids
    stay consistent with the current run's claims. Evidence whose sha no longer
    appears in the new run is preserved from the old envelope unchanged.
    """
    merged: dict[tuple[str, str], dict] = {}
    for r in old_refs or []:
        url = r.get("source_url")
        if not url:
            continue
        merged[(url, r.get("content_sha256") or "")] = r
    for r in new_refs or []:
        url = r.get("source_url")
        if not url:
            continue
        merged[(url, r.get("content_sha256") or "")] = r
    return list(merged.values())


def merge_source_snapshots(old_snaps: list[str] | None, new_snaps: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in list(old_snaps or []) + list(new_snaps or []):
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def apply_refresh(env: dict, previous_env: dict | None) -> dict:
    """Fill env['refresh'] by diffing against previous_env (may be None)."""
    if previous_env is None:
        env["refresh"] = {
            "previous_envelope_at": None,
            "observed_at": env.get("generated_at") or _now_iso(),
            "changes": [],
        }
        return env

    from .diff import diff_claims

    prev_at = previous_env.get("generated_at")
    if not prev_at:
        prev_refresh = previous_env.get("refresh") or {}
        prev_at = prev_refresh.get("observed_at") or prev_refresh.get("previous_envelope_at")

    observed_at = env.get("generated_at") or _now_iso()
    changes = diff_claims(
        previous_env.get("claims") or [],
        env.get("claims") or [],
        observed_at,
    )
    env["refresh"] = {
        "previous_envelope_at": prev_at,
        "observed_at": observed_at,
        "changes": changes,
    }
    return env