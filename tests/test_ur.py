"""Utilization review and leadership metrics."""

from __future__ import annotations

from datetime import datetime

import pytest

from wardsight.engine.chart import Chart, NoteText
from wardsight.engine.drg_table import DRG_FACTS
from wardsight.engine.gaps import find_flags
from wardsight.engine.ur import case_mix, midnights_crossed, review
from wardsight.models import Event

ADMIT = datetime(2026, 3, 1, 14, 0)


def chart(los: int, notes: str, creatinine=((1, 0.8),), reason="community-acquired pneumonia") -> Chart:
    return Chart("U1", "dev", 70, "female", los, reason, (),
                 tuple(Event(t, "lab", "creatinine", v) for t, v in creatinine),
                 (NoteText("progress_note", 1, notes),))


@pytest.mark.parametrize("admit,hours,expected", [
    (datetime(2026, 3, 1, 14), 8, 0),    # same-day discharge
    (datetime(2026, 3, 1, 23), 2, 1),    # crosses one midnight
    (datetime(2026, 3, 1, 9), 48, 2),
    (datetime(2026, 3, 1, 0), 72, 3),
])
def test_midnights_crossed(admit, hours, expected):
    from datetime import timedelta
    assert midnights_crossed(admit, admit + timedelta(hours=hours)) == expected


def test_stay_within_gmlos_is_ok():
    row = review(chart(2, "Community-acquired pneumonia."), ADMIT, [])
    assert (row.drg, row.status) == (195, "ok")


def test_long_stay_is_flagged():
    row = review(chart(5, "Community-acquired pneumonia."), ADMIT, [])
    assert row.status == "long_stay" and "review discharge barriers" in row.note


def test_long_stay_explained_by_documentation_gap():
    # 5-day pneumonia stay is long for DRG 195 (GMLOS 2.2) but fine once acute systolic HF is documented
    # (DRG 193, GMLOS 3.8, and 5 < 1.5 x 3.8).
    hf_chart = Chart("U2", "dev", 70, "female", 5, "community-acquired pneumonia", (), (
        Event(1, "lab", "bnp", 1500), Event(20, "imaging", "lvef", 30.0, "LVEF 30%"),
        Event(3, "med", "furosemide_iv", text="Furosemide 40 mg IV")),
        (NoteText("progress_note", 1, "Community-acquired pneumonia. CHF."),))
    row = review(hf_chart, ADMIT, find_flags(hf_chart))
    assert row.status == "explained_by_gap"
    assert (row.drg, row.drg_if_documented) == (195, 193)


def test_every_weight_is_ordered_within_its_family():
    families = [(193, 194, 195), (190, 191, 192), (377, 378, 379), (602, 603), (689, 690), (871, 872)]
    for family in families:
        weights = [DRG_FACTS[d].weight for d in family]
        assert weights == sorted(weights, reverse=True), family


def test_case_mix_index():
    cmi = case_mix([195, 195], [194, 195], [193, 194])
    assert cmi.first_documented == pytest.approx(0.6063)
    assert cmi.current == pytest.approx((0.7888 + 0.6063) / 2, abs=1e-4)
    assert cmi.if_all_resolved > cmi.current > cmi.first_documented
