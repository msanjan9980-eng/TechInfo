"""Sanity-check every profile: has orgnr, name, at least 5 facts, every fact has source+date."""
import json
import sys
from pathlib import Path

failures = 0
total = 0
fact_count = 0

for p in Path("profiles").glob("*.json"):
    total += 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[BAD JSON] {p.name}: {e}")
        failures += 1
        continue

    orgnr = data.get("orgnr")
    if not orgnr or orgnr != p.stem:
        print(f"[MISMATCH] {p.name}: orgnr={orgnr}")
        failures += 1
    if not data.get("name"):
        print(f"[NO NAME] {p.name}")
        failures += 1
    facts = data.get("facts") or []
    if len(facts) < 5:
        print(f"[THIN] {p.name}: {len(facts)} facts")
        failures += 1
    for f in facts:
        if not f.get("source") or not f.get("retrieved"):
            print(f"[NO SOURCE] {p.name}: {f.get('field')}")
            failures += 1
            break
    fact_count += len(facts)

print(f"\nProfiles: {total}, total facts: {fact_count}, failures: {failures}")
sys.exit(1 if failures else 0)
