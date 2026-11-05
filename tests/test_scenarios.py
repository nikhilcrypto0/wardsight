"""Prove each generated chart sits on the intended side of the published criteria.

The evaluators below read values back out of the chart events. They are
test-only and independent of the generator's internals.
"""

from __future__ import annotations

import random

import pytest

from wardsight import criteria as c
from wardsight.models import PatientSeed
from wardsight.scenarios import build_chart, choose_principal

SEEDS = range(40)
PATIENTS = [
    PatientSeed("T1", 70, "female", frozenset({"htn"}), "builtin"),
    PatientSeed("T2", 60, "male", frozenset({"ckd3", "copd", "dm2"}), "builtin"),
]


def chart(condition: str, evidence: str, seed: int, patient: PatientSeed):
    rng = random.Random(seed)
    principal = choose_principal(rng, condition, evidence)
    return build_chart(rng, patient, principal, condition, evidence)[1]


def series(events, key):
    return [(e.t_hours, e.value) for e in events if e.key == key and e.value is not None]


def texts(events):
    return " | ".join(e.text or "" for e in events)


def aki_met(events) -> bool:
    cr = series(events, "creatinine")
    for i, (t0, v0) in enumerate(cr):
        for t1, v1 in cr[i + 1:]:
            if t1 - t0 <= c.AKI_ABS_WINDOW_H and v1 - v0 >= c.AKI_ABS_RISE_MG_DL:
                return True
            if t1 - t0 <= 7 * 24 and v1 >= c.AKI_REL_RISE * v0:
                return True
    return False


def sofa_points(events) -> int:
    pts = 0
    pts += any(v < c.SOFA_MAP_MMHG for _, v in series(events, "map"))
    pts += any(v < c.SOFA_PLATELETS_K for _, v in series(events, "platelets"))
    pts += any(v >= c.SOFA_BILIRUBIN_MG_DL for _, v in series(events, "bilirubin"))
    return pts


def room_air_spo2(events) -> list[float]:
    o2 = dict(series(events, "o2_flow"))
    return [v for t, v in series(events, "spo2") if o2.get(t, 0.0) == 0.0]


def hgb_drop(events) -> float:
    hgb = [v for _, v in series(events, "hemoglobin")]
    return max(hgb[i] - min(hgb[i:]) for i in range(len(hgb)))


ALL = [(s, p) for s in SEEDS for p in PATIENTS]


@pytest.mark.parametrize("seed,patient", ALL)
def test_aki(seed, patient):
    assert aki_met(chart("aki", "meets", seed, patient))
    for evidence in ("near_miss", "absent"):
        assert not aki_met(chart("aki", evidence, seed, patient))
    ckd = PatientSeed("C", 75, "male", frozenset({"ckd3"}), "builtin")
    confounder = chart("aki", "confounder", seed, ckd)
    assert not aki_met(confounder)
    assert min(v for _, v in series(confounder, "creatinine")) >= 1.7  # high, but at baseline


@pytest.mark.parametrize("seed,patient", ALL)
def test_sepsis(seed, patient):
    met = chart("sepsis", "meets", seed, patient)
    assert sofa_points(met) >= c.SEPSIS_SOFA_DELTA
    assert "Blood cultures" in texts(met) and "IV" in texts(met)
    for evidence in ("near_miss", "absent"):
        assert sofa_points(chart("sepsis", evidence, seed, patient)) < c.SEPSIS_SOFA_DELTA


@pytest.mark.parametrize("seed,patient", ALL)
def test_hyponatremia(seed, patient):
    met = chart("hyponatremia", "meets", seed, patient)
    assert min(v for _, v in series(met, "sodium")) < c.HYPONATREMIA_NA_MMOL_L
    assert "Fluid restriction" in texts(met)
    near = chart("hyponatremia", "near_miss", seed, patient)
    assert 133 <= min(v for _, v in series(near, "sodium")) <= 134
    assert "Fluid restriction" not in texts(near) and "Sodium chloride" not in texts(near)
    absent = chart("hyponatremia", "absent", seed, patient)
    assert min(v for _, v in series(absent, "sodium")) >= c.HYPONATREMIA_NA_MMOL_L


@pytest.mark.parametrize("seed,patient", ALL)
def test_abla(seed, patient):
    met = chart("abla", "meets", seed, patient)
    assert hgb_drop(met) >= c.ABLA_HGB_DROP_G_DL and "Transfuse" in texts(met)
    for evidence in ("near_miss", "absent"):
        other = chart("abla", evidence, seed, patient)
        assert hgb_drop(other) < c.ABLA_HGB_DROP_G_DL and "Transfuse" not in texts(other)


@pytest.mark.parametrize("seed,patient", ALL)
def test_arf(seed, patient):
    met = chart("arf", "meets", seed, patient)
    assert min(room_air_spo2(met)) < c.ARF_SPO2_PCT
    assert min(v for _, v in series(met, "pao2")) < c.ARF_PAO2_MMHG
    assert max(v for _, v in series(met, "resp_rate")) > c.ARF_RR_PER_MIN
    for evidence in ("near_miss", "absent"):
        other = chart("arf", evidence, seed, patient)
        assert min(room_air_spo2(other)) >= c.ARF_SPO2_PCT
        assert max(v for _, v in series(other, "resp_rate")) <= c.ARF_RR_PER_MIN
        assert not series(other, "pao2")


@pytest.mark.parametrize("seed,patient", ALL)
def test_hf(seed, patient):
    met = chart("hf", "meets", seed, patient)
    assert series(met, "lvef")[0][1] <= c.HFREF_LVEF_PCT
    assert series(met, "bnp")[0][1] > c.HF_BNP_PG_ML
    assert "Furosemide 40 mg IV" in texts(met)
    for evidence in ("near_miss", "absent"):
        other = chart("hf", evidence, seed, patient)
        assert series(other, "lvef")[0][1] > c.HFREF_LVEF_PCT
        assert series(other, "bnp")[0][1] <= c.HF_BNP_PG_ML
        assert "IV" not in texts(other).replace("Ceftriaxone 1 g IV", "")
