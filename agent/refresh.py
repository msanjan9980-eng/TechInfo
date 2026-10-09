"""Refresh tracked companies using the Brreg 'oppdateringer' delta endpoint.

Local-dev convenience wrapper. Delegates envelope construction and merge to
agent.batch, so envelopes produced here are byte-for-byte equivalent to those
produced by the harness batch command.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm_asyncio

from . import batch as batch_mod
from .envelope import STATE_AVAILABLE, STATE_FAILED, error_envelope


async def refresh_one(orgnr: str, client: httpx.AsyncClient, out_dir: Path) -> bool:
    try:
        env = await batch_mod.envelope_for(orgnr, client, use_cache=True)
    except Exception as e:
        env = error_envelope(
            orgnr, STATE_FAILED, [f"refresh error: {type(e).__name__}: {e}"]
        )
    try:
        env = batch_mod.merge_with_previous(orgnr, env, out_dir)
    except Exception as e:
        env.setdefault("errors", []).append(f"merge error: {type(e).__name__}: {e}")
    batch_mod._write_atomic(out_dir / f"{orgnr}.json", env)
    return env.get("state") == STATE_AVAILABLE


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

        async def worker(o: str) -> bool:
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
    ap = argparse.ArgumentParser(
        description="Refresh tracked profiles from the Brreg delta endpoint."
    )
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--output", default="envelopes")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    n = asyncio.run(run(args.days, Path(args.output), args.concurrency))
    print(f"Refreshed {n} envelopes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())