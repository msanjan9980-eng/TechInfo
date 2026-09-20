"""Refresh profiles using the Brreg 'oppdateringer' delta endpoint."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm_asyncio

from .brreg_client import fetch_company, fetch_roles
from .assemble import assemble_profile


async def refresh_one(orgnr: str, client: httpx.AsyncClient, out_dir: Path) -> bool:
    try:
        company = await fetch_company(orgnr, client)
    except Exception:
        return False
    if company is None:
        return False
    try:
        roles = await fetch_roles(orgnr, client)
    except Exception:
        roles = []
    profile = assemble_profile(company, roles)
    (out_dir / f"{orgnr}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


async def run(days: int, out_dir: Path, concurrency: int = 8) -> int:
    since = (date.today() - timedelta(days=days)).isoformat()
    url = "https://data.brreg.no/enhetsregisteret/api/oppdateringer/enheter"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params={"dato": since})
        r.raise_for_status()
        data = r.json()
        orgnrs = [
            e["organisasjonsnummer"]
            for e in data.get("_embedded", {}).get("enheter", [])
        ]
        orgnrs = [o for o in orgnrs if (out_dir / f"{o}.json").exists()]
        print(f"Refreshing {len(orgnrs)} tracked companies changed since {since}")
        if not orgnrs:
            return 0
        sem = asyncio.Semaphore(concurrency)

        async def worker(o):
            async with sem:
                return await refresh_one(o, client, out_dir)

        ok = 0
        for coro in tqdm_asyncio.as_completed(
            [worker(o) for o in orgnrs], total=len(orgnrs)
        ):
            if await coro:
                ok += 1
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--output", default="profiles")
    args = ap.parse_args()
    n = asyncio.run(run(args.days, Path(args.output)))
    print(f"Refreshed {n} profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
