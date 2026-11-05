"""Immutable records passed between the data-factory stages."""

from __future__ import annotations

from dataclasses import dataclass, field

CONDITIONS = ("aki", "sepsis", "hyponatremia", "abla", "arf", "hf")

# How the chart's evidence relates to the target condition's published criteria.
EVIDENCE_MEETS = "meets"            # criteria clearly met
EVIDENCE_NEAR_MISS = "near_miss"    # close to, but below, the threshold
EVIDENCE_CONFOUNDER = "confounder"  # looks abnormal for a benign reason (CKD baseline)
EVIDENCE_ABSENT = "absent"          # values normal

GROUPS = ("missing", "unsupported", "correct", "near_miss", "confounder", "routine")


@dataclass(frozen=True)
class PatientSeed:
    patient_id: str
    age: int
    sex: str  # "female" | "male"
    chronic: frozenset[str]
    source: str  # "synthea" | "builtin"


@dataclass(frozen=True)
class Event:
    """One timestamped item in the chart, hours after admission."""

    t_hours: float
    kind: str  # "lab" | "vital" | "med" | "order" | "imaging"
    key: str  # analyte key for lab/vital (see codes.LOINC), else a short slug
    value: float | None = None
    text: str | None = None


@dataclass(frozen=True)
class Mention:
    """A diagnosis the notes must state (present) or explicitly rule out (negated)."""

    icd10: str
    term: str
    assertion: str  # "present" | "negated"


@dataclass(frozen=True)
class Encounter:
    encounter_id: str
    split: str
    patient: PatientSeed
    admit_hour: int  # hours from the simulation start; drives the ward replay
    los_days: int
    principal_icd10: str
    condition: str | None
    evidence: str | None
    group: str
    events: tuple[Event, ...] = field(default_factory=tuple)
    mentions: tuple[Mention, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AnswerKeyRow:
    encounter_id: str
    split: str
    group: str
    condition: str | None
    evidence: str | None
    true_icd10: str | None        # what the evidence supports
    documented_icd10: str | None  # what the notes say
    expected_flag: str            # "missing_dx" | "unsupported_dx" | "none"
    detail: str
