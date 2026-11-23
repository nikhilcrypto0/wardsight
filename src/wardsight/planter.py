"""Gap planter: decides each chart's test group and writes the answer key.

The planter knows the TRUTH (what the evidence supports) and decides what the
notes will SAY. Where the two disagree on purpose, the answer key records the
flag a correct detector must raise. It is deliberately independent of the
milestone-2 detection rules: it works from scenario labels, never from
reading values back out of the chart.
"""

from __future__ import annotations

import random
from dataclasses import replace

from wardsight.codes import CHRONIC_ICD10, CHRONIC_TERMS, PRINCIPAL_TERMS
from wardsight.models import (
    CONDITIONS,
    EVIDENCE_ABSENT,
    EVIDENCE_CONFOUNDER,
    EVIDENCE_MEETS,
    EVIDENCE_NEAR_MISS,
    AnswerKeyRow,
    Encounter,
    Mention,
    PatientSeed,
)
from wardsight.scenarios import build_chart, choose_principal

SIM_DAYS = 14

GROUP_COUNTS = {
    "dev": {"missing": 50, "unsupported": 25, "correct": 40,
            "near_miss": 30, "confounder": 15, "routine": 40},
    "heldout": {"missing": 25, "unsupported": 12, "correct": 20,
                "near_miss": 15, "confounder": 8, "routine": 20},
}

GROUP_EVIDENCE = {"missing": EVIDENCE_MEETS, "unsupported": EVIDENCE_ABSENT,
                  "correct": EVIDENCE_MEETS, "near_miss": EVIDENCE_NEAR_MISS,
                  "confounder": EVIDENCE_CONFOUNDER, "routine": None,
                  "unspecified": EVIDENCE_MEETS, "unspecified_near": EVIDENCE_NEAR_MISS,
                  "conflicting": EVIDENCE_MEETS, "conflict_near": EVIDENCE_MEETS}

# Added 2026-11-23 (U3): dev-only charts for two more alert types real CDI tools raise,
# "not fully specified" and "conflicting documentation". They come from their own random
# stream and from patients after the held-out slice, so the original 200 dev and 100
# held-out charts are unchanged. Encounter ids continue from D0201.
EXTRA_COUNTS = {"unspecified": 10, "unspecified_near": 6, "conflicting": 10, "conflict_near": 8}
EXTRA_START = 201
VAGUE = {"abla": ("D64.9", "anemia"), "hf": ("I50.9", "CHF")}  # what a vague note says instead
CONFLICT_CONDITIONS = ("aki", "sepsis", "hyponatremia", "abla", "arf")
CONFLICT_NEGATIONS = {"aki": "acute kidney injury ruled out", "sepsis": "no evidence of sepsis",
                      "hyponatremia": "hyponatremia ruled out", "abla": "no acute blood loss anemia",
                      "arf": "not in respiratory failure"}
ADMISSION, LATER = ("history_and_physical",), ("progress_note", "discharge_summary")

TRUE_ICD10 = {"aki": "N17.9", "sepsis": "A41.9", "hyponatremia": "E87.1",
              "abla": "D62", "arf": "J96.01", "hf": "I50.21"}

# (standard term, synonym a careful detector must also recognize)
TERMS = {
    "aki": ("acute kidney injury", "acute renal failure"),
    "sepsis": ("sepsis", "sepsis secondary to the infection"),
    "hyponatremia": ("hyponatremia", "hypotonic hyponatremia"),
    "abla": ("acute blood loss anemia", "acute posthemorrhagic anemia"),
    "arf": ("acute hypoxic respiratory failure", "acute respiratory failure with hypoxia"),
    "hf": ("acute systolic heart failure", "acute HFrEF exacerbation"),
}

NEGATIONS = {
    "aki": "acute kidney injury ruled out",
    "sepsis": "no evidence of sepsis",
    "hyponatremia": "sodium mildly low, not clinically significant",
    "abla": "no acute blood loss anemia; mild drop is dilutional",
    "arf": "not in respiratory failure",
    "hf": "no acute heart failure",
}

SYNONYM_SHARE = 1 / 3
NEGATION_SHARE = 1 / 2


def plan_slots(split: str, rng: random.Random) -> list[tuple[str, str | None]]:
    """(group, condition) for every chart in the split, shuffled."""
    slots: list[tuple[str, str | None]] = []
    for offset, (group, count) in enumerate(GROUP_COUNTS[split].items()):
        for i in range(count):
            if group == "routine":
                condition = None
            elif group == "confounder":
                condition = "aki"
            else:
                condition = CONDITIONS[(i + offset) % len(CONDITIONS)]
            slots.append((group, condition))
    rng.shuffle(slots)
    return slots


def build_split(split: str, patients: list[PatientSeed], seed: int) -> tuple[list[Encounter], list[AnswerKeyRow]]:
    rng = random.Random(f"{seed}-{split}")
    slots = plan_slots(split, rng)
    if len(patients) < len(slots):
        raise ValueError(f"{split} needs {len(slots)} patients, got {len(patients)}")
    prefix = split[0].upper()
    encounters, answers = [], []
    for i, ((group, condition), patient) in enumerate(zip(slots, patients), start=1):
        enc_id = f"{prefix}{i:04d}"
        enc, ans = _build_one(rng, split, enc_id, group, condition, patient)
        encounters.append(enc)
        answers.append(ans)
    return encounters, answers


