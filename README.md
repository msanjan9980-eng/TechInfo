# Norwegian Company Agent

An agent that returns Norwegian company facts from permitted public sources,
with source URLs and retrieval dates.

## One command to run

    .\run.ps1

## Sources

- **Enhetsregisteret (Bronnoysundregistrene)** - https://data.brreg.no/enhetsregisteret/api - free, keyless.

## Output

Profiles are written to `profiles/*.json`. Each profile contains:

- `orgnr`, `name`
- `facts[]` - each with `field`, `value`, `source` (URL), `retrieved` (ISO 8601), `confidence`, `note`
- `sources_used`
- `last_updated`

## Update mechanism

    python -m agent.refresh --days 1 --output profiles

Refreshes every tracked company whose record changed in Enhetsregisteret in the
last day, using the official delta endpoint.

## Requirements

- Python 3.11+ (tested on 3.14)
- Windows PowerShell

## Cost

- Enhetsregisteret API: $0
- No other paid APIs used
- Total expected cost per full run: $0
