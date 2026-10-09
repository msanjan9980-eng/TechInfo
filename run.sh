#!/usr/bin/env bash
# run.sh - one command to install dependencies and run the Signalpost agent.
#
# Usage:
#   ./run.sh                       # runs against data/seed_orgnrs.txt, writes envelopes/
#   ./run.sh <batch-file> <out>    # explicit batch file and output directory
set -euo pipefail
cd "$(dirname "$0")"

BATCH="${1:-data/seed_orgnrs.txt}"
OUT="${2:-envelopes}"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Running batch: $BATCH -> $OUT"
python -m agent.batch --batch "$BATCH" --output "$OUT"