"""Extract N org numbers from the bulk Enhetsregisteret dump (JSON array format)."""
import gzip
import json
import random
from pathlib import Path

src = Path("data/enheter.json.gz")
out = Path("data/seed_orgnrs.txt")
target = 1200

print(f"Opening {src} ...")
with gzip.open(src, "rt", encoding="utf-8") as fh:
    data = json.load(fh)

# The bulk dump is a bare JSON array, not a HAL envelope.
if isinstance(data, list):
    entities = data
elif isinstance(data, dict):
    entities = data.get("_embedded", {}).get("enheter", [])
else:
    entities = []

print(f"Bulk dump has {len(entities)} entities")

by_form: dict[str, list[str]] = {}
for e in entities:
    orgnr = e.get("organisasjonsnummer")
    form = (e.get("organisasjonsform") or {}).get("kode") or "UNK"
    if not orgnr:
        continue
    by_form.setdefault(form, []).append(orgnr)

print(f"Found {len(by_form)} distinct legal forms")

random.seed(42)
picked: list[str] = []
for form, lst in by_form.items():
    random.shuffle(lst)
    picked.extend(lst[:300])

random.shuffle(picked)
picked = picked[:target]

out.write_text("\n".join(picked), encoding="utf-8")
print(f"Wrote {len(picked)} orgnrs to {out}")
