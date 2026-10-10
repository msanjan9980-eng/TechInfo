"""Offline tests for NAV job-listing normalization and exact-company matching.

No network required. The rule under test: a job claim is published only when
the NAV businessName or employer.name matches the Enhetsregisteret name under
the normalized / suffix-stripped rules in agent.nav_client.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.nav_client import exact_match, names_match, normalize_name


def test_normalize_punctuation_and_case():
    assert normalize_name("Elopak ASA") == "elopak asa"
    assert normalize_name("FJORD STILLAS AS") == "fjord stillas as"
    assert normalize_name("A.B.C. Norge & Co.") == "a b c norge co"
    assert normalize_name("  Multiple   spaces  ") == "multiple spaces"


def test_names_match_exact_and_suffix():
    # Exact normalized match
    assert names_match("Fjord Stillas As", "FJORD STILLAS AS")
    # Suffix-stripped match
    assert names_match("Fjord Stillas", "Fjord Stillas AS")
    assert names_match("Elopak", "Elopak ASA")
    # Non-matches
    assert not names_match("Fjord Stillas AS", "Fjord Bygg AS")
    assert not names_match("", "Fjord Stillas AS")


def test_names_match_does_not_tolerate_different_company():
    # Two companies that share a suffix must not collide.
    assert not names_match("Bygg Partner AS", "Bygg Mesiter AS")
    assert not names_match("Nordic Bygg AS", "Nordic Bygg Service AS")


def test_exact_match_filters_non_matches():
    hits = [
        {"_source": {"uuid": "u1", "businessName": "Fjord Stillas As", "employer": {"name": "FJORD STILLAS AS"}, "title": "Stillasmontor"}},
        {"_source": {"uuid": "u2", "businessName": "Nordic Bygg As", "employer": {"name": "NORDIC BYGG AS"}, "title": "Tomrer"}},
        {"_source": {"uuid": "u3", "businessName": "Fjord Stillas", "employer": {"name": "Fjord Stillas"}, "title": "Stillasbygger"}},
        {"_source": {"uuid": "u4", "businessName": "Fjord Stillas Consulting As", "employer": {"name": "FJORD STILLAS CONSULTING AS"}, "title": "Konsulent"}},
    ]
    matched = exact_match(hits, "Fjord Stillas AS")
    uuids = sorted(j["uuid"] for j in matched)
    assert uuids == ["u1", "u3"], uuids

    matched2 = exact_match(hits, "Nordic Bygg AS")
    assert [j["uuid"] for j in matched2] == ["u2"]


def test_exact_match_empty_company_name_returns_nothing():
    hits = [{"_source": {"uuid": "u1", "businessName": "Fjord Stillas As"}}]
    assert exact_match(hits, "") == []


def test_job_dict_extracts_expected_fields():
    hit = {
        "_source": {
            "uuid": "abc-123",
            "title": "Stillasmontor med sertifikat",
            "businessName": "Fjord Stillas As",
            "employer": {"name": "FJORD STILLAS AS"},
            "published": "2026-10-09T20:07:40+02:00",
            "expires": "2026-10-30T00:00:00+01:00",
            "locationList": [{"city": "ALESUND", "municipal": "ALESUND", "county": "MORE OG ROMSDAL"}],
            "status": "ACTIVE",
        }
    }
    matched = exact_match([hit], "Fjord Stillas AS")
    assert len(matched) == 1
    j = matched[0]
    assert j["uuid"] == "abc-123"
    assert j["title"] == "Stillasmontor med sertifikat"
    assert j["city"] == "ALESUND"
    assert j["county"] == "MORE OG ROMSDAL"
    assert j["url"].endswith("/abc-123")


def main():
    tests = [
        test_normalize_punctuation_and_case,
        test_names_match_exact_and_suffix,
        test_names_match_does_not_tolerate_different_company,
        test_exact_match_filters_non_matches,
        test_exact_match_empty_company_name_returns_nothing,
        test_job_dict_extracts_expected_fields,
    ]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())