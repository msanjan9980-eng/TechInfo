"""End-to-end mutation test.

Sequence:
  1. Remove envelopes/.
  2. Run batch once.
  3. Capture one envelope.
  4. Mutate one claim value in place, write it back with BOM-less UTF-8.
  5. Run batch again.
  6. Read the envelope back and assert refresh.changes contains the mutation.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / "envelopes"
BATCH = ROOT / "data" / "smoke10.txt"


def run_batch() -> int:
    return subprocess.call(
        [sys.executable, "-m", "agent.batch", "--batch", str(BATCH), "--output", str(ENV_DIR)],
        cwd=str(ROOT),
    )


def main() -> int:
    if not BATCH.exists():
        print(f"[error] {BATCH} missing")
        return 1

    if ENV_DIR.exists():
        shutil.rmtree(ENV_DIR)
    print("== run 1 (fresh) ==")
    if run_batch() != 0:
        return 1

    env_files = sorted(ENV_DIR.glob("*.json"))
    if not env_files:
        print("[error] no envelopes produced")
        return 1
    target = env_files[0]
    print(f"target envelope: {target.name}")

    env = json.loads(target.read_text(encoding="utf-8"))
    if not env.get("claims"):
        print("[skip] target has no claims to mutate")
        return 0

    original = env["claims"][0]["value"]
    env["claims"][0]["value"] = "__MUTATION_PROBE__"
    target.write_text(
        json.dumps(env, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"mutated claims[0] from {original!r} to '__MUTATION_PROBE__'")

    print("== run 2 (against mutated previous) ==")
    if run_batch() != 0:
        return 1

    env2 = json.loads(target.read_text(encoding="utf-8"))
    changes = (env2.get("refresh") or {}).get("changes") or []
    if not changes:
        print("[FAIL] no changes recorded after mutation")
        return 1

    fields = sorted({c["field"] for c in changes})
    print(f"[OK] {len(changes)} change(s) recorded on fields: {fields}")

    prev_at = (env2.get("refresh") or {}).get("previous_envelope_at")
    if not prev_at:
        print("[FAIL] previous_envelope_at is empty")
        return 1
    print(f"[OK] previous_envelope_at = {prev_at}")

    print("== run 3 (idempotent, no mutation) ==")
    if run_batch() != 0:
        return 1
    env3 = json.loads(target.read_text(encoding="utf-8"))
    changes3 = (env3.get("refresh") or {}).get("changes") or []
    if changes3:
        print(f"[FAIL] expected zero changes on idempotent rerun, got {len(changes3)}")
        return 1
    print("[OK] idempotent rerun produced zero changes")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())