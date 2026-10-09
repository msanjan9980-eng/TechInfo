"""Challenge-level check: verify envelopes and report a summary."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if not Path("envelopes").exists():
        print("[error] envelopes/ directory not found; run ./run.sh first")
        return 1
    return subprocess.call([sys.executable, "tests/validate_envelopes.py"])


if __name__ == "__main__":
    raise SystemExit(main())