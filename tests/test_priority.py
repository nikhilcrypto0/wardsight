"""Worklist priority: each part behaves as documented, and the total is the sum of the parts."""

from __future__ import annotations

from wardsight.engine.drg_table import facts
from wardsight.queries.priority import STAY_MAX, priority

UTI, SEPSIS = 690, 872   # D0011: urinary tract infection -> septicemia without MCC


def test_sepsis_gap_scores_billing_and_time():
    p = priority(UTI, SEPSIS, "NONE", "NONE", los_days=5)
    parts = {x.label: x for x in p.parts}
    assert p.score == sum(x.points for x in p.parts)
    assert parts["Billing impact"].points > 0
    assert "+" in parts["Billing impact"].why
    assert parts["Complication level"].points == 0
    assert parts["Time pressure"].points == STAY_MAX  # 5 days is past the expected stay for 690


def test_unsupported_diagnosis_counts_even_though_weight_goes_down():
    up = priority(UTI, SEPSIS, "NONE", "NONE", los_days=1)
    down = priority(SEPSIS, UTI, "NONE", "NONE", los_days=1)
    assert {x.label: x.points for x in up.parts}["Billing impact"] == \
        {x.label: x.points for x in down.parts}["Billing impact"]


def test_mcc_outranks_cc():
    mcc = priority(UTI, UTI, "NONE", "MCC", los_days=1)
    cc = priority(UTI, UTI, "NONE", "CC", los_days=1)
    assert mcc.score > cc.score


def test_time_pressure_grows_with_stay_and_caps():
    gmlos = facts(UTI).gmlos
    early = priority(UTI, UTI, "NONE", "NONE", los_days=1)
    late = priority(UTI, UTI, "NONE", "NONE", los_days=gmlos * 3)
    assert early.score < late.score
    assert {x.label: x.points for x in late.parts}["Time pressure"] == STAY_MAX


def test_unknown_category_scores_zero_not_crash():
    p = priority(None, None, None, None, los_days=3)
    assert p.score == 0 and len(p.parts) == 3
