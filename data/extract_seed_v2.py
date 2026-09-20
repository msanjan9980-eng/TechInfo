"""Blend 1000 annual-account filers with 200 non-filers for diversity."""
import gzip, json, random
from pathlib import Path

with gzip.open("data/enheter.json.gz", "rt", encoding="utf-8") as fh:
    entities = json.load(fh)

filers, non_filers = [], []
for e in entities:
    o = e.get("organisasjonsnummer")
    if not o: continue
    if not e.get("forretningsadresse"): continue
    if not e.get("naeringskode1"): continue
    if e.get("sisteInnsendteAarsregnskap"):
        filers.append(o)
    else:
        non_filers.append(o)

print(f"Filers pool     : {len(filers)}")
print(f"Non-filers pool : {len(non_filers)}")

random.seed(42)
picked = random.sample(filers, 1000) + random.sample(non_filers, 200)
random.shuffle(picked)

Path("data/seed_orgnrs.txt").write_text("\n".join(picked) + "\n", encoding="utf-8")
print(f"Wrote {len(picked)} orgnrs (1000 filers + 200 non-filers) to data/seed_orgnrs.txt")
