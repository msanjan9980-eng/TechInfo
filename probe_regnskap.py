"""Probe the Regnskapsregisteret API for a known company."""
import httpx
import json

orgnr = "923609016"  # Equinor ASA

candidates = [
    f"https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}",
    f"https://data.brreg.no/regnskapsregisteret/regnskap?orgnr={orgnr}",
    f"https://data.brreg.no/regnskapsregisteret/api/regnskap/{orgnr}",
]

for url in candidates:
    print("=" * 70)
    print(f"GET {url}")
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        print(f"  status       : {r.status_code}")
        print(f"  content-type : {r.headers.get('content-type', 'unknown')}")
        print(f"  content-len  : {len(r.content)}")
        if r.status_code == 200:
            try:
                data = r.json()
                print("  json type    :", type(data).__name__)
                if isinstance(data, list):
                    print(f"  list length  : {len(data)}")
                    if data:
                        print("  first item keys:", sorted(data[0].keys()) if isinstance(data[0], dict) else "not a dict")
                        print()
                        print("  --- first item preview ---")
                        print(json.dumps(data[0], indent=2, ensure_ascii=False)[:2500])
                elif isinstance(data, dict):
                    print("  dict keys    :", sorted(data.keys()))
                    print()
                    print("  --- preview ---")
                    print(json.dumps(data, indent=2, ensure_ascii=False)[:2500])
            except Exception as e:
                print(f"  json parse failed: {e}")
                print("  raw preview:", r.text[:500])
        else:
            print("  raw preview:", r.text[:300])
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    print()
