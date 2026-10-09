"""Main entry point: build profiles for a list of orgnrs."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm_asyncio

from . import cache, roles_cache
from .brreg_client import (
    REGNSKAP_BASE,
    fetch_company,
    fetch_financials,
    fetch_roles,
    validate_orgnr,
)
from .assemble import assemble_profile

ENTITY_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
ROLES_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller"
FIN_URL = REGNSKAP_BASE + "/{orgnr}"


async def get_financials_cached(
    orgnr: str, client: httpx.AsyncClient, use_cache: bool = True
) -> tuple[list[dict], dict | None]:
    if use_cache:
        accounts, meta = cache.load(orgnr)
        if accounts is not None:
            return accounts, meta
    try:
        accounts, meta = await fetch_financials(orgnr, client)
    except Exception:
        accounts, meta = None, None
    cache.save(orgnr, accounts, meta)
    return accounts or [], meta


async def build_profile_dict(
    orgnr: str,
    client: httpx.AsyncClient,
    use_cache: bool = True,
) -> tuple[dict | None, list[str]]:
    """Return (profile, errors). profile is None if the company could not be built."""
    errors: list[str] = []
    if not validate_orgnr(orgnr):
        return None, ["invalid orgnr (MOD11 checksum)"]
    try:
        company, company_meta = await fetch_company(orgnr, client)
    except Exception as e:
        return None, [f"fetch_company error: {type(e).__name__}: {e}"]
    if company is None:
        return None, ["not found in Enhetsregisteret"]

    entity_url = ENTITY_URL.format(orgnr=orgnr)
    roles_url = ROLES_URL.format(orgnr=orgnr)
    fin_url = FIN_URL.format(orgnr=orgnr)
    source_meta: dict[str, dict] = {entity_url: company_meta}

    roles: list[dict] | None = None
    roles_meta: dict | None = None
    if use_cache:
        roles, roles_meta = roles_cache.load(orgnr)
    if roles is None:
        try:
            roles, roles_meta = await fetch_roles(orgnr, client)
        except Exception as e:
            errors.append(f"roles fetch error: {type(e).__name__}: {e}")
            roles, roles_meta = [], None
        roles_cache.save(orgnr, roles, roles_meta)
    if roles_meta:
        source_meta[roles_url] = roles_meta

    try:
        financials, fin_meta = await get_financials_cached(orgnr, client, use_cache=use_cache)
    except Exception as e:
        errors.append(f"financials fetch error: {type(e).__name__}: {e}")
        financials, fin_meta = [], None
    if fin_meta:
        source_meta[fin_url] = fin_meta

    try:
        profile = assemble_profile(
            company, roles, source_meta=source_meta, financials=financials or []
        )
    except Exception as e:
        return None, errors + [f"assemble error: {type(e).__name__}: {e}"]
    return profile, errors


async def build_one(
    orgnr: str,
    client: httpx.AsyncClient,
    out_dir: Path,
    use_cache: bool,
) -> bool:
    profile, errors = await build_profile_dict(orgnr, client, use_cache=use_cache)
    if profile is None:
        for e in errors:
            print(f"[skip] {orgnr}: {e}", file=sys.stderr)
        return False
    out_path = out_dir / f"{orgnr}.json"
    out_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


async def run(
    orgnrs: list[str],
    out_dir: Path,
    concurrency: int = 8,
    use_cache: bool = True,
) -> int:
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
                    return await build_one(o, client, out_dir, use_cache)
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
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        o = line.strip().lstrip("\ufeff").split(",")[0].strip()
        if o and o not in seen:
            seen.add(o)
            out.append(o)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgnrs", required=True, help="Text file with one orgnr per line")
    ap.add_argument("--output", default="profiles", help="Output directory")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--no-cache", action="store_true", help="Ignore financial cache and refetch")
    args = ap.parse_args()

    orgnrs = load_orgnrs(Path(args.orgnrs))
    print(f"Loaded {len(orgnrs)} orgnrs")
    ok = asyncio.run(
        run(
            orgnrs,
            Path(args.output),
            args.concurrency,
            use_cache=not args.no_cache,
        )
    )
    print(f"Built {ok}/{len(orgnrs)} profiles into {args.output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())