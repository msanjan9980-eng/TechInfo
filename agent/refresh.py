"""Refresh profiles using the Brreg 'oppdateringer' delta endpoint.

Only fetches companies that changed in Enhetsregisteret in the last N days
AND that we already track. Reuses roles and financial caches when fresh.

Usage:
    python -m agent.refresh --days 1
    python -m agent.refresh --days 7
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm_asyncio

from . import cache, roles_cache
from .brreg_client import fetch_company, fetch_financials, fetch_roles
from .assemble import assemble_profile


async def refresh_one(orgnr: str, client: httpx.AsyncClient, out_dir: Path) -> bool:
    try:
        company = await fetch_company(orgnr, client)
    except Exception:
        return False
    if company is None:
        return False
    roles = roles_cache.load(orgnr)
    if roles is None:
        try:
            roles = await fetch_roles(orgnr, client)
        except Exception:
            roles = []
        roles_cache.save(orgnr, roles)
    financials = cache.load(orgnr)
    if financials is None:
        try:
            financials = await fetch_financials(orgnr, client)
        except Exception:
            financials = None
        cache.save(orgnr, financials)
    profile = assemble_profile(company, roles, financials=financials or [])
    (out_dir / f"{orgnr}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


async def run(days: int, out_dir: Path, concurrency: int = 8) -> int:
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")
    url = "https://data.brreg.no/enhetsregisteret/api/oppdateringer/enheter"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, params={"dato": since, "size": 2000})
        r.raise_for_status()
        data = r.json()
        entries = data.get("_embedded", {}).get("oppdaterteEnheter", [])
        total = (data.get("page") or {}).get("totalElements", len(entries))
        print(f"Registry reports {total} change events since {since}")
        print(f"Fetched first page: {len(entries)} entries")

        # Build a set of tracked orgnrs that had a non-deletion change
        changed_orgnrs = set()
        for e in entries:
            kind = (e.get("endringstype") or "").lower()
            if kind == "slettet":
                continue
            o = e.get("organisasjonsnummer")
            if o:
                changed_orgnrs.add(o)

        tracked = sorted(o for o in changed_orgnrs if (out_dir / f"{o}.json").exists())
        print(f"Tracked companies among changes: {len(tracked)}")
        if not tracked:
            return 0
        sem = asyncio.Semaphore(concurrency)

        async def worker(o):
            async with sem:
                return await refresh_one(o, client, out_dir)

        ok = 0
        for coro in tqdm_asyncio.as_completed(
            [worker(o) for o in tracked], total=len(tracked)
        ):
            if await coro:
                ok += 1
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh tracked profiles from the Brreg delta endpoint.")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--output", default="profiles")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    n = asyncio.run(run(args.days, Path(args.output), args.concurrency))
    print(f"Refreshed {n} profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
