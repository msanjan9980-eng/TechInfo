"""Phase 4(a): verify new Brreg fields are emitted as claims. No network required."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.assemble import assemble_profile
from agent.brreg_client import CompanyRecord


def _company(**kw) -> CompanyRecord:
    base = {"organisasjonsnummer": "811413682", "navn": "TEST AS"}
    base.update(kw)
    return CompanyRecord(**base)


def test_new_facts_emitted():
    c = _company(
        aktivitet=["Produksjon og salg av emballasje,", "samt deltagelse i andre selskaper."],
        vedtektsfestetFormaal=["Drive virksomhet med", "emballasje og maskiner."],
        institusjonellSektorkode={"kode": "2100", "beskrivelse": "Private aksjeselskaper mv."},
        erEnkeltpersonforetak=False,
        harRegistrertAntallAnsatte=True,
        sisteEndring="2024-05-15",
        overordnetEnhet={"organisasjonsnummer": "999999999", "navn": "PARENT AS"},
    )
    profile = assemble_profile(c, roles=[])
    fields = {f["field"]: f for f in profile["facts"]}

    for name in [
        "activity", "purpose", "sector_code", "sole_proprietorship",
        "has_registered_employee_count", "last_registry_change", "parent",
    ]:
        assert name in fields, f"missing field {name}; have {sorted(fields)}"

    assert fields["activity"]["value"] == (
        "Produksjon og salg av emballasje, samt deltagelse i andre selskaper."
    )
    assert fields["purpose"]["value"] == "Drive virksomhet med emballasje og maskiner."
    assert fields["sector_code"]["value"] == {
        "kode": "2100", "beskrivelse": "Private aksjeselskaper mv."
    }
    assert fields["sole_proprietorship"]["value"] is False
    assert fields["has_registered_employee_count"]["value"] is True
    assert fields["last_registry_change"]["value"] == "2024-05-15"
    assert fields["parent"]["value"] == {"orgnr": "999999999", "name": "PARENT AS"}


def test_absent_fields_emit_nothing():
    c = _company()  # every new field absent
    profile = assemble_profile(c, roles=[])
    names = {f["field"] for f in profile["facts"]}
    for name in [
        "activity", "purpose", "sector_code", "sole_proprietorship",
        "has_registered_employee_count", "last_registry_change", "parent",
    ]:
        assert name not in names, f"unexpected {name} in {sorted(names)}"


def test_parent_string_shape():
    c = _company(overordnetEnhet="999999999")
    profile = assemble_profile(c, roles=[])
    fields = {f["field"]: f for f in profile["facts"]}
    assert fields["parent"]["value"] == {"orgnr": "999999999", "name": None}


def test_parent_null_and_false_booleans_not_emitted_as_zero():
    c = _company(
        overordnetEnhet=None,
        erEnkeltpersonforetak=None,
        harRegistrertAntallAnsatte=None,
        sisteEndring=None,
    )
    profile = assemble_profile(c, roles=[])
    names = {f["field"] for f in profile["facts"]}
    assert "parent" not in names
    assert "sole_proprietorship" not in names
    assert "has_registered_employee_count" not in names
    assert "last_registry_change" not in names


def main():
    tests = [
        test_new_facts_emitted,
        test_absent_fields_emit_nothing,
        test_parent_string_shape,
        test_parent_null_and_false_booleans_not_emitted_as_zero,
    ]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())