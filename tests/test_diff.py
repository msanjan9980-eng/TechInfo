"""Offline unit tests for the claim diff. No network required."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.diff import diff_claims


def c(field, value, period=None, ref="e1"):
    return {
        "claim_id": "x",
        "field": field,
        "value": value,
        "reporting_period": period,
        "confidence": "high",
        "evidence_ref": ref,
    }


def test_idempotent():
    """Identical claim sets produce zero changes."""
    a = [c("website", "example.no"), c("role:Daglig leder", {"name": "Ola"})]
    b = [c("website", "example.no"), c("role:Daglig leder", {"name": "Ola"})]
    assert diff_claims(a, b, "t") == [], "identical claims should produce no changes"


def test_role_identity_by_name_ignores_order():
    """Same people in the same roles, different order, produce no changes."""
    a = [c("role:Styremedlem", {"name": "A"}), c("role:Styremedlem", {"name": "B"})]
    b = [c("role:Styremedlem", {"name": "B"}), c("role:Styremedlem", {"name": "A"})]
    assert diff_claims(a, b, "t") == [], "reordering should not produce changes"


def test_role_person_replacement_is_remove_plus_add():
    """A different person in the same role label = old person out, new person in."""
    old = [c("role:Styreleder", {"name": "Ola", "since": "2020"})]
    new = [c("role:Styreleder", {"name": "Kari", "since": "2024"})]
    changes = diff_claims(old, new, "t")
    types = sorted(x["change_type"] for x in changes)
    assert types == ["new_role", "removed_role"], changes

    by_type = {x["change_type"]: x for x in changes}
    assert by_type["removed_role"]["discriminator"] == "Ola"
    assert by_type["removed_role"]["previous"] == {"name": "Ola", "since": "2020"}
    assert by_type["removed_role"]["current"] is None
    assert by_type["new_role"]["discriminator"] == "Kari"
    assert by_type["new_role"]["current"] == {"name": "Kari", "since": "2024"}
    assert by_type["new_role"]["previous"] is None


def test_role_same_person_attribute_change_is_changed_role():
    """Same person, different since date = changed_role."""
    old = [c("role:Daglig leder", {"name": "Ola", "since": "2020"})]
    new = [c("role:Daglig leder", {"name": "Ola", "since": "2024"})]
    changes = diff_claims(old, new, "t")
    assert len(changes) == 1, changes
    assert changes[0]["change_type"] == "changed_role"
    assert changes[0]["previous"] == {"name": "Ola", "since": "2020"}
    assert changes[0]["current"] == {"name": "Ola", "since": "2024"}


def test_financial_value_change_is_changed_filing():
    old = [c("revenue", {"value": 100, "period": "2023"}, period="2023")]
    new = [c("revenue", {"value": 200, "period": "2024"}, period="2024")]
    changes = diff_claims(old, new, "t")
    assert len(changes) == 1, changes
    assert changes[0]["change_type"] == "changed_filing"
    assert changes[0]["previous"]["value"] == 100
    assert changes[0]["current"]["value"] == 200
    assert changes[0]["previous_period"] == "2023"
    assert changes[0]["current_period"] == "2024"


def test_new_and_removed_claims():
    old = [c("revenue", {"value": 100}), c("website", "old.no")]
    new = [c("revenue", {"value": 100}), c("email", "hi@example.no")]
    changes = diff_claims(old, new, "t")
    by_field = {x["field"]: x for x in changes}
    assert by_field["website"]["change_type"] == "removed_claim"
    assert by_field["email"]["change_type"] == "new_claim"


def test_address_field_is_location_family():
    old = [c("business_address", {"adresse": ["A"]})]
    new = [c("business_address", {"adresse": ["B"]})]
    changes = diff_claims(old, new, "t")
    assert len(changes) == 1
    assert changes[0]["change_type"] == "changed_location"


def main():
    tests = [
        test_idempotent,
        test_role_identity_by_name_ignores_order,
        test_role_person_replacement_is_remove_plus_add,
        test_role_same_person_attribute_change_is_changed_role,
        test_financial_value_change_is_changed_filing,
        test_new_and_removed_claims,
        test_address_field_is_location_family,
    ]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())