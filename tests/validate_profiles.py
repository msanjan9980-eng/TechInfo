"""Sanity-check every profile; write machine-readable report."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

failures = 0
total = 0
fact_count = 0
failure_details = []

for p in Path("profiles").glob("*.json"):
    total += 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[BAD JSON] {p.name}: {e}")
        failures += 1
        failure_details.append({"file": p.name, "reason": f"bad json: {e}"})
        continue

    orgnr = data.get("orgnr")
    if not orgnr or orgnr != p.stem:
        print(f"[MISMATCH] {p.name}: orgnr={orgnr}")
        failures += 1
        failure_details.append({"file": p.name, "reason": "orgnr mismatch"})
    if not data.get("name"):
        print(f"[NO NAME] {p.name}")
        failures += 1
        failure_details.append({"file": p.name, "reason": "no name"})
    facts = data.get("facts") or []
    if len(facts) < 5:
        print(f"[THIN] {p.name}: {len(facts)} facts")
        failures += 1
        failure_details.append({"file": p.name, "reason": f"only {len(facts)} facts"})
    for f in facts:
        if not f.get("source") or not f.get("retrieved"):
            print(f"[NO SOURCE] {p.name}: {f.get('field')}")
            failures += 1
            failure_details.append({"file": p.name, "reason": "fact missing source/date"})
            break
    fact_count += len(facts)

summary = {
    "profiles": total,
    "total_facts": fact_count,
    "failures": failures,
    "failure_details": failure_details[:20],
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}

Path("validation_report.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(f"\nProfiles: {total}, total facts: {fact_count}, failures: {failures}")
print("Wrote validation_report.json")
sys.exit(1 if failures else 0)
