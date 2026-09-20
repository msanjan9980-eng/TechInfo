"""Look up a single Norwegian company by organisation number.

Usage:
    python -m agent.lookup 923609016
    python -m agent.lookup 923609016 --summary
    python -m agent.lookup 923609016 --output profiles/923609016.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from . import cache, roles_cache
from .brreg_client import fetch_company, fetch_financials, fetch_roles, validate_orgnr
from .assemble import assemble_profile


async def _lookup(orgnr: str) -> dict | None:
    if not validate_orgnr(orgnr):
        print(f"Invalid orgnr: {orgnr} (fails MOD11 checksum)", file=sys.stderr)
        return None
    headers = {"User-Agent": "norwegian-company-agent/1.0 (research)"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        company = await fetch_company(orgnr, client)
        if company is None:
            print(f"Company not found in Enhetsregisteret: {orgnr}", file=sys.stderr)
            return None
        roles = roles_cache.load(orgnr)
        if roles is None:
            try:
                roles = await fetch_roles(orgnr, client)
            except Exception as e:
                print(f"Roles fetch failed: {e}", file=sys.stderr)
                roles = []
            roles_cache.save(orgnr, roles)
        financials = cache.load(orgnr)
        if financials is None:
            try:
                financials = await fetch_financials(orgnr, client)
            except Exception:
                financials = None
            cache.save(orgnr, financials)
        return assemble_profile(company, roles, financials=financials or [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Look up one Norwegian company by orgnr.")
    ap.add_argument("orgnr", help="Norwegian organisation number (9 digits)")
    ap.add_argument("--output", "-o", help="Write profile JSON to this path")
    ap.add_argument("--summary", action="store_true", help="Print a short summary")
    args = ap.parse_args()

    profile = asyncio.run(_lookup(args.orgnr))
    if profile is None:
        return 1

    if args.summary:
        print(f"Company : {profile['name']}")
        print(f"Orgnr   : {profile['orgnr']}")
        print(f"Facts   : {len(profile['facts'])}")
        print(f"Sources : {', '.join(profile['sources_used'])}")
        print()
        for f in profile["facts"]:
            if f["field"] in ("legal_form", "employees", "revenue", "net_result", "total_assets", "equity"):
                v = f["value"]
                if isinstance(v, dict):
                    v = f"{v.get('value'):,} {v.get('currency')}"
                print(f"  {f['field']:14s} = {v}")
        return 0

    text = json.dumps(profile, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
