"""Claim-level diff between two terminal envelopes.

Produces typed change records for the envelope's refresh.changes list. Claims
are matched by a stable identity key: the field name, plus (for multi-valued
fields such as roles) a discriminator derived from the claim value itself.
"""
from __future__ import annotations

from typing import Any


def _identity_of(claim: dict) -> tuple[str, str]:
    """Return (field, discriminator). Discriminator is empty for singletons.

    For role:* fields, the discriminator is the person or entity name so that
    multiple board members are matched individually rather than colliding on
    the field name.
    """
    field = str(claim.get("field") or "")
    discriminator = ""
    if field.startswith("role:"):
        v = claim.get("value")
        if isinstance(v, dict):
            name = v.get("name")
            if isinstance(name, list):
                name = "|".join(str(x) for x in name)
            discriminator = str(name or "")
    return field, discriminator


def _family(field: str) -> str:
    f = field.lower()
    if f.startswith("role:"):
        return "role"
    if f.startswith("job") or f.startswith("jobs."):
        return "job"
    if "address" in f or "location" in f:
        return "location"
    if f in {
        "fiscal_year", "financials_filing_count", "last_annual_account",
        "accounting_currency",
        "revenue", "operating_result", "net_result",
        "total_assets", "equity", "total_liabilities",
    }:
        return "filing"
    if f in {"parent", "parent_orgnr", "parent_name"}:
        return "group"
    return "generic"


_FAMILY_CHANGE = {
    "role":     {"add": "new_role",         "remove": "removed_role",     "change": "changed_role"},
    "job":      {"add": "new_job",          "remove": "closed_job",       "change": "changed_job"},
    "location": {"add": "new_location",     "remove": "removed_location", "change": "changed_location"},
    "filing":   {"add": "new_filing",       "remove": "removed_filing",   "change": "changed_filing"},
    "group":    {"add": "new_parent",       "remove": "removed_parent",   "change": "changed_parent"},
    "generic":  {"add": "new_claim",        "remove": "removed_claim",    "change": "changed_value"},
}


def _change_name(field: str, kind: str) -> str:
    return _FAMILY_CHANGE[_family(field)][kind]


def _value(claim: dict) -> Any:
    return claim.get("value")


def _period(claim: dict) -> str | None:
    p = claim.get("reporting_period")
    return p if isinstance(p, str) else None


def diff_claims(
    old_claims: list[dict],
    new_claims: list[dict],
    observed_at: str,
) -> list[dict]:
    """Return a list of typed change records between two claim lists."""
    old_by_key: dict[tuple[str, str], dict] = {}
    for c in old_claims or []:
        old_by_key[_identity_of(c)] = c
    new_by_key: dict[tuple[str, str], dict] = {}
    for c in new_claims or []:
        new_by_key[_identity_of(c)] = c

    changes: list[dict] = []
    for key in sorted(set(old_by_key) | set(new_by_key)):
        field, discriminator = key
        old = old_by_key.get(key)
        new = new_by_key.get(key)

        if old is None and new is not None:
            changes.append({
                "change_type": _change_name(field, "add"),
                "field": field,
                "discriminator": discriminator,
                "previous": None,
                "current": _value(new),
                "previous_period": None,
                "current_period": _period(new),
                "observed_at": observed_at,
            })
        elif old is not None and new is None:
            changes.append({
                "change_type": _change_name(field, "remove"),
                "field": field,
                "discriminator": discriminator,
                "previous": _value(old),
                "current": None,
                "previous_period": _period(old),
                "current_period": None,
                "observed_at": observed_at,
            })
        elif _value(old) != _value(new) or _period(old) != _period(new):
            changes.append({
                "change_type": _change_name(field, "change"),
                "field": field,
                "discriminator": discriminator,
                "previous": _value(old),
                "current": _value(new),
                "previous_period": _period(old),
                "current_period": _period(new),
                "observed_at": observed_at,
            })
    return changes