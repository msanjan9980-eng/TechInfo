# Norwegian Company Agent

An agent that returns Norwegian company facts from permitted public sources,
with source URLs, retrieval dates and confidence levels.

**Repository:** https://github.com/msanjan9980-eng/TechInfo

## One command to run

    .\run.ps1

Provisions the Python venv, installs dependencies, downloads the Enhetsregisteret
bulk dump on first run, extracts a seed list, builds profiles from cached or
live data, and validates the result.

## Look up any company on demand

    python -m agent.lookup 923609016 --summary

Returns the full profile for any Norwegian orgnr (not just the 1,200 seeded
ones). Uses the roles and financials caches when available, fetches live from
Brreg otherwise.

## Sources

All facts come from public, permitted Norwegian government registers:

- **Enhetsregisteret (Bronnoysundregistrene)**
  https://data.brreg.no/enhetsregisteret/api
  Free, keyless, no registration required.

- **Regnskapsregisteret (Register of Annual Accounts)**
  https://data.brreg.no/regnskapsregisteret/regnskap
  Free, keyless. Provides revenue, operating result, net result, total assets,
  equity and total liabilities for companies that file annual accounts.

No LLM used. No paid APIs used. No external dependencies outside Brreg.

## Profile counts

- **Seeded profiles:** 1,200 companies (1,000 annual-account filers + 200 non-filers)
- **Tracked profiles total:** ~2,400 companies (includes delta-refresh additions)
- **Average facts per profile:** ~21
- **~80% of profiles include financial statements** from Regnskapsregisteret

## Output format

Each profile is `profiles/{orgnr}.json` and contains facts of the form:

    {
      "field": "revenue",
      "value": {"value": 67956000000.0, "currency": "USD", "period": "2025-01-01..2025-12-31"},
      "source": "https://data.brreg.no/regnskapsregisteret/regnskap/923609016",
      "retrieved": "2026-09-20T12:29:27Z",
      "confidence": "high",
      "note": "Operating revenue (sum of operating income) from the most recent annual accounts."
    }

Every fact carries a source URL, retrieval timestamp, confidence level and a
human-readable explanation of what it means.

## Keeping profiles current

    python -m agent.refresh --days 1

Uses the official Brreg delta endpoint `oppdateringer/enheter` to find every
company that changed in the register in the last N days, filters to those we
already track, and re-fetches only that subset. Roles and financials are reused
from cache when fresh, so a daily refresh costs roughly 20-50 requests.
Verified working: 3 tracked companies refreshed for --days 7, 8 for --days 30.

## Architecture

- `agent/brreg_client.py` - Enhetsregisteret + Regnskapsregisteret HTTP client,
  MOD11 checksum validation, retry/backoff.
- `agent/assemble.py` - turns raw responses into sourced, dated, explained facts.
- `agent/build.py` - async bulk builder with concurrency limits and caching.
- `agent/lookup.py` - single-orgnr CLI for on-demand queries.
- `agent/refresh.py` - daily delta refresh.
- `agent/cache.py`, `agent/roles_cache.py` - 7-14 day disk caches so a rebuild
  never re-hits the network unnecessarily.
- `tests/validate_profiles.py` - enforces that every fact has a source and a date.

## Limits and cost

- Enhetsregisteret and Regnskapsregisteret are free and unlimited.
- No paid APIs. No LLM calls.
- Full rebuild from warm cache: ~30-45 seconds, 0-2 HTTP requests per profile.
- Expected cost per run: 0 USD.

## Requirements

- Python 3.11+ (tested on 3.14)
- Windows PowerShell
- ~500 MB disk for the bulk dump (optional; deleted after seed extraction)
