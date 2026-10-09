"""Local 100-company smoke test: run the agent and verify one envelope per input."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    seed = Path("data/seed_orgnrs.txt")
    if not seed.exists():
        print("[error] data/seed_orgnrs.txt not found")
        return 1

    orgnrs = [ln.strip() for ln in seed.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    first100 = orgnrs[:100]
    batch = Path("data/showcase_batch.txt")
    batch.write_text("\n".join(first100) + "\n", encoding="utf-8")
    print(f"Wrote {len(first100)} orgnrs to {batch}")

    rc = subprocess.call(
        [sys.executable, "-m", "agent.batch", "--batch", str(batch), "--output", "envelopes"]
    )
    if rc != 0:
        return rc

    out = Path("envelopes")
    wanted = set(first100)
    got = [p for p in out.glob("*.json") if p.stem in wanted]
    print(f"Envelopes for showcase batch: {len(got)}/{len(first100)}")
    return 0 if len(got) == len(first100) else 1


if __name__ == "__main__":
    raise SystemExit(main())