"""Main entry point: build profiles for a list of orgnrs."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm_asyncio

from .brreg_client import fetch_company, fetch_roles, validate_orgnr
from .assemble import assemble_profile


async def build_one(orgnr: str, client: httpx.AsyncClient, out_dir: Path) -> bool:
    if not validate_orgnr(orgnr):
        print(f"[skip] {orgnr} failed MOD11 checksum", file=sys.stderr)
        return False
    try:
        company = await fetch_company(orgnr, client)
    except Exception as e:
        print(f"[err-fetch] {orgnr}: {e}", file=sys.stderr)
        return False
    if company is None:
        print(f"[miss] {orgnr} not found in Enhetsregisteret", file=sys.stderr)
        return False
    try:
        roles = await fetch_roles(orgnr, client)
    except Exception as e:
        print(f"[err-roles] {orgnr}: {e}", file=sys.stderr)
        roles = []
    profile = assemble_profile(company, roles)
    out_path = out_dir / f"{orgnr}.json"
    out_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


async def run(orgnrs: list[str], out_dir: Path, concurrency: int = 8) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "norwegian-company-agent/1.0 (research)"}
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    ok = 0

    async with httpx.AsyncClient(headers=headers, limits=limits, timeout=30) as client:
        async def worker(o: str) -> bool:
            async with sem:
                try:
                    return await build_one(o, client, out_dir)
                except Exception as e:
                    print(f"[err] {o}: {e}", file=sys.stderr)
                    return False

        tasks = [worker(o) for o in orgnrs]
        for coro in tqdm_asyncio.as_completed(
            tasks, total=len(tasks), desc="Building profiles"
        ):
            if await coro:
                ok += 1
    return ok


def load_orgnrs(path: Path) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        o = line.strip().split(",")[0].strip()
        if o and o not in seen:
            seen.add(o)
            out.append(o)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgnrs", required=True, help="Text file with one orgnr per line")
    ap.add_argument("--output", default="profiles", help="Output directory")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    orgnrs = load_orgnrs(Path(args.orgnrs))
    print(f"Loaded {len(orgnrs)} orgnrs")
    ok = asyncio.run(run(orgnrs, Path(args.output), args.concurrency))
    print(f"Built {ok}/{len(orgnrs)} profiles into {args.output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
