"""The answer key must say exactly what was planted, every time."""

from __future__ import annotations

from collections import Counter

import pytest

from wardsight.patients import builtin_patients
from wardsight.planter import GROUP_COUNTS, TRUE_ICD10, build_split


@pytest.fixture(scope="module")
def dev():
    return build_split("dev", builtin_patients(200, 7), 7)


def test_group_counts(dev):
    _, answers = dev
    assert Counter(a.group for a in answers) == Counter(GROUP_COUNTS["dev"])


def test_expected_flags(dev):
    _, answers = dev
    expected = {"missing": "missing_dx", "unsupported": "unsupported_dx"}
    for a in answers:
        assert a.expected_flag == expected.get(a.group, "none"), a


def test_notes_spec_matches_answer_key(dev):
    encounters, answers = dev
    for enc, ans in zip(encounters, answers):
        if enc.condition is None:
            continue
        code = TRUE_ICD10[enc.condition]
        present = {m.icd10 for m in enc.mentions if m.assertion == "present"}
        negated = {m.icd10 for m in enc.mentions if m.assertion == "negated"}
        if enc.group == "missing":
            assert code not in present
            assert ("I50.9" in present) == (enc.condition == "hf")
        elif enc.group in ("unsupported", "correct"):
            assert code in present
        else:
            assert code not in present and negated <= {code}


def test_confounders_have_ckd(dev):
    encounters, _ = dev
    for enc in encounters:
        if enc.group == "confounder":
            assert "ckd3" in enc.patient.chronic and enc.condition == "aki"


def test_every_condition_is_tested(dev):
    _, answers = dev
    for group in ("missing", "unsupported", "correct", "near_miss"):
        assert {a.condition for a in answers if a.group == group} == set(TRUE_ICD10)


def test_deterministic():
    first = build_split("heldout", builtin_patients(100, 3), 3)[1]
    again = build_split("heldout", builtin_patients(100, 3), 3)[1]
    other = build_split("heldout", builtin_patients(100, 4), 4)[1]
    assert first == again
    assert first != other
