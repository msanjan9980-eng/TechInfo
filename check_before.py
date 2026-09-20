import json
from pathlib import Path
p = next(Path("profiles").glob("*.json"))
d = json.loads(p.read_text(encoding="utf-8"))
print(f"File     : {p.name}")
print(f"Company  : {d['name']}")
print(f"Updated  : {d['last_updated']}")
