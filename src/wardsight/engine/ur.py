"""Utilization review and leadership metrics (plain code, `ehr` + engine output only).

Utilization review per stay:
- Two-midnight benchmark (42 CFR 412.3(d)(1)): an inpatient admission is generally
  appropriate when the stay is expected to cross two midnights; fewer = review
  for observation status.
- Length of stay vs the DRG's geometric mean LOS (GMLOS). A stay well beyond the
  GMLOS is flagged for discharge-barrier review, UNLESS an open documentation gap
  explains it: once documented, the true DRG's GMLOS covers the stay. That is the
  point where UR and CDI meet.

Leadership: case mix index (mean relative weight) as first documented, now, and if
every open gap were resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from wardsight.engine.chart import Chart
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.engine.drg_table import facts
from wardsight.engine.gaps import Flag

MIDNIGHT_BENCHMARK = 2
LONG_STAY_RATIO = 1.5       # actual LOS at least 1.5x the GMLOS ...
LONG_STAY_MIN_EXCESS = 1.0  # ... and at least a full day over it


@dataclass(frozen=True)
class UrRow:
    encounter_id: str
    drg: int
    drg_description: str
    gmlos: float | None
    los_days: int
    midnights: int
    status: str            # "ok" | "observation_review" | "long_stay" | "explained_by_gap" | "no_benchmark"
    note: str
    drg_if_documented: int | None
    gmlos_if_documented: float | None


def midnights_crossed(admit: datetime, discharge: datetime) -> int:
    first = datetime(admit.year, admit.month, admit.day) + timedelta(days=1)
    return 0 if discharge < first else (discharge - first).days + 1


def codes_if_resolved(chart: Chart, flags: list[Flag]) -> set[str]:
    codes = coded_diagnoses(chart)
    for f in flags:
        if f.kind == "missing_dx":
            codes = (codes - {"I50.9"}) | {f.icd10} if f.condition == "hf" else codes | {f.icd10}
        else:
            codes = codes - {f.icd10}
    return codes


def _long(los: float, gmlos: float) -> bool:
    return los >= gmlos * LONG_STAY_RATIO and los - gmlos >= LONG_STAY_MIN_EXCESS


def review(chart: Chart, admit: datetime, flags: list[Flag]) -> UrRow:
    now = group(chart, coded_diagnoses(chart))
    known = facts(now.drg)
    midnights = midnights_crossed(admit, admit + timedelta(days=chart.los_days))
    missing = [f for f in flags if f.kind == "missing_dx"]
    if_doc = group(chart, codes_if_resolved(chart, missing)) if missing else None
    doc_facts = facts(if_doc.drg) if if_doc else None
    base = UrRow(chart.encounter_id, now.drg, now.description, known.gmlos if known else None,
                 chart.los_days, midnights, "ok", "", if_doc.drg if if_doc else None,
                 doc_facts.gmlos if doc_facts else None)

    if midnights < MIDNIGHT_BENCHMARK:
        return replace(base, status="observation_review",
                       note=f"Crossed {midnights} midnight(s); two-midnight benchmark not met")
    if known is None:
        return replace(base, status="no_benchmark", note="No GMLOS on file for this DRG")
    if not _long(chart.los_days, known.gmlos):
        return base
    if doc_facts and not _long(chart.los_days, doc_facts.gmlos):
        return replace(base, status="explained_by_gap",
                       note=(f"{chart.los_days} days vs {known.gmlos} expected, but an open documentation gap "
                             f"(DRG {if_doc.drg}, expected {doc_facts.gmlos} days) explains the stay"))
    return replace(base, status="long_stay",
                   note=f"{chart.los_days} days vs {known.gmlos} expected; review discharge barriers")


@dataclass(frozen=True)
class CaseMix:
    first_documented: float
    current: float
    if_all_resolved: float
    cases: int


def case_mix(first: list[int], current: list[int], potential: list[int]) -> CaseMix:
    def cmi(drgs: list[int]) -> float:
        weights = [f.weight for d in drgs if (f := facts(d))]
        return round(sum(weights) / len(weights), 4) if weights else 0.0
    return CaseMix(cmi(first), cmi(current), cmi(potential), len(current))