def plan_extra_slots(rng: random.Random) -> list[tuple[str, str]]:
    slots = []
    for group, count in EXTRA_COUNTS.items():
        pool = tuple(VAGUE) if group.startswith("unspecified") else CONFLICT_CONDITIONS
        slots += [(group, pool[i % len(pool)]) for i in range(count)]
    rng.shuffle(slots)
    return slots


def build_extra(patients: list[PatientSeed], seed: int) -> tuple[list[Encounter], list[AnswerKeyRow]]:
    """The U3 dev charts (D0201+)."""
    rng = random.Random(f"{seed}-dev-u3")
    slots = plan_extra_slots(rng)
    if len(patients) < len(slots):
        raise ValueError(f"U3 charts need {len(slots)} patients, got {len(patients)}")
    encounters, answers = [], []
    for i, ((group, condition), patient) in enumerate(zip(slots, patients), start=EXTRA_START):
        enc, ans = _build_one(rng, "dev", f"D{i:04d}", group, condition, patient)
        encounters.append(enc)
        answers.append(ans)
    return encounters, answers


def _build_one(rng: random.Random, split: str, enc_id: str, group: str,
               condition: str | None, patient: PatientSeed) -> tuple[Encounter, AnswerKeyRow]:
    evidence = GROUP_EVIDENCE[group]
    if group == "confounder":
        patient = replace(patient, chronic=patient.chronic | {"ckd3"})
    principal = choose_principal(rng, condition, evidence)
    los, events = build_chart(rng, patient, principal, condition, evidence)
    mentions = _mentions(rng, group, condition, principal, patient)
    encounter = Encounter(enc_id, split, patient, rng.randrange(SIM_DAYS * 24), los,
                          principal, condition, evidence, group, events, mentions)
    return encounter, _answer(enc_id, split, group, condition, evidence)


def _mentions(rng: random.Random, group: str, condition: str | None,
              principal: str, patient: PatientSeed) -> tuple[Mention, ...]:
    out = [Mention(principal, PRINCIPAL_TERMS[principal], "present")]
    out += [Mention(CHRONIC_ICD10[c], CHRONIC_TERMS[c], "present") for c in sorted(patient.chronic)]
    if condition is None:
        return tuple(out)
    standard, synonym = TERMS[condition]
    true_code = TRUE_ICD10[condition]
    if (group == "missing" and condition == "hf") or group.startswith("unspecified"):
        out.append(Mention(*VAGUE[condition], "present"))  # specificity gap: vague wording only
    elif group == "conflicting":  # one note states it, later notes rule it out
        out.append(Mention(true_code, standard, "present", ADMISSION))
        out.append(Mention(true_code, CONFLICT_NEGATIONS[condition], "negated", LATER))
    elif group == "conflict_near":  # stated, then resolved: a change over time, not a conflict
        out.append(Mention(true_code, standard, "present", ADMISSION))
        out.append(Mention(true_code, f"{standard}, resolved", "present", ("discharge_summary",)))
    elif group == "unsupported":
        out.append(Mention(true_code, standard, "present"))
    elif group == "correct":
        term = synonym if rng.random() < SYNONYM_SHARE else standard
        out.append(Mention(true_code, term, "present"))
    elif group in ("near_miss", "confounder") and rng.random() < NEGATION_SHARE:
        out.append(Mention(true_code, NEGATIONS[condition], "negated"))
    return tuple(out)


def _answer(enc_id: str, split: str, group: str, condition: str | None,
            evidence: str | None) -> AnswerKeyRow:
    true_code = TRUE_ICD10.get(condition) if evidence == EVIDENCE_MEETS else None
    if (group == "missing" and condition == "hf") or group == "unspecified":
        # relabelled 2026-11-23 (U3, Nikhil's decision): vague wording is a specificity gap
        vague_code, vague_term = VAGUE[condition]
        return AnswerKeyRow(enc_id, split, group, condition, evidence, true_code, vague_code,
                            "unspecified_dx", f"evidence supports {condition}; notes say only '{vague_term}'")
    if group == "missing":
        return AnswerKeyRow(enc_id, split, group, condition, evidence, true_code, None, "missing_dx",
                            f"evidence meets criteria; {condition} never documented")
    if group == "conflicting":
        return AnswerKeyRow(enc_id, split, group, condition, evidence, true_code, true_code, "conflicting_dx",
                            f"{condition} stated on admission, ruled out in later notes")
    if group == "unsupported":
        return AnswerKeyRow(enc_id, split, group, condition, evidence, None,
                            TRUE_ICD10[condition], "unsupported_dx",
                            f"{condition} documented but evidence is normal")
    documented = (true_code if group in ("correct", "conflict_near") else
                  VAGUE[condition][0] if group == "unspecified_near" else None)
    details = {"correct": "evidence and documentation agree",
               "unspecified_near": "vague wording, but the evidence does not support the specific diagnosis",
               "conflict_near": "stated on admission and later resolved: a change over time, not a conflict",
               "near_miss": "evidence close to but below criteria; no flag expected",
               "confounder": "creatinine high from CKD baseline, stable; not AKI",
               "routine": "no target condition"}
    return AnswerKeyRow(enc_id, split, group, condition, evidence, true_code,
                        documented, "none", details[group])
