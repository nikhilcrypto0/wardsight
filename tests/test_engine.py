"""Detection engine on hand-built charts (not generator output), plus DRG checks."""

from __future__ import annotations

import pytest

from wardsight.engine.chart import Chart, NoteText
from wardsight.engine.documentation import documented_codes, find_mentions
from wardsight.engine.drg import group
from wardsight.engine.evidence import abla, aki, arf, hf, hyponatremia, sepsis
from wardsight.engine.gaps import find_flags
from wardsight.models import Event


def chart(events=(), notes=(), reason="community-acquired pneumonia", problems=()) -> Chart:
    return Chart("X1", "dev", 70, "female", 4, reason, tuple(problems), tuple(events),
                 tuple(NoteText("progress_note", 1, n) for n in notes))


def labs(key: str, *points: tuple[float, float]) -> list[Event]:
    return [Event(t, "lab", key, v) for t, v in points]


# ---- evidence rules ---------------------------------------------------------

def test_aki_absolute_rise_within_48h():
    assert aki(chart(labs("creatinine", (1, 0.8), (37, 1.1)))).met
    assert not aki(chart(labs("creatinine", (1, 0.8), (37, 1.05))))  .met
    assert not aki(chart(labs("creatinine", (1, 0.8), (60, 1.15)))).met  # rise outside 48 h


def test_aki_relative_rise_and_ckd_baseline():
    assert aki(chart(labs("creatinine", (1, 0.6), (100, 0.9)))).met  # 1.5x within 7 days
    assert not aki(chart(labs("creatinine", (1, 2.1), (25, 2.2), (49, 2.0)))).met  # CKD, stable


def test_sepsis_needs_infection_workup_and_two_sofa_points():
    organ = [Event(0, "vital", "map", 62), *labs("platelets", (1, 120))]
    workup = [Event(1, "order", "bc", text="Blood cultures x2"), Event(2, "med", "abx", text="Ceftriaxone 1 g IV")]
    assert sepsis(chart([*organ, *workup])).met
    assert not sepsis(chart(organ)).met                      # no suspected infection
    assert not sepsis(chart([organ[0], *workup])).met        # only one SOFA point


def test_sepsis_renal_points_count_only_as_a_rise():
    workup = [Event(1, "order", "bc", text="Blood cultures x2"), Event(2, "med", "abx", text="Cefazolin 2 g IV")]
    stable_ckd = labs("creatinine", (1, 2.2), (25, 2.3))
    assert not sepsis(chart([*workup, *stable_ckd, Event(0, "vital", "map", 66)])).met


def test_hyponatremia_requires_clinical_significance():
    low_once = labs("sodium", (1, 133), (25, 138))
    assert not hyponatremia(chart(low_once)).met
    treated = [*labs("sodium", (1, 127), (25, 130)), Event(3, "order", "fr", text="Fluid restriction 1.2 L/day")]
    assert hyponatremia(chart(treated)).met


def test_abla_needs_drop_and_bleeding_or_transfusion():
    drop = labs("hemoglobin", (1, 12.8), (29, 10.2))
    assert not abla(chart(drop)).met
    assert abla(chart([*drop, Event(31, "order", "t", text="Transfuse 1 unit packed red blood cells")])).met
    assert not abla(chart([*drop, Event(20, "imaging", "egd", text="EGD: mild nonbleeding gastritis")])).met


def test_arf_two_indicators_plus_oxygen():
    room_air = [Event(0, "vital", "spo2", 87), Event(0, "vital", "o2_flow", 0.0),
                Event(0, "vital", "resp_rate", 31)]
    on_o2 = [Event(4, "vital", "o2_flow", 5.0), Event(4, "vital", "spo2", 94)]
    assert arf(chart([*room_air, *on_o2])).met
    assert not arf(chart(room_air)).met  # no oxygen given
    assert not arf(chart([Event(0, "vital", "spo2", 87), Event(0, "vital", "o2_flow", 0.0), *on_o2])).met


def test_hf_needs_low_ef_high_bnp_and_iv_diuretic():
    base = [*labs("bnp", (1, 1500)), Event(20, "imaging", "lvef", 30.0, "LVEF 30%")]
    assert hf(chart([*base, Event(3, "med", "f", text="Furosemide 40 mg IV")])).met  # capital F matters
    assert not hf(chart([*base, Event(3, "med", "f", text="Furosemide 20 mg PO daily")])).met


# ---- documentation reader ---------------------------------------------------

@pytest.mark.parametrize("text,code,affirmed", [
    ("Assessment: acute renal failure, improving.", "N17.9", True),
    ("Acute kidney injury ruled out.", "N17.9", False),
    ("No evidence of sepsis.", "A41.9", False),
    ("Sepsis secondary to the infection.", "A41.9", True),
    ("Not in respiratory failure.", "J96.01", False),
    ("No acute blood loss anemia; mild drop is dilutional.", "D62", False),
    ("Taking medications as prescribed.", "N17.9", False),  # "aki" inside a word must not match
])
def test_documentation_reader(text, code, affirmed):
    notes = (NoteText("progress_note", 1, text),)
    assert (code in documented_codes(notes)) is affirmed


def test_specific_hf_phrase_wins_over_generic():
    mentions = find_mentions((NoteText("progress_note", 1, "Acute HFrEF exacerbation."),))
    assert {m.icd10 for m in mentions} == {"I50.21"}


# ---- gap finder + DRG -------------------------------------------------------

AKI_EVIDENCE = labs("creatinine", (1, 0.8), (37, 1.4))


def test_missing_dx_flag_with_drg_shift():
    flags = find_flags(chart(AKI_EVIDENCE, ["Community-acquired pneumonia."]))
    assert [(f.condition, f.kind) for f in flags] == [("aki", "missing_dx")]
    assert (flags[0].drg_now.drg, flags[0].drg_if_resolved.drg) == (195, 194)


def test_documented_and_supported_raises_nothing():
    assert find_flags(chart(AKI_EVIDENCE, ["Community-acquired pneumonia. Acute kidney injury."])) == []


def test_unsupported_dx_flag():
    flags = find_flags(chart(labs("creatinine", (1, 0.8)), ["Community-acquired pneumonia. AKI."]))
    assert [(f.condition, f.kind) for f in flags] == [("aki", "unsupported_dx")]
    assert (flags[0].drg_now.severity, flags[0].drg_if_resolved.severity) == ("CC", "NONE")


@pytest.mark.parametrize("codes,expected_drg", [
    (set(), 195), ({"N17.9"}, 194), ({"E87.1"}, 194), ({"J96.01"}, 193), ({"I50.21"}, 193),
    ({"I50.9"}, 195), ({"A41.9"}, 871),
])
def test_drg_grouping(codes, expected_drg):
    assert group(chart(), codes).drg == expected_drg


def test_gi_bleed_with_abla_is_cc():
    bleed = chart(reason="upper GI bleed")
    assert (group(bleed, set()).drg, group(bleed, {"D62"}).drg) == (379, 378)
