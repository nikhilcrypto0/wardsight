"""Scenario engine: turns a patient + target condition into an hour-by-hour chart.

Each condition has four evidence levels (see models.EVIDENCE_*). Values are
generated around the published thresholds in `criteria.py` with margins wide
enough that measurement noise never flips a case across a threshold; the
tests in tests/test_scenarios.py prove that for many seeds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import pairwise

from wardsight.models import (
    EVIDENCE_ABSENT,
    EVIDENCE_CONFOUNDER,
    EVIDENCE_MEETS,
    EVIDENCE_NEAR_MISS,
    Event,
    PatientSeed,
)

Points = list[tuple[float, float]]

VITAL_EVERY_H = 4
DAILY_LABS = ("creatinine", "sodium", "hemoglobin", "platelets", "wbc")
LAB_JITTER = {"creatinine": 0.03, "sodium": 0.5, "hemoglobin": 0.15,
              "platelets": 6.0, "wbc": 0.4, "bilirubin": 0.05}
VITAL_JITTER = {"heart_rate": 3.0, "resp_rate": 1.0, "sbp": 4.0, "dbp": 3.0,
                "spo2": 1.0, "temp": 0.15}
ROUND_TO = {"creatinine": 2, "hemoglobin": 1, "wbc": 1, "bilirubin": 2,
            "temp": 1, "map": 0, "sodium": 0, "platelets": 0, "heart_rate": 0,
            "resp_rate": 0, "sbp": 0, "dbp": 0, "spo2": 0}


@dataclass(frozen=True)
class Plan:
    """What a condition adds to the base chart."""

    los_days: int
    curves: dict[str, Points]            # overrides for daily labs and vitals
    o2_steps: Points                     # inhaled O2 L/min, piecewise constant
    extra_lab_hours: tuple[float, ...]   # extra draws of the daily labs
    events: tuple[Event, ...]            # one-off labs, meds, orders, imaging
    skip_principal_meds: bool = False


@dataclass(frozen=True)
class Baseline:
    creatinine: float
    sodium: float
    hemoglobin: float
    platelets: float
    wbc: float
    bilirubin: float
    heart_rate: float
    resp_rate: float
    sbp: float
    dbp: float
    spo2: float
    temp: float


def make_baseline(rng: random.Random, patient: PatientSeed) -> Baseline:
    has_ckd = "ckd3" in patient.chronic
    hgb_low, hgb_high = (11.8, 13.8) if patient.sex == "female" else (13.0, 15.0)
    return Baseline(
        creatinine=rng.uniform(1.8, 2.4) if has_ckd else rng.uniform(0.7, 1.1),
        sodium=rng.uniform(138, 141),
        hemoglobin=rng.uniform(hgb_low, hgb_high),
        platelets=rng.uniform(190, 320),
        wbc=rng.uniform(5.5, 9.5),
        bilirubin=rng.uniform(0.4, 0.9),
        heart_rate=rng.uniform(70, 88),
        resp_rate=rng.uniform(14, 17),
        sbp=rng.uniform(118, 136),
        dbp=rng.uniform(66, 80),
        spo2=rng.uniform(93, 95) if "copd" in patient.chronic else rng.uniform(96, 98),
        temp=rng.uniform(36.6, 37.1),
    )


def interp(points: Points, t: float) -> float:
    """Piecewise-linear value of a curve at hour t, flat beyond its ends."""
    pts = sorted(points)
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in pairwise(pts):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return pts[-1][1]


def step(points: Points, t: float) -> float:
    """Piecewise-constant value: the last step at or before hour t."""
    value = 0.0
    for t0, v0 in sorted(points):
        if t0 <= t:
            value = v0
    return value


def _round(key: str, value: float) -> float:
    return round(value, ROUND_TO.get(key, 1))


def _sampled(rng: random.Random, key: str, curve: Points, t: float, jitter: dict[str, float]) -> float:
    spread = jitter.get(key, 0.0)
    return _round(key, interp(curve, t) + rng.uniform(-spread, spread))


def build_chart(rng: random.Random, patient: PatientSeed, principal: str,
                condition: str | None, evidence: str | None) -> tuple[int, tuple[Event, ...]]:
    """Return (length of stay in days, time-ordered chart events)."""
    base = make_baseline(rng, patient)
    plan = plan_condition(rng, base, patient, condition, evidence)
    los_h = plan.los_days * 24
    curves = {key: [(0.0, getattr(base, key))] for key in (*DAILY_LABS, *VITAL_JITTER)}
    curves.update(plan.curves)

    events: list[Event] = []
    lab_hours = sorted({1.0 + 24 * d for d in range(plan.los_days)} | set(plan.extra_lab_hours))
    for t in (h for h in lab_hours if h < los_h):
        events.extend(Event(t, "lab", k, _sampled(rng, k, curves[k], t, LAB_JITTER)) for k in DAILY_LABS)
    if not any(e.key == "bilirubin" for e in plan.events):
        events.append(Event(1.0, "lab", "bilirubin", _round("bilirubin", base.bilirubin)))

    for t in range(0, los_h, VITAL_EVERY_H):
        vitals = {k: _sampled(rng, k, curves[k], t, VITAL_JITTER) for k in VITAL_JITTER}
        vitals["spo2"] = min(vitals["spo2"], 100.0)
        mean_bp = (vitals["sbp"] + 2 * vitals["dbp"]) / 3
        events.extend(Event(float(t), "vital", k, v) for k, v in vitals.items())
        events.append(Event(float(t), "vital", "map", _round("map", mean_bp)))
        events.append(Event(float(t), "vital", "o2_flow", step(plan.o2_steps, t)))

    events.extend(e for e in plan.events if e.t_hours < los_h)
    if not plan.skip_principal_meds:
        events.extend(principal_events(principal, los_h))
    return plan.los_days, tuple(sorted(events, key=lambda e: (e.t_hours, e.kind, e.key)))


def principal_events(principal: str, los_h: int) -> list[Event]:
    """Routine treatment for the reason the patient was admitted."""
    daily = range(2, los_h, 24)
    if principal == "J18.9":
        return [Event(1.5, "imaging", "cxr", text="Chest x-ray: right lower lobe opacity"),
                *(Event(float(t), "med", "ceftriaxone", text="Ceftriaxone 1 g IV") for t in daily)]
    if principal == "N39.0":
        return [Event(1.0, "lab", "urinalysis", text="Urinalysis: positive nitrites, >50 WBC/hpf"),
                *(Event(float(t), "med", "ceftriaxone", text="Ceftriaxone 1 g IV") for t in daily)]
    if principal == "L03.116":
        return [Event(float(t), "med", "cefazolin", text="Cefazolin 2 g IV") for t in range(2, los_h, 8)]
    if principal == "J44.1":
        return [*(Event(float(t), "med", "prednisone", text="Prednisone 40 mg PO") for t in daily),
                *(Event(float(t), "med", "albuterol", text="Albuterol-ipratropium nebulizer")
                  for t in range(2, los_h, 6))]
    if principal == "R55":
        return [Event(1.0, "order", "telemetry", text="Cardiac telemetry monitoring")]
    if principal == "K92.2":
        return [Event(1.0, "med", "pantoprazole", text="Pantoprazole 80 mg IV")]
    return []


def choose_principal(rng: random.Random, condition: str | None, evidence: str | None) -> str:
    if condition == "abla" and evidence in (EVIDENCE_MEETS, EVIDENCE_ABSENT):
        return "K92.2"
    if condition in ("arf", "hf"):
        return rng.choice(("J18.9", "J44.1")) if condition == "arf" else "J18.9"
    if condition in ("aki", "sepsis", "hyponatremia", "abla"):
        return rng.choice(("J18.9", "N39.0", "L03.116"))
    return rng.choice(("J18.9", "N39.0", "L03.116", "J44.1", "R55"))


def plan_condition(rng: random.Random, base: Baseline, patient: PatientSeed,
                   condition: str | None, evidence: str | None) -> Plan:
    if condition is None:
        return Plan(rng.randint(2, 4), {}, [(0.0, 0.0)], (), ())
    builders = {"aki": _aki, "sepsis": _sepsis, "hyponatremia": _hyponatremia,
                "abla": _abla, "arf": _arf, "hf": _hf}
    return builders[condition](rng, base, patient, evidence)


def _los(rng: random.Random, evidence: str, meets: tuple[int, int], other: tuple[int, int]) -> int:
    """Length of stay in days, near the MS-DRG expected stay (GMLOS, 2-5 days for these DRGs).

    A stay with a real acute complication runs a little longer than one without.
    Every range keeps the lab draws each scenario depends on inside the stay.
    """
    low, high = meets if evidence == EVIDENCE_MEETS else other
    return rng.randint(low, high)


def _aki(rng: random.Random, b: Baseline, p: PatientSeed, evidence: str) -> Plan:
    los = _los(rng, evidence, (3, 5), (2, 4))
    cr = b.creatinine
    events: tuple[Event, ...] = ()
    if evidence == EVIDENCE_MEETS:
        rise, peak = rng.uniform(0.5, 1.2), rng.uniform(36, 46)
        curve = [(0.0, cr), (peak, cr + rise), (los * 24.0, cr + 0.25 * rise)]
        events = (Event(peak - 8, "med", "lr_bolus", text="Lactated Ringer's 1 L IV bolus"),)
        if "htn" in p.chronic:
            events += (Event(peak - 8, "order", "hold_ace", text="Hold lisinopril"),)
    elif evidence == EVIDENCE_NEAR_MISS:
        curve = [(0.0, cr), (40.0, cr + rng.uniform(0.1, 0.18)), (los * 24.0, cr)]
    elif evidence == EVIDENCE_CONFOUNDER:
        curve = [(0.0, cr), (30.0, cr + rng.uniform(-0.06, 0.06)), (los * 24.0, cr)]
    else:
        curve = [(0.0, cr)]
    return Plan(los, {"creatinine": curve}, [(0.0, 0.0)], (13.0, 37.0), events)


def _sepsis(rng: random.Random, b: Baseline, p: PatientSeed, evidence: str) -> Plan:
    if evidence == EVIDENCE_MEETS:
        los = rng.randint(4, 6)
        curves = {
            "temp": [(0, 39.0), (18, 38.6), (36, 37.3)],
            "heart_rate": [(0, 116), (24, 100), (48, 86)],
            "resp_rate": [(0, 25), (24, 20), (48, 17)],
            "sbp": [(0, 89), (12, 95), (36, 120)],
            "dbp": [(0, 49), (12, 54), (36, 70)],
            "wbc": [(0, rng.uniform(16, 20)), (48, 11), (120, 8)],
            "platelets": [(0, rng.uniform(112, 132)), (48, 140), (120, 190)],
        }
        events = (
            Event(1.0, "lab", "lactate", round(rng.uniform(2.6, 4.0), 1)),
            Event(7.0, "lab", "lactate", round(rng.uniform(1.6, 2.0), 1)),
            Event(1.0, "lab", "bilirubin", round(rng.uniform(1.4, 1.7), 2)),
            Event(1.5, "order", "blood_cultures", text="Blood cultures x2"),
            Event(2.0, "med", "lr_bolus", text="Lactated Ringer's 30 mL/kg IV bolus"),
            *(Event(float(t), "med", "pip_tazo", text="Piperacillin-tazobactam 4.5 g IV")
              for t in range(2, los * 24, 6)),
        )
    elif evidence == EVIDENCE_NEAR_MISS:
        los = rng.randint(2, 4)
        curves = {
            "temp": [(0, 38.5), (24, 37.4)],
            "heart_rate": [(0, 99), (24, 84)],
            "resp_rate": [(0, 21), (24, 17)],
            "wbc": [(0, rng.uniform(12.5, 14.5)), (48, 9)],
        }
        events = (
            Event(1.0, "lab", "lactate", round(rng.uniform(1.1, 1.6), 1)),
            Event(1.5, "order", "blood_cultures", text="Blood cultures x2"),
            *(Event(float(t), "med", "ceftriaxone", text="Ceftriaxone 1 g IV")
              for t in range(2, los * 24, 24)),
        )
    else:
        los = rng.randint(2, 4)
        curves = {"temp": [(0, 37.4), (24, 37.0)]}
        events = tuple(Event(float(t), "med", "ceftriaxone", text="Ceftriaxone 1 g IV")
                       for t in range(2, los * 24, 24))
    return Plan(los, curves, [(0.0, 0.0)], (), events, skip_principal_meds=True)


def _hyponatremia(rng: random.Random, b: Baseline, p: PatientSeed, evidence: str) -> Plan:
    los = _los(rng, evidence, (3, 5), (2, 3))
    if evidence == EVIDENCE_MEETS:
        na0 = rng.randint(124, 130)
        curve = [(0, na0), (24, na0 + 3), (48, na0 + 6), (los * 24.0, min(136, na0 + 9))]
        events = (Event(3.0, "order", "fluid_restriction", text="Fluid restriction 1.2 L/day"),
                  Event(6.0, "med", "nacl_tabs", text="Sodium chloride 1 g PO TID"))
        return Plan(los, {"sodium": curve}, [(0.0, 0.0)], (7.0, 13.0, 19.0, 31.0, 37.0, 43.0), events)
    if evidence == EVIDENCE_NEAR_MISS:
        return Plan(los, {"sodium": [(0, 133.6), (24, b.sodium)]}, [(0.0, 0.0)], (), ())
    return Plan(los, {}, [(0.0, 0.0)], (), ())


def _abla(rng: random.Random, b: Baseline, p: PatientSeed, evidence: str) -> Plan:
    los = _los(rng, evidence, (3, 4), (2, 3))
    h0 = b.hemoglobin
    if evidence == EVIDENCE_MEETS:
        drop = rng.uniform(2.6, 3.4)
        curve = [(0, h0), (30, h0 - drop), (34, h0 - drop + 0.9), (los * 24.0, h0 - drop + 1.2)]
        events = (Event(20.0, "imaging", "egd",
                        text="EGD: bleeding duodenal ulcer, treated with endoscopic clips"),
                  Event(31.0, "order", "transfuse", text="Transfuse 1 unit packed red blood cells"))
        return Plan(los, {"hemoglobin": curve}, [(0.0, 0.0)], (9.0, 17.0, 29.0, 37.0, 45.0), events)
    if evidence == EVIDENCE_NEAR_MISS:
        curve = [(0, h0), (48, h0 - rng.uniform(0.6, 1.1)), (los * 24.0, h0 - 0.5)]
        events = (Event(2.0, "med", "ns_bolus", text="Normal saline 1 L IV"),)
        return Plan(los, {"hemoglobin": curve}, [(0.0, 0.0)], (), events)
    events = (Event(20.0, "imaging", "egd", text="EGD: mild nonbleeding gastritis"),)
    return Plan(los, {}, [(0.0, 0.0)], (), events)


def _arf(rng: random.Random, b: Baseline, p: PatientSeed, evidence: str) -> Plan:
    if evidence == EVIDENCE_MEETS:
        los = rng.randint(3, 5)
        curves = {"spo2": [(0, 87), (3, 93), (48, 94)],
                  "resp_rate": [(0, 31), (24, 26), (48, 20), (72, 17)]}
        hfnc = rng.random() < 0.3
        o2 = [(0.0, 0.0), (2.0, 40.0 if hfnc else 5.0), (48.0, 3.0), (72.0, 0.0)]
        text = "High-flow nasal cannula 40 L/min, FiO2 0.6" if hfnc else "Oxygen via nasal cannula 5 L/min"
        events = (Event(1.0, "lab", "pao2", round(rng.uniform(52, 58))),
                  Event(2.0, "order", "oxygen", text=text))
        return Plan(los, curves, o2, (), events)
    los = rng.randint(2, 3)
    if evidence == EVIDENCE_NEAR_MISS:
        curves = {"spo2": [(0, 92.6), (8, 95)], "resp_rate": [(0, 21), (24, 17)]}
        events = (Event(6.0, "order", "oxygen", text="Oxygen 2 L/min nasal cannula for comfort"),)
        return Plan(los, curves, [(0.0, 0.0), (6.0, 2.0), (30.0, 0.0)], (), events)
    return Plan(los, {}, [(0.0, 0.0)], (), ())


def _hf(rng: random.Random, b: Baseline, p: PatientSeed, evidence: str) -> Plan:
    los = _los(rng, evidence, (3, 5), (2, 4))
    if evidence == EVIDENCE_MEETS:
        lvef = round(rng.uniform(25, 35))
        events = (
            Event(1.0, "lab", "bnp", round(rng.uniform(900, 2200))),
            Event(2.0, "imaging", "cxr_hf",
                  text="Chest x-ray: pulmonary vascular congestion, small bilateral effusions"),
            Event(20.0, "imaging", "lvef", float(lvef),
                  text=f"Transthoracic echo: LVEF {lvef}%, global hypokinesis"),
            *(Event(float(t), "med", "furosemide_iv", text="Furosemide 40 mg IV")
              for t in range(3, 72, 12)),
        )
    elif evidence == EVIDENCE_NEAR_MISS:
        lvef = round(rng.uniform(55, 60))
        events = (
            Event(1.0, "lab", "bnp", round(rng.uniform(120, 250))),
            Event(20.0, "imaging", "lvef", float(lvef),
                  text=f"Transthoracic echo: LVEF {lvef}%, grade I diastolic dysfunction"),
            *(Event(float(t), "med", "furosemide_po", text="Furosemide 20 mg PO daily (home med)")
              for t in range(8, los * 24, 24)),
        )
    else:
        lvef = round(rng.uniform(58, 65))
        events = (
            Event(1.0, "lab", "bnp", round(rng.uniform(40, 120))),
            Event(20.0, "imaging", "lvef", float(lvef), text=f"Transthoracic echo: LVEF {lvef}%, normal"),
        )
    return Plan(los, {}, [(0.0, 0.0)], (), events)
