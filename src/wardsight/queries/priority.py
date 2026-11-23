"""Worklist priority: which open gap a CDI reviewer should work first (0-100, parts shown).

Real CDI tools rank cases so reviewers spend their limited time where it matters. Every
point here comes from a visible part, so a reviewer can see why a case is on top:

- Billing impact (up to 45): how far the MS-DRG relative weight moves if the gap is resolved,
  up or down. A downward move (an unsupported diagnosis) is a compliance risk, so it counts too.
- Complication level (up to 30): the gap adds or removes a CC or an MCC.
- Time pressure (up to 25): days in hospital against the expected stay (GMLOS) for the
  billing category; a query has to be answered before the patient goes home.
"""

from __future__ import annotations

from dataclasses import dataclass

from wardsight.engine.drg_table import facts

WEIGHT_MAX, WEIGHT_PER_UNIT = 45, 45   # a full relative-weight point of change earns the maximum
SEVERITY_MAX = 30
SEVERITY_POINTS = {"MCC": 30, "CC": 18, "NONE": 0}
STAY_MAX = 25


@dataclass(frozen=True)
class Part:
    label: str
    points: int
    why: str


@dataclass(frozen=True)
class Priority:
    score: int
    parts: tuple[Part, ...]


def _weight(drg: int | None) -> float | None:
    f = facts(drg) if drg else None
    return f.weight if f else None


def priority(drg_now: int | None, drg_if_resolved: int | None, severity_now: str | None,
             severity_if_resolved: str | None, los_days: float) -> Priority:
    parts = []

    now, then = _weight(drg_now), _weight(drg_if_resolved)
    if now is not None and then is not None:
        delta = then - now
        points = min(WEIGHT_MAX, round(abs(delta) * WEIGHT_PER_UNIT))
        why = (f"weight {now:.2f} to {then:.2f} ({delta:+.2f})" if delta else
               "billing category does not change")
    else:
        points, why = 0, "no published weight for this category"
    parts.append(Part("Billing impact", points, why))

    before = SEVERITY_POINTS.get((severity_now or "NONE").upper(), 0)
    after = SEVERITY_POINTS.get((severity_if_resolved or "NONE").upper(), 0)
    changed = (severity_now or "NONE").upper() != (severity_if_resolved or "NONE").upper()
    parts.append(Part("Complication level", min(SEVERITY_MAX, abs(after - before)),
                      f"{(severity_now or 'none').upper()} to {(severity_if_resolved or 'none').upper()}"
                      if changed else "no CC/MCC change"))

    gmlos = (facts(drg_now) if drg_now else None)
    if gmlos:
        ratio = los_days / gmlos.gmlos
        parts.append(Part("Time pressure", round(STAY_MAX * min(1.0, ratio)),
                          f"{los_days:g} days in hospital, {gmlos.gmlos:g} expected"))
    else:
        parts.append(Part("Time pressure", 0, "no expected stay for this category"))

    return Priority(sum(p.points for p in parts), tuple(parts))
