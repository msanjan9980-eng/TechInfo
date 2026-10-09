"""Validate that every file in envelopes/ is a well-formed terminal envelope."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VALID_STATES = {
    "available",
    "not_available",
    "blocked",
    "not_applicable",
    "ambiguous",
    "failed",
}

REQUIRED_KEYS = {
    "orgnr",
    "state",
    "generated_at",
    "legal_identity",
    "claims",
    "evidence_refs",
    "source_snapshots",
    "refresh",
    "errors",
}


def main() -> int:
    root = Path("envelopes")
    if not root.exists():
        print("[error] envelopes/ directory not found; run ./run.sh first")
        return 1

    failures: list[dict] = []
    total = 0
    state_counts = {s: 0 for s in VALID_STATES}
    claim_count = 0
    evidence_count = 0
    change_count = 0
    envelopes_with_changes = 0

    for p in sorted(root.glob("*.json")):
        total += 1
        try:
            env = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append({"file": p.name, "reason": f"bad json: {e}"})
            continue

        missing = REQUIRED_KEYS - set(env.keys())
        if missing:
            failures.append({"file": p.name, "reason": f"missing keys: {sorted(missing)}"})
            continue

        if env.get("orgnr") != p.stem:
            failures.append({"file": p.name, "reason": f"orgnr mismatch: {env.get('orgnr')}"})
            continue

        state = env.get("state")
        if state not in VALID_STATES:
            failures.append({"file": p.name, "reason": f"invalid state: {state}"})
            continue
        state_counts[state] += 1

        claims = env.get("claims") or []
        claim_count += len(claims)
        evidence_count += len(env.get("evidence_refs") or [])

        ref_ids = {e.get("ref_id") for e in env.get("evidence_refs") or []}
        for c in claims:
            if c.get("evidence_ref") not in ref_ids:
                failures.append(
                    {
                        "file": p.name,
                        "reason": f"claim {c.get('claim_id')} points to missing evidence_ref",
                    }
                )
                break

        refresh = env.get("refresh") or {}
        if "changes" not in refresh or "previous_envelope_at" not in refresh:
            failures.append({"file": p.name, "reason": "refresh missing required keys"})
            continue
        changes = refresh.get("changes") or []
        change_count += len(changes)
        if changes:
            envelopes_with_changes += 1

    summary = {
        "envelopes": total,
        "claims": claim_count,
        "evidence_refs": evidence_count,
        "changes": change_count,
        "envelopes_with_changes": envelopes_with_changes,
        "state_counts": state_counts,
        "failures": len(failures),
        "failure_details": failures[:20],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    Path("validation_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())