"""Batch entry point: read an organisation-number batch, emit one envelope per input.

Each envelope is merged with the previous run's envelope for the same company,
so refresh metadata and evidence preservation appear on every harness run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from tqdm.asyncio import tqdm_asyncio

from .build import build_profile_dict
from .envelope import (
    STATE_AVAILABLE,
    STATE_BLOCKED,
    STATE_FAILED,
    STATE_NOT_AVAILABLE,
    apply_refresh,
    envelope_from_profile,
    error_envelope,
    merge_evidence_refs,
    merge_source_snapshots,
)


def load_orgnrs(path: Path) -> list[str]:
    """Accept text (one orgnr per line) or JSONL with orgnr/organisasjonsnummer."""
    seen: set[str] = set()
    out: list[str] = []
    text = path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        o: str | None = None
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            o = obj.get("organisasjonsnummer") or obj.get("orgnr") or obj.get("org")
            if isinstance(o, int):
                o = str(o)
        else:
            o = line.split(",")[0].strip().lstrip("\ufeff")
        if o and o.isdigit() and len(o) == 9 and o not in seen:
            seen.add(o)
            out.append(o)
    return out


def _classify_failure(errors: list[str]) -> str:
    blob = " | ".join(errors).lower()
    if "not found in enhetsregisteret" in blob:
        return STATE_NOT_AVAILABLE
    if "403" in blob or "429" in blob or "robots" in blob:
        return STATE_BLOCKED
    return STATE_FAILED


async def envelope_for(
    orgnr: str,
    client: httpx.AsyncClient,
    use_cache: bool = True,
) -> dict:
    profile, errors = await build_profile_dict(orgnr, client, use_cache=use_cache)
    if profile is None:
        return error_envelope(orgnr, _classify_failure(errors), errors)
    return envelope_from_profile(orgnr, profile, state=STATE_AVAILABLE, errors=errors)


def _load_previous_envelope(out_dir: Path, orgnr: str) -> tuple[dict | None, str | None]:
    p = out_dir / f"{orgnr}.json"
    if not p.exists():
        return None, None
    try:
        env = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"previous envelope unreadable: {type(e).__name__}: {e}"
    if not isinstance(env, dict):
        return None, "previous envelope not a JSON object"
    return env, None


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def merge_with_previous(orgnr: str, new_env: dict, out_dir: Path) -> dict:
    """Load the previous envelope, compute refresh, merge prior evidence, return the final envelope."""
    prev_env, prev_err = _load_previous_envelope(out_dir, orgnr)
    if prev_err:
        new_env.setdefault("errors", []).append(prev_err)

    apply_refresh(new_env, prev_env)

    if prev_env is not None:
        new_env["evidence_refs"] = merge_evidence_refs(
            prev_env.get("evidence_refs"), new_env.get("evidence_refs")
        )
        new_env["source_snapshots"] = merge_source_snapshots(
            prev_env.get("source_snapshots"), new_env.get("source_snapshots")
        )

    return new_env


async def run(
    batch_path: Path,
    out_dir: Path,
    concurrency: int = 8,
    use_cache: bool = True,
    snapshot_path: Path | None = None,
) -> int:
    orgnrs = load_orgnrs(batch_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loaded {len(orgnrs)} orgnrs from {batch_path}")
    if snapshot_path is not None:
        print(f"Snapshot argument accepted (not yet used for identity anchoring): {snapshot_path}")

    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "norwegian-company-agent/1.0 (research)"}
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    available = 0

    async with httpx.AsyncClient(headers=headers, limits=limits, timeout=30) as client:
        async def worker(o: str) -> bool:
            async with sem:
                try:
                    env = await envelope_for(o, client, use_cache=use_cache)
                except Exception as e:
                    env = error_envelope(
                        o, STATE_FAILED, [f"worker error: {type(e).__name__}: {e}"]
                    )
                try:
                    env = merge_with_previous(o, env, out_dir)
                except Exception as e:
                    env.setdefault("errors", []).append(
                        f"merge error: {type(e).__name__}: {e}"
                    )
                _write_atomic(out_dir / f"{o}.json", env)
                return env.get("state") == STATE_AVAILABLE

        tasks = [worker(o) for o in orgnrs]
        for coro in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="Envelopes"):
            if await coro:
                available += 1

    print(f"Wrote {len(orgnrs)} envelopes into {out_dir} ({available} available)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build one terminal envelope per input organisation number."
    )
    ap.add_argument(
        "--batch",
        required=True,
        help="Batch file: one orgnr per line, or JSONL with orgnr/organisasjonsnummer",
    )
    ap.add_argument("--output", default="envelopes", help="Output directory")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--no-cache", action="store_true", help="Ignore caches and refetch")
    ap.add_argument(
        "--snapshot",
        default=None,
        help="Optional Builderr-supplied registry snapshot for identity anchoring",
    )
    args = ap.parse_args()

    asyncio.run(
        run(
            Path(args.batch),
            Path(args.output),
            args.concurrency,
            use_cache=not args.no_cache,
            snapshot_path=Path(args.snapshot) if args.snapshot else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())